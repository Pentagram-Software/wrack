'use strict';

/**
 * Health-leg push Cloud Function (PEN-228).
 *
 * Receives exactly one health record per POST — unifiedIngress's
 * pushHealthRecord() (cloud/functions/ingress.js) calls this directly and
 * synchronously per record, not in a batch — and pushes it onward to
 * Grafana Cloud's hosted OTLP gateway: numeric payload fields become gauge
 * metrics (Mimir), the full record becomes one structured log line (Loki).
 * See docs/monitoring/architecture.md#the-health-leg-decided for the wire
 * protocol and delivery-mechanism decisions this implements.
 *
 * Deployed WITHOUT --allow-unauthenticated. Unlike controlRobot/
 * telemetryIngestion/unifiedIngress (each has an external caller and does
 * its own app-level auth check — API key or per-device token), this
 * function's only caller is unifiedIngress itself, so GCP's built-in
 * Cloud Functions/Cloud Run IAM handles authentication: a request without
 * a valid identity token for this function is rejected by the platform
 * before this code ever runs. There is deliberately no app-level auth
 * check here to duplicate that.
 *
 * Always fails open: a malformed body, a Secret Manager error, or a
 * Grafana push failure is logged and swallowed, never thrown back at the
 * caller as a reason to retry — a missed health sample is low stakes
 * (docs/monitoring/architecture.md), and this leg never retries on its own,
 * matching the ingress's own no-retry policy for type=health.
 */

const functions = require('@google-cloud/functions-framework');
const { resourceFromAttributes } = require('@opentelemetry/resources');
const { MeterProvider, PeriodicExportingMetricReader } = require('@opentelemetry/sdk-metrics');
const { LoggerProvider, SimpleLogRecordProcessor } = require('@opentelemetry/sdk-logs');
const { OTLPMetricExporter } = require('@opentelemetry/exporter-metrics-otlp-http');
const { OTLPLogExporter } = require('@opentelemetry/exporter-logs-otlp-http');
const { ExportResultCode } = require('@opentelemetry/core');
const { getGrafanaCredentials } = require('./grafana-credentials');
const { mapEventToMetricPoints, mapEventToLogRecord } = require('./otlp-mapper');

// Stays comfortably under the ingress's own HEALTH_LEG_FETCH_TIMEOUT_MS
// (3000ms, ingress.js) so a slow Grafana gateway response is caught by
// this function's own export timeout — which we can log details for —
// rather than only by the caller's AbortSignal, which just sees a generic
// abort with no OTLP-side error message.
const OTLP_EXPORT_TIMEOUT_MS = 2200;

const RESOURCE = resourceFromAttributes({ 'service.name': 'wrack-health-leg' });

function _basicAuthHeader(instanceId, token) {
  return `Basic ${Buffer.from(`${instanceId}:${token}`, 'utf8').toString('base64')}`;
}

/**
 * Wraps a raw OTLP exporter so a push failure is logged right here (and
 * thus reliably observed for the fail-open policy) instead of only
 * reaching OTel's internal diagnostic logger — MeterProvider/LoggerProvider
 * shutdown()/forceFlush() resolve successfully regardless of whether the
 * underlying export actually succeeded, by SDK design, so without this
 * wrapper a failed push would look identical to a successful one from the
 * caller's point of view.
 */
function _withResultLogging(exporter, label, eventId) {
  return {
    export(data, resultCallback) {
      exporter.export(data, (result) => {
        if (result.code !== ExportResultCode.SUCCESS) {
          console.error(
            `[health-leg] ${label} push failed for event ${eventId} (fail open):`,
            result.error && result.error.message
          );
        }
        resultCallback(result);
      });
    },
    forceFlush: () => (exporter.forceFlush ? exporter.forceFlush() : Promise.resolve()),
    shutdown: () => exporter.shutdown(),
  };
}

/**
 * Push a single health event to Grafana Cloud via OTLP. Never throws for a
 * downstream push failure (logged by _withResultLogging above and swallowed
 * by MeterProvider/LoggerProvider's own fail-open shutdown semantics) —
 * only credential loading (Secret Manager) can still reject, which the
 * caller wraps in its own try/catch to preserve the fail-open contract.
 *
 * @param {object} event  A validated `type: "health"` telemetry event.
 */
async function pushToGrafana(event) {
  const credentials = await getGrafanaCredentials();
  const headers = { Authorization: _basicAuthHeader(credentials.instance_id, credentials.token) };
  const baseUrl = credentials.otlp_endpoint.replace(/\/+$/, '');

  const metricPoints = mapEventToMetricPoints(event);
  const logRecord = mapEventToLogRecord(event);

  const logExporter = _withResultLogging(
    new OTLPLogExporter({ url: `${baseUrl}/v1/logs`, headers, timeoutMillis: OTLP_EXPORT_TIMEOUT_MS }),
    'logs',
    event.event_id
  );
  const loggerProvider = new LoggerProvider({
    resource: RESOURCE,
    processors: [new SimpleLogRecordProcessor({ exporter: logExporter })],
  });

  // No metric reader/exporter at all when there's nothing numeric to send
  // (e.g. device_status's payload is all strings) — avoids an OTLP call
  // that would just ship an empty metrics batch.
  const meterProvider = new MeterProvider({
    resource: RESOURCE,
    readers:
      metricPoints.length > 0
        ? [
            new PeriodicExportingMetricReader({
              exporter: _withResultLogging(
                new OTLPMetricExporter({ url: `${baseUrl}/v1/metrics`, headers, timeoutMillis: OTLP_EXPORT_TIMEOUT_MS }),
                'metrics',
                event.event_id
              ),
              // Exceeds this function's own lifetime — collection is only
              // ever triggered explicitly via shutdown()'s internal flush
              // below, never by this timer actually firing.
              exportIntervalMillis: 60 * 60 * 1000,
            }),
          ]
        : [],
  });

  try {
    for (const point of metricPoints) {
      meterProvider.getMeter('wrack-health-leg').createGauge(point.name).record(point.value, point.attributes);
    }
    loggerProvider.getLogger('wrack-health-leg').emit({
      body: logRecord.body,
      severityNumber: logRecord.severityNumber,
      severityText: logRecord.severityText,
      attributes: logRecord.attributes,
      timestamp: logRecord.timestampMs,
    });
  } finally {
    // shutdown() flushes internally (MetricReader.onShutdown calls
    // onForceFlush()) — calling forceFlush() first as well as shutdown()
    // would double-send every metric point, so this is the only flush call.
    await Promise.all([meterProvider.shutdown(), loggerProvider.shutdown()]);
  }
}

functions.http('healthLegPush', (req, res) => {
  (async () => {
    if (req.method !== 'POST') {
      return res.status(405).json({ error: 'Method not allowed' });
    }

    const event = req.body;
    if (!event || typeof event !== 'object' || Array.isArray(event) || !event.event_id) {
      // Malformed body — not a Grafana outage, so this is worth a distinct
      // 400 for visibility rather than folding into the generic fail-open
      // 502 below.
      return res.status(400).json({ error: 'a single event object with event_id is required' });
    }

    try {
      await pushToGrafana(event);
      return res.status(200).json({ success: true });
    } catch (err) {
      // Credential loading failed (Secret Manager outage, missing IAM
      // grant, malformed secret) — the only path that still reaches here,
      // since pushToGrafana() otherwise fails open internally.
      console.error(`[health-leg] push failed for event ${event.event_id} (fail open):`, err.message);
      return res.status(502).json({ success: false, error: 'push failed' });
    }
  })();
});

module.exports = {
  pushToGrafana,
  _basicAuthHeader,
  _withResultLogging,
};
