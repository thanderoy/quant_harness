"""research.post.sweeps.build_momentum_report — HTML report for the H1
intraday-momentum finding (research log seq 57-62).

Reads the artefacts produced by feature_screen / feature_combine /
momentum_nested_wf / momentum_cost_stress / momentum_dsr and renders a
single self-contained page using the shared report_style shell.
"""
from __future__ import annotations

import json
from pathlib import Path

from research.post.sweeps.report_style import HEAD

ART = Path(__file__).resolve().parents[2] / "pre" / "artifacts"
OUT = Path(__file__).resolve().parents[1] / "artifacts" / "momentum_report.html"

COST_MULTS = [1.0, 1.5, 2.0, 3.0, 4.0]
SLIPS = [0.0, 0.05, 0.1, 0.2]
DSR_NS = ["1", "21", "126", "276"]
DSR_THRESHOLD = 0.95


def _load(name: str) -> dict:
    return json.loads((ART / name).read_text())


def _sign(v: float) -> str:
    return "pos" if v > 0 else ("neg" if v < 0 else "muted")


def _bar(v: float, scale: float = 1.8) -> str:
    pct = min(abs(v) / scale, 1.0) * 100
    return f'<span class="bar"><span class="bt {_sign(v)}" style="width:{pct:.0f}%"></span></span>'


def gate_rows(summary: dict, stress: dict, dsr: dict) -> str:
    unf = dsr["variants"]["unfiltered"]
    gates = [
        ("M1", "Out-of-sample folds are positive",
         f'Mean OOS Sharpe +{summary["m1_mean"]:.3f}, median +{summary["m1_median"]:.3f}, '
         f'{summary["m1_positive"]}/{summary["n_folds"]} folds above zero.', True),
        ("M2", "The selection beats its own candidate pool",
         f'Selected config beat the fold pool median in {summary["m2_wins"]}/{summary["m2_n"]} folds '
         f'(sign p={summary["m2_p"]:.4f}, Wilcoxon p=0.0056). Mean margin +{summary["mean_diff"]:.3f}.', True),
        ("M3", "Selection lookahead is small",
         f'Fixed-parameter run scores +{summary["fixed_mean"]:.3f} against the nested +{summary["m1_mean"]:.3f} '
         f'— leakage of {summary["leakage"]:.3f} Sharpe, versus 0.7-0.8 measured at seq=49.', True),
        ("M4", "The chosen horizon is stable across folds",
         f'Horizon h=12 was selected in 17/17 folds. Feature choice concentrates on the momentum '
         f'family ({summary["momentum_picks"]}/{summary["n_folds"]} picks).', True),
        ("M5", "The edge survives realistic costs",
         f'At modelled cost with swap the unfiltered rule holds +{stress["swap=on|mult=1.0|slip=0.0"]["mean_sharpe"]:.3f}; '
         f'breakeven sits near 3-4x cost. Cost has genuine headroom.', True),
        ("DSR", "Deflated Sharpe clears the pre-registered threshold",
         f'Per-observation Sharpe {unf["per_obs_sharpe"]:.4f} over {unf["n_trades"]} OOS trades gives '
         f'DSR {unf["dsr"]["126"]:.3f} at N=126 and {unf["dsr"]["276"]:.3f} at N=276, against a '
         f'{DSR_THRESHOLD} threshold.', False),
    ]
    out = []
    for gid, title, body, passed in gates:
        state = "pass" if passed else "fail"
        label = "Pass" if passed else "Fail"
        out.append(
            f'<div class="krow {state}"><div class="kid">{gid}</div>'
            f'<div><h3>{title}</h3><p>{body}</p></div>'
            f'<div class="kstate"><span class="pill {state}">{label}</span></div></div>'
        )
    return '<div class="kgrid">' + "".join(out) + "</div>"


def feature_table(comb: dict) -> str:
    rows = []
    for feat, d in comb["individual"].items():
        rows.append(
            f'<tr><td class="tf">{feat}</td>'
            f'<td class="num">{d["n"]:,}</td>'
            f'<td class="num">{d["spread_usd_per_oz"]:.3f}</td>'
            f'<td class="num barcell {_sign(d["net_usd_per_oz"])}">{d["net_usd_per_oz"]:+.3f}'
            f'{_bar(d["net_usd_per_oz"], 2.6)}</td>'
            f'<td class="num">{d["nw_t"]:.2f}</td>'
            f'<td class="num">{d["monotonicity"]:+.2f}</td></tr>'
        )
    for key, label in (("composite_momentum", "composite (momentum only)"),
                       ("composite_all", "composite (all five)")):
        d = comb[key]
        rows.append(
            f'<tr><td class="cfg">{label}</td>'
            f'<td class="num">{d["n"]:,}</td>'
            f'<td class="num">{d["spread_usd_per_oz"]:.3f}</td>'
            f'<td class="num hl">{d["net_usd_per_oz"]:+.3f}</td>'
            f'<td class="num">{d["nw_t"]:.2f}</td>'
            f'<td class="num">{d["monotonicity"]:+.2f}</td></tr>'
        )
    return (
        '<div class="scroll"><table><thead><tr>'
        '<th>Feature</th><th class="num">Bars</th><th class="num">Gross $/oz</th>'
        '<th class="num">Net of cost $/oz</th><th class="num">NW t</th>'
        '<th class="num">Decile monotonicity</th>'
        '</tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"
    )


