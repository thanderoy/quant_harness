"""T9b mask-on — what the tradability mask does to the `crest_n_keel` folds.

The T9a half of criterion 3 asks for the E-Ratio divergence to be split into
channels. This half asks for something narrower and stricter: **every
differing trade traced to a named mask flag.** A trade is a discrete event, so
there is no decomposition to do — either each difference has a name or the
criterion is not met.

Three kinds of difference exist, and collapsing them would lose the part that
matters:

``lost``
    An entry that no longer fires, because the mask NaN'd an indicator the
    signal depended on.
``gained``
    An entry that now fires and did not before.
``diverged``
    Same entry bar, different exit — the trade survived but its bracket moved,
    because the ATR that sizes the stop changed when masked bars stopped
    feeding the accumulator. These are invisible in a trade count and are
    exactly the ones a "number of trades" comparison would miss.

**The engine is not modified.** ``cnk_engine`` is the frozen generator behind
the T9b mask-off fixture, and changing its arithmetic would put that fixture's
provenance in question. It already takes the indicator arrays as arguments, so
the masked versions are computed here and passed in. The mask-off path through
this module calls the identical engine function with the identical inputs,
which is why the two are comparable at all.

**The starvation law, and why it does not bite here.** R3 NaNs a WINDOW
indicator whose lookback spans an untradable bar, so such an indicator dies
wherever its lookback exceeds the length of a clean run — the same law the
rollover flag exposed in T9a, stated at the timeframe level rather than the
flag level. Clean runs are one trading week, ~114 bars at H1 but only ~29 at
H4, so the margin narrows sharply as the timeframe coarsens: a 55-bar HMA is
comfortable at H1 and impossible at H4.

It happens not to bite in this run, because the fixed arm's longest lookback
is 61 bars at H1 and 16 at H4, both inside their clean runs. That is the luck
of one frozen config, not a property of the strategy, which is why
``clean_run_median`` and ``max_lookback`` are reported per timeframe on every
run: the margin is the thing to watch and it is one parameter change from
gone. ``annihilated`` names any timeframe where it has closed.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from resources.data.mask import MaskReason

from research.parity.t9a_mask_on import build_mask
from research.parity.t9b_crest_n_keel import (
    HYPOTHESIS_ID,
    SEQ,
    TIMEFRAMES,
    _arms,
    _config_of,
    load_fixture,
    recompute,
)

__all__ = ["FLAGS_APPLIED", "MaskOnTradeReport", "check_mask_on", "log_mask_on"]

#: Weekend only. The rollover flag was shown at seq=103 to annihilate any
#: window longer than a day, which would make every timeframe here empty and
#: the comparison contentless. Restricting to the flag the spec actually
#: anticipates ("weekend and holiday boundaries") keeps the result readable;
#: the rollover finding is recorded there rather than re-derived here.
FLAGS_APPLIED = (MaskReason.WEEKEND_GAP,)


def _contaminated(tradable: np.ndarray, window: int) -> np.ndarray:
    """True where a lookback of ``window`` bars ending here spans a masked bar."""
    untradable = (~tradable).astype(float)
    csum = np.concatenate([[0.0], np.cumsum(untradable)])
    out = np.ones(len(tradable), dtype=bool)
    idx = np.arange(len(tradable))
    start = np.maximum(0, idx - window + 1)
    out = (csum[idx + 1] - csum[start]) > 0
    return out


def masked_hma(engine, close: np.ndarray, period: int,
               tradable: np.ndarray) -> np.ndarray:
    """HMA as a WINDOW indicator under R3.

    The lookback is the composed one: ``wma(period)`` feeds a further
    ``wma(round(sqrt(period)))``, so a value at bar t depends on roughly
    ``period + round(sqrt(period)) - 1`` bars. Using the composed span rather
    than ``period`` matters — the shorter one would let a contaminated bar
    leak through the outer smoothing and call the result clean.
    """
    raw = engine.hma(close, period)
    span = period + int(round(math.sqrt(period))) - 1
    return np.where(_contaminated(tradable, span), np.nan, raw)


def masked_stochastic(engine, high, low, close, k_period, d_period, smooth,
                      tradable: np.ndarray):
    k, d = engine.stochastic(high, low, close, k_period, d_period, smooth)
    span = k_period + smooth + d_period - 2
    bad = _contaminated(tradable, span)
    return np.where(bad, np.nan, k), np.where(bad, np.nan, d)


def masked_atr(engine, high, low, close, period: int,
               tradable: np.ndarray) -> np.ndarray:
    """ATR as an ACCUMULATOR under R3.

    Masked bars are dropped and the Wilder recursion runs on what remains, so
    its state advances across the gap instead of being destroyed by it. The
    result is placed back on the calendar with the masked bars left NaN: a
    forward fill would hand the sizer a volatility reading taken from bars the
    trade was not allowed to see.
    """
    out = np.full(len(close), np.nan)
    if tradable.sum() == 0:
        return out
    kept = engine.atr(high[tradable], low[tradable], close[tradable], period)
    out[tradable] = kept
    return out


@dataclass
class TimeframeResult:
    timeframe: str
    n_trades_off: int
    n_trades_on: int
    lost: list[str]
    gained: list[str]
    diverged: list[str]
    attribution: dict[str, int]
    unattributed: list[str]
    annihilated: bool = False
    clean_run_median: int = 0
    max_lookback: int = 0

    @property
    def fully_attributed(self) -> bool:
        return not self.unattributed


@dataclass
class MaskOnTradeReport:
    timeframes: list[TimeframeResult] = field(default_factory=list)

    @property
    def fully_attributed(self) -> bool:
        return all(t.fully_attributed for t in self.timeframes)

    def as_dict(self) -> dict:
        return {
            "hypothesis_id": HYPOTHESIS_ID,
            "seq": SEQ,
            "mode": "mask_on",
            "flags_applied": [f.value for f in FLAGS_APPLIED],
            "fully_attributed": self.fully_attributed,
            "timeframes": [
                {
                    "timeframe": t.timeframe,
                    "n_trades_off": t.n_trades_off,
                    "n_trades_on": t.n_trades_on,
                    "n_lost": len(t.lost),
                    "n_gained": len(t.gained),
                    "n_diverged": len(t.diverged),
                    "attribution": t.attribution,
                    "unattributed": t.unattributed,
                    "annihilated": t.annihilated,
                    "clean_run_median": t.clean_run_median,
                    "max_lookback": t.max_lookback,
                }
                for t in self.timeframes
            ],
        }


def _clean_runs(tradable: np.ndarray) -> np.ndarray:
    runs, cur = [], 0
    for ok in tradable:
        if ok:
            cur += 1
        else:
            if cur:
                runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    return np.array(runs) if runs else np.array([0])


def _simulate_with(state, bars, cfg, tradable: Optional[np.ndarray]):
    """``_simulate`` from the mask-off module, with the indicators swapped.

    Kept structurally identical to it on purpose: the only difference between
    the mask-off and mask-on runs must be the indicator arrays, never the
    engine call or its parameters.
    """
    engine, sweep = state["engine"], state["sweep"]
    if tradable is None:
        hma_v = engine.hma(bars.close, cfg["hma"])
        atr_v = engine.atr(bars.high, bars.low, bars.close, cfg["atr"])
    else:
        hma_v = masked_hma(engine, bars.close, cfg["hma"], tradable)
        atr_v = masked_atr(engine, bars.high, bars.low, bars.close,
                           cfg["atr"], tradable)

    if cfg["mode"] == "pullback":
        if tradable is None:
            k, d = engine.stochastic(bars.high, bars.low, bars.close,
                                     cfg["stoch_k"], sweep.STOCH_D,
                                     sweep.STOCH_SMOOTH)
        else:
            k, d = masked_stochastic(engine, bars.high, bars.low, bars.close,
                                     cfg["stoch_k"], sweep.STOCH_D,
                                     sweep.STOCH_SMOOTH, tradable)
        long_sig, short_sig = engine.pullback_signals(
            bars, hma_v, k, d, cfg["zone"][0], cfg["zone"][1])
    else:
        long_sig, short_sig = engine.momentum_signals(bars, hma_v)

    direction = cfg["direction"]
    sim = engine.simulate(
        bars, cfg["mode"], hma_v, atr_v, long_sig, short_sig,
        enable_long=direction in ("both", "long"),
        enable_short=direction in ("both", "short"),
        sl_mult=cfg["sl"], tp_mult=cfg["tp"], trail_mult=cfg["trail"],
        risk_pct=sweep.RISK_PCT, min_atr=cfg["min_atr"], max_dd_halt=1.0,
        record_trades=True)
    return sim, {"hma": hma_v, "atr": atr_v}


def _max_lookback(cfg: dict) -> int:
    span = cfg["hma"] + int(round(math.sqrt(cfg["hma"]))) - 1
    return max(span, cfg["atr"], cfg.get("stoch_k") or 0)


def check_mask_on(fixture: Optional[dict] = None) -> MaskOnTradeReport:
    """Run the fixed arm of every fold with and without the mask.

    Only the ``fixed`` arm is used. The ``selected`` arm's config was chosen
    per fold by a training-window search, and re-running that search under the
    mask would confound two changes — different parameters AND different
    indicator values — in one comparison. The fixed arm holds the config
    constant, so every difference in its trades is the mask.

    Indicators are computed on the test slice, matching what the frozen
    mask-off run does. That inherits seq=67's warm-up caveat, and inheriting
    it is the point: the two runs must differ in the mask alone.
    """
    fixture = fixture or load_fixture()
    state_all = recompute()
    report = MaskOnTradeReport()

    for tf in TIMEFRAMES:
        state = state_all[tf]
        lost: list[str] = []
        gained: list[str] = []
        diverged: list[str] = []
        n_off = n_on = 0
        max_lb = 0
        runs_all: list[int] = []
        counts: dict[str, int] = {WINDOW_CAUSE: 0, ACCUMULATOR_CAUSE: 0}
        unattributed: list[str] = []

        for fold_fx, fold_rc in zip(fixture["folds"][tf], state["folds"]):
            bars = fold_rc["bars"]
            mask = build_mask(bars.index, FLAGS_APPLIED)
            tradable = mask.tradable.to_numpy()
            runs_all.extend(_clean_runs(tradable).tolist())

            for name, arm in _arms(fold_fx):
                if name != "fixed":
                    continue
                cfg = _config_of(arm)
                max_lb = max(max_lb, _max_lookback(cfg))
                off, off_ind = _simulate_with(state, bars, cfg, None)
                on, on_ind = _simulate_with(state, bars, cfg, tradable)

                by_off = {r["entry_ts"]: r for r in off["records"]}
                by_on = {r["entry_ts"]: r for r in on["records"]}
                n_off += len(by_off)
                n_on += len(by_on)

                changed: list = []
                for t in by_off.keys() - by_on.keys():
                    lost.append(str(t)); changed.append((t, None))
                for t in by_on.keys() - by_off.keys():
                    gained.append(str(t)); changed.append((t, None))
                for ts in by_off.keys() & by_on.keys():
                    a, b = by_off[ts], by_on[ts]
                    if (a["exit_ts"] != b["exit_ts"]
                            or a["exit_px"] != b["exit_px"]
                            or a["lots"] != b["lots"]):
                        diverged.append(str(ts))
                        # A diverged trade kept its entry and moved its exit,
                        # so the bar that moved it can be anywhere in the
                        # holding period — the trailing stop reads every bar.
                        changed.append((ts, max(a["exit_ts"], b["exit_ts"])))

                _attribute_fold(changed, bars.index, tradable,
                                _max_lookback(cfg),
                                off_ind, on_ind, counts, unattributed)

        runs = np.array(runs_all) if runs_all else np.array([0])
        report.timeframes.append(TimeframeResult(
            timeframe=tf, n_trades_off=n_off, n_trades_on=n_on,
            lost=sorted(lost), gained=sorted(gained),
            diverged=sorted(diverged), attribution=counts,
            unattributed=unattributed,
            annihilated=(n_on == 0 and n_off > 0),
            clean_run_median=int(np.median(runs)), max_lookback=max_lb))

    return report


#: The two mechanisms by which the mask can move a trade. Both trace to the
#: same flag, but through different routes, and telling them apart is the
#: difference between "the signal vanished" and "the signal survived and its
#: stop moved".
WINDOW_CAUSE = "weekend_gap:window_contamination"
ACCUMULATOR_CAUSE = "weekend_gap:atr_accumulator_shift"


def _attribute_fold(changed, index, tradable, lookback, off_ind, on_ind,
                    counts: dict[str, int], unattributed: list[str]) -> None:
    """Trace each differing trade to the mechanism that moved it.

    Attribution is against the indicator arrays actually fed to the engine,
    not against a guess from the bar index, because the two mechanisms have
    completely different reach:

    WINDOW
        An HMA or Stochastic value is NaN because its lookback spanned a
        masked bar. Local — it can only affect bars within one lookback.
    ACCUMULATOR
        The Wilder ATR ran on the compacted series, so from the first masked
        bar onward *every* later value differs. Unbounded reach, which is why
        a windowed rule left most diverged trades unexplained: their cause is
        genuinely hundreds of bars behind them.

    A trade with neither is unattributed, and that is the finding.
    """
    pos_of = {ts: i for i, ts in enumerate(index)}
    for ts, until in changed:
        t = pos_of.get(pd.Timestamp(ts))
        if t is None:
            unattributed.append(str(ts))
            continue
        # A lost or gained trade is decided at its entry bar. A diverged one
        # is decided anywhere up to its exit, because the trailing stop reads
        # each bar as it goes, so the span runs to whichever exit is later.
        end = t if until is None else pos_of.get(pd.Timestamp(until), t)
        sl = slice(t, max(t, end) + 1)
        a, b = off_ind["hma"], on_ind["hma"]
        window_hit = bool(
            (np.isnan(b[sl]) & ~np.isnan(a[sl])).any()
            or (~tradable[max(0, t - lookback):max(t, end) + 1]).any())
        x, y = off_ind["atr"], on_ind["atr"]
        both = np.isfinite(x[sl]) & np.isfinite(y[sl])
        accum_hit = bool(
            (np.isnan(y[sl]) != np.isnan(x[sl])).any()
            or (both & (x[sl] != y[sl])).any())
        if window_hit:
            counts[WINDOW_CAUSE] += 1
        elif accum_hit:
            counts[ACCUMULATOR_CAUSE] += 1
        else:
            unattributed.append(str(ts))


def log_mask_on(report: MaskOnTradeReport, log_dir: Optional[Path] = None):
    from research import log as research_log

    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    annihilated = [t.timeframe for t in report.timeframes if t.annihilated]
    return research_log.append_record(
        research_log.EventType.PARITY_FIXTURE,
        record_id=f"record:t9b-{HYPOTHESIS_ID}-mask-on",
        title=f"T9b mask-on trade divergence, attributed — {HYPOTHESIS_ID} seq={SEQ}",
        note=(
            "Mask-on run of the seq=49 walk-forward's selection-independent "
            "arm. Differences are split into lost, gained and diverged "
            "(same entry, moved exit) and each is traced to a named "
            "MaskReason. "
            f"Timeframes annihilated by window starvation: {annihilated or 'none'}. "
            "Not a trial: a known behaviour change is being measured and the "
            "crest_n_keel verdict is not reopened."
        ),
        metrics={
            "mode": "mask_on",
            "flags_applied": [f.value for f in FLAGS_APPLIED],
            "fully_attributed": report.fully_attributed,
            "annihilated_timeframes": annihilated,
            **{f"{t.timeframe}_n_trades_off": t.n_trades_off
               for t in report.timeframes},
            **{f"{t.timeframe}_n_trades_on": t.n_trades_on
               for t in report.timeframes},
            **{f"{t.timeframe}_n_diverged": len(t.diverged)
               for t in report.timeframes},
            **{f"{t.timeframe}_clean_run_median": t.clean_run_median
               for t in report.timeframes},
            **{f"{t.timeframe}_max_lookback": t.max_lookback
               for t in report.timeframes},
        },
        **kwargs,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args()

    report = check_mask_on()
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(f"T9b mask-on — flags {[f.value for f in FLAGS_APPLIED]}")
        for t in report.timeframes:
            tag = "  ANNIHILATED" if t.annihilated else ""
            print(f"  {t.timeframe}: trades {t.n_trades_off} -> "
                  f"{t.n_trades_on}{tag}")
            print(f"      lost {len(t.lost)} gained {len(t.gained)} "
                  f"diverged {len(t.diverged)} unattributed "
                  f"{len(t.unattributed)}")
            print(f"      clean-run median {t.clean_run_median} bars vs "
                  f"max lookback {t.max_lookback}")
    if args.log:
        entry = log_mask_on(report)
        print(f"logged seq={entry.seq}")
    return 0 if report.fully_attributed else 1


if __name__ == "__main__":
    raise SystemExit(main())
