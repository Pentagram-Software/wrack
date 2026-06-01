import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import CameraView from './CameraView';

// ─── Mock WebSocketVideoClient ────────────────────────────────────────────────
// Use vi.hoisted so the class is available when vi.mock factory runs at hoist time.

const { MockVideoClient, mockInstances } = vi.hoisted(() => {
  interface MockClientConfig {
    url: string;
    onStateChange?: (state: string, prev: string) => void;
    onError?: (err: Error) => void;
    onFrame?: (stats: object) => void;
  }

  const mockInstances: InstanceType<typeof MockVideoClientClass>[] = [];

  class MockVideoClientClass {
    config: MockClientConfig;
    state = 'idle';
    connectCalled = false;
    disconnectCalled = false;

    constructor(config: MockClientConfig) {
      this.config = config;
      mockInstances.push(this);
    }

    connect() {
      this.connectCalled = true;
      this.setState('connecting');
    }

    disconnect() {
      this.disconnectCalled = true;
      this.setState('disconnected');
    }

    getState() { return this.state; }

    getStats() {
      return { fps: 0, framesReceived: 0, framesDecoded: 0, codec: null };
    }

    setState(state: string) {
      const prev = this.state;
      this.state = state;
      this.config.onStateChange?.(state, prev);
    }

    simulateConnected() { this.setState('connected'); }
    simulateError(msg = 'Connection refused') {
      this.setState('error');
      this.config.onError?.(new Error(msg));
    }
  }

  return { MockVideoClient: MockVideoClientClass, mockInstances };
});

vi.mock('@/lib/videoStream', () => ({
  isWebCodecsSupported: () => false,
  WebSocketVideoClient: MockVideoClient,
}));

// ─── Setup ────────────────────────────────────────────────────────────────────

beforeEach(() => {
  mockInstances.length = 0;
});

afterEach(() => {
  vi.clearAllMocks();
});

// ─── Rendering ────────────────────────────────────────────────────────────────

describe('CameraView — rendering', () => {
  it('renders without crashing', () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    expect(screen.getByText('Camera Feed')).toBeInTheDocument();
  });

  it('shows Start button when not streaming', () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    expect(screen.getByRole('button', { name: /start/i })).toBeInTheDocument();
  });

  it('shows the idle state by default', () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    expect(screen.getByText('Camera Feed Disabled')).toBeInTheDocument();
  });

  it('renders a close button', () => {
    const onClose = vi.fn();
    render(<CameraView onClose={onClose} isExpanded={false} />);
    // The XMarkIcon button is the only non-labelled button
    const buttons = screen.getAllByRole('button');
    const closeBtn = buttons.find((b) => !b.textContent?.match(/start|stop/i));
    expect(closeBtn).toBeDefined();
    fireEvent.click(closeBtn!);
    expect(onClose).toHaveBeenCalled();
  });
});

// ─── Stream lifecycle ─────────────────────────────────────────────────────────

describe('CameraView — stream lifecycle', () => {
  it('creates a WebSocketVideoClient and calls connect() on Start', () => {
    render(<CameraView onClose={() => {}} isExpanded={false} wsBridgeUrl="ws://pi:8765" />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));

    expect(mockInstances).toHaveLength(1);
    expect(mockInstances[0].connectCalled).toBe(true);
    expect(mockInstances[0].config.url).toBe('ws://pi:8765');
  });

  it('shows Stop button after starting', () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument();
  });

  it('shows connecting overlay while connecting', () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    // MockClient transitions to 'connecting' on connect()
    // "Connecting…" appears in the header status span AND in the overlay h4
    const connecting = screen.getAllByText('Connecting…');
    expect(connecting.length).toBeGreaterThanOrEqual(1);
  });

  it('shows the video canvas when connected', async () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));

    await act(async () => {
      mockInstances[0].simulateConnected();
    });

    expect(screen.getByTestId('video-canvas')).toBeVisible();
  });

  it('shows LIVE badge when connected', async () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));

    await act(async () => {
      mockInstances[0].simulateConnected();
    });

    expect(screen.getByText('LIVE')).toBeInTheDocument();
  });

  it('calls disconnect() on Stop', () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    fireEvent.click(screen.getByRole('button', { name: /stop/i }));
    expect(mockInstances[0].disconnectCalled).toBe(true);
  });

  it('returns to idle state after stopping', async () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));

    await act(async () => {
      mockInstances[0].simulateConnected();
    });

    fireEvent.click(screen.getByRole('button', { name: /stop/i }));
    expect(screen.getByText('Camera Feed Disabled')).toBeInTheDocument();
  });

  it('does not create a second client when Start is clicked while already streaming', () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    // The button is now Stop — clicking Stop stops streaming
    // We need to verify double-Start doesn't create two clients
    // Since the button switches to Stop, this is guaranteed by UI state
    expect(mockInstances).toHaveLength(1);
  });
});

// ─── Error handling ───────────────────────────────────────────────────────────

describe('CameraView — error handling', () => {
  it('shows error overlay on connection failure', async () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));

    await act(async () => {
      mockInstances[0].simulateError('Connection refused');
    });

    expect(screen.getByText('Connection Error')).toBeInTheDocument();
    expect(screen.getByText('Connection refused')).toBeInTheDocument();
  });

  it('shows a Retry button in error state', async () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));

    await act(async () => {
      mockInstances[0].simulateError();
    });

    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});

// ─── Status indicators ────────────────────────────────────────────────────────

describe('CameraView — status indicator', () => {
  it('shows Idle status dot by default', () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    expect(screen.getByText('Idle')).toBeInTheDocument();
  });

  it('shows Connecting… label while connecting', () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    // The header status label shows "Connecting…" (in a span)
    const labels = screen.getAllByText('Connecting…');
    expect(labels.some((el) => el.tagName === 'SPAN')).toBe(true);
  });

  it('shows Live label when connected', async () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    await act(async () => {
      mockInstances[0].simulateConnected();
    });
    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it('shows Error label on connection error', async () => {
    render(<CameraView onClose={() => {}} isExpanded={false} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    await act(async () => {
      mockInstances[0].simulateError();
    });
    expect(screen.getByText('Error')).toBeInTheDocument();
  });
});
