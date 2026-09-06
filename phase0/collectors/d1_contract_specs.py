"""D1 — contract spec dump for the candidate universe.

Runs unattended the moment a terminal is up:

    python3 -m phase0.collectors.d1_contract_specs

Writes ``phase0/d1_contract_specs_<UTCDATE>.json``. Every snapshot carries a
``provenance`` field with exactly two legal values, ``MT5_SYMBOL_INFO`` or
``HAND_ENTERED``. There is no third state and no default: this collector only
ever emits the former, and a hand-entered spec must be authored deliberately
elsewhere. A hand-entered contract spec is a seeded, unverified value of the
kind the log provenance audit exists to catch — except this one propagates
silently into every sizing calculation downstream.

PREREQUISITE — mt5-api does not yet expose symbol_info
------------------------------------------------------
As of WMPS 63d93f6 the service exposes /api/v1/{account,rates,tick,...} but no
symbol-info endpoint, so this collector raises ``EndpointMissing`` on a live
API. The required addition is small and is specified in
``docs/mt5_api_additions.md``. This file is committed *now*, unrun, because the
session the terminal comes up is the session you want pulling data, not
authoring the puller.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from phase0.collectors._client import (
    UNIVERSE,
    broker_context,
    server_mismatch,
    EndpointMissing,
    MT5Unavailable,
    get,
    now_iso,
    probe,
    write_artifact,
)

#: Every field D1 requires. Absence of any one is recorded, not silently
#: tolerated — a missing tick_value is not a cosmetic gap, it is the term the
#: whole position-size calculation is built on.
REQUIRED_FIELDS: tuple[str, ...] = (
    "contract_size", "tick_size", "tick_value",
    "volume_min", "volume_max", "volume_step",
    "currency_profit", "currency_margin", "digits",
    "trade_stops_level", "trade_freeze_level",
    "filling_mode", "swap_long", "swap_short", "swap_mode",
)

PROVENANCE = "MT5_SYMBOL_INFO"

#: The current codebase assumes IOC everywhere on the strength of one symbol
#: on one broker. D1's guard is to find out where that stops being true.
IOC_FLAG = 2  # SYMBOL_FILLING_IOC


def fetch_symbol(symbol: str) -> dict:
    res = get("/api/v1/symbol_info", {"symbol": symbol})
    info = dict(res.payload) if isinstance(res.payload, dict) else {}
    missing = [f for f in REQUIRED_FIELDS if f not in info or info[f] is None]
    fill = info.get("filling_mode")
    return {
        "symbol": symbol,
        "provenance": PROVENANCE,
        "as_of_utc": now_iso(),
        "fields": {f: info.get(f) for f in REQUIRED_FIELDS},
        "missing_fields": missing,
        "ioc_supported": (bool(fill & IOC_FLAG) if isinstance(fill, int) else None),
        "raw": info,
    }


def terminal_build() -> dict:
    """Terminal build number, pinned alongside the specs.

    A contract spec without the build that produced it is a number without a
    source; broker-side spec changes are exactly what an as_of pin is for.
    """
    try:
        return dict(get("/").payload or {})
    except (MT5Unavailable, EndpointMissing) as exc:
        return {"error": str(exc)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="directory for the artifact (default: phase0/)")
    ap.add_argument("--expect-server", default=None,
                    help="refuse to collect unless the terminal's trade "
                         "server contains this substring (case-insensitive)")
    args = ap.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact: dict = {
        "task": "D1",
        "collected_at_utc": now_iso(),
        "universe": list(UNIVERSE),
        "provenance_rule": "MT5_SYMBOL_INFO | HAND_ENTERED — no third state, "
                           "no default. This collector emits only the former.",
        "probe": probe(),
    }

    if not artifact["probe"]["reachable"]:
        artifact["status"] = "BLOCKED"
        artifact["blocked_reason"] = artifact["probe"]["error"]
        artifact["dependency"] = "mt5-api reachable at MT5_API_URL"
        path = write_artifact(f"d1_contract_specs_{stamp}.json", artifact,
                              args.out_dir)
        print(f"BLOCKED — {artifact['blocked_reason']}", file=sys.stderr)
        print(f"artifact: {path}")
        return 2

    artifact["terminal"] = terminal_build()

    # Recorded before any spec is fetched. Contract specs are broker policy —
    # filling modes, volume caps, swap rates all differ per broker — so a dump
    # that does not name its server cannot be interpreted, and worse, can be
    # mislabelled by whoever writes it up later. That is exactly what happened
    # on 2026-09-01.
    artifact["broker"] = broker_context()
    mismatch = server_mismatch(artifact["broker"], args.expect_server)
    if mismatch:
        artifact["status"] = "REFUSED_SERVER_MISMATCH"
        artifact["blocked_reason"] = mismatch
        path = write_artifact(f"d1_contract_specs_{stamp}.json", artifact,
                              args.out_dir)
        print(f"REFUSED — {mismatch}", file=sys.stderr)
        print(f"artifact: {path}")
        return 4

    specs: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for sym in UNIVERSE:
        try:
            specs[sym] = fetch_symbol(sym)
        except EndpointMissing as exc:
            artifact["status"] = "BLOCKED"
            artifact["blocked_reason"] = str(exc)
            artifact["dependency"] = (
                "mt5-api must expose GET /api/v1/symbol_info — see "
                "docs/mt5_api_additions.md"
            )
            path = write_artifact(f"d1_contract_specs_{stamp}.json", artifact,
                              args.out_dir)
            print(f"BLOCKED — {exc}", file=sys.stderr)
            print(f"artifact: {path}")
            return 3
        except MT5Unavailable as exc:
            errors[sym] = str(exc)

    artifact["specs"] = specs
    artifact["errors"] = errors
    artifact["status"] = "PARTIAL_UNIVERSE" if errors else "OK"

    no_ioc = [s for s, v in specs.items() if v["ioc_supported"] is False]
    incomplete = {s: v["missing_fields"] for s, v in specs.items()
                  if v["missing_fields"]}
    artifact["guards"] = {
        "symbols_without_ioc": no_ioc,
        "ioc_assumption_generalises": not no_ioc,
        "symbols_with_missing_fields": incomplete,
    }

    path = write_artifact(f"d1_contract_specs_{stamp}.json", artifact,
                              args.out_dir)
    print(json.dumps({
        "status": artifact["status"],
        "server": artifact["broker"].get("server"),
        "n_specs": len(specs),
        "n_errors": len(errors),
        "symbols_without_ioc": no_ioc,
        "artifact": str(path),
    }, indent=2))
    return 0 if artifact["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
