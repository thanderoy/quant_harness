"""Regenerate the T9b trade-level parity reference for ``crest_n_keel``.

X15b asserts that the rewritten ``post/`` path reproduces the seq=49 nested
walk-forward **trade for trade** — timestamps, prices, direction and volume.
Nothing in either repository records that. The stored artifacts
(``research/data/crest_n_keel/cnk_nested_wf_{H1,H4}.json`` in
wine-mt5-python-setup, both gitignored) keep per-fold statistics only, and a
sweep of every other JSON and CSV artifact found no trade-for-trade record
anywhere. So the reference has to be derived, and the derivation has to earn
the right to be called one.

The gate this script enforces, and refuses to write without:

1. Recompute the fold geometry from the raw bars and require every
   ``train_start`` / ``train_end`` / ``test_end`` to match the stored artifact.
2. Read each fold's config back from its stored label, re-run it on that fold's
   own untouched test window, and require every recorded statistic to come back
   identical under float equality.
3. Do the same for the independent ``fixed`` arm, which does not depend on the
   selection step at all.

If any of that disagrees, the script exits non-zero and writes nothing. That
outcome is worth more than a passing test: "the pre-rebuild stack does not
reproduce its own recorded results" would weaken the *stored* artifact, not
this one, and no fixture should paper over it.

What a pass does and does not buy is stamped into the fixture itself. Briefly:
``cnk_engine.py`` was untracked when the artifact was produced and its
virtualenv is gone, so there is no recorded frozen stack to re-run — a match
establishes de facto equivalence, not identity. And selection is not
reproduced; configs are read back from labels rather than re-derived by
re-running the 30,132-config grid per fold. X15b asserts on the simulation
path, which is what is verified.

Run from the repo root::

    python -m phase0.build_t9b_cnk_fixture [--wmps PATH]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import types

OUT = (pathlib.Path(__file__).resolve().parents[1] / "packages" / "qh-research"
       / "research" / "parity" / "fixtures" / "t9b_crest_n_keel_maskoff.json")

DEFAULT_WMPS = pathlib.Path.home() / "Local" / "wine-mt5-python-setup"

# The generating commit of the source repo, recorded so the fixture names the
# code it came from even though the artifact itself carries no SHA.
WMPS_COMMIT = "27f94d8575b295e8a3a54a75126218296c0b85f1"

MOM = re.compile(r"^momentum/(\w+) hma(\d+) atr(\d+) trail([\d.]+) minATR([\d.]+)$")
PUL = re.compile(r"^pullback/(\w+) hma(\d+) atr(\d+) k(\d+) z(\d+)/(\d+) "
                 r"sl([\d.]+) tp([\d.]+) minATR([\d.]+)$")

SELECTED_FIELDS = [("oos_sharpe", "sharpe"), ("oos_trades", "n_trades"),
                   ("oos_max_dd", "max_dd"), ("oos_profit_factor", "profit_factor"),
                   ("oos_cagr_acct", "cagr_acct")]
FIXED_FIELDS = [("oos_sharpe", "sharpe"), ("oos_trades", "n_trades")]


# --------------------------------------------------------------------------- #
# Instrumentation                                                              #
# --------------------------------------------------------------------------- #
# `cnk_engine.simulate` computes entry price, exit price, direction and volume
# and then throws all four away, returning only what `metrics` needs. Rather
# than vendor a modified copy — which would drift silently — the source is
# patched here, textually and with assertions, so an upstream change breaks the
# build instead of quietly producing a fixture from different arithmetic.
PATCHES = [
    ('    rets, pnls, px_rets, entry_ts, exit_ts = [], [], [], [], []',
     '    rets, pnls, px_rets, entry_ts, exit_ts = [], [], [], [], []\n'
     '    rec: list[dict] = []   # INSTRUMENTATION ONLY'),
    ('        entry_ts.append(idx[f])\n'
     '        exit_ts.append(idx[exit_bar])',
     '        entry_ts.append(idx[f])\n'
     '        exit_ts.append(idx[exit_bar])\n'
     '        rec.append({"entry_ts": str(idx[f]), "exit_ts": str(idx[exit_bar]),\n'
     '                    "direction": "long" if is_long else "short",\n'
     '                    "entry_px": entry_px, "exit_px": exit_px,\n'
     '                    "lots": lots, "size_oz": size_oz,\n'
     '                    "effective_atr": eff_atr, "sl": sl,\n'
     '                    "tp": (tp if not is_mom else None),\n'
     '                    "pnl": pnl, "pnl_bt": pnl_bt,\n'
     '                    "commission": commission, "swap": swap})'),
    ('        "equity_final": equity,\n    }',
     '        "equity_final": equity,\n        "records": rec,\n    }'),
    ('             "pnls": np.array([]), "entry_ts": [], "exit_ts": [],\n'
     '             "equity_final": cash}',
     '             "pnls": np.array([]), "entry_ts": [], "exit_ts": [],\n'
     '             "equity_final": cash, "records": []}'),
]


def load_instrumented_engine(wmps: pathlib.Path) -> types.ModuleType:
    """Import `cnk_engine` with trade recording patched in."""
    src_path = wmps / "research" / "post" / "sweeps" / "cnk_engine.py"
    src = src_path.read_text()
    for old, new in PATCHES:
        if src.count(old) != 1:
            raise SystemExit(
                f"instrumentation patch no longer applies to {src_path} "
                f"(expected exactly one occurrence of {old[:60]!r}); "
                "the engine changed and the fixture must not be rebuilt blindly")
        src = src.replace(old, new)
    mod = types.ModuleType("cnk_engine_instrumented")
    mod.__file__ = str(src_path)
    exec(compile(src, str(src_path), "exec"), mod.__dict__)
    return mod


# --------------------------------------------------------------------------- #
# Comparison                                                                   #
# --------------------------------------------------------------------------- #
def same(a, b) -> bool:
    """Float equality, with NaN treated as reproducing NaN.

    A fold whose selected config took fewer than two trades out of sample
    reports NaN for every ratio metric. Under IEEE-754 ``nan != nan``, so a
    naive ``==`` would report a mismatch where the two runs in fact agree.
    """
    if isinstance(a, float) and isinstance(b, float) and a != a and b != b:
        return True
    return a == b


def parse_label(label: str) -> dict:
    """Recover a full config dict from the artifact's printed label."""
    m = MOM.match(label)
    if m:
        direction, hma, atr, trail, min_atr = m.groups()
        return dict(mode="momentum", hma=int(hma), atr=int(atr), stoch_k=0,
                    zone=None, sl=0.0, tp=0.0, trail=float(trail),
                    direction=direction, min_atr=float(min_atr))
    m = PUL.match(label)
    if not m:
        raise SystemExit(f"unparsed config label: {label!r}")
    direction, hma, atr, k, z0, z1, sl, tp, min_atr = m.groups()
    return dict(mode="pullback", hma=int(hma), atr=int(atr), stoch_k=int(k),
                zone=(float(z0), float(z1)), sl=float(sl), tp=float(tp),
                trail=0.0, direction=direction, min_atr=float(min_atr))


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mtime(path: pathlib.Path) -> str:
    return subprocess.run(["stat", "-c", "%y", str(path)],
                          capture_output=True, text=True).stdout.strip()


