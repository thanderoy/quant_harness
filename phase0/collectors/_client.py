"""Shared HTTP client and universe for the Phase 0 MT5 collectors.

The collectors talk to the mt5-api FastAPI service, never to ``MetaTrader5``
directly. That service is the only process permitted to import the MT5 library
(WMPS ``CLAUDE.md`` architecture rule 1), and honouring it here is what lets
these run from the research repo at all.

Stdlib-only on purpose: a collector that cannot run because its environment is
missing a dependency is a collector that will not run on the one day the
terminal happens to be up.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

#: Base URL of the mt5-api service. ``demo`` maps to the mt5-test container.
DEFAULT_BASE_URL = os.environ.get("MT5_API_URL", "http://localhost:5001")

#: Seven majors plus the two metals — the D1/D2/D3 candidate universe.
UNIVERSE: tuple[str, ...] = (
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "USDCAD", "AUDUSD", "NZDUSD",
    "XAUUSD", "XAGUSD",
)

ARTIFACT_DIR = Path(__file__).resolve().parents[1]


class MT5Unavailable(RuntimeError):
    """The terminal or the API is not reachable.

    Raised rather than returning a partial result, because a collector that
    silently produces a thin artifact is exactly how a BLOCKED task turns into
    an unnoticed hole.
    """


class EndpointMissing(RuntimeError):
    """The API is up but does not expose the endpoint this collector needs.

    Distinct from :class:`MT5Unavailable`: the fix is a code change to
    mt5-api, not waiting for a terminal.
    """


@dataclass(frozen=True)
class ApiResult:
    status: int
    payload: object


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get(path: str, params: dict | None = None, *,
        base_url: str = DEFAULT_BASE_URL, timeout: float = 15.0) -> ApiResult:
    """GET ``path``, mapping transport failures onto the two error classes."""
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return ApiResult(resp.status, json.loads(resp.read().decode()))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise EndpointMissing(
                f"{path} returned 404 — mt5-api does not expose this endpoint"
            ) from exc
        raise MT5Unavailable(f"{path} -> HTTP {exc.code}: {exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise MT5Unavailable(f"{path} unreachable at {base_url}: {exc}") from exc


def probe() -> dict:
    """Cheap reachability check. Returns a dict; never raises."""
    try:
        res = get("/")
        return {"reachable": True, "status": res.status, "root": res.payload}
    except (MT5Unavailable, EndpointMissing) as exc:
        return {"reachable": False, "error": str(exc)}


def write_artifact(name: str, payload: dict, out_dir: Path | None = None) -> Path:
    """Write a Phase 0 artifact and return its path.

    ``out_dir`` overrides the default location so a test run does not deposit
    artifacts into the repo alongside real collection output.
    """
    out = (out_dir or ARTIFACT_DIR) / name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    return out


def broker_context() -> dict:
    """Identify the trade server the caller is about to collect from.

    Load-bearing, and shared by every collector. The D1/D3a/D3b runs of
    2026-09-01 were labelled "Pepperstone (demo)" on the strength of the
    container's name; the terminal was authorized on MetaQuotes-Demo, and
    nothing in any output recorded otherwise, so the mislabel survived into a
    committed snapshot and into conclusions about filling modes and spreads.
    A measurement with no broker on it is not a measurement of anything.

    Records ``server``, ``trade_mode`` and ``currency`` only. ``login`` and
    ``name`` are account identity and are deliberately dropped.
    """
    try:
        payload = get("/api/v1/account").payload
    except (MT5Unavailable, EndpointMissing) as exc:
        return {"server": None, "trade_mode": None, "error": str(exc)}
    return {
        "server": payload.get("server"),
        "trade_mode": payload.get("trade_mode"),
        "currency": payload.get("currency"),
    }


def server_mismatch(broker: dict, expect: str | None) -> str | None:
    """Return an error string when the server does not match ``expect``."""
    if not expect:
        return None
    server = broker.get("server")
    if not server or expect.lower() not in server.lower():
        return (f"trade server {server!r} does not match expected "
                f"substring {expect!r}")
    return None
