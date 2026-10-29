"""London-open sweep of the Asian range, faded back to its midpoint (XAUUSD M15).

**The claim.** Stops rest just beyond the Asian session's high and low. When
early London trading runs them and the price closes back inside the range,
the move was a grab for liquidity rather than an expansion, and it fades
toward the range's midpoint. The rules are taken as written in an external
research note (owner-supplied, 2026-10-28), with no grid and no tuning.

**Relatives in this log.** seq=15/48 faded the Asian session's *overshoot*
over a fixed 6h window: statistically real, economically dead (gross
$0.08/oz against a $0.29 round trip). seq=26/27 faded sweeps of AVWAP, POC
and HVN levels on M15; E-Ratios 0.74-0.81. Both are cousins, not this test:
neither conditions on London breaching the Asian extreme and then closing
back inside it. seq=48's London control showed *continuation* (t +1.84),
which is evidence against this claim, recorded here before the run.

**Rules, all UTC, frozen.**

- Asian range: the 24 bars opening in [00:00, 06:00). Width $5-35.
- Sweep: the first bar opening in [07:00, 10:00) whose high is at least
  $1.50 above the range high (fade short) or whose low is at least $1.50
  below the range low (fade long). A bar that does both skips the day.
- Reclaim: that bar or one of the next two closes back inside the range.
- Entry: the open of the bar after the reclaim.
- Target: the range midpoint. A day whose entry is already past it is
  skipped. Stop: the sweep's extreme, at least $2 from entry.
- Exit: stop or target, whichever a bar reaches first; a bar reaching both
  is a stop. Otherwise the open of the 16:00 bar.
- A day needs every bar from 00:00 to 16:00 present.

**Decisive statistic.** Mean gross $/oz per trade, against a null that
keeps each trade's day, direction, stop distance and target distance and
moves only its entry to a random bar opening in [07:00, 10:00) the same
day. Holding the day and direction fixed is what rule 3 asks of a long
trade on gold: it is judged against being long at another time that
morning, not against zero. One-sided: the claim is that the timing pays.

Nothing computes an outcome until the registration exists in the log.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.pre.decisive_stream import DecisiveStream, declare
from research.pre.normalizer_check import assert_disjoint

HYPOTHESIS_ID = "london_sweep_reclaim_m15"
FAMILY = "mean_reversion"
SYMBOL = "XAUUSD"
TIMEFRAME = "M15"
ASIAN_HOURS = (0, 6)
KILLZONE_HOURS = (7, 10)
EXIT_HOUR = 16
BARS_PER_HOUR = 4
MIN_WIDTH_USD = 5.0
MAX_WIDTH_USD = 35.0
SWEEP_BUFFER_USD = 1.5
RECLAIM_BARS = 3
MIN_STOP_USD = 2.0
ROUNDTRIP_COST_USD = 0.29
MIN_TRADES_PER_SIDE = 150
N_PERMUTATIONS = 1000
RANDOM_SEED = 42
ALPHA = 0.05
STREAMS = frozenset({"p_timing", "p_timing_long", "p_timing_short"})
REGISTRY_SNAPSHOT = "pepperstone_live_20261009b.json"

DAY_BARS = EXIT_HOUR * BARS_PER_HOUR
KZ_FIRST = KILLZONE_HOURS[0] * BARS_PER_HOUR
KZ_END = KILLZONE_HOURS[1] * BARS_PER_HOUR
EXIT_BAR = DAY_BARS


def decisive_stream() -> DecisiveStream:
    return declare(
        "p_timing", ALPHA, set(STREAMS),
        rationale=(
            "The claim is that entering on the sweep's reclaim beats entering "
            "the same direction at another time that morning. Both sides are "
            "one mechanism, so the pooled timing p decides; per-side p are "
            "reported, never decisive."))


def feature_spec() -> dict:
    """Feature inputs and target normalizer, asserted disjoint (rule 1)."""
    spec = {"feature_inputs": {"asian_high", "asian_low", "killzone_high",
                               "killzone_low", "killzone_close"},
            "target_normalizer": {"none_raw_usd_per_oz"}}
    assert_disjoint(spec["feature_inputs"], spec["target_normalizer"],
                    name=HYPOTHESIS_ID)
    return {k: sorted(v) for k, v in spec.items()}


@dataclass
class Setup:
    """One day's trigger, everything known at entry. No outcome."""
    date: str
    direction: int
    asian_high: float
    asian_low: float
    sweep_bar: int
    reclaim_bar: int
    entry_bar: int
    entry: float
    stop: float
    target: float