def simulate(engine, sweep, bars, cfg: dict) -> tuple[dict, dict]:
    """Run one config, returning the raw sim (with records) and its metrics."""
    hma_v = engine.hma(bars.close, cfg["hma"])
    atr_v = engine.atr(bars.high, bars.low, bars.close, cfg["atr"])
    if cfg["mode"] == "pullback":
        k, d = engine.stochastic(bars.high, bars.low, bars.close, cfg["stoch_k"],
                                 sweep.STOCH_D, sweep.STOCH_SMOOTH)
        long_sig, short_sig = engine.pullback_signals(
            bars, hma_v, k, d, cfg["zone"][0], cfg["zone"][1])
    else:
        long_sig, short_sig = engine.momentum_signals(bars, hma_v)
    direction = cfg["direction"]
    sim = engine.simulate(bars, cfg["mode"], hma_v, atr_v, long_sig, short_sig,
                          enable_long=direction in ("both", "long"),
                          enable_short=direction in ("both", "short"),
                          sl_mult=cfg["sl"], tp_mult=cfg["tp"],
                          trail_mult=cfg["trail"], risk_pct=sweep.RISK_PCT,
                          min_atr=cfg["min_atr"], max_dd_halt=1.0)
    price = engine.metrics(sim, basis="price")
    account = engine.metrics(sim, basis="account")
    return sim, {"n_trades": price["n_trades"], "sharpe": price["sharpe"],
                 "max_dd": price["max_dd"],
                 "profit_factor": price["profit_factor"],
                 "win_rate": price["win_rate"], "cagr_acct": account["cagr"],
                 "max_dd_acct": account["max_dd"]}


