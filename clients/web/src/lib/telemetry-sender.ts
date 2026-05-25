/**
 * TelemetrySender — non-blocking, batched telemetry dispatcher for the web client.
 *
 * Events are accumulated in an in-memory buffer and flushed to the
 * `telemetryIngestion` Cloud Function either:
 *  - immediately when the buffer reaches `maxBatchSize` (default 100), or
 *  - on a periodic background timer (default every 30 s), or
 *  - explicitly via `flush()`.
 *
 * Failed sends are retried with exponential backoff (max 3 retries by default).
 * When the device is offline (`navigator.onLine === false`) the batch is dropped
 * with an error logged — there is no persistent queue between page sessions.
 */

import type { TelemetryEventEnvelope } from '../../../../shared/telemetry-types/typescript/events';

export type { TelemetryEventEnvelope };

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

export interface TelemetrySenderConfig {
  /** URL of the `telemetryIngestion` Cloud Function. */
  url: string;
  /** API key sent in the `X-API-Key` request header. */
  apiKey: string;
  /** Maximum events sent in a single HTTP request (default 100). */
  maxBatchSize?: number;
  /** Interval between background flushes in milliseconds (default 30 000). */
  flushIntervalMs?: number;
  /** Maximum number of retry attempts per batch after the first failure (default 3). */
  maxRetries?: number;
  /**
   * Initial backoff delay in milliseconds before the first retry.
   * Each subsequent retry doubles this value (default 1 000).
   */
  initialBackoffMs?: number;
}

const DEFAULT_MAX_BATCH_SIZE = 100;
const DEFAULT_FLUSH_INTERVAL_MS = 30_000;
const DEFAULT_MAX_RETRIES = 3;
const DEFAULT_INITIAL_BACKOFF_MS = 1_000;

// ---------------------------------------------------------------------------
// TelemetrySender class
// ---------------------------------------------------------------------------

export class TelemetrySender {
  private readonly url: string;
  private readonly apiKey: string;
  private readonly maxBatchSize: number;
  private readonly flushIntervalMs: number;
  private readonly maxRetries: number;
  private readonly initialBackoffMs: number;

  private buffer: TelemetryEventEnvelope[] = [];
  private flushTimer: ReturnType<typeof setTimeout> | null = null;
  private isFlushing = false;
  private destroyed = false;

  constructor(config: TelemetrySenderConfig) {
    this.url = config.url;
    this.apiKey = config.apiKey;
    this.maxBatchSize = config.maxBatchSize ?? DEFAULT_MAX_BATCH_SIZE;
    this.flushIntervalMs = config.flushIntervalMs ?? DEFAULT_FLUSH_INTERVAL_MS;
    this.maxRetries = config.maxRetries ?? DEFAULT_MAX_RETRIES;
    this.initialBackoffMs = config.initialBackoffMs ?? DEFAULT_INITIAL_BACKOFF_MS;

    this.scheduleFlush();
  }

  /**
   * Enqueue an event for delivery.
   *
   * If the buffer reaches `maxBatchSize`, a flush is triggered immediately
   * (fire-and-forget — errors are logged but never thrown to the caller).
   */
  track(event: TelemetryEventEnvelope): void {
    if (this.destroyed) return;

    this.buffer.push(event);

    if (this.buffer.length >= this.maxBatchSize) {
      this.flush().catch(() => {
        // Already logged inside flush(); suppress unhandled rejection.
      });
    }
  }

  /**
   * Drain the buffer and send all pending events to the Cloud Function.
   *
   * Batches are sent sequentially, at most `maxBatchSize` events per request.
   * If a batch exhausts all retry attempts it is dropped and the next batch
   * continues; errors are logged to the console but never re-thrown.
   *
   * Concurrent `flush()` calls are coalesced — only one is active at a time.
   */
  async flush(): Promise<void> {
    if (this.destroyed || this.buffer.length === 0) return;
    if (this.isFlushing) return;

    this.isFlushing = true;
    try {
      while (this.buffer.length > 0) {
        const batch = this.buffer.splice(0, this.maxBatchSize);
        try {
          await this.sendBatchWithRetry(batch);
        } catch (err) {
          console.error('[TelemetrySender] Batch dropped after max retries:', err);
        }
      }
    } finally {
      this.isFlushing = false;
    }
  }

  /**
   * Stop background flushing.
   *
   * Any events still in the buffer are discarded. Call this during teardown
   * (e.g. in tests) to prevent the background timer from leaking.
   */
  destroy(): void {
    this.destroyed = true;
    if (this.flushTimer !== null) {
      clearTimeout(this.flushTimer);
      this.flushTimer = null;
    }
  }

  /** Number of events currently waiting in the buffer (exposed for testing). */
  get bufferSize(): number {
    return this.buffer.length;
  }

  // ── Private helpers ────────────────────────────────────────────────────────

  /** Reschedule the recurring background flush. */
  private scheduleFlush(): void {
    if (this.destroyed) return;

    this.flushTimer = setTimeout(() => {
      this.flush().catch(() => {});
      this.scheduleFlush();
    }, this.flushIntervalMs);
  }

  /**
   * Attempt to send `batch` with exponential backoff.
   * Throws if all retries are exhausted or the device is offline.
   */
  private async sendBatchWithRetry(batch: TelemetryEventEnvelope[]): Promise<void> {
    let attempt = 0;
    let lastError: unknown;

    while (attempt <= this.maxRetries) {
      if (attempt > 0) {
        const backoffMs = this.initialBackoffMs * Math.pow(2, attempt - 1);
        await this.sleep(backoffMs);
      }

      // Graceful offline degradation — skip the network call entirely.
      if (typeof navigator !== 'undefined' && !navigator.onLine) {
        throw new Error('[TelemetrySender] Device is offline; batch not sent');
      }

      try {
        await this.sendBatch(batch);
        return;
      } catch (err) {
        lastError = err;
        attempt++;
        if (attempt <= this.maxRetries) {
          console.warn(`[TelemetrySender] Retry ${attempt}/${this.maxRetries} after error:`, err);
        }
      }
    }

    throw lastError;
  }

  /** Execute a single HTTP POST for the given event batch. */
  private async sendBatch(batch: TelemetryEventEnvelope[]): Promise<void> {
    const response = await fetch(this.url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': this.apiKey,
      },
      body: JSON.stringify({ events: batch }),
    });

    // HTTP 207 (partial success) is considered non-fatal — some events may have
    // failed validation or BigQuery insertion, but the rest were stored.
    if (!response.ok && response.status !== 207) {
      const text = await response.text().catch(() => String(response.status));
      throw new Error(`[TelemetrySender] HTTP ${response.status}: ${text}`);
    }
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

// ---------------------------------------------------------------------------
// Singleton — shared instance used by the web app
// ---------------------------------------------------------------------------

export const telemetrySender = new TelemetrySender({
  url:
    process.env.NEXT_PUBLIC_TELEMETRY_FUNCTION_URL ??
    'https://europe-central2-wrack-control.cloudfunctions.net/telemetryIngestion',
  apiKey: process.env.NEXT_PUBLIC_API_KEY ?? '',
});
