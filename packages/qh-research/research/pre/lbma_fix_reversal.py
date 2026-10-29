"""Does the move into an LBMA gold auction reverse after it? (XAUUSD M5)

**The claim.** Benchmark orders are worked in the half hour before the LBMA
gold price auctions (10:30 and 15:00 London). Once the auction prints that
pressure lifts, so the pre-auction move partly reverses over the next half
hour. The input is the auction calendar, not another transform of price,
which is what the screen-hygiene ceiling asks for. seq=140's dead macro
releases were news; this is scheduled flow.

**Two trials, one module.** The PM (15:00) and AM (10:30) auctions are
registered separately. Neither is a fallback for the other.

**Construction, London local time.** P(t) is the open of the M5 bar opening
at t. For an anchor T,

    pre  = ln P(T-5m)  - ln P(T-30m)
    post = ln P(T+30m) - ln P(T)

and the statistic is corr(pre, post) across days with every bar from T-30m
to T+30m present. The five minutes before T are left out so the auction's
own opening bar sits in neither window.

**Decisive control.** The same correlation at every placebo anchor on the
30-minute grid from 01:00 to 21:00 London, excluding any within 60 minutes
of either auction so no placebo window touches an auction window. The
auction must be more negative than every placebo (31 of them; the smallest
reachable p is 1/32). This rules out a generic intraday reversal.

**Cost check.** Fading the pre-auction move (enter at T against the sign of
pre, exit at T+30m) must gross at least twice the $0.29/oz round trip, or
the verdict is UNTRADEABLE.

Nothing computes an outcome until the trial's registration is in the log.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.pre.decisive_stream import DecisiveStream, declare
from research.pre.normalizer_check import assert_disjoint

FAMILY = "scheduled_flow"
SYMBOL = "XAUUSD"
TIMEFRAME = "M5"
LONDON = "Europe/London"
AUCTIONS = {"pm": "15:00", "am": "10:30"}
HYPOTHESIS_IDS = {"pm": "lbma_pm_fix_reversal_m5", "am": "lbma_am_fix_reversal_m5"}
GRID_FIRST, GRID_LAST, GRID_STEP_MIN = "01:00", "21:00", 30
PLACEBO_EXCLUSION_MIN = 60
PRE_START_MIN, PRE_END_MIN, POST_END_MIN = -30, -5, 30
ROUNDTRIP_COST_USD = 0.29
COST_MULTIPLE = 2.0
MIN_DAYS = 1000
ALPHA = 0.05
STREAMS = frozenset({"p_placebo_rank", "p_placebo_rank_two_sided"})
REGISTRY_SNAPSHOT = "pepperstone_live_20261009b.json"


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def anchors(which: str) -> tuple[int, list[int]]:
    """The auction anchor and its placebo anchors, in London minutes."""
    auction = _minutes(AUCTIONS[which])
    fixes = [_minutes(t) for t in AUCTIONS.values()]
    grid = range(_minutes(GRID_FIRST), _minutes(GRID_LAST) + 1, GRID_STEP_MIN)
    placebos = [t for t in grid
                if all(abs(t - f) > PLACEBO_EXCLUSION_MIN for f in fixes)]
    return auction, placebos


def decisive_stream() -> DecisiveStream:
    return declare(
        "p_placebo_rank", ALPHA, set(STREAMS),
        rationale=(
            "The claim is about the auction, not about intraday reversal in "
            "general, so the auction's correlation is ranked against the "
            "same statistic at every other half hour. One-sided, because the "
            "mechanism predicts reversal; the two-sided rank is reported, "
            "never decisive."))


def feature_spec() -> dict:
    """Feature inputs and target normalizer, asserted disjoint (rule 1)."""
    spec = {"feature_inputs": {"open_T-30m", "open_T-5m"},
            "target_normalizer": {"none_correlation_is_scale_free"}}
    assert_disjoint(spec["feature_inputs"], spec["target_normalizer"],
                    name="lbma_fix_reversal")
    return {k: sorted(v) for k, v in spec.items()}


def london_opens(df: pd.DataFrame) -> pd.DataFrame:
    """Bar opens as a (London date x London minute-of-day) table."""
    local = df.index.tz_convert(LONDON)
    minute = local.hour * 60 + local.minute
    return pd.DataFrame({"date": local.normalize().tz_localize(None),
                         "minute": minute, "open": df["open"].to_numpy(float)}
                        ).pivot_table(index="date", columns="minute",
                                      values="open", aggfunc="first")


def window(table: pd.DataFrame, anchor: int, with_outcome: bool) -> pd.DataFrame:
    """pre (and post) per day where every bar in [T-30m, T+30m] exists."""
    need = list(range(anchor + PRE_START_MIN, anchor + POST_END_MIN + 1, 5))
    if not set(need) <= set(table.columns):
        return pd.DataFrame(columns=["pre", "post", "fade_usd"])
    sub = table[need].dropna()
    sub = sub[sub.index.dayofweek < 5]
    p = lambda off: sub[anchor + off].to_numpy(float)  # noqa: E731
    out = pd.DataFrame({"pre": np.log(p(PRE_END_MIN)) - np.log(p(PRE_START_MIN))},
                       index=sub.index)
    if with_outcome:
        out["post"] = np.log(p(POST_END_MIN)) - np.log(p(0))
        out["fade_usd"] = -np.sign(out["pre"]) * (p(POST_END_MIN) - p(0))
    return out


def placebo_test(table: pd.DataFrame, which: str) -> dict:
    """Rank the auction's corr(pre, post) among the placebo anchors."""
    auction, placebos = anchors(which)
    stats = {}
    for t in [auction, *placebos]:
        w = window(table, t, with_outcome=True)
        if len(w) >= MIN_DAYS:
            stats[t] = {"n": int(len(w)),
                        "corr": float(np.corrcoef(w["pre"], w["post"])[0, 1]),
                        "fade_gross_usd": float(w["fade_usd"].mean())}
    if auction not in stats:
        return {"auction": auction, "stats": stats, "decidable": False}
    obs = stats[auction]["corr"]
    others = np.array([v["corr"] for t, v in stats.items() if t != auction])
    p_one = (1 + int((others <= obs).sum())) / (1 + len(others))
    p_two = (1 + int((np.abs(others) >= abs(obs)).sum())) / (1 + len(others))
    return {"auction": auction, "decidable": True, "observed": obs,
            "n_placebos": int(len(others)), "stats": stats,
            "streams": {"p_placebo_rank": p_one,
                        "p_placebo_rank_two_sided": p_two},
            "fade_gross_usd": stats[auction]["fade_gross_usd"],
            "n_days": stats[auction]["n"]}


