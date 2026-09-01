"""Pin the gitignored ``research/data/`` OHLCV inputs with a tracked manifest.

``research/data/`` is gitignored (``.gitignore:106``) — ~150 MB of broker CSV
exports. That is the right call for the repo's size, but it leaves every
recorded ``ohlc_hash`` resting on an untracked file nobody would notice
changing. A re-pull from MT5 that silently altered a series would surface as
an apparent indicator regression, which is exactly the misattribution the
ordered T9a assertions exist to prevent.

This manifest is the cheap half of the fix: it records, per file, the sha256
of the bytes, the row count, the first and last bar timestamps, and — for the
house ``;``-separated OHLCV format — the ``ohlc_hash`` produced by the same
loader the research drivers use, so a recorded artifact hash can be checked
against the data on disk without re-running the driver.

Run:
    python3 -m research.data_manifest            # verify against the manifest
    python3 -m research.data_manifest --write    # regenerate it

``--write`` is for a deliberate, explained data refresh. Routine use is the
bare form, which exits non-zero on any drift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

#: Where the OHLCV inputs live. Override with ``QH_DATA_DIR`` so the tree can
#: be relocated -- the four-package split moves this module without moving the
#: ~150 MB of broker exports beside it.
DATA_DIR = Path(
    os.environ.get("QH_DATA_DIR", Path(__file__).resolve().parent / "data")
).expanduser()

MANIFEST = Path(__file__).resolve().parent / "data_manifest.json"

# Files not in the house ``;``-separated OHLCV format get bytes-level pinning
# only; there is no ohlc_hash to reproduce for them.
NON_OHLCV = {"DFII10.csv"}

#: Tracked in git rather than merely hashed. The test is dependency, not size.
#: Broker OHLCV is not durably reproducible -- bars get revised, gaps
#: backfilled, and history retention is finite -- so a hashed-only file cannot
#: be restored once lost, and a parity claim resting on it becomes permanently
#: uncheckable rather than merely stale. These underpin T9a and the seq=31
#: artifact, so they must be recoverable, not merely verifiable.
TRACKED_IN_GIT = {"XAUUSD_H1.csv"}

#: Advisory ceiling for anything added from here on. GitHub warns above 50 MB
#: and hard-fails at 100 MB.
SIZE_POLICY_WARN_BYTES = 50 * 1024 * 1024

#: Grandfathered: already in history, deliberately not rewritten. Excising it
#: would mean rewriting the history of a repository whose premise is that
#: records are appended and never altered, and would break the X21 git
#: cross-check for every commit before the rewrite. Documented exception, not
#: a precedent.
GRANDFATHERED = {
    "quant_harness cb48e00:qhf/data/raw/XAUUSD_M5.csv": {
        "size_bytes_approx": 74_361_143,
        "reason": "committed before the policy existed; history not rewritten",
    },
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_ohlcv(path: Path) -> pd.DataFrame:
    """House loader — byte-identical in behaviour to the one the research
    drivers use, so ``ohlc_hash`` values are comparable to logged artifacts."""
    df = pd.read_csv(
        path, sep=";", header=0,
        names=["datetime", "open", "high", "low", "close", "volume"],
        parse_dates=["datetime"], date_format="%Y.%m.%d %H:%M",
    )
    df = df.set_index("datetime").sort_index()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df[["open", "high", "low", "close"]].astype(float)


def describe_ohlcv(path: Path) -> dict:
    df = load_ohlcv(path)
    return {
        "n_bars": int(len(df)),
        "first_bar_utc": str(df.index[0]),
        "last_bar_utc": str(df.index[-1]),
        "ohlc_hash_sha16": hashlib.sha256(
            df.to_csv().encode("utf-8")
        ).hexdigest()[:16],
    }


def describe_raw(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        lines = sum(1 for _ in fh)
    return {"n_lines_incl_header": lines}


def describe(path: Path) -> dict:
    entry = {
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "tracked_in_git": path.name in TRACKED_IN_GIT,
    }
    if path.name in NON_OHLCV:
        entry["format"] = "non_ohlcv"
        entry.update(describe_raw(path))
    else:
        entry["format"] = "house_semicolon_ohlcv"
        entry.update(describe_ohlcv(path))
    return entry


def build() -> dict:
    files = sorted(p for p in DATA_DIR.glob("*.csv") if p.is_file())
    if not files:
        raise SystemExit(f"no CSVs under {DATA_DIR}")
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": "research/data_manifest.py",
        "data_dir": str(DATA_DIR),
        "data_dir_env_override": "QH_DATA_DIR",
        "policy": {
            "default": "gitignored; pinned here, not stored in git",
            "tracked_in_git": sorted(TRACKED_IN_GIT),
            "tracked_because": "not durably reproducible from the broker, and "
                               "T9a/seq=31 depend on it -- must be "
                               "recoverable, not merely verifiable",
            "size_warn_bytes": SIZE_POLICY_WARN_BYTES,
            "grandfathered": GRANDFATHERED,
            "off_disk_archive_required": True,
            "off_disk_archive_note": "A checksum on a file that exists in "
                                     "exactly one place is a detection "
                                     "mechanism with nothing behind it. "
                                     "Untracked bulk series need their own "
                                     "off-disk archive; this manifest detects "
                                     "divergence but cannot restore.",
        },
        "note": "Most of research/data/ is not tracked. This manifest pins its "
                "contents so a silent data change cannot be mistaken for a "
                "code regression.",
        "files": {p.name: describe(p) for p in files},
    }


def compare(old: dict, new: dict) -> list[str]:
    drifts: list[str] = []
    o, n = old["files"], new["files"]
    for name in sorted(set(o) - set(n)):
        drifts.append(f"{name}: MISSING from disk")
    for name in sorted(set(n) - set(o)):
        drifts.append(f"{name}: NEW, not in manifest")
    for name in sorted(set(o) & set(n)):
        for key in ("sha256", "n_bars", "ohlc_hash_sha16",
                    "first_bar_utc", "last_bar_utc", "n_lines_incl_header"):
            if key in o[name] and o[name][key] != n[name].get(key):
                drifts.append(
                    f"{name}.{key}: {o[name][key]!r} -> {n[name].get(key)!r}"
                )
    return drifts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true",
                    help="regenerate the manifest instead of verifying")
    args = ap.parse_args()

    new = build()

    if args.write:
        MANIFEST.write_text(json.dumps(new, indent=2, sort_keys=False) + "\n")
        print(f"wrote {MANIFEST} ({len(new['files'])} files)")
        return 0

    if not MANIFEST.exists():
        print(f"no manifest at {MANIFEST}; run with --write", file=sys.stderr)
        return 2

    drifts = compare(json.loads(MANIFEST.read_text()), new)
    if drifts:
        print("DATA DRIFT", file=sys.stderr)
        for d in drifts:
            print(f"  {d}", file=sys.stderr)
        return 1
    print(f"data manifest ok ({len(new['files'])} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
