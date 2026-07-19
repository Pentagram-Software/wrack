'use strict';

/**
 * Loads Grafana Cloud OTLP push credentials (endpoint, instance ID, Access
 * Policy token) from the `grafana-cloud-push-credentials` Secret Manager
 * secret (PEN-189, provisioned by cloud/monitoring/setup-grafana-secret.sh)
 * for the health-leg push function (PEN-228).
 *
 * TTL-cached across warm invocations, mirroring ingress.js's device-tokens
 * cache: bounds how long an already-warm instance keeps using a rotated-out
 * token instead of living forever until the instance happens to cold-start.
 */

const { SecretManagerServiceClient } = require('@google-cloud/secret-manager');

const GCP_PROJECT_ID = process.env.GCP_PROJECT_ID || process.env.BIGQUERY_PROJECT_ID || 'wrack-control';
const GRAFANA_CREDENTIALS_SECRET = process.env.GRAFANA_CREDENTIALS_SECRET || 'grafana-cloud-push-credentials';

let _secretClient = null;
function _getSecretClient() {
  if (!_secretClient) {
    _secretClient = new SecretManagerServiceClient();
  }
  return _secretClient;
}

const CREDENTIALS_CACHE_TTL_MS = 5 * 60 * 1000;

let _cache = null;
let _cacheTime = 0;

/**
 * True only for the shape write_credentials.py writes: a flat object with
 * non-empty otlp_endpoint/instance_id/token strings. Guards against a
 * malformed or partially-written secret being trusted silently.
 */
function _isValidCredentialsShape(value) {
  return (
    value !== null &&
    typeof value === 'object' &&
    !Array.isArray(value) &&
    typeof value.otlp_endpoint === 'string' &&
    value.otlp_endpoint.length > 0 &&
    typeof value.instance_id === 'string' &&
    value.instance_id.length > 0 &&
    typeof value.token === 'string' &&
    value.token.length > 0
  );
}

/**
 * Returns the cached credentials object ({otlp_endpoint, instance_id,
 * token}) if still fresh, otherwise fetches the latest secret version.
 * Throws (never returns a partial/invalid value) if the secret is missing,
 * unreadable, or malformed — callers are expected to fail open around this.
 */
async function getGrafanaCredentials() {
  const isFresh = _cache && Date.now() - _cacheTime < CREDENTIALS_CACHE_TTL_MS;
  if (isFresh) {
    return _cache;
  }

  const client = _getSecretClient();
  const name = `projects/${GCP_PROJECT_ID}/secrets/${GRAFANA_CREDENTIALS_SECRET}/versions/latest`;
  const [version] = await client.accessSecretVersion({ name });
  const parsed = JSON.parse(version.payload.data.toString('utf8'));

  if (!_isValidCredentialsShape(parsed)) {
    throw new Error(
      'grafana-cloud-push-credentials secret has an unexpected shape (expected otlp_endpoint, instance_id, token strings)'
    );
  }

  _cache = parsed;
  _cacheTime = Date.now();
  return _cache;
}

/** Exposed for unit-test injection only. */
function _resetCredentialsCache() {
  _cache = null;
  _cacheTime = 0;
}

module.exports = {
  getGrafanaCredentials,
  _isValidCredentialsShape,
  _resetCredentialsCache,
};
