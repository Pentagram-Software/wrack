/**
 * Unit tests for TelemetrySender.
 *
 * Strategy:
 *  - `fetch` is mocked via `vi.fn()` — no real HTTP calls are made.
 *  - The `TelemetrySender` class is instantiated directly (not the singleton)
 *    so each test controls its own config.
 *  - `initialBackoffMs: 0` removes the need to advance fake timers for retry
 *    delay tests while still validating retry count and error handling.
 *  - `flushIntervalMs: 1_000_000` (very large) prevents background flushes
 *    from interfering with tests that don't test the timer behaviour.
 *  - Tests that verify timer-driven flushing use `vi.useFakeTimers()` and
 *    `vi.advanceTimersByTimeAsync()`.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TelemetrySender } from './telemetry-sender';
import type { TelemetryEventEnvelope } from './telemetry-sender';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Build a minimal valid event envelope. */
function makeEvent(overrides: Partial<TelemetryEventEnvelope> = {}): TelemetryEventEnvelope {
  return {
    event_id: crypto.randomUUID(),
    event_type: 'device_status',
    source: 'web',
    timestamp: new Date().toISOString(),
    payload: { device_name: 'test', status: 'connected' },
    ...overrides,
  };
}

/** Create a Response-like object with `ok`, `status`, and `text()`. */
function makeResponse(status: number, body = ''): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: vi.fn().mockResolvedValue(body),
  } as unknown as Response;
}

/** Default TelemetrySender config used across most tests. */
const TEST_URL = 'https://example.com/telemetryIngestion';
const TEST_API_KEY = 'test-api-key-123';

