"""research.post.sweeps.data — OHLCV loading + timeframe helpers for the sweep."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from pytz.exceptions import AmbiguousTimeError as pytz_AmbiguousTimeError

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "research" / "data"

# Broker-history holes documented in qhf.engines.btpy_runner.
KNOWN_GAPS = [("2025-09-12", "2025-10-15"), ("2026-01-13", "2026-01-22")]

TIMEFRAMES = {
    "M5":  {"file": "XAUUSD_M5.csv",  "bias": ["H1", "H4", "D1"]},
    "M15": {"file": "XAUUSD_M15.csv", "bias": ["H4", "D1"]},
    "H1":  {"file": "XAUUSD_H1.csv",  "bias": ["H4", "D1"]},
    "H4":  {"file": "XAUUSD_H4.csv",  "bias": ["D1", "W1"]},
    "D1":  {"file": "XAUUSD_D1.csv",  "bias": ["W1"]},
}

RESAMPLE_RULE = {"H1": "1h", "H4": "4h", "D1": "1D", "W1": "7D"}


# ---------------------------------------------------------------------------
# TIMEZONE. Read this before doing anything session-dependent.
#
# The CSVs are MetaTrader terminal exports and their timestamps are in BROKER
# SERVER TIME, not UTC. Pepperstone runs the MetaQuotes EET/EEST convention:
# UTC+2 in winter, UTC+3 in summer. Calibrated empirically rather than assumed
# -- mean volume by hour peaks at index hour 16 in summer and 16/17 in winter,
# against a true NY cash open of 13:30 UTC (summer) and 14:30 UTC (winter).
# Corroborating: there are no Sunday bars and the week opens at a CONSTANT hour
# 1 in every month, which is a broker-session clock rather than UTC; and hour 0
# is nearly empty because it is the daily rollover break.
#
# Two modes, and the wrong one is the default ON PURPOSE:
#
#   "legacy_utc"  Stamp the naive server-time timestamps as UTC without
#                 shifting them. This is WRONG by 2-3 hours, DST-dependent.
#                 It is the default because research log seq 39-46 were all
#                 produced through it. Those runs are 24/7 with no session
#                 filter, so a relabel cannot change a single indicator, trade
#                 or Sharpe -- bar order and spacing are untouched. Keeping it
#                 keeps them reproducible.
#
#   "server_eet"  Localise to Europe/Athens (EET/EEST, DST-aware) and convert
#                 to true UTC. Use this for ANYTHING session-dependent.
#
# Anything that filters by hour-of-day MUST pass tz="server_eet". Using the
# default would shift a "22:00-05:00 GMT" window to roughly 19:00-02:00 GMT
# and silently test a different session.
# ---------------------------------------------------------------------------
SERVER_TZ = "Europe/Athens"


def _apply_tz(idx: pd.DatetimeIndex, tz: str) -> pd.DatetimeIndex:
    if idx.tz is not None:
        return idx.tz_convert("UTC")
    if tz == "legacy_utc":
        return idx.tz_localize("UTC")
    if tz != "server_eet":
        raise ValueError(f"tz must be 'legacy_utc' or 'server_eet', got {tz!r}")
    # The autumn DST rollback repeats an hour, so those stamps are ambiguous.
    # "infer" resolves them from monotonic order where it can; if the repeated
    # hour is missing from the export it cannot, and we fall back to standard
    # time for the ambiguous stamps rather than dropping bars.
    try:
        out = idx.tz_localize(SERVER_TZ, ambiguous="infer",
                              nonexistent="shift_forward")
    except (pytz_AmbiguousTimeError, ValueError):
        out = idx.tz_localize(SERVER_TZ, ambiguous=False,
                              nonexistent="shift_forward")
    return out.tz_convert("UTC")


def load(tf: str, start: str | None = None, end: str | None = None,
         tz: str = "legacy_utc", with_volume: bool = False,
         symbol: str = "XAUUSD") -> pd.DataFrame:
    """Load OHLCV for `symbol` at timeframe `tf`.

    `symbol` defaults to XAUUSD so every existing caller is unchanged; the
    TIMEFRAMES table's filenames are exactly f"{symbol}_{tf}.csv" for it. Pass
    another symbol for cross-instrument work -- note that the timezone
    reasoning below was calibrated on the XAUUSD export and the EET/EEST
    convention is broker-wide, so it carries, but KNOWN_GAPS are XAUUSD's and
    do not.
    """
    path = DATA_DIR / f"{symbol}_{tf}.csv"
    df = pd.read_csv(
        path, sep=";", header=0,
        names=["datetime", "open", "high", "low", "close", "volume"],
        parse_dates=["datetime"], date_format="%Y.%m.%d %H:%M",
    ).set_index("datetime").sort_index()
    df.index = _apply_tz(df.index, tz)
    cols = ["open", "high", "low", "close"] + (["volume"] if with_volume else [])
    df = df[cols].astype(float)
    if start:
        df = df.loc[df.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        df = df.loc[df.index <= pd.Timestamp(end, tz="UTC")]
    return df
