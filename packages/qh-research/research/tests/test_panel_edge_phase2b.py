"""Phase 2b panel — GER40 on the same terms as the FX majors and metals.

Four things are pinned here:

* H4 resampling on a calendar with a nightly close neither invents bars nor
  merges across a closure. There is no native GER40 H4 to compare against, so
  this is structural; the exact-match check lives on XAUUSD
  (``test_panel_edge_resampling.py``).
* The panel mask flags closures (weekends and whole days missing) but not
  session breaks, and leaves room for the 55-bar Donchian (the mask
  starvation law).
* The mask-off path still reproduces seq=109 instrument for instrument.
* The Phase 2b verdict rule and its pre-registration.

Tests that need out-of-repo data skip when it is absent.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from resources.data.mask import MaskReason
from research.pre import panel_edge as pe
from research.pre.signals.flood_tide import FloodTideParams

DATA = Path(os.environ.get(
    "QH_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
LOG = Path(__file__).resolve().parents[1] / "log" / "entries.jsonl"


def _have(*symbols: str) -> bool:
    return all((DATA / f"{s}_H1.csv").exists() for s in symbols)


def _load(symbol: str) -> pd.DataFrame:
    from research import admission
    from research.pre.scripts.run_flood_tide_edge import load_ohlcv
    h1 = load_ohlcv(DATA / f"{symbol}_H1.csv")
    return h1[h1.index >= admission.require(symbol, "H1", DATA)]


def _calendar(*days: tuple[str, int, int]) -> pd.DatetimeIndex:
    """H1 bars for (date, first_hour, last_hour) sessions."""
    parts = [pd.date_range(f"{d} {a:02d}:00", f"{d} {b:02d}:00", freq="h",
                           tz="UTC") for d, a, b in days]
    out = parts[0]
    for p in parts[1:]:
        out = out.append(p)
    return out


def _frame(index: pd.DatetimeIndex) -> pd.DataFrame:
    x = np.linspace(100, 110, len(index))
    return pd.DataFrame({"open": x, "high": x + 1, "low": x - 1, "close": x},
                        index=index)


# -- H4 resampling on an exchange calendar ----------------------------------

def test_h4_does_not_merge_across_a_nightly_close():
    """Session 02:00-22:00 (GER40 since 2024). The 20:00 bin holds 20-22, the
    00:00 bin holds 02-03; neither reaches across the close."""
    idx = _calendar(("2024-06-03", 2, 22), ("2024-06-04", 2, 22))
    s = pe.h4_structure(_frame(idx))
    assert s["empty_bins_emitted"] == 0
    assert s["bins_spanning_more_than_width"] == 0
    assert s["max_member_span_hours"] <= 3.0
    r = pe.resample_h4(_frame(idx))
    assert list(r.index.hour[:6]) == [0, 4, 8, 12, 16, 20]
    first_bin = _frame(idx).loc[r.index[0]:r.index[0] + pd.Timedelta("3h")]
    assert len(first_bin) == 2                      # 02:00 and 03:00 only


def test_h4_reports_a_session_break_that_falls_inside_a_bin():
    """A close at 21:00 reopening 23:00 leaves a gap inside the 20:00 bin.
    That is counted rather than hidden."""
    idx = _calendar(("2024-06-03", 16, 21), ("2024-06-03", 23, 23))
    s = pe.h4_structure(_frame(idx))
    assert s["bins_straddling_a_session_break"] == 1
    assert s["bins_spanning_more_than_width"] == 0


def test_h4_emits_no_bar_for_a_holiday():
    idx = _calendar(("2024-12-23", 2, 22), ("2024-12-27", 2, 22))
    r = pe.resample_h4(_frame(idx))
    assert not (r.index.normalize() == pd.Timestamp("2024-12-25", tz="UTC")).any()
    assert pe.h4_structure(_frame(idx))["empty_bins_emitted"] == 0


@pytest.mark.skipif(not _have("GER40"), reason="GER40_H1.csv not present")
def test_ger40_h4_is_structurally_sound():
    """Measured 2026-10-11 on the admitted range (from 2018-07-13). GER40's
    nightly closes all fall on 4h bin edges, so no bin straddles one."""
    s = pe.h4_structure(_load("GER40"))
    assert s["h1_bars"] == 45_316
    assert s["empty_bins_emitted"] == 0
    assert s["bins_spanning_more_than_width"] == 0
    assert s["bins_straddling_a_session_break"] == 0
    assert s["h4_bars"] == 12_224
    # Six bins on a full day, four on the 2018-19 09:00-22:00 session.
    assert set(s["h4_bars_per_day"]) <= {3, 4, 5, 6}


# -- the mask ---------------------------------------------------------------

def test_panel_mask_flags_closures_but_not_session_breaks():
    idx = _calendar(
        ("2024-12-19", 2, 22),       # Thu
        ("2024-12-20", 2, 22),       # Fri  (nightly close before: not flagged)
        ("2024-12-23", 2, 22),       # Mon  (weekend before: flagged)
        ("2024-12-27", 2, 22),       # Fri  (Christmas closure, 76h: flagged)
        ("2024-12-30", 2, 22),       # Mon
        ("2024-12-31", 2, 14),       # Tue  early close
        ("2025-01-02", 2, 22),       # Thu  (New Year, 36h: HOLIDAY only)
    )
    m = pe.build_panel_mask(idx)
    after_gap = idx.to_series().diff().dt.total_seconds().div(3600).fillna(0)
    flagged = ~m.tradable
    assert not flagged[after_gap.between(1.5, 11)].any()
    assert flagged[after_gap > 24].all()
    ny = idx[idx.normalize() == pd.Timestamp("2025-01-02", tz="UTC")][0]
    assert m.reason(MaskReason.HOLIDAY)[ny]
    assert not m.reason(MaskReason.WEEKEND_GAP)[ny]
    assert m.attribution_exclusive()["holiday"] == 1


@pytest.mark.skipif(not _have("GER40", "XAUUSD"),
                    reason="GER40 and XAUUSD H1 not both present")
def test_the_panel_mask_leaves_room_for_the_donchian_and_session_flags_would_not():
    """The mask starvation law, checked on the two instruments with a daily
    close. Under the panel mask the median clean run is a trading week, well
    over the 55-bar Donchian. Flagging every session break instead would cap
    it at one session and R3 would NaN the channel almost everywhere."""
    lookback = FloodTideParams().entry_len
    for sym in ("GER40", "XAUUSD"):
        idx = _load(sym).index
        clean = (~pe.build_panel_mask(idx).tradable).cumsum().value_counts()
        assert clean.median() > 2 * lookback, sym
        session = idx.to_series().diff() > pd.Timedelta("1h")
        assert session.cumsum().value_counts().median() < lookback, sym


@pytest.mark.skipif(not _have("GER40"), reason="GER40_H1.csv not present")
def test_ger40_mask_attribution():
    """Measured 2026-10-11: 439 masked of 45,316. Five are mid-week closures
    the 40h weekend flag misses; every weekend is also a HOLIDAY gap."""
    s = pe.build_panel_mask(_load("GER40").index).summary()
    assert s["n_masked"] == 439
    assert s["attribution"] == {"holiday": 439, "weekend_gap": 434}
    assert s["attribution_exclusive"] == {"holiday": 5, "weekend_gap": 0}


def test_masked_atr_skips_the_masked_bar():
    idx = _calendar(("2024-06-06", 0, 23), ("2024-06-07", 0, 23),
                    ("2024-06-10", 0, 23))
    df = _frame(idx)
    m = pe.build_panel_mask(idx)
    atr = pe.masked_atr(df, m)
    masked = ~m.tradable.to_numpy()
    assert masked.sum() == 1
    assert np.isnan(atr[masked]).all()
    assert np.isfinite(atr[-10:]).all()


# -- seq=109 still reproduces -----------------------------------------------

def _seq(n: int) -> dict:
    for line in LOG.read_text().splitlines():
        e = json.loads(line)
        if e["seq"] == n:
            return e
    raise KeyError(n)


@pytest.mark.skipif(not _have(*pe.MAJORS), reason="FX majors H1 not present")
def test_mask_off_reproduces_seq_109_per_instrument():
    """The per-instrument outputs do not depend on the null, so one
    permutation is enough to compare them with what seq=109 logged."""
    logged = _seq(109)["metrics"]
    r = pe.check_panel(DATA, n_permutations=1)
    assert not r.masked
    for i in r.instruments:
        assert i.n_signals == logged["per_instrument_n_signals"][i.symbol]
        assert ({str(h): v for h, v in i.e_ratio.items()}
                == logged["per_instrument_e_ratio"][i.symbol]), i.symbol


# -- verdict rule -----------------------------------------------------------

def _inst(sym: str, e: float, n: int = 100) -> pe.InstrumentEdge:
    return pe.InstrumentEdge(
        symbol=sym, n_bars=1000, start="", end="", n_signals=n,
        e_ratio={h: e for h in pe.HORIZONS}, sum_mfe={}, sum_mae={},
        eligible_bars=500, structure=pe.STRUCTURE[sym])


def _report(insts, p: float) -> pe.PanelEdgeReport:
    return pe.PanelEdgeReport(
        instruments=insts, pooled_p_value={h: p for h in pe.HORIZONS},
        symbols=tuple(i.symbol for i in insts))


def test_verdict_dead_everywhere():
    insts = [_inst("EURUSD", 0.95), _inst("XAUUSD", 1.0), _inst("GER40", 0.9)]
    v = pe.phase2b_verdict(_report(insts, 0.6), _report(insts, 0.6))
    assert v["verdict"] == "DEAD_EVERYWHERE"


def test_verdict_dead_on_average_when_one_instrument_clears_the_gate():
    insts = [_inst("EURUSD", 0.95), _inst("XAUUSD", 1.2), _inst("GER40", 0.9)]
    v = pe.phase2b_verdict(_report(insts, 0.6), _report(insts, 0.6))
    assert v["verdict"] == "DEAD_ON_AVERAGE"
    assert v["alive_anywhere"] == ["XAUUSD"]


def test_verdict_untested_structure_when_ger40_cannot_decide():
    insts = [_inst("EURUSD", 0.95), _inst("XAUUSD", 1.0),
             _inst("GER40", 0.9, n=12)]
    v = pe.phase2b_verdict(_report(insts, 0.6), _report(insts, 0.6))
    assert v["verdict"] == "UNTESTED_STRUCTURE"
    assert v["untested_structures"] == ["equity_index"]


def test_verdict_is_decided_by_the_mask_on_stream_only():
    insts = [_inst("EURUSD", 0.95), _inst("XAUUSD", 1.0), _inst("GER40", 0.9)]
    alive_off = pe.phase2b_verdict(_report(insts, 0.6), _report(insts, 0.001))
    assert alive_off["verdict"] == "DEAD_EVERYWHERE"
    alive_on = pe.phase2b_verdict(_report(insts, 0.04), _report(insts, 0.6))
    assert alive_on["verdict"] == "ALIVE_POOLED"


def test_preregistration_names_the_decisive_stream_and_is_not_a_trial(tmp_path):
    from research import log as research_log
    e = pe.preregister_phase2b(log_dir=tmp_path)
    assert e.counts_as_trial is False
    assert e.metrics["decisive_stream"] == "pooled_p_min"
    assert e.metrics["decisive_threshold"] == 0.05
    assert e.metrics["panel"] == list(pe.PANEL_2B)
    assert research_log.trial_count(tmp_path) == 0