function makeSender(overrides: Partial<ConstructorParameters<typeof TelemetrySender>[0]> = {}) {
  return new TelemetrySender({
    url: TEST_URL,
    apiKey: TEST_API_KEY,
    maxBatchSize: 100,
    flushIntervalMs: 1_000_000, // effectively disable background flush
    maxRetries: 3,
    initialBackoffMs: 0, // no delay so tests run fast
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

let mockFetch: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch = vi.fn().mockResolvedValue(makeResponse(200));
  vi.stubGlobal('fetch', mockFetch);

  // Default: online
  Object.defineProperty(navigator, 'onLine', { value: true, configurable: true, writable: true });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

// ---------------------------------------------------------------------------
// track() — buffering behaviour
// ---------------------------------------------------------------------------

describe('TelemetrySender — track()', () => {
  it('buffers events without immediately flushing', () => {
    const sender = makeSender();
    sender.track(makeEvent());
    sender.track(makeEvent());
    expect(sender.bufferSize).toBe(2);
    expect(mockFetch).not.toHaveBeenCalled();
    sender.destroy();
  });

  it('triggers an immediate flush when the buffer reaches maxBatchSize', async () => {
    const sender = makeSender({ maxBatchSize: 5 });

    for (let i = 0; i < 5; i++) {
      sender.track(makeEvent());
    }

    // flush() is fire-and-forget — we need to yield to the microtask queue
    await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    expect(sender.bufferSize).toBe(0);
    sender.destroy();
  });

  it('does not add events after destroy()', () => {
    const sender = makeSender();
    sender.destroy();
    sender.track(makeEvent());
    expect(sender.bufferSize).toBe(0);
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// flush() — sending behaviour
// ---------------------------------------------------------------------------

describe('TelemetrySender — flush()', () => {
  it('sends buffered events in a single POST', async () => {
    const sender = makeSender();
    sender.track(makeEvent());
    sender.track(makeEvent());
    await sender.flush();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const [url, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(TEST_URL);
    const body = JSON.parse(init.body as string) as { events: unknown[] };
    expect(body.events).toHaveLength(2);
    sender.destroy();
  });

  it('includes the X-API-Key header', async () => {
    const sender = makeSender();
    sender.track(makeEvent());
    await sender.flush();

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers['X-API-Key']).toBe(TEST_API_KEY);
    sender.destroy();
  });

  it('sets Content-Type to application/json', async () => {
    const sender = makeSender();
    sender.track(makeEvent());
    await sender.flush();

    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/json');
    sender.destroy();
  });

  it('is a no-op on an empty buffer', async () => {
    const sender = makeSender();
    await sender.flush();
    expect(mockFetch).not.toHaveBeenCalled();
    sender.destroy();
  });

  it('does nothing after destroy()', async () => {
    const sender = makeSender();
    sender.track(makeEvent());
    sender.destroy();
    await sender.flush();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('clears the buffer after a successful flush', async () => {
    const sender = makeSender();
    sender.track(makeEvent());
    sender.track(makeEvent());
    await sender.flush();
    expect(sender.bufferSize).toBe(0);
    sender.destroy();
  });
});

// ---------------------------------------------------------------------------
// Batch size cap (max 100 events per request)
// ---------------------------------------------------------------------------

describe('TelemetrySender — batch size limit', () => {
  it('sends at most maxBatchSize events per request', async () => {
    const sender = makeSender({ maxBatchSize: 100 });

    // Tracking 150 events triggers an auto-flush at the 100th event.
    // The flush continuation then drains the remaining 50.
    // We use waitFor to let both batches complete before asserting.
    for (let i = 0; i < 150; i++) {
      sender.track(makeEvent());
    }

    await vi.waitFor(() => {
      expect(sender.bufferSize).toBe(0);
    });

    expect(mockFetch).toHaveBeenCalledTimes(2);
    const firstBatch = JSON.parse(
      (mockFetch.mock.calls[0] as [string, RequestInit])[1].body as string,
    ) as { events: unknown[] };
    const secondBatch = JSON.parse(
      (mockFetch.mock.calls[1] as [string, RequestInit])[1].body as string,
    ) as { events: unknown[] };
    expect(firstBatch.events).toHaveLength(100);
    expect(secondBatch.events).toHaveLength(50);
    sender.destroy();
  });

  it('auto-flushes exactly at the maxBatchSize boundary', async () => {
    const maxBatchSize = 10;
    const sender = makeSender({ maxBatchSize });

    for (let i = 0; i < maxBatchSize; i++) {
      sender.track(makeEvent());
    }

    await vi.waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
    const batch = JSON.parse(
      (mockFetch.mock.calls[0] as [string, RequestInit])[1].body as string,
    ) as { events: unknown[] };
    expect(batch.events).toHaveLength(maxBatchSize);
    expect(sender.bufferSize).toBe(0);
    sender.destroy();
  });
});

// ---------------------------------------------------------------------------
// HTTP 207 (partial success) — treated as non-fatal
// ---------------------------------------------------------------------------

describe('TelemetrySender — HTTP 207 partial success', () => {
  it('does not retry on HTTP 207', async () => {
    mockFetch.mockResolvedValue(makeResponse(207, JSON.stringify({ success: false, inserted: 1, failed: 1 })));

    const sender = makeSender();
    sender.track(makeEvent());
    await sender.flush();

    // Exactly one request, no retries
    expect(mockFetch).toHaveBeenCalledTimes(1);
    sender.destroy();
  });
});

// ---------------------------------------------------------------------------
// Retry logic
// ---------------------------------------------------------------------------

describe('TelemetrySender — retry behaviour', () => {
  it('retries up to maxRetries times on HTTP 5xx errors', async () => {
    mockFetch.mockResolvedValue(makeResponse(500, 'Internal Server Error'));

    const sender = makeSender({ maxRetries: 3 });
    sender.track(makeEvent());
    await sender.flush();

    // 1 initial attempt + 3 retries = 4 total
    expect(mockFetch).toHaveBeenCalledTimes(4);
    sender.destroy();
  });

  it('retries on network-level fetch rejections', async () => {
    mockFetch.mockRejectedValue(new TypeError('Failed to fetch'));

    const sender = makeSender({ maxRetries: 2 });
    sender.track(makeEvent());
    await sender.flush();

    // 1 initial + 2 retries = 3 total
    expect(mockFetch).toHaveBeenCalledTimes(3);
    sender.destroy();
  });

  it('succeeds if a retry returns 200 after initial failure', async () => {
    mockFetch
      .mockResolvedValueOnce(makeResponse(503))
      .mockResolvedValueOnce(makeResponse(200));

    const sender = makeSender({ maxRetries: 3 });
    sender.track(makeEvent());
    await sender.flush();

    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(sender.bufferSize).toBe(0);
    sender.destroy();
  });

  it('drops batch after exhausting retries (does not throw to caller)', async () => {
    mockFetch.mockResolvedValue(makeResponse(500));

    const sender = makeSender({ maxRetries: 2 });
    sender.track(makeEvent());

    // flush() must resolve without throwing
    await expect(sender.flush()).resolves.toBeUndefined();
    expect(mockFetch).toHaveBeenCalledTimes(3); // 1 + 2 retries
    sender.destroy();
  });

  it('applies exponential backoff between retries', async () => {
    // Mock sleep to be instant so the test doesn't need fake timers,
    // but capture the delay arguments to verify the doubling sequence.
    const sleepSpy = vi
      .spyOn(
        TelemetrySender.prototype as unknown as { sleep: (ms: number) => Promise<void> },
        'sleep',
      )
      .mockResolvedValue(undefined);

    mockFetch.mockResolvedValue(makeResponse(500));

    // Track only 1 event so the buffer never hits maxBatchSize (100).
    // This ensures the manual flush() below (not an auto-flush) runs the retry loop.
    const sender = makeSender({ maxRetries: 3, initialBackoffMs: 1_000 });
    sender.track(makeEvent());
    await sender.flush();

    // Retry 1: 1000 ms, Retry 2: 2000 ms, Retry 3: 4000 ms
    const delays = sleepSpy.mock.calls.map((c) => c[0] as number);
    expect(delays).toEqual([1_000, 2_000, 4_000]);

    sender.destroy();
  });

  it('does not make any HTTP call when maxRetries is 0 and first attempt succeeds', async () => {
    const sender = makeSender({ maxRetries: 0 });
    sender.track(makeEvent());
    await sender.flush();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    sender.destroy();
  });
});

// ---------------------------------------------------------------------------
// Offline graceful degradation
// ---------------------------------------------------------------------------

describe('TelemetrySender — offline degradation', () => {
  it('does not call fetch when navigator.onLine is false', async () => {
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });

    const sender = makeSender({ maxRetries: 0 });
    sender.track(makeEvent());
    await sender.flush();

    expect(mockFetch).not.toHaveBeenCalled();
    sender.destroy();
  });

  it('logs an error and drops the batch when offline', async () => {
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const sender = makeSender({ maxRetries: 0 });
    sender.track(makeEvent());
    await sender.flush();

    expect(errorSpy).toHaveBeenCalledWith(
      expect.stringContaining('[TelemetrySender]'),
      expect.anything(),
    );
    sender.destroy();
  });

  it('resumes sending when back online', async () => {
    Object.defineProperty(navigator, 'onLine', { value: false, configurable: true });

    const sender = makeSender({ maxRetries: 0 });
    sender.track(makeEvent());
    await sender.flush(); // offline — dropped

    // Come back online
    Object.defineProperty(navigator, 'onLine', { value: true, configurable: true });
    sender.track(makeEvent());
    await sender.flush();

    expect(mockFetch).toHaveBeenCalledTimes(1);
    sender.destroy();
  });
});

// ---------------------------------------------------------------------------
// Background periodic flush
// ---------------------------------------------------------------------------

describe('TelemetrySender — background flush timer', () => {
  it('flushes buffered events after the flush interval elapses', async () => {
    vi.useFakeTimers();

    const sender = makeSender({ flushIntervalMs: 5_000, initialBackoffMs: 0 });
    sender.track(makeEvent());
    sender.track(makeEvent());

    expect(mockFetch).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(5_000);

    expect(mockFetch).toHaveBeenCalledTimes(1);
    const body = JSON.parse(
      (mockFetch.mock.calls[0] as [string, RequestInit])[1].body as string,
    ) as { events: unknown[] };
    expect(body.events).toHaveLength(2);

    sender.destroy();
  });

  it('does not flush after destroy()', async () => {
    vi.useFakeTimers();

    const sender = makeSender({ flushIntervalMs: 5_000 });
    sender.track(makeEvent());
    sender.destroy();

    await vi.advanceTimersByTimeAsync(10_000);

    expect(mockFetch).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Concurrent flush coalescing
// ---------------------------------------------------------------------------

describe('TelemetrySender — concurrent flush coalescing', () => {
  it('only runs one flush at a time when called concurrently', async () => {
    // Make fetch take a moment so two concurrent flush calls overlap
    let resolveFetch!: () => void;
    mockFetch.mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          resolveFetch = () => resolve(makeResponse(200));
        }),
    );

    const sender = makeSender();
    sender.track(makeEvent());

    const p1 = sender.flush();
    const p2 = sender.flush(); // second call while first is in-flight

    resolveFetch();
    await Promise.all([p1, p2]);

    // Only one HTTP request despite two concurrent flush() calls
    expect(mockFetch).toHaveBeenCalledTimes(1);
    sender.destroy();
  });
});
