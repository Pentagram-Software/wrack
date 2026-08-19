/**
 * Unit tests for the CameraView component.
 *
 * useVideoStream (and therefore hls.js) is mocked so these tests focus purely
 * on the component's rendering logic and UI interactions.
 *
 * IMPORTANT: Variables referenced inside vi.mock() factory functions must be
 * created via vi.hoisted() — they are in the temporal dead zone when the
 * hoisted mock runs, even though they appear above vi.mock() in source.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import CameraView from './CameraView';

// ---------------------------------------------------------------------------
// Mock useVideoStream using vi.hoisted() so the factory can reference the spy
// ---------------------------------------------------------------------------

const { mockUseVideoStream } = vi.hoisted(() => ({
  mockUseVideoStream: vi.fn(() => ({ status: 'idle', error: null })),
}));

vi.mock('@/lib/useVideoStream', () => ({
  useVideoStream: mockUseVideoStream,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setStreamStatus(status: string, error: string | null = null) {
  mockUseVideoStream.mockReturnValue({ status, error });
}

const defaultProps = {
  onClose: vi.fn(),
  isExpanded: true,
  streamUrl: 'http://localhost/stream.m3u8',
};

beforeEach(() => {
  vi.clearAllMocks();
  setStreamStatus('idle');
});

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

describe('CameraView — rendering', () => {
  it('renders the Camera Feed header', () => {
    render(<CameraView {...defaultProps} />);
    expect(screen.getByText('Camera Feed')).toBeInTheDocument();
  });

  it('renders a Start button when not streaming', () => {
    render(<CameraView {...defaultProps} />);
    expect(screen.getByRole('button', { name: /start/i })).toBeInTheDocument();
  });

  it('renders an accessible close button', () => {
    render(<CameraView {...defaultProps} />);
    expect(screen.getByRole('button', { name: /close camera/i })).toBeInTheDocument();
  });

  it('renders the video element (always mounted for HLS attachment)', () => {
    const { container } = render(<CameraView {...defaultProps} />);
    expect(container.querySelector('video')).not.toBeNull();
  });

  it('shows Camera Feed Disabled placeholder when not streaming', () => {
    render(<CameraView {...defaultProps} />);
    expect(screen.getByText('Camera Feed Disabled')).toBeInTheDocument();
  });

  it('displays resolution and FPS metadata', () => {
    render(<CameraView {...defaultProps} />);
    expect(screen.getByText('Resolution: 640x480')).toBeInTheDocument();
    expect(screen.getByText('FPS: 30')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Status indicator
// ---------------------------------------------------------------------------

describe('CameraView — status indicator', () => {
  it('shows "disconnected" label when status is idle', () => {
    setStreamStatus('idle');
    render(<CameraView {...defaultProps} />);
    expect(screen.getByText('disconnected')).toBeInTheDocument();
  });

  it('shows "loading" label when status is loading', () => {
    setStreamStatus('loading');
    render(<CameraView {...defaultProps} />);
    expect(screen.getByText('loading')).toBeInTheDocument();
  });

  it('shows "ready" label when status is ready', () => {
    setStreamStatus('ready');
    render(<CameraView {...defaultProps} />);
    expect(screen.getByText('ready')).toBeInTheDocument();
  });

  it('shows "error" label when status is error', () => {
    setStreamStatus('error', 'Stream unavailable');
    render(<CameraView {...defaultProps} />);
    expect(screen.getByText('error')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Toggle interaction
// ---------------------------------------------------------------------------

describe('CameraView — stream toggle', () => {
  it('switches button label to Stop when Start is clicked', () => {
    render(<CameraView {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument();
  });

  it('switches button label back to Start when Stop is clicked', () => {
    render(<CameraView {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    fireEvent.click(screen.getByRole('button', { name: /stop/i }));
    expect(screen.getByRole('button', { name: /start/i })).toBeInTheDocument();
  });

  it('passes the streamUrl to useVideoStream after clicking Start', () => {
    render(<CameraView {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    const lastCall = mockUseVideoStream.mock.calls.at(-1)?.[0] as { url: string | null } | undefined;
    expect(lastCall?.url).toBe(defaultProps.streamUrl);
  });

  it('passes null url to useVideoStream after clicking Stop', () => {
    render(<CameraView {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    fireEvent.click(screen.getByRole('button', { name: /stop/i }));
    const lastCall = mockUseVideoStream.mock.calls.at(-1)?.[0] as { url: string | null } | undefined;
    expect(lastCall?.url).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Content area states
// ---------------------------------------------------------------------------

describe('CameraView — content area states', () => {
  it('shows the connecting spinner when streaming on and status is loading', () => {
    setStreamStatus('loading');
    render(<CameraView {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    expect(screen.getByText('Connecting to Camera')).toBeInTheDocument();
  });

  it('shows an error message when streaming and status is error', () => {
    setStreamStatus('error', 'networkError');
    render(<CameraView {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    expect(screen.getByText('Stream Error')).toBeInTheDocument();
    expect(screen.getByText('networkError')).toBeInTheDocument();
  });

  it('shows the LIVE overlay when status is ready', () => {
    setStreamStatus('ready');
    render(<CameraView {...defaultProps} />);
    expect(screen.getByText('LIVE')).toBeInTheDocument();
  });

  it('shows Snapshot and Fullscreen overlay buttons when status is ready', () => {
    setStreamStatus('ready');
    render(<CameraView {...defaultProps} />);
    expect(screen.getByRole('button', { name: /snapshot/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /fullscreen/i })).toBeInTheDocument();
  });

  it('shows Latency info when status is ready', () => {
    setStreamStatus('ready');
    render(<CameraView {...defaultProps} />);
    expect(screen.getByText(/latency/i)).toBeInTheDocument();
  });

  it('does not show Latency info when idle', () => {
    setStreamStatus('idle');
    render(<CameraView {...defaultProps} />);
    expect(screen.queryByText(/latency/i)).toBeNull();
  });

  it('falls back to generic error message when error detail is null', () => {
    setStreamStatus('error', null);
    render(<CameraView {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    expect(screen.getByText('Stream Error')).toBeInTheDocument();
    expect(screen.getByText(/unable to connect/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Close button
// ---------------------------------------------------------------------------

describe('CameraView — close button', () => {
  it('calls onClose when the close button is clicked', () => {
    const onClose = vi.fn();
    render(<CameraView {...defaultProps} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: /close camera/i }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});

// ---------------------------------------------------------------------------
// No stream URL provided
// ---------------------------------------------------------------------------

describe('CameraView — no streamUrl prop', () => {
  it('passes null url to useVideoStream even when streaming is toggled on', () => {
    render(<CameraView onClose={vi.fn()} isExpanded={false} />);
    fireEvent.click(screen.getByRole('button', { name: /start/i }));
    const lastCall = mockUseVideoStream.mock.calls.at(-1)?.[0] as { url: string | null } | undefined;
    expect(lastCall?.url).toBeNull();
  });
});
