"""Local server for the flow map (spec section 14, decision B38).

Serves exactly two things on 127.0.0.1 only: docs/flowmap.html and one run log.
GET only, no other paths, no outbound requests. The page polls the log; the
server never controls the pipeline. This is not data-fetching code, so it lives
outside net.py and its allowlist, which stay untouched.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE = REPO_ROOT / "docs" / "flowmap.html"
HOST = "127.0.0.1"


class FlowServer:
    def __init__(self, log_path: Path, page: Path = PAGE):
        self.log_path = Path(log_path)
        self.page = Path(page)
        self.finished_served = threading.Event()   # the page has read a log with the report event
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 (stdlib name)
                path = self.path.split("?", 1)[0]
                if path in ("/", "/flowmap.html"):
                    body, ctype = outer.page.read_bytes(), "text/html; charset=utf-8"
                elif path == "/run.jsonl":
                    body = outer.log_path.read_bytes() if outer.log_path.exists() else b""
                    ctype = "application/x-ndjson; charset=utf-8"
                    lines = body.strip().splitlines()
                    if lines and b'"stage": "report"' in lines[-1]:   # the latest run has ended
                        outer.finished_served.set()
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):   # keep the CLI output clean
                pass

        self.httpd = ThreadingHTTPServer((HOST, 0), Handler)
        self.port = self.httpd.server_address[1]
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/flowmap.html?live=1&log=/run.jsonl"

    def start(self) -> "FlowServer":
        self._thread.start()
        return self

    def wait_until_read(self, timeout: float) -> bool:
        """Block until the page has fetched the finished log, or the timeout ends."""
        return self.finished_served.wait(timeout)

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
