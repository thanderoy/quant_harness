# Signal-Edge Tool — Calibration Results

Calibration artifact for `research/pre/signal_edge.py`. This records what the
E-Ratio tool reports on known reference strategies, so we can trust (or
distrust) its output on novel signals.

- **Data:** `research/data/XAUUSD_H1.csv`, XAUUSD H1, 2004-06-11 → 2020-12-30
  (`95,832` bars after the 2004–2020 filter).
- **Settings:** `atr_period=14`, `forward_windows=[10, 30, 70]`,
  `n_permutations=1000`, `random_seed=42`.
- **Reproduce:** `research/.venv/bin/python -m pytest research/tests/test_signal_edge.py -k "calibration or weak or control"`

---

## Summary

| Signal | N (L/S) | E-Ratio 10 / 30 / 70 | p-value 10 / 30 / 70 | Baseline ER 10/30/70 | Verdict |
|---|---|---|---|---|---|
| `crest_n_keel` (HMA-55 + Stoch cross) | 166 (65/101) | 0.90 / 0.79 / 0.82 | 0.82 / 0.98 / 0.95 | 0.88 / 0.91 / 0.87 | **No standalone entry edge** |
| `ebb_n_flow` (BB-lower + ER<0.30, long) | 4243 (4243/0) | 0.97 / 0.99 / 1.04 | 0.74 / 0.76 / 0.72 | 0.99 / 1.00 / 1.06 | **Weak (as expected)** |
| `donchian_50_breakout` (positive control, long) | 3806 (3806/0) | 1.11 / 1.12 / 1.17 | 0.00 / 0.00 / 0.00 | 0.98 / 1.03 / 1.07 | **Strong, significant** |

E-Ratio = mean(norm-MFE) / mean(norm-MAE); p-value is the one-sided fraction of
the permuted null ≥ the actual E-Ratio. "Baseline ER" is a single random-entry
realisation at the same long/short frequency.

---

## Test 3 — `crest_n_keel` (the surprising result)

**Expected by the original spec:** E-Ratio > 1.15 at ≥1 window, p < 0.05 —
because this entry was assumed to underpin a strategy with a validated
Sharpe ≈ 1.76.

**Premise falsified.** The original E-Ratio expectation (>1.15) was derived
assuming a validated Sharpe ≈ 1.76. That figure has been falsified by
walk-forward harness validation (OOS Sharpe ~0.3–0.4, DSR fails — see
`research/log` seq=29). The E-Ratio measurement of <1.0 is therefore consistent
with the strategy's actual edge profile, not contradictory to it. The entry has
no standalone edge, and the exit asymmetry does not raise the full-strategy
Sharpe above DSR significance either.

**Measured:** E-Ratio **below 1.0** at every window (0.79–0.90), p-values
0.82–0.98 (the actual statistic sits in the *left* half of the null, i.e. the
entry is marginally *adverse*, not edged). Forward returns are negative at all
windows (−7 to −12 bp). The result is stable across HMA periods 16/21/34/55 and
holds when longs and shorts are measured separately (long-only ER ≈ 0.96,
short-only ER ≈ 0.86 at w=10).

### Is this a tool bug? No.

We ruled out the tool before trusting the finding:

1. **Random entries → E-Ratio ≈ 1.0, p > 0.05** (Test 1). No false edge.
2. **Synthetic +2 ATR / −0.5 ATR construction → E-Ratio ≈ 4.0** (Test 2). The
   MFE/MAE mechanics are correct.
3. **Look-ahead probe is clean** (Test 6): ATR[t] and per-signal MFE/MAE are
   invariant to truncating the future.
4. **Positive control on the *same real data*** — a 50-bar Donchian breakout —
   produces E-Ratio 1.11 → 1.17 rising with horizon, **p = 0.000**. The tool
   *can and does* detect genuine edge on this exact XAUUSD series.

So the measurement is sound: **the HMA + Stochastic entry has no standalone
forward-return asymmetry.**

### Interpretation

The original intuition — "high Sharpe ⟹ entry E-Ratio > 1.15" — is **falsified**.
Entry edge and strategy edge are decoupled, which is precisely the premise this
tool was built to expose. For `crest_n_keel`, the profit is manufactured by the
**exit/risk layer**, not the entry:

- It is a trend-pullback entry (HMA rising + stochastic crossing up out of
  oversold). Buying a pullback inside an uptrend means price often dips *further*
  immediately after entry — hence E-Ratio slightly < 1 over the next 10–70 bars.
- The strategy's `SL = 1.5·ATR`, `TP = 3.0·ATR` exit imposes a 2:1 reward:risk
  *asymmetry that the raw entry does not have*, and the HMA trend filter keeps it
  on the right side of multi-day moves that mature well beyond a 70-bar window.

**Consequence for how we use this tool:** the E-Ratio gate must **not** be used
to *reject* trend-pullback entries that are designed to be carried by an
asymmetric exit. It is a clean gate for **breakout / continuation** ideas (where
the entry itself should show forward asymmetry, as the Donchian control does) and
a **diagnostic**, not a veto, for mean-reversion/pullback entries. A weak
E-Ratio on a profitable strategy is a *useful* signal: it tells us the edge is in
the exits, so that is where robustness testing should focus.

---

## Test 4 — `ebb_n_flow` (expected weak, confirmed weak)

**Expected:** E-Ratio < 1.10 OR p > 0.10 — this strategy failed full
backtesting (PF 0.76, SQN −2.36).

**Measured:** E-Ratio 0.97 / 0.99 / 1.04, p 0.74 / 0.76 / 0.72. Best E-Ratio
(1.04) is under 1.10 **and** every p-value is well above 0.10. The Bollinger
lower-band + low-efficiency-ratio entry has no significant forward asymmetry,
consistent with its failed backtest. Mild positive forward returns at longer
windows (≈ 18 bp at w=70) are explained by the 2004–2020 gold uptrend, not the
signal — the random long-only baseline matches it (ER 1.06 at w=70).

This is the reassuring half of the calibration: a known-bad signal reads as bad,
and the reading is *not* contradicted by a known-good full strategy. Unlike
`crest_n_keel`, `ebb_n_flow` has neither entry edge nor a profitable exit — so
here a weak E-Ratio correctly anticipates the strategy's failure.

---

## Takeaways

1. The tool is **validated**: it flags real edge (Donchian control, p=0.000),
   stays neutral on noise (random ≈ 1.0), and is free of look-ahead.
2. E-Ratio is a **continuation-edge** detector. Use it as a hard gate for
   breakout/momentum entries; use it as a *diagnostic* (not a veto) for
   pullback/mean-reversion entries whose edge is intended to come from exits.
3. The most actionable finding: a profitable strategy (`crest_n_keel`) with a
   near-1.0 entry E-Ratio is telling us **the exits are doing the work** — focus
   robustness/sensitivity testing there, and treat the entry as replaceable.