def verdict(res: dict, stream: DecisiveStream) -> tuple[str, str]:
    """The registered rule, VOID first."""
    if not res["decidable"]:
        return "VOID", f"fewer than {MIN_DAYS} complete days at the auction"
    passed, why = stream.verdict({stream.name: res["streams"][stream.name]})
    if passed == "FAIL":
        return "DEAD", why
    floor = COST_MULTIPLE * ROUNDTRIP_COST_USD
    if not res["fade_gross_usd"] >= floor:
        return "UNTRADEABLE", (f"{why}; fade grosses ${res['fade_gross_usd']:.3f}"
                               f"/oz, needs ${floor:.2f}")
    return "ALIVE", why


def _load() -> pd.DataFrame:
    """Admitted bars in UTC; admission's cut converted like the index."""
    from research import admission
    from research.post.sweeps import data as sweeps_data
    start = admission.require(SYMBOL, TIMEFRAME)
    cut = start.tz_convert(None).tz_localize("Europe/Athens").tz_convert("UTC")
    df = sweeps_data.load(TIMEFRAME, tz="server_eet", symbol=SYMBOL)
    return df[df.index >= cut]


def count_days() -> dict:
    """Complete days per anchor. Reads no post-anchor price."""
    table = london_opens(_load())
    out = {}
    for which in AUCTIONS:
        auction, placebos = anchors(which)
        out[which] = {"auction_days": len(window(table, auction, False)),
                      "n_placebos": len(placebos),
                      "min_placebo_days": min(len(window(table, t, False))
                                              for t in placebos)}
    out["first"] = str(table.index.min().date())
    out["last"] = str(table.index.max().date())
    return out


