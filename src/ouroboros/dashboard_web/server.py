"""Dependency-free HTTP + SSE server that streams runs' Kanbans to the browser.

ONE server (a singleton daemon) serves EVERY run — a run is selected per request
via ``?run=<execution_id>``, never baked into the server. This is deliberate: the
dashboard must NOT spawn a web server per MCP session/run (that would worsen the
process sprawl). The daemon is db-scoped only; :mod:`daemon` handles its single
lifecycle.

Each ``GET /events?run=<id>`` connection is one cursor tail of that run. Built on
stdlib ``http.server`` (threaded), read-only against the EventStore.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from typing import Any
from urllib.parse import parse_qs, urlparse

from ouroboros.dashboard_web.kanban import reduce_board
from ouroboros.dashboard_web.page import INDEX_HTML, static_html
from ouroboros.dashboard_web.reader import (
    EventTail,
    InterviewTail,
    PickerIndexContractError,
    linked_interview_id,
    list_recent_executions,
    list_recent_interviews,
    read_interview_source,
)
from ouroboros.persistence.picker_indexes import RUNTIME_STATUS_ASCII_WHITESPACE

# SSE poll cadence. Fast enough to feel live, slow enough that tailing a shared
# multi-hundred-MB SQLite file stays negligible.
_POLL_INTERVAL_SEC = 0.7
# Heartbeat comment cadence so idle connections stay open through proxies/tunnels.
_HEARTBEAT_SEC = 15.0
_PICKER_CONTRACT_ERROR = "picker_index_contract_unavailable"


def _selected_aggregate(query: dict[str, list[str]]) -> tuple[str, str] | None:
    """Return one unambiguous run or Interview query selection."""
    runs = query.get("run", [])
    interviews = query.get("interview", [])
    if (len(runs), len(interviews)) not in {(1, 0), (0, 1)}:
        return None
    run_id = runs[0] if runs else ""
    interview_id = interviews[0] if interviews else ""
    if not run_id.strip(RUNTIME_STATUS_ASCII_WHITESPACE) and not interview_id.strip(
        RUNTIME_STATUS_ASCII_WHITESPACE
    ):
        return None
    return run_id, interview_id


class _DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, addr: tuple[str, int], db_path: str) -> None:
        super().__init__(addr, _Handler)
        self.db_path = db_path
        # Liveness signal for the daemon's idle-shutdown watchdog: monotonic time
        # of the last successful browser activity, and the current open-stream count.
        self.last_activity: float = time.monotonic()
        self.open_streams: int = 0
        self._lock = threading.Lock()

    def touch(self) -> None:
        with self._lock:
            self.last_activity = time.monotonic()

    def stream_opened(self) -> None:
        with self._lock:
            self.open_streams += 1
            self.last_activity = time.monotonic()

    def stream_closed(self) -> None:
        with self._lock:
            self.open_streams = max(0, self.open_streams - 1)
            self.last_activity = time.monotonic()

    def idle_seconds(self) -> float:
        with self._lock:
            if self.open_streams > 0:
                return 0.0
            return time.monotonic() - self.last_activity


class _Handler(BaseHTTPRequestHandler):
    server: _DashboardServer  # type: ignore[assignment]

    def log_message(self, *_args: Any) -> None:  # noqa: D401 (silence stderr spam)
        return

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)
        if path in ("/", "/index.html"):
            self._send_bytes(INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/healthz":
            self._send_bytes(b"ok", "text/plain")
        elif path == "/api/interviews":
            try:
                limit = int((query.get("limit") or ["10"])[0])
                interviews = list_recent_interviews(self.server.db_path, limit=limit)
            except ValueError:
                self._send_json({"error": "limit must be an integer from 1 to 100"}, status=400)
                return
            except PickerIndexContractError:
                self._send_json({"interviews": [], "error": _PICKER_CONTRACT_ERROR}, status=503)
                return
            self._send_json({"interviews": interviews})
            self.server.touch()
        elif path == "/api/runs":
            try:
                runs = list_recent_executions(self.server.db_path)
            except PickerIndexContractError:
                self._send_json(
                    {"runs": [], "error": _PICKER_CONTRACT_ERROR},
                    status=503,
                )
                return
            self._send_json({"runs": runs})
            # The picker is a real dashboard client even though it polls instead
            # of holding an SSE stream. Refresh only after a successful response.
            self.server.touch()
        elif path == "/api/interview-source":
            source_id = _selected_source_identity(query)
            if source_id is None:
                self.send_error(400, "provide exactly one nonblank Interview identity")
                return
            try:
                source = read_interview_source(self.server.db_path, source_id)
            except PickerIndexContractError:
                self._send_json({"error": _PICKER_CONTRACT_ERROR}, status=503)
                return
            self._send_json({"source": source.as_dict()})
            self.server.touch()
        elif path == "/snapshot":
            selected = _selected_aggregate(query)
            if selected is None:
                self.send_error(400, "provide exactly one unambiguous run or Interview selector")
                return
            self._send_snapshot(*selected)
        elif path == "/events":
            selected = _selected_aggregate(query)
            if selected is None:
                self.send_error(400, "provide exactly one unambiguous run or Interview selector")
                return
            self._stream_events(*selected)
        else:
            self.send_error(404)

    def _send_snapshot(self, run_id: str, interview_id: str) -> None:
        """Serve a frozen, SSE-free snapshot of one selected aggregate."""
        if bool(run_id) == bool(interview_id):
            self.send_error(400, "provide exactly one of ?run=<execution_id> or ?interview=<id>")
            return
        tail = (
            EventTail(self.server.db_path, run_id)
            if run_id
            else InterviewTail(self.server.db_path, interview_id)
        )
        try:
            events = tail.fetch_new(limit=100000)
            board = self._board_with_source(events, run_id, interview_id)
        except PickerIndexContractError:
            self._send_json({"error": _PICKER_CONTRACT_ERROR}, status=503)
            return
        self._send_bytes(
            static_html(board, run_id=run_id or interview_id).encode("utf-8"),
            "text/html; charset=utf-8",
        )

    def _send_bytes(self, body: bytes, content_type: str, *, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj: Any, *, status: int = 200) -> None:
        self._send_bytes(
            json.dumps(obj, default=str).encode("utf-8"),
            "application/json",
            status=status,
        )

    def _stream_events(self, run_id: str, interview_id: str) -> None:
        if bool(run_id) == bool(interview_id):
            self.send_error(400, "provide exactly one of ?run=<execution_id> or ?interview=<id>")
            return
        tail = (
            EventTail(self.server.db_path, run_id)
            if run_id
            else InterviewTail(self.server.db_path, interview_id)
        )
        try:
            first_batch = tail.fetch_new()
            first_board = self._board_with_source(first_batch, run_id, interview_id)
        except PickerIndexContractError:
            # The HTTP status cannot change after SSE headers are committed, so
            # validate the stream and its source once before announcing success.
            self._send_json({"error": _PICKER_CONTRACT_ERROR}, status=503)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        self.server.stream_opened()
        accumulated: list[dict[str, Any]] = []
        last_emit = 0.0
        last_payload: str | None = None
        try:
            while True:
                if first_batch is not None:
                    new = first_batch
                    first_batch = None
                    board = first_board
                else:
                    new = tail.fetch_new()
                    board = None
                now = time.monotonic()
                if new:
                    accumulated.extend(new)
                    if board is None:
                        board = self._board_with_source(accumulated, run_id, interview_id)
                    payload = json.dumps(board, default=str)
                    if payload != last_payload:
                        self._sse_send(payload)
                        last_payload = payload
                        last_emit = now
                        self.server.touch()
                elif now - last_emit >= _HEARTBEAT_SEC:
                    self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
                    last_emit = now
                    self.server.touch()
                time.sleep(_POLL_INTERVAL_SEC)
        except PickerIndexContractError:
            # A contract can drift after the preflight in a long-lived stream.
            # Close cleanly; EventSource reconnects and receives a deliberate
            # pre-header 503 from the next request.
            self.close_connection = True
            return
        except (BrokenPipeError, ConnectionResetError):
            return  # client navigated away
        except OSError:
            return
        finally:
            self.server.stream_closed()

    def _sse_send(self, data: str) -> None:
        # One SSE event; data may not contain bare newlines (json.dumps escapes them).
        self.wfile.write(f"data: {data}\n\n".encode())
        self.wfile.flush()

    def _board_with_source(
        self, events: list[dict[str, Any]], run_id: str, interview_id: str
    ) -> dict[str, Any]:
        """Attach only canonical source turns to an already read-only board."""
        source_id = interview_id or linked_interview_id(self.server.db_path, run_id)
        board = reduce_board(events, execution_id=run_id or None)
        if source_id is not None:
            board["meta"]["interview_source"] = read_interview_source(
                self.server.db_path, source_id
            ).as_dict()
        return board


def _selected_source_identity(query: dict[str, list[str]]) -> str | None:
    """Accept only one identity selector; no path-like resource parameter exists."""
    if set(query) != {"interview"} or len(query["interview"]) != 1:
        return None
    identity = query["interview"][0]
    return identity if identity.strip(RUNTIME_STATUS_ASCII_WHITESPACE) else None


def make_server(*, db_path: str, host: str, port: int) -> _DashboardServer:
    """Build (but do not start) the dashboard HTTP server (db-scoped, multi-run)."""
    return _DashboardServer((host, port), db_path)


def serve_blocking(
    *,
    db_path: str,
    host: str,
    port: int,
    idle_shutdown_sec: float | None = None,
) -> None:
    """Run the server in the current thread until interrupted or idle.

    When ``idle_shutdown_sec`` is set, a watchdog stops the server once neither
    a successful picker poll nor an SSE client has been active for that long —
    so the daemon never lingers as a zombie after its viewers leave.
    """
    server = make_server(db_path=db_path, host=host, port=port)
    stop = threading.Event()

    def _watchdog() -> None:
        assert idle_shutdown_sec is not None
        while not stop.wait(min(idle_shutdown_sec, 30.0)):
            if server.idle_seconds() >= idle_shutdown_sec:
                threading.Thread(target=server.shutdown, daemon=True).start()
                return

    if idle_shutdown_sec is not None:
        threading.Thread(target=_watchdog, name="ooo-dash-idle", daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


def serve_background(
    *, db_path: str, host: str, port: int
) -> tuple[_DashboardServer, threading.Thread]:
    """Start the server on a daemon thread; return (server, thread). Testing/dev."""
    server = make_server(db_path=db_path, host=host, port=port)
    thread = threading.Thread(target=server.serve_forever, name="ooo-dashboard", daemon=True)
    thread.start()
    return server, thread


__all__ = ["make_server", "serve_background", "serve_blocking"]
