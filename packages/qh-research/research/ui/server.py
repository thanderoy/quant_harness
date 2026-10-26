"""research.ui.server — a local, read-only web view of the harness.

    cd packages/qh-research && python -m research.ui [--port 8765]

Standard library only. Binds to 127.0.0.1, answers GET and nothing else, and
reads the research log on every request, so a newly appended entry shows on
the next refresh. No route writes anything.
"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote, urlparse

from research.ui import data

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
DEFAULT_PORT = 8765
STATIC_DIR = Path(__file__).resolve().parent / "static"
#: Pages are rendered client-side; each path serves the same shell.
PAGES = ("/", "/experiments", "/divisions", "/trials", "/observation",
         "/log", "/protocols", "/artifacts")
STATIC_FILES = {**{p: "index.html" for p in PAGES},
                "/app.js": "app.js", "/app.css": "app.css"}

ROUTES: dict[str, Callable[[], object]] = {
    "/api/summary": data.summary,
    "/api/hypotheses": data.hypotheses,
    "/api/ledger": data.ledger,
    "/api/trials": data.trial_timeline,
    "/api/trial_breakdown": data.trial_breakdown,
    "/api/status": data.status,
    "/api/pending": data.pending,
    "/api/artifacts": data.artifacts,
}
PREFIX_ROUTES: dict[str, Callable[[str], Optional[object]]] = {
    "/api/hypothesis/": data.hypothesis,
    "/api/artifact/": data.artifact,
}


def resolve(path: str) -> tuple[HTTPStatus, Optional[object]]:
    """Route an API path to its view. Separate from the handler for testing."""
    if path in ROUTES:
        return HTTPStatus.OK, ROUTES[path]()
    for prefix, view in PREFIX_ROUTES.items():
        if path.startswith(prefix):
            body = view(unquote(path[len(prefix):]))
            return (HTTPStatus.OK, body) if body is not None else (HTTPStatus.NOT_FOUND, None)
    return HTTPStatus.NOT_FOUND, None


class Handler(BaseHTTPRequestHandler):
    server_version = "HarnessLedger/1"

    def do_GET(self) -> None:  # noqa: N802 (stdlib name)
        path = urlparse(self.path).path
        if path in STATIC_FILES:
            self._static(STATIC_FILES[path])
            return
        if path.startswith("/api/"):
            try:
                code, body = resolve(path)
            except Exception:  # a broken view must not take the server down
                logger.exception("view failed: %s", path)
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                           {"error": "the view failed; see the server log"})
                return
            self._json(code, body if body is not None else {"error": "not found"})
            return
        # Any other path gets the page shell, which renders its own 404.
        self._static("index.html", HTTPStatus.NOT_FOUND)

    def _refuse(self) -> None:
        self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "read-only"})

    do_POST = do_PUT = do_PATCH = do_DELETE = _refuse  # noqa: N815

    def _json(self, code: HTTPStatus, body: object) -> None:
        raw = json.dumps(body, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _static(self, name: str, code: HTTPStatus = HTTPStatus.OK) -> None:
        p = STATIC_DIR / name
        raw = p.read_bytes()
        self.send_response(code)
        self.send_header("Content-Type", mimetypes.guess_type(name)[0] or "text/plain")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args) -> None:
        logger.debug("%s - " + fmt, self.address_string(), *args)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    httpd = ThreadingHTTPServer((HOST, args.port), Handler)
    logger.info("Harness Ledger on http://%s:%d  (Ctrl+C to stop)", HOST, args.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0