def fold_table(folds: list) -> str:
    rows = []
    for i, f in enumerate(folds, 1):
        s = f["selected"]
        oos = s["oos_sharpe"]
        pool = f["pool"]["median"]
        rows.append(
            f'<tr><td class="num muted">{i}</td>'
            f'<td class="cfg">{f["train_end"]} &rarr; {f["test_end"]}</td>'
            f'<td class="tf">{s["feature"]}</td>'
            f'<td class="num">{s["horizon"]}</td>'
            f'<td class="num">{"yes" if s["regime_filter"] else "no"}</td>'
            f'<td class="num muted">{s["train_sharpe"]:+.2f}</td>'
            f'<td class="num barcell {_sign(oos)}">{oos:+.3f}{_bar(oos)}</td>'
            f'<td class="num">{s["oos_trades"]}</td>'
            f'<td class="num {_sign(pool)}">{pool:+.3f}</td></tr>'
        )
    return (
        '<div class="scroll"><table><thead><tr>'
        '<th class="num">#</th><th>Test window</th><th>Feature picked</th>'
        '<th class="num">h</th><th class="num">Low-vol filter</th>'
        '<th class="num">Train SR</th><th class="num">OOS SR</th>'
        '<th class="num">Trades</th><th class="num">Pool median</th>'
        '</tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"
    )