def ensure_pytz() -> None:
    """Make `pytz` importable if the interpreter lacks it.

    `research.post.sweeps.data` imports pytz for one exception class without
    declaring it anywhere, and pandas 3 no longer pulls it in. Rather than add
    a dependency to this repo for a module belonging to another one, fall back
    to the system site-packages, appended so it cannot shadow the venv.
    """
    try:
        import pytz  # noqa: F401
    except ModuleNotFoundError:
        for candidate in ("/usr/lib/python3/dist-packages",):
            if pathlib.Path(candidate, "pytz").is_dir():
                sys.path.append(candidate)
                return
        raise SystemExit(
            "pytz is required by research.post.sweeps.data and is not importable")


def regenerate(wmps: pathlib.Path) -> tuple[dict, list[str]]:
    """Re-run every stored fold; return the records and any mismatches."""
    ensure_pytz()
    sys.path.insert(0, str(wmps))
    engine = load_instrumented_engine(wmps)
    from research.post.sweeps import cnk_nested_wf as wf
    from research.post.sweeps import run_cnk_sweep as sweep
    from research.post.sweeps.data import load

    art_dir = wmps / "research" / "data" / "crest_n_keel"
    failures: list[str] = []
    out: dict = {}

    for tf in ("H1", "H4"):
        stored = json.loads((art_dir / f"cnk_nested_wf_{tf}.json").read_text())
        df = load(tf)
        folds = wf._folds(df, tf)
        if len(folds) != len(stored["folds"]):
            failures.append(f"{tf}: recomputed {len(folds)} folds, "
                            f"stored has {len(stored['folds'])}")
            continue

        tf_out = []
        for i, (fold, sf) in enumerate(zip(folds, stored["folds"])):
            tr_start, tr_end, te_end = fold
            for got, want, name in (
                    (str(tr_start.date()), sf["train_start"], "train_start"),
                    (str(tr_end.date()), sf["train_end"], "train_end"),
                    (str(te_end.date()), sf["test_end"], "test_end")):
                if got != want:
                    failures.append(f"{tf} fold {i}: {name} {got} != {want}")

            test_df = df.loc[(df.index >= tr_end) & (df.index < te_end)]
            bars = engine.Bars(test_df)
            entry = {"fold": i, "train_start": sf["train_start"],
                     "train_end": sf["train_end"], "test_end": sf["test_end"]}

            selected = sf.get("selected")
            if selected is None:
                entry["selected"] = None
            else:
                cfg = parse_label(selected["config"])
                if wf._label(cfg) != selected["config"]:
                    failures.append(f"{tf} fold {i}: label round-trip produced "
                                    f"{wf._label(cfg)!r}")
                sim, stats = simulate(engine, sweep, bars, cfg)
                for stored_key, stat_key in SELECTED_FIELDS:
                    if not same(stats[stat_key], selected[stored_key]):
                        failures.append(
                            f"{tf} fold {i} selected.{stored_key}: "
                            f"{stats[stat_key]!r} != {selected[stored_key]!r}")
                entry["selected"] = {"config": selected["config"], **cfg,
                                     "stats": stats, "trades": sim["records"]}

            fixed = sf.get("fixed")
            if fixed:
                cfg = wf.FIXED_LEADER[tf]
                sim, stats = simulate(engine, sweep, bars, cfg)
                for stored_key, stat_key in FIXED_FIELDS:
                    if not same(stats[stat_key], fixed[stored_key]):
                        failures.append(
                            f"{tf} fold {i} fixed.{stored_key}: "
                            f"{stats[stat_key]!r} != {fixed[stored_key]!r}")
                entry["fixed"] = {"config": wf._label(cfg), **cfg,
                                  "stats": stats, "trades": sim["records"]}

            tf_out.append(entry)
            print(f"  {tf} fold {i:>2}/{len(folds)} checked", flush=True)
        out[tf] = tf_out
    return out, failures