def _day_arrays(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """Every complete weekday as a (DAY_BARS + 1)-bar block from 00:00 UTC.

    The extra bar is the 16:00 bar, whose open is the time exit.
    """
    slot = (df.index.hour * BARS_PER_HOUR + df.index.minute // 15).to_numpy()
    date = df.index.normalize()
    keep = (slot <= EXIT_BAR) & (df.index.minute % 15 == 0) & (df.index.dayofweek < 5)
    sub = df[keep]
    sub_slot, sub_date = slot[keep], date[keep]
    counts = pd.Series(1, index=sub_date).groupby(level=0).size()
    full = counts.index[counts.to_numpy() == EXIT_BAR + 1]
    out = {}
    if not len(full):
        return out
    ok = np.isin(sub_date, full)
    sub, sub_slot, sub_date = sub[ok], sub_slot[ok], sub_date[ok]
    order = np.lexsort((sub_slot, sub_date))
    blocks = sub.iloc[order][["open", "high", "low", "close"]].to_numpy(float)
    blocks = blocks.reshape(len(full), EXIT_BAR + 1, 4)
    for d, b in zip(full, blocks):
        out[str(d.date())] = b
    return out


def find_setup(date: str, b: np.ndarray) -> tuple[Optional[Setup], str]:
    """Apply the trigger rules to one day. Returns (setup, reason)."""
    o, h, l, c = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    a0, a1 = ASIAN_HOURS[0] * BARS_PER_HOUR, ASIAN_HOURS[1] * BARS_PER_HOUR
    ah, al = h[a0:a1].max(), l[a0:a1].min()
    width = ah - al
    if not MIN_WIDTH_USD <= width <= MAX_WIDTH_USD:
        return None, "width"
    sweep, direction = None, 0
    for i in range(KZ_FIRST, KZ_END):
        up = h[i] >= ah + SWEEP_BUFFER_USD
        dn = l[i] <= al - SWEEP_BUFFER_USD
        if up and dn:
            return None, "both_sides"
        if up or dn:
            sweep, direction = i, (-1 if up else 1)
            break
    if sweep is None:
        return None, "no_sweep"
    reclaim = None
    for j in range(sweep, min(sweep + RECLAIM_BARS, EXIT_BAR - 1)):
        if (direction == -1 and c[j] < ah) or (direction == 1 and c[j] > al):
            reclaim = j
            break
    if reclaim is None:
        return None, "no_reclaim"
    entry_bar = reclaim + 1
    entry = o[entry_bar]
    mid = (ah + al) / 2
    if direction * (mid - entry) <= 0:
        return None, "target_passed"
    if direction == -1:
        stop = max(h[sweep:reclaim + 1].max(), entry + MIN_STOP_USD)
    else:
        stop = min(l[sweep:reclaim + 1].min(), entry - MIN_STOP_USD)
    return Setup(date, direction, float(ah), float(al), sweep, reclaim,
                 entry_bar, float(entry), float(stop), float(mid)), "setup"


def simulate(b: np.ndarray, direction: int, entry_bar: int,
             stop_dist: float, target_dist: float) -> float:
    """Gross $/oz of one trade entered at ``entry_bar``'s open.

    A bar reaching both levels is a stop. An adverse gap fills at the open;
    a favourable one fills at the target.
    """
    o, h, l = b[:, 0], b[:, 1], b[:, 2]
    entry = o[entry_bar]
    stop = entry - direction * stop_dist
    target = entry + direction * target_dist
    for k in range(entry_bar, EXIT_BAR):
        if k > entry_bar and direction * (o[k] - stop) <= 0:
            return direction * (o[k] - entry)
        worst = l[k] if direction == 1 else h[k]
        best = h[k] if direction == 1 else l[k]
        if direction * (worst - stop) <= 0:
            return direction * (stop - entry)
        if direction * (best - target) >= 0:
            return direction * (target - entry)
    return direction * (o[EXIT_BAR] - entry)


def _load() -> pd.DataFrame:
    """Admitted bars in UTC. Admission reads the raw server-time stamps, so
    its cut is converted the same way the loader converts the index."""
    from research import admission
    from research.post.sweeps import data as sweeps_data
    start = admission.require(SYMBOL, TIMEFRAME)
    cut = start.tz_convert(None).tz_localize("Europe/Athens").tz_convert("UTC")
    df = sweeps_data.load(TIMEFRAME, tz="server_eet", symbol=SYMBOL)
    return df[df.index >= cut]


def setups(days: dict[str, np.ndarray]) -> tuple[list[Setup], dict]:
    found, reasons = [], {}
    for d, b in days.items():
        s, why = find_setup(d, b)
        reasons[why] = reasons.get(why, 0) + 1
        if s is not None:
            found.append(s)
    return found, reasons


def count_setups() -> dict:
    """Trigger counts per side. Computes no entry-to-exit outcome."""
    days = _day_arrays(_load())
    found, reasons = setups(days)
    return {"complete_days": len(days), "reasons": reasons,
            "long": sum(s.direction == 1 for s in found),
            "short": sum(s.direction == -1 for s in found),
            "first": min(days) if days else None,
            "last": max(days) if days else None}


def _null_table(days: dict[str, np.ndarray], found: list[Setup]) -> np.ndarray:
    """Gross $/oz for every event at every killzone entry bar."""
    table = np.empty((len(found), KZ_END - KZ_FIRST))
    for n, s in enumerate(found):
        sd, td = abs(s.stop - s.entry), abs(s.target - s.entry)
        for m, k in enumerate(range(KZ_FIRST, KZ_END)):
            table[n, m] = simulate(days[s.date], s.direction, k, sd, td)
    return table


def timing_test(observed: np.ndarray, table: np.ndarray,
                n_permutations: int = N_PERMUTATIONS,
                seed: int = RANDOM_SEED) -> dict:
    """One-sided p that the actual entries beat random same-morning ones."""
    rng = np.random.default_rng(seed)
    obs = float(observed.mean())
    picks = rng.integers(0, table.shape[1], size=(n_permutations, len(observed)))
    null = table[np.arange(len(observed)), picks].mean(axis=1)
    p = (1 + int((null >= obs).sum())) / (1 + n_permutations)
    return {"observed": obs, "null_mean": float(null.mean()),
            "null_p95": float(np.quantile(null, 0.95)), "p": p,
            "n": int(len(observed))}


def verdict(res: dict, stream: DecisiveStream) -> tuple[str, str]:
    """The registered rule, VOID first."""
    thin = {k: res["sides"][k]["n"] for k in ("long", "short")
            if res["sides"][k]["n"] < MIN_TRADES_PER_SIDE}
    if thin:
        return "VOID", f"fewer than {MIN_TRADES_PER_SIDE} trades: {thin}"
    passed, why = stream.verdict({stream.name: res["streams"][stream.name]})
    if passed == "FAIL":
        return "DEAD", why
    if not res["net_mean_usd"] > 0:
        return "UNTRADEABLE", f"{why}; net ${res['net_mean_usd']:.3f}/oz after cost"
    losing = [k for k in ("long", "short") if not res["sides"][k]["net_mean_usd"] > 0]
    if losing:
        return "ALIVE_ONE_SIDE", f"{why}; net <= 0 on {losing}"
    return "ALIVE", why


def _registered(log_dir: Optional[Path]) -> bool:
    from research import log as research_log
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return bool(research_log.history(HYPOTHESIS_ID, **kwargs))


def evaluate(days: dict[str, np.ndarray],
             n_permutations: int = N_PERMUTATIONS) -> dict:
    """Outcomes, the timing test and the descriptive rates. No registry check."""
    found, reasons = setups(days)
    gross = np.array([simulate(days[s.date], s.direction, s.entry_bar,
                               abs(s.stop - s.entry), abs(s.target - s.entry))
                      for s in found])
    table = _null_table(days, found)
    dirs = np.array([s.direction for s in found])
    pooled = timing_test(gross, table, n_permutations)
    hit = np.array([abs(g - abs(s.target - s.entry)) < 1e-9
                    for g, s in zip(gross, found)])
    sides = {}
    for name, sign in (("long", 1), ("short", -1)):
        m = dirs == sign
        if not m.any():
            sides[name] = {"observed": float("nan"), "p": 1.0, "n": 0,
                           "net_mean_usd": float("nan"), "target_rate": float("nan")}
            continue
        t = timing_test(gross[m], table[m], n_permutations)
        sides[name] = {**t, "net_mean_usd": t["observed"] - ROUNDTRIP_COST_USD,
                       "target_rate": float(hit[m].mean())}
    return {"n_trades": int(len(found)), "reasons": reasons,
            "gross_mean_usd": float(gross.mean()),
            "net_mean_usd": float(gross.mean()) - ROUNDTRIP_COST_USD,
            "target_rate": float(hit.mean()) if len(hit) else float("nan"),
            "timing": pooled, "sides": sides,
            "streams": {"p_timing": pooled["p"],
                        "p_timing_long": sides["long"]["p"],
                        "p_timing_short": sides["short"]["p"]},
            "trades": [{**asdict(s), "gross_usd": float(g)}
                       for s, g in zip(found, gross)]}


def run(log_dir: Optional[Path] = None,
        n_permutations: int = N_PERMUTATIONS) -> dict:
    """The registered test. Refuses to compute an outcome before registration."""
    if not _registered(log_dir):
        raise RuntimeError(
            f"{HYPOTHESIS_ID!r} is not registered in the research log; "
            "register it before any outcome is computed.")
    res = evaluate(_day_arrays(_load()), n_permutations)
    stream = decisive_stream()
    label, why = verdict(res, stream)
    return {"hypothesis_id": HYPOTHESIS_ID, "verdict": label, "reason": why,
            "decisive_stream": stream.name, **res,
            "n_permutations": n_permutations, "random_seed": RANDOM_SEED}


def registration_parameters() -> dict:
    stream = decisive_stream()
    return {
        "symbol": SYMBOL, "timeframe": TIMEFRAME, "clock": "UTC",
        "asian_hours": list(ASIAN_HOURS), "killzone_hours": list(KILLZONE_HOURS),
        "exit_hour": EXIT_HOUR, "min_width_usd": MIN_WIDTH_USD,
        "max_width_usd": MAX_WIDTH_USD, "sweep_buffer_usd": SWEEP_BUFFER_USD,
        "reclaim_bars": RECLAIM_BARS, "min_stop_usd": MIN_STOP_USD,
        "target": "asian midpoint", "stop": "sweep extreme, at least min_stop_usd",
        "entry": "open of the bar after the reclaim",
        "same_bar_rule": "a bar reaching stop and target is a stop",
        "roundtrip_cost_usd": ROUNDTRIP_COST_USD,
        "min_trades_per_side": MIN_TRADES_PER_SIDE,
        "null": "same day, direction, stop and target distance; entry at a "
                "uniformly random bar opening in the killzone",
        "n_permutations": N_PERMUTATIONS, "random_seed": RANDOM_SEED,
        "decisive_stream": stream.name, "decisive_threshold": stream.threshold,
        "decisive_rationale": stream.rationale, "one_sided": True,
        "streams_emitted": sorted(STREAMS), **feature_spec(),
        "admission": "research.admission.require",
        "verdict_labels": ["ALIVE", "ALIVE_ONE_SIDE", "UNTRADEABLE", "DEAD", "VOID"],
    }


#: :func:`count_setups` on 2026-10-29, before registration; no outcome read.
INTENDED_N_OBS = 453
#: ``min_decidable_sharpe(INTENDED_N_OBS, sr_star=0.0)``, normal moments.
MIN_DECIDABLE_SHARPE = 0.077483

NULL_BASELINE = (
    "Per trade, the same day, direction, stop distance and target distance "
    "with the entry moved to a uniformly random bar opening in "
    "[07:00, 10:00) UTC; 1000 draws, seed 42; mean gross $/oz recomputed. "
    "Keeps the day's path and the trade's geometry; breaks only the link "
    "between entry time and the sweep-and-reclaim.")

DECLARED = (
    "Prior exposure: seq=15/48 (Asian overshoot fade, shelved on cost) and "
    "seq=26/27 (AVWAP/POC/HVN sweep-and-reclaim, E-Ratio 0.74-0.81). "
    "seq=48's London control continued rather than reverted. Before this "
    "registration only trigger counts were read (count_setups, 2026-10-29): "
    "3,492 complete days from 2012-03-26 (admission) to 2025-12-31; 453 "
    "setups, 244 long and 209 short; 1,245 days fail the $5-35 width band. "
    "The owner was told 300 trades per side before the count; that floor "
    "would void the test, so it was lowered to 150 having seen counts, never "
    "outcomes. The band and buffer are fixed dollars from the note, so they "
    "admit different days as the price level moves (about $1,650 in 2012, "
    "$4,300 in 2025); this is the note's rule taken literally, not a choice "
    "made here. Cost is $0.29/oz (seq=48), and the gold commission behind it "
    "is contested between two Pepperstone sources. The E-Ratio is not "
    "computed: the role is DIAGNOSTIC and the timing null decides.")


def preregister(log_dir: Optional[Path] = None):
    """Append the HYPOTHESIS event. Must precede :func:`run`."""
    from research import log as research_log
    stream = decisive_stream()
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return research_log.register_hypothesis(
        HYPOTHESIS_ID,
        title="Does a London-open sweep of the Asian range fade to its midpoint?",
        mechanism=(
            "When a bar between 07:00 and 10:00 UTC runs at least $1.50 "
            "beyond the Asian (00:00-06:00 UTC) high or low and price closes "
            "back inside within three M15 bars, fading toward the Asian "
            "midpoint beats the same trade entered at a random time that "
            "morning. The payer is the stop and breakout flow resting beyond "
            "the Asian extreme."),
        market=SYMBOL, timeframe=TIMEFRAME, family=FAMILY,
        edge_gate_role=research_log.EdgeGateRole.DIAGNOSTIC,
        predictions=[
            f"{stream.name} < {stream.threshold}, one-sided, decides; "
            "per-side p are reported, never decisive",
            "ALIVE also requires a positive mean net of the $0.29/oz round "
            "trip on both sides; otherwise UNTRADEABLE or ALIVE_ONE_SIDE",
            f"fewer than {MIN_TRADES_PER_SIDE} trades on either side is VOID",
            "the note's 65% target-hit rate is reported, never decisive"],
        note=("Pre-registered before any outcome was computed; run() refuses "
              "until this entry exists. Rules are an external research "
              "note's, taken literally. " + DECLARED),
        universe=[SYMBOL],
        selection_rule=research_log.SelectionRule.POOLED_ALL,
        null_baseline_structure=NULL_BASELINE,
        benchmark_sharpe=0.0,
        min_decidable_sharpe=MIN_DECIDABLE_SHARPE,
        registry_snapshot=REGISTRY_SNAPSHOT,
        parameters=registration_parameters(),
        **kwargs,
    )


def log_result(res: dict, artifact: str, log_dir: Optional[Path] = None,
               extra_note: str = ""):
    """Record a :func:`run` result against the registration. Not a trial."""
    from research import log as research_log
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return research_log.update_hypothesis(
        HYPOTHESIS_ID,
        stage=research_log.Stage.SIGNAL_EDGE,
        verdict=(research_log.Verdict.OPEN if res["verdict"] == "ALIVE"
                 else research_log.Verdict.KILLED),
        metrics={
            "verdict": res["verdict"], "reason": res["reason"],
            "artifact": artifact, "streams": res["streams"],
            "n_trades": res["n_trades"], "gross_mean_usd": res["gross_mean_usd"],
            "net_mean_usd": res["net_mean_usd"],
            "null_mean_usd": res["timing"]["null_mean"],
            "sides": {k: {kk: v[kk] for kk in ("n", "observed", "net_mean_usd",
                                               "null_mean", "p", "target_rate")
                          if kk in v} for k, v in res["sides"].items()},
            "reasons": res["reasons"],
        },
        note=(f"Registered run: {res['verdict']} ({res['reason']}). Decided "
              "by the pre-declared stream alone."
              + (" " + extra_note if extra_note else "")),
        **kwargs,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", action="store_true",
                    help="trigger counts only; reads no outcome")
    ap.add_argument("--preregister", action="store_true",
                    help="append the HYPOTHESIS event to the research log")
    ap.add_argument("--run", action="store_true",
                    help="the registered test; refuses before registration")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if args.count:
        print(json.dumps(count_setups(), indent=1))
        return 0
    if args.preregister:
        entry = preregister()
        print(f"registered seq={entry.seq} {entry.hypothesis_id}")
        return 0
    if args.run:
        res = run()
        text = json.dumps(res, indent=1, default=float)
        if args.out:
            args.out.write_text(text + "\n")
        print(res["verdict"], "—", res["reason"])
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
