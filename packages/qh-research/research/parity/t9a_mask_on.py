"""T9a mask-on — what the tradability mask does to the `flood_tide_h1` edge.

Mask-off parity (``t9a_flood_tide``) asks whether the rewrite reproduces
seq=31. This asks the opposite question: the mask is *supposed* to change the
answer, so what exactly does it change, and can every part of the change be
named?

The spec (REWRITE.md §T9a) requires the difference to be split into two
channels that are reported separately, and the reason is that they are not
comparable quantities. One is about *which signals exist*; the other is about
*what the E-Ratio divides by*. A single "mask-on E-Ratio moved by X" number
mixes them, and a reader cannot tell whether the entry got better or the
denominator got smaller.

The decomposition is additive and exact, by construction::

    E0 = E(S_off,      ATR_off)     the seq=31 value
    E1 = E(S_retained, ATR_off)     - signals the mask removed
    E2 = E(S_retained, ATR_on)      - normaliser changed
    E3 = E(S_on,       ATR_on)      + signals the mask added

    total = E3 - E0 = (E1-E0) + (E2-E1) + (E3-E2)
            ^^^^^^^   ^^^^^^^^^^^^^^^   ^^^^^^^
            removals    normaliser      additions

``E2 - E1`` is the normaliser channel the spec asks for, measured on the
intersection of retained signals exactly as it specifies: same signals, two
ATRs, so nothing but the denominator differs. The other two terms are the
signal-set channel, kept apart from each other because a lost signal and a
gained one are different events with different causes.

**Attribution is the load-bearing part.** Criterion 3 does not ask for the
divergence to be measured, it asks for it to be *attributed* — every changed
signal traced to a named ``MaskReason``. So every lost and gained signal is
walked back to the mask flags on the bars responsible, and any signal that
cannot be traced to one lands in ``unattributed``. That bucket must be empty.
A non-empty one does not mean the mask is wrong; it means the change has a
cause this module cannot name, which is precisely the state criterion 3
exists to forbid.

This module recomputes rather than pins. There is no mask-on artifact to
reproduce — seq=31 predates the mask — so there is nothing to be parity
*against*, and a fixture here would only pin this module's own output. What
is asserted instead is the structure of the answer: the decomposition adds
up, and nothing is unattributed.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from resources.data.mask import MaskReason, TradabilityMask
from research.pre.signal_edge import signal_edge_report, wilder_atr
from research.pre.signals.flood_tide import FloodTideParams, generate_signals

from research.parity.t9a_flood_tide import (
    ATR_PERIOD,
    HORIZONS,
    HYPOTHESIS_ID,
    RANDOM_SEED,
    SEQ,
    default_data_paths,
    load_ohlcv,
    source_data_available,
)

__all__ = [
    "FLAGS_APPLIED",
    "MaskOnReport",
    "build_mask",
    "check_mask_on",
    "log_mask_on",
]

#: The flags this run applies, and the only ones a difference may be
#: attributed to. Both are derivable from the bar index alone, which matters:
#: the seq=31 history is 2004-2025 H1 gold and there is no contemporaneous
#: spread or tick-count series for it, so SPREAD_ABOVE_THRESHOLD and
#: INSUFFICIENT_TICKS cannot be evaluated honestly over that window and are
#: deliberately not flagged rather than flagged with invented data.
FLAGS_APPLIED = (MaskReason.WEEKEND_GAP, MaskReason.ROLLOVER_WINDOW)

#: A gap longer than this ends a trading week. 40h is the mask module's own
#: default and sits comfortably between the ~49h weekend and the longest
#: intraweek hole.
WEEKEND_GAP_HOURS = 40.0

#: Pepperstone rolls the day at 21:00 UTC (approximately — it shifts with DST,
#: which is why the window has width rather than being a single bar).
ROLLOVER_UTC_HOUR = 21
ROLLOVER_MINUTES = 15


def build_mask(index: pd.DatetimeIndex,
               flags: tuple[MaskReason, ...] = FLAGS_APPLIED
               ) -> TradabilityMask:
    """The mask this comparison runs under.

    Kept as one function so the mask-on result is reproducible from the index
    alone and cannot quietly acquire another flag between runs.
    """
    mask = TradabilityMask(index)
    if MaskReason.WEEKEND_GAP in flags:
        mask.flag_weekend_gap(max_gap_hours=WEEKEND_GAP_HOURS)
    if MaskReason.ROLLOVER_WINDOW in flags:
        mask.flag_rollover(utc_hour=ROLLOVER_UTC_HOUR,
                           minutes=ROLLOVER_MINUTES)
    return mask


@dataclass
class ChannelResult:
    """One horizon's decomposition. All four E-Ratios, so the arithmetic in
    the module docstring can be re-checked by a reader rather than trusted."""

    horizon: int
    e_off: float
    e_retained_old_atr: float
    e_retained_new_atr: float
    e_on: float

    @property
    def removals(self) -> float:
        return self.e_retained_old_atr - self.e_off

    @property
    def normaliser(self) -> float:
        return self.e_retained_new_atr - self.e_retained_old_atr

    @property
    def additions(self) -> float:
        return self.e_on - self.e_retained_new_atr

    @property
    def total(self) -> float:
        return self.e_on - self.e_off

    def adds_up(self, tol: float = 1e-12) -> bool:
        parts = self.removals + self.normaliser + self.additions
        return abs(parts - self.total) <= tol


@dataclass
class MaskOnReport:
    n_signals_off: int
    n_signals_on: int
    n_retained: int
    lost: list[str]
    gained: list[str]
    attribution_lost: dict[str, int]
    attribution_gained: dict[str, int]
    unattributed: list[str]
    masked_bar_counts: dict[str, int]
    flags: tuple[MaskReason, ...] = FLAGS_APPLIED
    channels: list[ChannelResult] = field(default_factory=list)

    @property
    def fully_attributed(self) -> bool:
        return not self.unattributed

    def as_dict(self) -> dict:
        return {
            "hypothesis_id": HYPOTHESIS_ID,
            "seq": SEQ,
            "mode": "mask_on",
            "flags_applied": [f.value for f in self.flags],
            "n_signals_off": self.n_signals_off,
            "n_signals_on": self.n_signals_on,
            "n_retained": self.n_retained,
            "n_lost": len(self.lost),
            "n_gained": len(self.gained),
            "attribution_lost": self.attribution_lost,
            "attribution_gained": self.attribution_gained,
            "unattributed": self.unattributed,
            "fully_attributed": self.fully_attributed,
            "masked_bar_counts": self.masked_bar_counts,
            "channels": [
                {**asdict(c), "removals": c.removals,
                 "normaliser": c.normaliser, "additions": c.additions,
                 "total": c.total}
                for c in self.channels
            ],
        }


def _signal_series(sig: pd.DataFrame, index: pd.DatetimeIndex) -> pd.Series:
    out = pd.Series(0, index=index, dtype=np.int64)
    out[sig["entry_signal"].to_numpy()] = 1
    return out


def _e_ratios(signal: pd.Series, ohlc: pd.DataFrame,
              atr: Optional[pd.Series]) -> dict[int, float]:
    """E-Ratios per horizon for one (signal set, normaliser) pair.

    ``n_permutations=1`` throughout: the permutation null is not part of this
    comparison and running it four times would only add cost and a seed to
    argue about.
    """
    report = signal_edge_report(
        signal=signal, ohlc=ohlc, forward_windows=list(HORIZONS),
        atr_period=ATR_PERIOD, n_permutations=1, random_seed=RANDOM_SEED,
        atr=atr,
    )
    return {int(r["window"]): float(r["e_ratio"])
            for _, r in report.per_window.iterrows()}


def _reasons_at(mask: TradabilityMask, positions: np.ndarray) -> set[str]:
    """Which named flags are set on any of ``positions``."""
    found: set[str] = set()
    for reason in FLAGS_APPLIED:
        flagged = mask.reason(reason).to_numpy()
        if positions.size and flagged[positions].any():
            found.add(reason.value)
    return found


#: Not a MaskReason — a *derived* cause. The re-entry cooldown couples signals
#: to each other, so removing one can un-suppress a later one that no mask flag
#: goes anywhere near. Such a signal is still traced to the mask, just
#: transitively, and calling that out separately keeps "attributed" from
#: quietly meaning two different things.
COOLDOWN_CAUSE = "reentry_cooldown_after_masked_signal"


def _attribute(timestamps: pd.DatetimeIndex, index: pd.DatetimeIndex,
               mask: TradabilityMask, window: int,
               primary_changed: Optional[pd.DatetimeIndex] = None,
               cooldown_bars: int = 0
               ) -> tuple[dict[str, int], list[str]]:
    """Trace each changed signal to the flags that could have caused it.

    A signal at bar ``t`` depends on the Donchian window ending at ``t-1`` and
    on bar ``t`` itself, so the bars that can explain a change are
    ``[t-window, t]``. A flag set anywhere in that span is a candidate cause;
    a signal with no flag anywhere in it is unattributed and is the finding.
    """
    counts: dict[str, int] = {f.value: 0 for f in FLAGS_APPLIED}
    counts[COOLDOWN_CAUSE] = 0
    unattributed: list[str] = []
    pos_of = {ts: i for i, ts in enumerate(index)}
    primary_pos = (np.array(sorted(pos_of[t] for t in primary_changed))
                   if primary_changed is not None and len(primary_changed)
                   else np.array([], dtype=int))

    for ts in timestamps:
        t = pos_of[ts]
        span = np.arange(max(0, t - window), t + 1)
        reasons = _reasons_at(mask, span)
        if reasons:
            for r in reasons:
                counts[r] += 1
            continue
        # No flag touches this signal's own window. The remaining legitimate
        # cause is the cooldown: a signal the mask removed stopped suppressing
        # this one. Only accept it when such a removal really is close enough
        # to have been the suppressor.
        if primary_pos.size and cooldown_bars:
            near = primary_pos[(primary_pos < t)
                               & (primary_pos >= t - cooldown_bars - window)]
            if near.size:
                counts[COOLDOWN_CAUSE] += 1
                continue
        unattributed.append(ts.isoformat())
    return counts, unattributed



def _attribute_coupled(lost: pd.DatetimeIndex, gained: pd.DatetimeIndex,
                       index: pd.DatetimeIndex, mask: TradabilityMask,
                       window: int, cooldown_bars: int):
    """Attribute both directions to a fixed point.

    Round 0 attributes every change a mask flag reaches directly. Each later
    round attributes any remaining change that sits downstream of one already
    explained, in either direction. The loop ends when a round explains
    nothing new, which is the point at which the leftovers genuinely have no
    traceable cause rather than merely an unvisited one.
    """
    pos_of = {ts: i for i, ts in enumerate(index)}
    lost_counts, lost_un = _attribute(lost, index, mask, window)
    gained_counts, gained_un = _attribute(gained, index, mask, window)

    explained = sorted(
        pos_of[t] for t in list(lost) + list(gained)
        if t.isoformat() not in set(lost_un) | set(gained_un))

    while True:
        before = len(lost_un) + len(gained_un)
        exp = np.array(explained, dtype=int)

        def resolve(pending: list[str], counts: dict[str, int]) -> list[str]:
            still: list[str] = []
            for iso in pending:
                t = pos_of[pd.Timestamp(iso)]
                near = exp[(exp < t) & (exp >= t - cooldown_bars - window)]
                if near.size:
                    counts[COOLDOWN_CAUSE] += 1
                    explained.append(t)
                else:
                    still.append(iso)
            return still

        lost_un = resolve(lost_un, lost_counts)
        gained_un = resolve(gained_un, gained_counts)
        explained.sort()
        if len(lost_un) + len(gained_un) == before:
            return (lost_counts, lost_un), (gained_counts, gained_un)


def check_mask_on(h1_path: Optional[Path] = None,
                  h4_path: Optional[Path] = None,
                  params: FloodTideParams = FloodTideParams(),
                  flags: tuple[MaskReason, ...] = FLAGS_APPLIED
                  ) -> MaskOnReport:
    """Run both paths and decompose the difference."""
    if h1_path is None or h4_path is None:
        h1_path, h4_path = default_data_paths()

    h1 = load_ohlcv(h1_path)
    h4 = load_ohlcv(h4_path)
    mask = build_mask(h1.index, flags)

    sig_off = generate_signals(h1, h4, params)
    sig_on = generate_signals(h1, h4, params, mask=mask)

    s_off = _signal_series(sig_off, h1.index)
    s_on = _signal_series(sig_on, h1.index)

    ts_off = h1.index[s_off == 1]
    ts_on = h1.index[s_on == 1]
    lost = ts_off.difference(ts_on)
    gained = ts_on.difference(ts_off)
    retained = ts_off.intersection(ts_on)

    s_retained = pd.Series(0, index=h1.index, dtype=np.int64)
    s_retained[retained] = 1

    atr_off = wilder_atr(h1["high"], h1["low"], h1["close"], ATR_PERIOD)
    atr_on = _masked_atr(h1, mask)

    e_off = _e_ratios(s_off, h1, None)
    e_ret_old = _e_ratios(s_retained, h1, atr_off)
    e_ret_new = _e_ratios(s_retained, h1, atr_on)
    e_on = _e_ratios(s_on, h1, atr_on)

    # Losses and gains are coupled both ways by the re-entry cooldown: a
    # removed signal can un-suppress a later one, and an added signal can
    # suppress a later one that used to fire. Attributing in one direction
    # leaves the other's knock-on effects unexplained, so this runs to a fixed
    # point — flag-caused changes first, then anything downstream of an
    # already-explained change, repeatedly, until nothing new resolves.
    (lost_counts, lost_un), (gained_counts, gained_un) = _attribute_coupled(
        lost, gained, h1.index, mask, params.entry_len,
        params.reentry_cooldown_bars)

    return MaskOnReport(
        n_signals_off=int((s_off == 1).sum()),
        n_signals_on=int((s_on == 1).sum()),
        n_retained=len(retained),
        lost=[t.isoformat() for t in lost],
        gained=[t.isoformat() for t in gained],
        attribution_lost=lost_counts,
        attribution_gained=gained_counts,
        unattributed=sorted(lost_un + gained_un),
        masked_bar_counts={
            f.value: int(mask.reason(f).sum()) for f in flags
        },
        flags=tuple(flags),
        channels=[
            ChannelResult(horizon=h, e_off=e_off[h],
                          e_retained_old_atr=e_ret_old[h],
                          e_retained_new_atr=e_ret_new[h], e_on=e_on[h])
            for h in sorted(HORIZONS)
        ],
    )


def _masked_atr(h1: pd.DataFrame, mask: TradabilityMask) -> pd.Series:
    """Wilder ATR with masked bars skipped.

    ATR is an ACCUMULATOR (R3): its state must advance across an untradable
    bar rather than be destroyed by it, so the masked bars are dropped and the
    recursion runs on what remains, then the result is put back on the
    calendar. Forward-filling onto the masked bars would hand a signal a
    denominator computed from bars it is not allowed to see; leaving them NaN
    is correct and simply removes those bars from the normalisable pool, which
    ``signal_edge_report`` already handles via its finite-ATR filter.
    """
    tradable = mask.tradable
    kept = h1[tradable]
    atr_kept = wilder_atr(kept["high"], kept["low"], kept["close"], ATR_PERIOD)
    return atr_kept.reindex(h1.index)


def log_mask_on(report: MaskOnReport, log_dir: Optional[Path] = None):
    """Record the attributed divergence. Not a trial: no hypothesis is tested."""
    from research import log as research_log

    totals = {f"total_h{c.horizon}": c.total for c in report.channels}
    norm = {f"normaliser_h{c.horizon}": c.normaliser for c in report.channels}
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return research_log.append_record(
        research_log.EventType.PARITY_FIXTURE,
        record_id=f"record:t9a-{HYPOTHESIS_ID}-mask-on",
        title=f"T9a mask-on divergence, attributed — {HYPOTHESIS_ID} seq={SEQ}",
        note=(
            "Mask-on run of the seq=31 entry under "
            f"{[f.value for f in FLAGS_APPLIED]}. The divergence is split into "
            "the signal-set channel (signals removed and added) and the "
            "normaliser channel (same retained signals, ATR recomputed with "
            "masked bars skipped), per REWRITE.md T9a. Every changed signal is "
            "traced to a named MaskReason; the unattributed bucket is "
            f"{'empty' if report.fully_attributed else 'NOT EMPTY'}. This is a "
            "measurement of a known, intended behaviour change, not a new "
            "trial — the verdict on flood_tide_h1 is not reopened."
        ),
        metrics={
            "mode": "mask_on",
            "flags_applied": [f.value for f in FLAGS_APPLIED],
            "n_signals_off": report.n_signals_off,
            "n_signals_on": report.n_signals_on,
            "n_lost": len(report.lost),
            "n_gained": len(report.gained),
            "fully_attributed": report.fully_attributed,
            "attribution_lost": report.attribution_lost,
            "attribution_gained": report.attribution_gained,
            **totals,
            **norm,
        },
        **kwargs,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args()

    if not source_data_available():
        print("source OHLC not available; set $QH_PARITY_DATA_DIR")
        return 2

    report = check_mask_on()
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print(f"T9a mask-on — flags {[f.value for f in FLAGS_APPLIED]}")
        print(f"  signals {report.n_signals_off} -> {report.n_signals_on} "
              f"(retained {report.n_retained}, lost {len(report.lost)}, "
              f"gained {len(report.gained)})")
        print(f"  lost attributed to   : {report.attribution_lost}")
        print(f"  gained attributed to : {report.attribution_gained}")
        print(f"  unattributed         : {len(report.unattributed)}")
        for c in report.channels:
            print(f"  h={c.horizon:<4} E {c.e_off:.4f} -> {c.e_on:.4f}  "
                  f"(removals {c.removals:+.4f}, normaliser {c.normaliser:+.4f}, "
                  f"additions {c.additions:+.4f})")
    if args.log:
        entry = log_mask_on(report)
        print(f"logged seq={entry.seq}")
    return 0 if report.fully_attributed else 1


if __name__ == "__main__":
    raise SystemExit(main())