def cost_table(res: dict, swap: str) -> str:
    rows = []
    for m in COST_MULTS:
        cells = []
        for s in SLIPS:
            v = res[f"swap={swap}|mult={m}|slip={s}"]
            cls = "hl" if (m == 1.0 and s == 0.0) else _sign(v["mean_sharpe"])
            cells.append(
                f'<td class="num {cls}">{v["mean_sharpe"]:+.3f}'
                f'<span class="muted"> &middot; {v["folds_positive"]}/17</span></td>'
            )
        rows.append(f'<tr><td class="tf">{m:g}&times;</td>' + "".join(cells) + "</tr>")
    heads = "".join(f'<th class="num">slip ${s:.2f}/oz</th>' for s in SLIPS)
    return (
        '<div class="scroll"><table><thead><tr><th>Cost multiple</th>'
        + heads + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def dsr_table(dsr: dict) -> str:
    rows = []
    for key, label in (("unfiltered", "Unfiltered"), ("lowvol_filter", "Low-volatility filter")):
        v = dsr["variants"][key]
        cells = []
        for n in DSR_NS:
            val = v["dsr"][n]
            cls = "pos" if val >= DSR_THRESHOLD else "neg"
            cells.append(f'<td class="num {cls}">{val:.4f}</td>')
        rows.append(
            f'<tr><td class="tf">{label}</td>'
            f'<td class="num">{v["n_trades"]:,}</td>'
            f'<td class="num">{v["per_obs_sharpe"]:.4f}</td>' + "".join(cells) + "</tr>"
        )
    heads = "".join(f'<th class="num">N={n}</th>' for n in DSR_NS)
    return (
        '<div class="scroll"><table><thead><tr><th>Variant</th>'
        '<th class="num">OOS trades</th><th class="num">Per-obs Sharpe</th>'
        + heads + "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def build() -> Path:
    comb = _load("feature_combine.json")
    summary = _load("momentum_nested_summary.json")
    wf = _load("momentum_nested_wf.json")
    stress_u = _load("momentum_cost_stress_nolowvol.json")
    stress_f = _load("momentum_cost_stress.json")
    dsr = _load("momentum_dsr.json")
    null = _load("momentum_null_calibration.json")
    nf = null["streams"]["fixed"]
    nn = null["streams"]["nested"]

    unf = dsr["variants"]["unfiltered"]
    html = f"""<title>H1 Intraday Momentum</title>
{HEAD}
<div class="wrap">
<header class="hero">
  <p class="eyebrow">Research log seq 57&ndash;62 &middot; XAUUSD H1</p>
  <h1>A real effect we cannot reliably find</h1>
  <p class="lede">An H1 intraday-momentum rule survived nested walk-forward selection
  and 2&ndash;3&times; cost stress. The Deflated Sharpe gate rejected it &mdash; and
  that gate turned out to be measuring the wrong thing. A purpose-built permutation
  null says the effect is real at p=0.010, and that the procedure which would have
  found it is not.</p>
  <div class="meta">
    <span><b>Instrument</b> XAUUSD</span>
    <span><b>Timeframe</b> H1</span>
    <span><b>Folds</b> {summary['n_folds']} nested</span>
    <span><b>OOS trades</b> {unf['n_trades']:,}</span>
    <span><b>Permutation null</b> p=0.010 fixed / 0.105 nested</span>
    <span><b>Verdict</b> Do not promote</span>
  </div>
</header>

<section>
  <h2>The rule</h2>
  <p class="sub">Frozen before the walk-forward ran</p>
  <div class="prose">
  <p>The simplest expression of the effect the feature screen surfaced. No stop, no
  target, no sizing logic, no re-entry &mdash; deliberately, so that anything the rule
  earns is attributable to the entry signal rather than to an exit that happens to
  be well tuned.</p>
  </div>
  <pre><code>feature       intraday_ret  (return from the session's first bar)
entry         long when the causal expanding percentile of the feature >= 0.90
hold          {dsr['horizon']} bars, then exit at market
direction     long only
stop / target none
sizing        constant
costs         $0.29/oz round trip (spread $0.22 + commission $0.07)</code></pre>
  <p class="note">The percentile is computed on an expanding window from history
  available at the bar, not with <code>pd.qcut</code> over the full sample. That
  distinction is worth about 0.15 Sharpe and is the difference between a causal
  rule and a mildly lookahead one.</p>
</section>

<section>
  <h2>Where the feature came from</h2>
  <p class="sub">264 screen tests &rarr; 186 FDR-significant &rarr; 22 that pay costs</p>
  <div class="prose">
  <p>A broad screen tested candidate features for forward predictive content across
  M5, M15 and H1. Statistical significance was abundant and almost meaningless:
  186 of 264 tests survived Benjamini&ndash;Hochberg FDR control. Only 22 produced a
  top-versus-bottom decile spread large enough to pay the $0.29/oz round trip,
  and 21 of those 22 were on H1. M5 produced <em>none</em> &mdash; which is the
  direct answer to the scalping preference: at this instrument's cost structure,
  the shorter the timeframe, the more completely costs eat the signal.</p>
  </div>
  {feature_table(comb)}
  <p class="note">Spreads are top-decile minus bottom-decile forward return over
  12 bars, in dollars per ounce. Newey&ndash;West t-statistics correct for the
  overlapping windows. The five surviving features are highly collinear
  (Spearman 0.59&ndash;0.84), so they are variations on one effect, not five
  independent edges &mdash; which is why the composite adds nothing over
  <code>intraday_ret</code> alone.</p>
</section>

<section>
  <h2>Gate results</h2>
  <p class="sub">Five pre-registered checks, plus the Deflated Sharpe threshold</p>
  {gate_rows(summary, stress_u['results'], dsr)}
</section>

<section>
  <h2>Nested walk-forward, fold by fold</h2>
  <p class="sub">Feature and horizon re-selected inside every training window</p>
  <div class="prose">
  <p>Each fold trains on four years, selects a feature/horizon/filter combination
  from the candidate pool using training data only, then trades that choice forward
  for one year. The pool median column is the honest control: it shows what a
  randomly chosen candidate from the same pool would have earned in the same window.</p>
  </div>
  {fold_table(wf['folds'])}
  <p class="note">Train-to-OOS decay is {summary['train_mean']:.3f} &rarr;
  {summary['m1_mean']:.3f}. Selection lookahead measured against a fixed-parameter
  run is {summary['leakage']:.3f} Sharpe &mdash; compare seq=49, where
  top-of-grid selection carried 0.7&ndash;0.8 of pure lookahead and no
  out-of-sample information at all.</p>
</section>

<section>
  <h2>Cost stress</h2>
  <p class="sub">Mean OOS Sharpe and folds positive, swap costs included</p>
  <div class="prose">
  <p>Broker cost was multiplied up to 4&times; and per-side slippage added on top,
  with overnight swap charged at &minus;$10/lot/night long and triple on Wednesdays.
  A rule that dies at 1.1&times; cost is not tradeable; this one holds to roughly
  3&ndash;4&times;.</p>
  </div>
  <h3>Unfiltered &mdash; {stress_u['results']['swap=on|mult=1.0|slip=0.0']['trades']:,} trades</h3>
  {cost_table(stress_u['results'], 'on')}
  <h3>Low-volatility filter &mdash; {stress_f['results']['swap=on|mult=1.0|slip=0.0']['trades']:,} trades</h3>
  {cost_table(stress_f['results'], 'on')}
  <p class="note">The filtered variant starts lower but degrades more slowly, crossing
  above the unfiltered version at roughly 2&times; cost plus $0.10 slippage. Under the
  modelled cost structure the unfiltered variant is the better choice, and its larger
  trade count also makes every downstream statistic less fragile.</p>
</section>

<section>
  <h2>Deflated Sharpe &mdash; the gate it fails</h2>
  <p class="sub">Computed on concatenated out-of-sample fold returns</p>
  {dsr_table(dsr)}
  <div class="callout warn">
  <p><strong>It fails at every trial count except N=1.</strong> The per-observation
  Sharpe of {unf['per_obs_sharpe']:.4f} annualises to roughly 0.55 at ~52 trades a
  year, consistent with the walk-forward's +{summary['m1_mean']:.3f}. The effect is
  genuine &mdash; it survived nested selection at p={summary['m2_p']:.4f} against a
  pool control, and 2&ndash;3&times; cost stress. It is also <em>small</em>, and DSR
  asks whether a Sharpe that size could be the best of N tries under a null. At
  N=126 it could be.</p>
  </div>
  <div class="prose">
  <p>One caveat runs the other way, and it is not an escape hatch. DSR assumes the
  Sharpe was selected as the maximum of N trials <em>on the data it is measured on</em>.
  These are out-of-sample returns from a procedure that did its selecting inside
  training windows, so the haircut is arguably too harsh here. That is a reason to
  read the number carefully. It is not a reason to waive a pre-registered threshold
  because the result is one we would like to keep &mdash; which is precisely the
  failure mode the research log exists to prevent.</p>
  </div>
</section>

<section>
  <h2>The gate itself was wrong</h2>
  <p class="sub">Three defects, found by calibrating rather than arguing</p>
  <div class="prose">
  <p>Asking whether a threshold is too strict, immediately after a result you liked
  failed it, is the worst possible moment to move it. So the question was settled by
  measurement, with the acceptance rule fixed in advance. Three things turned out to be
  wrong &mdash; and only one of them made the gate too harsh.</p>
  </div>
  <div class="kgrid">
    <div class="krow fail"><div class="kid">1</div><div>
      <h3>We were on the lenient branch, not the strict one</h3>
      <p>No <code>trial_sharpes</code> was passed, so the calculation silently took the
      estimated Var(SR) path. The module's own docstring calls that &ldquo;a leniency
      that should be flagged&rdquo;. Using per-fold Sharpes instead gives DSR 0.0099 at
      N=21 and 0.0000 at N=126, against the 0.766 and 0.514 reported. Neither path is
      unambiguously right &mdash; and a verdict that swings from 0.51 to 0.00 on an
      unobservable choice is not measuring the strategy.</p>
    </div><div class="kstate"><span class="pill fail">Lenient</span></div></div>
    <div class="krow fail"><div class="kid">2</div><div>
      <h3>The gate had almost no power</h3>
      <p>Bootstrapped at 4,000 replications: at N=126 the false-positive rate is 0.0000
      and power at the observed effect size is 0.061. A real edge of exactly this size
      would have failed roughly 94% of the time. Gold's own buy-and-hold &mdash; +1,173%
      over 21 years, annualised Sharpe 0.744 &mdash; scores 0.811 at N=126 and also
      fails.</p>
    </div><div class="kstate"><span class="pill fail">No power</span></div></div>
    <div class="krow fail"><div class="kid">3</div><div>
      <h3>It benchmarked against zero on a long-only rule</h3>
      <p>The permutation null's mean is <strong>+0.011</strong>, not zero: a long-only
      rule on a drifting instrument earns a Sharpe from drift alone even after every
      trace of intraday predictability is destroyed. About 14% of the raw statistic is
      drift capture that a zero-benchmark test never subtracts.</p>
    </div><div class="kstate"><span class="pill fail">Wrong null</span></div></div>
  </div>
</section>

<section>
  <h2>The replacement, and what it found</h2>
  <p class="sub">200 permutation runs of the entire pipeline &middot; rule fixed before results</p>
  <div class="prose">
  <p>The null needs neither a trial count nor a Var(SR) choice. Bar order is permuted
  <em>within each trading day</em>, so the daily return distribution, volatility
  clustering, bar geometry, volume and session structure all survive, but no first-bar
  return can predict what follows. The whole pipeline &mdash; feature build, nested
  training selection, out-of-sample concatenation &mdash; is then re-run on each
  permuted history.</p>
  </div>
  <div class="scroll"><table><thead><tr>
    <th>Stream</th><th class="num">Observed</th><th class="num">Null mean</th>
    <th class="num">Null q95</th><th class="num">Excess</th><th class="num">p</th><th>Result</th>
  </tr></thead><tbody>
    <tr><td class="tf">fixed</td>
      <td class="num hl">{nf['observed']:.5f}</td>
      <td class="num">{nf['null_mean']:+.5f}</td>
      <td class="num">{nf['null_q95']:+.5f}</td>
      <td class="num pos">2.93 sd</td>
      <td class="num pos">{nf['p_value']:.4f}</td>
      <td><span class="pill pass">Pass</span></td></tr>
    <tr><td class="tf">nested</td>
      <td class="num hl">{nn['observed']:.5f}</td>
      <td class="num">{nn['null_mean']:+.5f}</td>
      <td class="num">{nn['null_q95']:+.5f}</td>
      <td class="num">1.23 sd</td>
      <td class="num neg">{nn['p_value']:.4f}</td>
      <td><span class="pill fail">Fail</span></td></tr>
  </tbody></table></div>
  <p class="note"><code>fixed</code> is the frozen intraday_ret/h=12 rule &mdash; the
  statistic the Deflated Sharpe actually evaluated. <code>nested</code> lets each fold
  select freely from all 126 candidates, so it is the stream carrying the cost of
  choosing. Only 1 of 200 permuted histories reached the fixed rule's result; 20 of 200
  reached the nested one.</p>
  <div class="callout warn">
  <p><strong>The streams split, and the pre-registration did not say which one wins.</strong>
  That is a defect in the pre-registration, and not one that can be resolved by picking
  the stream that gives the answer we want after seeing both. Resolving it on the text
  that was actually written: the pre-registration describes the nested stream as
  &ldquo;the selection procedure itself, which is what carries the selection cost&rdquo;.
  Nested is decisive. The rule does not clear the bar.</p>
  </div>
</section>

<section>
  <h2>Verdict</h2>
  <p class="sub">What this licenses, and what it does not</p>
  <div class="callout">
  <p><strong>Do not promote &mdash; but not for the reason originally given.</strong>
  The effect is real: the fixed rule beats its own permutation null at p=0.010, nearly
  three null standard deviations clear, against a benchmark that already includes the
  drift a long-only rule captures for free. The Deflated Sharpe score of 0.514
  understated the evidence.</p>
  <p>What fails is <em>recoverability</em>. Selecting freely per fold yields 0.037
  against a null whose 95th percentile is 0.044. The effect is real conditional on
  already knowing to freeze <code>intraday_ret</code> at h=12 &mdash; and that knowledge
  came from a screen run over the full sample, including every test window. The
  procedure that would have discovered it honestly does not beat chance.</p>
  </div>
  <div class="prose">
  <p>This is the same finding as seq=49, where the nested walk-forward on
  <code>crest_n_keel</code> showed training rank carried no information about the test
  window (p=0.430). Two unrelated hypothesis families, different machinery, same lesson.
  The momentum feature family is markedly more informative than the crest_n_keel grid
  &mdash; 0.105 against 0.430 &mdash; and still does not clear 0.05.</p>
  <p>One path is now closed for good. Resolving this on forward data is clean in
  principle, but the rule trades about 54 times a year and roughly 3,000 trades are
  needed before the question is answerable. That is decades; anyone proposing to wait is
  proposing something that does not terminate. More instruments would work. Higher
  frequency would not &mdash; the screen found <strong>zero</strong> features paying the
  $0.29/oz round trip at M5. Scalping XAUUSD at this cost structure is arithmetic, not
  tuning.</p>
  <p>Separately, <code>crest_n_keel</code> (magic 1100001) and <code>asqs</code> are
  still running on demo on premises this programme has refuted, and
  <code>zerolag_chandelier</code> has never had a nested walk-forward at all &mdash; its
  honest status is untested out-of-sample, not refuted.</p>
  </div>
</section>

<footer>
  Generated from research/pre/artifacts by research/post/sweeps/build_momentum_report.py &middot;
  Research log seq 57&ndash;62, chain verified &middot;
  Runners: feature_screen.py, feature_combine.py, momentum_nested_wf.py,
  momentum_cost_stress.py, momentum_dsr.py
</footer>
</div>"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)
    return OUT


if __name__ == "__main__":
    print(build())