def _registered(which: str, log_dir: Optional[Path]) -> bool:
    from research import log as research_log
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return bool(research_log.history(HYPOTHESIS_IDS[which], **kwargs))


def run(which: str, log_dir: Optional[Path] = None) -> dict:
    """The registered test. Refuses to compute an outcome before registration."""
    if not _registered(which, log_dir):
        raise RuntimeError(
            f"{HYPOTHESIS_IDS[which]!r} is not registered in the research log; "
            "register it before any outcome is computed.")
    res = placebo_test(london_opens(_load()), which)
    stream = decisive_stream()
    label, why = verdict(res, stream)
    return {"hypothesis_id": HYPOTHESIS_IDS[which], "verdict": label,
            "reason": why, "decisive_stream": stream.name, **res}


def registration_parameters(which: str) -> dict:
    stream = decisive_stream()
    auction, placebos = anchors(which)
    return {
        "symbol": SYMBOL, "timeframe": TIMEFRAME, "clock": LONDON,
        "auction": AUCTIONS[which],
        "price": "open of the M5 bar opening at t",
        "pre": "ln P(T-5m) - ln P(T-30m)", "post": "ln P(T+30m) - ln P(T)",
        "statistic": "corr(pre, post) across days with every bar T-30m..T+30m",
        "placebo_grid": f"{GRID_FIRST}-{GRID_LAST} every {GRID_STEP_MIN} min",
        "placebo_exclusion_min": PLACEBO_EXCLUSION_MIN,
        "placebo_anchors_min": placebos, "min_days": MIN_DAYS,
        "fade_rule": "enter at T against sign(pre), exit at T+30m",
        "roundtrip_cost_usd": ROUNDTRIP_COST_USD, "cost_multiple": COST_MULTIPLE,
        "decisive_stream": stream.name, "decisive_threshold": stream.threshold,
        "decisive_rationale": stream.rationale, "one_sided": True,
        "predicted_sign": "negative (reversal)",
        "streams_emitted": sorted(STREAMS), **feature_spec(),
        "admission": "research.admission.require",
        "verdict_labels": ["ALIVE", "UNTRADEABLE", "DEAD", "VOID"],
    }


#: :func:`count_days` on 2026-10-29, before registration; no outcome read.
INTENDED_N_OBS = {"pm": 3536, "am": 3541}
#: ``min_decidable_sharpe(INTENDED_N_OBS[which], sr_star=0.0)``.
MIN_DECIDABLE_SHARPE = {"pm": 0.02767, "am": 0.027651}

NULL_BASELINE = (
    "The same corr(pre, post) at each placebo anchor on the 30-minute "
    "London grid 01:00-21:00, excluding anchors within 60 minutes of either "
    "auction. One-sided p = (1 + placebos at or below the auction) / "
    "(1 + placebos). Keeps the day set, the window geometry and intraday "
    "seasonality in volatility; changes only which half hour is measured.")

DECLARED = (
    "Prior exposure: no work in this repo has conditioned on the LBMA "
    "auctions. seq=59 (Gao et al. intraday momentum, H1) and seq=140 (macro "
    "releases vs placebo hours) are the nearest; seq=140 found metals "
    "continuing at h=4 after releases, the opposite sign. Before this "
    "registration only complete-day counts were read (count_days, "
    "2026-10-29): 3,536 PM and 3,541 AM days from 2012-03-23 (admission) to "
    "2026-01-30, at least 3,169 at every placebo. KNOWN CONFOUNDS, stated "
    "before the run: the PM pre-window opens at 14:30 London, which is the "
    "NYSE open except in the weeks US and UK clocks disagree, so a PM "
    "reversal could be an equity-open effect; the placebo grid holds other "
    "session opens (London 08:00) but not that one. UK bank holidays (about "
    "8 days a year) have no auction and are not removed, which dilutes "
    "toward the null. Before 2015-03-20 the auction was the London Gold "
    "Fixing at the same times. Cost is $0.29/oz (seq=48), contested.")


