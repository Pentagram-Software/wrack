"""LL-HLS HTTP server.

Serves M3U8 playlists and ``.ts`` segment files, and implements the
*blocking playlist reload* mechanism required by LL-HLS
(RFC 8216bis §6.2.5.2):

  A client includes ``?_HLS_msn=<N>&_HLS_part=<P>`` in its playlist
  request.  The server **holds** the response until segment sequence *N*,
  part index *P* (or any later content) is available in the
  :class:`~hls.store.SegmentStore`, then replies with a fresh playlist.

Routes
------
``GET /``              → master playlist (``index.m3u8``)
``GET /index.m3u8``   → master playlist
``GET /stream.m3u8``  → media playlist  (supports ``_HLS_msn`` / ``_HLS_part``)
``GET /<name>.ts``    → segment or partial-segment file
"""

import logging
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

from .playlist import PlaylistGenerator
from .store import SegmentStore

logger = logging.getLogger(__name__)


class _RequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for LL-HLS content delivery."""

    # Suppress default request-per-line logging; we use our own logger.
    def log_message(self, fmt, *args):
        logger.debug("[HTTP] %s %s", self.address_string(), fmt % args)

    def do_GET(self):  # noqa: N802 (name required by BaseHTTPRequestHandler)
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.strip("/")
        params = urllib.parse.parse_qs(parsed.query)

        store: SegmentStore = self.server.hls_store          # type: ignore[attr-defined]
        generator: PlaylistGenerator = self.server.hls_gen   # type: ignore[attr-defined]
        output_dir: Path = self.server.hls_dir               # type: ignore[attr-defined]

        if path in ("", "index.m3u8"):
            content = generator.generate_master_playlist()
            self._send_playlist(content)

        elif path == "stream.m3u8":
            msn_val = params.get("_HLS_msn", [None])[0]
            part_val = params.get("_HLS_part", [None])[0]

            if msn_val is not None:
                # Blocking reload: wait until the requested content is available.
                msn = int(msn_val)
                part_idx = int(part_val) if part_val is not None else 0
                if not store.wait_for_part(msn, part_idx, timeout=10.0):
                    self.send_error(503, "Requested segment/part not available in time")
                    return

            segments, pending_parts, media_sequence = store.get_snapshot()
            content = generator.generate_media_playlist(
                segments,
                pending_parts,
                media_sequence,
                store.next_segment_sequence,
            )
            self._send_playlist(content)

        elif path.endswith(".ts"):
            seg_path = output_dir / path
            if seg_path.exists():
                data = seg_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "video/mp2t")
                self.send_header("Content-Length", str(len(data)))
                # Segments are immutable once written; cache aggressively.
                self.send_header("Cache-Control", "max-age=31536000, public")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404, f"Segment not found: {path}")

        else:
            self.send_error(404, "Not found")

    def _send_playlist(self, content: str) -> None:
        data = content.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.send_header("Content-Length", str(len(data)))
        # Playlists must not be cached – clients refresh them continuously.
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)


class LLHLSServer:
    """Threaded HTTP server that delivers LL-HLS content.

    Parameters
    ----------
    segment_store:
        Shared :class:`~hls.store.SegmentStore` populated by an
        :class:`~hls.segmenter.HLSSegmenter`.
    playlist_generator:
        :class:`~hls.playlist.PlaylistGenerator` configured with the same
        target/part durations as the segmenter.
    output_dir:
        Directory containing the ``.ts`` segment files written by the
        segmenter.  Must be the same directory.
    host:
        Bind address (default ``"0.0.0.0"``).
    port:
        TCP port (default ``8888``).
    """

    def __init__(
        self,
        segment_store: SegmentStore,
        playlist_generator: PlaylistGenerator,
        output_dir: Path,
        host: str = "0.0.0.0",
        port: int = 8888,
    ) -> None:
        self.segment_store = segment_store
        self.playlist_generator = playlist_generator
        self.output_dir = Path(output_dir)
        self.host = host
        self.port = port
        self._httpd: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the HTTP server in a background daemon thread."""
        httpd = HTTPServer((self.host, self.port), _RequestHandler)
        # Attach shared objects so the handler can access them.
        httpd.hls_store = self.segment_store      # type: ignore[attr-defined]
        httpd.hls_gen = self.playlist_generator   # type: ignore[attr-defined]
        httpd.hls_dir = self.output_dir           # type: ignore[attr-defined]

        self._httpd = httpd
        self._thread = threading.Thread(
            target=httpd.serve_forever,
            name="llhls-http-server",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "LL-HLS server listening on http://%s:%d  (index.m3u8 / stream.m3u8)",
            self.host,
            self.port,
        )

    def stop(self) -> None:
        """Shut down the HTTP server and wait for the thread to finish."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("LL-HLS server stopped")

    @property
    def is_running(self) -> bool:
        """True while the server thread is alive."""
        return self._thread is not None and self._thread.is_alive()