def build_document(wmps: pathlib.Path, folds: dict) -> dict:
    art_dir = wmps / "research" / "data" / "crest_n_keel"
    sweeps = wmps / "research" / "post" / "sweeps"
    n_trades = sum(len(arm["trades"]) for tf in folds for fold in folds[tf]
                   for arm in (fold.get("selected"), fold.get("fixed")) if arm)
    return {
        "fixture": "t9b_crest_n_keel_maskoff",
        "hypothesis_id": "crest_n_keel",
        "seq": 49,
        "seq_note": "Registered at seq=47, result recorded at seq=49.",
        "mode": "mask_off",
        "provenance": "REGENERATED_FROM",
        "provenance_note": (
            "This is a DERIVED fixture, not the original artifact. The stored "
            "nested walk-forward artifacts record per-fold statistics only; no "
            "artifact in either repository contains trade-for-trade records, so "
            "X15b's trade-level assertions had nothing to assert against. These "
            "records were regenerated by re-running each fold's recorded config "
            "on its own untouched test window, and were admitted only because "
            "every fold boundary and every recorded statistic came back "
            "identical to the stored artifact under float equality."),
        "source_artifacts": [
            {"id": f"cnk_nested_wf_{tf}.json",
             "path": f"research/data/crest_n_keel/cnk_nested_wf_{tf}.json",
             "repo": "wine-mt5-python-setup",
             "tracked_in_git": False,
             "gitignored_by": ".gitignore:123 research/data/*",
             "sha256": sha256(art_dir / f"cnk_nested_wf_{tf}.json"),
             "mtime": mtime(art_dir / f"cnk_nested_wf_{tf}.json")}
            for tf in ("H1", "H4")],
        "regenerated": {
            "date": "2026-09-17",
            "repo": "wine-mt5-python-setup",
            "commit": WMPS_COMMIT,
            "generating_modules": [
                {"path": f"research/post/sweeps/{name}",
                 "sha256": sha256(sweeps / name)}
                for name in ("cnk_engine.py", "cnk_nested_wf.py")],
            "instrumentation": (
                "cnk_engine.simulate was patched in memory to also return entry "
                "and exit price, direction, lots, size_oz, effective_atr, sl, tp "
                "and the pnl decomposition. The patch adds recording only; that "
                "it changes no arithmetic is what the exact statistic match "
                "below demonstrates."),
            "not_the_original_stack": (
                "cnk_engine.py was UNTRACKED when the artifact was produced on "
                "2026-08-23 — it was first committed on 2026-09-01 in 81e38c0 — "
                "and the generating virtualenv no longer exists. There is "
                "therefore no recorded frozen stack to re-run. A match "
                "establishes de facto equivalence of today's committed code to "
                "whatever produced the artifact; it does not prove the two "
                "stacks were identical."),
            "what_was_not_reproduced": (
                "Selection. Each fold's config was read back from its stored "
                "label rather than re-derived by re-running the 30,132-config "
                "grid on the training window, and the rng-dependent `pool` "
                "control arm was not regenerated. What is verified is the "
                "simulation path, which is what X15b asserts on."),
        },
        "verification": {
            "folds_checked": sum(len(v) for v in folds.values()),
            "fold_boundaries_matched": True,
            "statistics_matched": True,
            "float_equality": True,
            "nan_convention": (
                "NaN is treated as reproducing NaN. H4 fold 11's selected config "
                "takes 1 out-of-sample trade, so every ratio metric is NaN in "
                "both the stored artifact and the regeneration; `nan != nan` "
                "would otherwise report a mismatch where the runs agree."),
            "compared_fields": {
                "selected": [k for k, _ in SELECTED_FIELDS],
                "fixed": [k for k, _ in FIXED_FIELDS]},
            "trade_records": n_trades,
        },
        "folds": folds,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wmps", type=pathlib.Path, default=DEFAULT_WMPS,
                    help="path to the wine-mt5-python-setup checkout")
    args = ap.parse_args()

    folds, failures = regenerate(args.wmps)
    if failures:
        print(f"\nGATE FAILED — {len(failures)} mismatch(es); nothing written:")
        for line in failures[:40]:
            print("  " + line)
        return 1

    doc = build_document(args.wmps, folds)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, separators=(",", ":")))
    print(f"\nGATE PASSED — {doc['verification']['folds_checked']} folds, every "
          f"boundary and statistic reproduced exactly")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.2f} MB, "
          f"{doc['verification']['trade_records']} trade records)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