def preregister(which: str, log_dir: Optional[Path] = None):
    """Append the HYPOTHESIS event for one auction. Must precede :func:`run`."""
    from research import log as research_log
    stream = decisive_stream()
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    t = AUCTIONS[which]
    return research_log.register_hypothesis(
        HYPOTHESIS_IDS[which],
        title=f"Does the move into the {t} LBMA gold auction reverse after it?",
        mechanism=(
            f"Benchmark orders worked before the {t} London LBMA gold auction "
            "push price; once it prints the pressure lifts and the move "
            "partly reverses. The return from T-30m to T-5m is negatively "
            "correlated with the return from T to T+30m, more so than at any "
            "other half hour of the London day."),
        market=SYMBOL, timeframe=TIMEFRAME, family=FAMILY,
        edge_gate_role=research_log.EdgeGateRole.UNSET,
        predictions=[
            f"{stream.name} < {stream.threshold}, one-sided for reversal, "
            "decides; the two-sided rank is reported, never decisive",
            "ALIVE also requires the fade to gross at least "
            f"${COST_MULTIPLE * ROUNDTRIP_COST_USD:.2f}/oz; otherwise UNTRADEABLE",
            f"fewer than {MIN_DAYS} complete auction days is VOID"],
        note=(f"One of two auction trials ({', '.join(HYPOTHESIS_IDS.values())}), "
              "registered together and decided separately. Pre-registered "
              "before any outcome was computed; run() refuses until this "
              "entry exists. " + DECLARED),
        universe=[SYMBOL],
        selection_rule=research_log.SelectionRule.POOLED_ALL,
        null_baseline_structure=NULL_BASELINE,
        benchmark_sharpe=0.0,
        min_decidable_sharpe=MIN_DECIDABLE_SHARPE[which],
        registry_snapshot=REGISTRY_SNAPSHOT,
        parameters=registration_parameters(which),
        **kwargs,
    )


def log_result(res: dict, artifact: str, log_dir: Optional[Path] = None,
               extra_note: str = ""):
    """Record a :func:`run` result against its registration. Not a trial."""
    from research import log as research_log
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return research_log.update_hypothesis(
        res["hypothesis_id"],
        stage=research_log.Stage.SIGNAL_EDGE,
        verdict=(research_log.Verdict.OPEN if res["verdict"] == "ALIVE"
                 else research_log.Verdict.KILLED),
        metrics={
            "verdict": res["verdict"], "reason": res["reason"],
            "artifact": artifact, "streams": res.get("streams", {}),
            "auction_corr": res.get("observed"), "n_days": res.get("n_days"),
            "n_placebos": res.get("n_placebos"),
            "fade_gross_usd": res.get("fade_gross_usd"),
            "placebo_corr": {str(k): round(v["corr"], 5)
                             for k, v in res["stats"].items()},
        },
        note=(f"Registered run: {res['verdict']} ({res['reason']}). Decided "
              "by the pre-declared stream alone."
              + (" " + extra_note if extra_note else "")),
        **kwargs,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", action="store_true",
                    help="complete-day counts only; reads no outcome")
    ap.add_argument("--preregister", choices=sorted(AUCTIONS),
                    help="append that auction's HYPOTHESIS event")
    ap.add_argument("--run", choices=sorted(AUCTIONS),
                    help="the registered test; refuses before registration")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if args.count:
        print(json.dumps(count_days(), indent=1))
        return 0
    if args.preregister:
        entry = preregister(args.preregister)
        print(f"registered seq={entry.seq} {entry.hypothesis_id}")
        return 0
    if args.run:
        res = run(args.run)
        text = json.dumps(res, indent=1, default=float)
        if args.out:
            args.out.write_text(text + "\n")
        print(res["verdict"], "—", res["reason"])
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
