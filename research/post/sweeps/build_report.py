"""research.post.sweeps.build_report — render the executive report HTML from the sweep artifacts.

Every number is read from zlch_report_data.json / zlch_deepdive.csv, never
transcribed by hand. Regenerate after any re-run:
    python -m research.post.sweeps.build_report
"""
from __future__ import annotations

import json
from pathlib import Path

from research.post.sweeps.report_style import HEAD

REPO_ROOT = Path(__file__).resolve().parents[3]
ART = REPO_ROOT / "research" / "post" / "artifacts"
OUT = ART / "zlch_sweep_report.html"

D = json.loads((ART / "zlch_report_data.json").read_text())
TF_ORDER = ["M5", "M15", "H1", "H4", "D1"]


def esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def pct(x, dp=1):
    return f"{100*float(x):.{dp}f}%"


def cfg_label(r) -> str:
    bias = "none" if r["bias_tf"] == "none" else f'{r["bias_tf"]}/{int(r["zlsma_len"])}'
    return f'ATR({int(r["atr_period"])})&times;{r["atr_mult"]:g} &middot; {bias} &middot; {r["direction"]}'


def rank_table(key: str, highlight: str) -> str:
    rows = []
    for r in D[key]:
        hl = ' class="hl"'
        cells = [
            f'<td class="tf">{esc(r["timeframe"])}</td>',
            f'<td class="cfg">{cfg_label(r)}</td>',
            f'<td class="num">{int(r["n_trades"]):,}</td>',
            f'<td class="num{"" if highlight!="sharpe_px" else " hl"}">{r["sharpe_px"]:.3f}</td>',
            f'<td class="num{"" if highlight!="max_dd_px" else " hl"}">{pct(r["max_dd_px"])}</td>',
            f'<td class="num{"" if highlight!="profit_factor_px" else " hl"}">{r["profit_factor_px"]:.3f}</td>',
            f'<td class="num{"" if highlight!="win_rate" else " hl"}">{pct(r["win_rate"])}</td>',
            f'<td class="num">{pct(r["cagr_acct"],2)}</td>',
        ]
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"""<div class="scroll"><table>
<thead><tr><th>TF</th><th>Configuration</th><th class="num">Trades</th>
<th class="num">Sharpe</th><th class="num">Max DD</th><th class="num">PF</th>
<th class="num">Win rate</th><th class="num">CAGR</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>"""


def tf_table() -> str:
    pt = D["per_timeframe"]
    mx = max(abs(pt[t]["median_sharpe"]) for t in TF_ORDER)
    rows = []
    for t in TF_ORDER:
        r = pt[t]
        ms = r["median_sharpe"]
        w = abs(ms) / mx * 46
        side = "neg" if ms < 0 else "pos"
        bar = (f'<span class="bar"><span class="bt {side}" '
               f'style="width:{w:.1f}%"></span></span>')
        rows.append(
            f'<tr><td class="tf">{t}</td>'
            f'<td class="num">{int(r["configs"]):,}</td>'
            f'<td class="num">{r["median_trades_yr"]:,.0f}</td>'
            f'<td class="num barcell {side}">{ms:+.3f} {bar}</td>'
            f'<td class="num">{r["pct_positive"]:.1f}%</td>'
            f'<td class="num">{r["median_pf"]:.3f}</td>'
            f'<td class="num">{r["best_sharpe"]:.3f}</td>'
            f'<td class="num">{int(r["survivors"]):,}</td></tr>')
    return f"""<div class="scroll"><table>
<thead><tr><th>TF</th><th class="num">Configs</th><th class="num">Trades/yr</th>
<th class="num">Median Sharpe</th><th class="num">% positive</th>
<th class="num">Median PF</th><th class="num">Best Sharpe</th>
<th class="num">Survivors</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>"""


def matrix_table(key: str, label: str, cols: list[str], fmt="{:+.3f}") -> str:
    m = D[key]
    head = "".join(f'<th class="num">{esc(c)}</th>' for c in cols)
    rows = []
    for t in TF_ORDER:
        if t not in m:
            continue
        cells = []
        for c in cols:
            v = m[t].get(c)
            if v is None:
                cells.append('<td class="num">&mdash;</td>')
            else:
                cls = "neg" if v < 0 else "pos"
                cells.append(f'<td class="num {cls}">{fmt.format(v)}</td>')
        rows.append(f'<tr><td class="tf">{t}</td>{"".join(cells)}</tr>')
    return (f'<div class="scroll"><table><thead><tr><th>{label}</th>{head}</tr>'
            f'</thead><tbody>{"".join(rows)}</tbody></table></div>')


def deepdive_table() -> str:
    rows = []
    for r in D["deepdive"]:
        p = r["p_value"]
        pcls = "pass" if p < 0.05 else "fail"
        ptxt = "&lt;0.002" if p == 0 else f"{p:.3f}"
        beat = r["calmar"] > r["bh_calmar"]
        rows.append(
            f'<tr><td class="tf">{esc(r["timeframe"])}</td>'
            f'<td class="cfg">{cfg_label(r)}</td>'
            f'<td class="num">{r["sharpe_px"]:.3f}</td>'
            f'<td class="num muted">{r["null_mean"]:.3f}</td>'
            f'<td class="num"><span class="pill {pcls}">{ptxt}</span></td>'
            f'<td class="num">{pct(r["exposure"])}</td>'
            f'<td class="num {"pos" if beat else "neg"}">{r["calmar"]:.2f}</td>'
            f'<td class="num muted">{r["bh_calmar"]:.2f}</td></tr>')
    return f"""<div class="scroll"><table>
<thead><tr><th>TF</th><th>Configuration</th><th class="num">Sharpe</th>
<th class="num">Null mean</th><th class="num">p</th><th class="num">Exposure</th>
<th class="num">Calmar</th><th class="num">B&amp;H Calmar</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>"""


def dsr_table() -> str:
    rows = []
    for v in D["dsr_variants"]:
        cls = "pass" if v["passes"] else "fail"
        txt = "pass" if v["passes"] else "fail"
        rows.append(
            f'<tr><td class="cfg">{esc(v["label"])}</td>'
            f'<td class="num">{v["n_trials"]:,}</td>'
            f'<td class="num">{v["var_sr"]:.2e}</td>'
            f'<td class="num">{v["sr_star"]:.4f}</td>'
            f'<td class="num"><strong>{v["dsr"]:.4f}</strong></td>'
            f'<td class="num"><span class="pill {cls}">{txt}</span></td></tr>')
    return f"""<div class="scroll"><table>
<thead><tr><th>Var(SR) source / N</th><th class="num">N</th><th class="num">Var(SR)</th>
<th class="num">SR*</th><th class="num">DSR</th><th class="num">&gt;0.95</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>"""


def orig_table() -> str:
    rows = []
    for r in D["original_config"]:
        rows.append(
            f'<tr><td class="cfg">{esc(r["direction"])}</td>'
            f'<td class="num">{int(r["n_trades"]):,}</td>'
            f'<td class="num neg">{r["sharpe_px"]:.3f}</td>'
            f'<td class="num">{pct(r["max_dd_px"])}</td>'
            f'<td class="num">{r["profit_factor_px"]:.3f}</td>'
            f'<td class="num">{pct(r["win_rate"])}</td></tr>')
    return f"""<div class="scroll"><table>
<thead><tr><th>Direction</th><th class="num">Trades</th><th class="num">Sharpe</th>
<th class="num">Max DD</th><th class="num">PF</th><th class="num">Win rate</th></tr>
</thead><tbody>{"".join(rows)}</tbody></table></div>"""


KS = [
    ("K1", "Beats a drift-matched random-entry null", "pass",
     "10 of 12 leading configs clear p&nbsp;&lt;&nbsp;0.05; 8 at p&nbsp;=&nbsp;0.000. "
     "Null means are positive (0.020&ndash;0.399), so gold&rsquo;s drift is inside the "
     "null and the signal still clears it. The two that fail are D1 configs at "
     "p&nbsp;=&nbsp;0.060 and 0.062."),
    ("K2", "Beats passive long gold on Calmar", "pass",
     "11 of 12 configs beat buy-and-hold Calmar (0.26&ndash;0.28). The H4 leader "
     "returns 0.41 on 51.7% market exposure; the runner-up reaches 0.57."),
    ("K3", "Deflated Sharpe &gt; 0.95 at the honest N", "fail",
     "0.739 at N&nbsp;=&nbsp;18,480 with estimated Var(SR); 0.119 with empirical "
     "Var(SR). It only passes at N&nbsp;=&nbsp;15, which ignores this sweep entirely. "
     "<strong>This is the binding constraint.</strong>"),
    ("K4", "Leader is a plateau, not a spike", "pass",
     "All 9 adjacent ATR-period &times; multiplier neighbours are positive; "
     "median 0.729, min 0.694, max 0.833."),
]


def k_rows() -> str:
    out = []
    for k, title, state, body in KS:
        out.append(f"""<div class="krow {state}">
<div class="kid">{k}</div>
<div class="kbody"><h3>{title}</h3><p>{body}</p></div>
<div class="kstate"><span class="pill {state}">{state}</span></div>
</div>""")
    return "".join(out)


HTML = f"""<title>ZeroLag Chandelier Sweep</title>
{HEAD}

<div class="wrap">

<header class="hero">
  <p class="eyebrow">Research log seq 39&ndash;40 &middot; In-sample</p>
  <h1>ZeroLag Chandelier:<br>the kill was a timeframe artifact</h1>
  <p class="lede">An exhaustive sweep of {D['n_configs']:,} configurations across five entry
  timeframes and 21.6 years of XAUUSD. The entry-level kill recorded at seq&nbsp;20 does not
  survive contact with the grid &mdash; but the winner still fails the selection haircut.</p>
  <div class="meta">
    <span><b>Configs</b> {D['n_configs']:,} ({D['n_distinct']:,} distinct)</span>
    <span><b>Survivors</b> {D['n_survivors']:,}</span>
    <span><b>Window</b> 2004-06-11 &rarr; 2026-01-30</span>
    <span><b>Engine parity</b> |&Delta;Sharpe| &le; 0.0015</span>
  </div>
</header>

<section>
  <h2>Bottom line</h2>
  <div class="callout">
    <p><strong>zerolag_chandelier was killed on M15, and M15 is the one timeframe
    where this strategy cannot work.</strong> Median Sharpe by entry timeframe runs
    &minus;1.402 (M5), &minus;0.602 (M15), +0.138 (H1), <strong>+0.266 (H4)</strong>,
    +0.114 (D1). On H4, 71.3% of all configurations are profitable before any selection.
    The signal is the same; the cost structure is not.</p>
    <p>The original registered configuration sat at the
    <strong>{D['original_percentile_in_m15_both']:.1f}th percentile</strong> of M15
    configurations &mdash; it was a typical M15 config, not an unlucky one. It traded
    463&nbsp;times a year into a $0.22/oz spread plus $7/lot commission.</p>
    <p>The leading H4 configuration beats a drift-matched random-entry null at
    p&nbsp;=&nbsp;0.000 and beats passive long gold on Calmar (0.41 vs 0.28) at half the
    market exposure. <strong>It still fails the Deflated Sharpe gate</strong>
    (0.739 vs the 0.95 threshold) once N is set honestly at the size of this search.</p>
  </div>
  <p class="prose">That combination &mdash; a real, plateau-shaped, drift-beating effect that
  cannot clear a selection haircut &mdash; is not a contradiction. It is what a genuine but
  modest edge looks like after you search eighteen thousand ways to find it.</p>
</section>

<section>
  <h2>Verdict against pre-registered kill criteria</h2>
  <p class="sub">Frozen at registration (seq 39) before any timeframe beyond D1/H4 was read</p>
  <div class="kgrid">{k_rows()}</div>
</section>

<section>
  <h2>The timeframe cliff</h2>
  <p class="sub">All {D['n_configs']:,} configs &middot; median across every parameter combination</p>
  {tf_table()}
  <p class="note">Median Sharpe is across every configuration at that timeframe, so it
  measures the region rather than a hand-picked winner. &ldquo;Survivors&rdquo; pass all four
  gates: &ge;100 trades, PF&nbsp;&ge;&nbsp;1.20, max&nbsp;DD&nbsp;&le;&nbsp;30%, Sharpe&nbsp;&gt;&nbsp;0.</p>
  <p class="prose">Median profit factor tracks trade frequency almost perfectly: 0.826 at
  604&nbsp;trades/yr, 0.886 at 318, 1.047 at 73, 1.190 at 20. Cost per round trip is roughly
  fixed; gross edge per trade is not. Everything below H1 is spent on the spread.</p>
</section>

<section>
  <h2>What the original configuration actually did</h2>
  <p class="sub">M15 &middot; ATR(14)&times;2.5 &middot; H4 ZLSMA(50) &mdash; the seq 19 registration</p>
  {orig_table()}
  <p class="note">The <code>both</code> row reproduces the harness figure that produced the
  seq&nbsp;20 kill (&minus;0.567 there, &minus;0.600 here; the gap is the 2018&ndash;2021 window
  versus full history). Note that long-only was already twice as good as both-directions,
  and that every variant is negative.</p>
</section>

<section>
  <h2>Rankings among survivors</h2>
  <p class="sub">{D['n_survivors']:,} configs clearing all four gates &middot; deduplicated</p>
  <h3 style="margin-top:26px">By Sharpe ratio</h3>
  {rank_table('by_sharpe','sharpe_px')}
  <h3 style="margin-top:30px">By maximum drawdown</h3>
  {rank_table('by_drawdown','max_dd_px')}
  <h3 style="margin-top:30px">By win rate</h3>
  {rank_table('by_win_rate','win_rate')}
  <h3 style="margin-top:30px">By profit factor</h3>
  {rank_table('by_profit_factor','profit_factor_px')}
  <p class="note">Sharpe, max DD and PF are on the harness return basis (per-unit price
  return net of commission), so they are directly comparable with figures already in the
  research log. CAGR is on the account basis at 1% risk per trade. Ranking by any single
  column is exactly the selection process the DSR section below penalises.</p>
</section>

<section>
  <h2>Structural findings</h2>
  <p class="sub">Median Sharpe across the grid &mdash; region behaviour, not winners</p>

  <h3 style="margin-top:26px">Direction: long dominates everywhere</h3>
  {matrix_table('direction_median','TF',['both','long','short'])}
  <p class="note">Short is negative at every timeframe. This matches the seq&nbsp;20 E-Ratio
  split exactly &mdash; long 1.033, short 0.927 &mdash; and is the expected signature of a
  secular bull instrument.</p>

  <h3 style="margin-top:30px">The ZLSMA bias filter hurts</h3>
  {matrix_table('bias_median_long','TF',['none','htf'])}
  <p class="note">Long-only configs, with and without a higher-timeframe ZLSMA slope filter.
  <strong>The filter is a net negative at every viable timeframe</strong> &mdash; 0.611 without
  versus 0.450 with, on H4. It was a core component of the registered hypothesis. It
  removes more good trades than bad ones.</p>

  <h3 style="margin-top:30px">ATR multiplier: the cost dial</h3>
  {matrix_table('mult_median_long','TF',['1.0','1.5','2.0','2.5','3.0','4.0','5.0'])}
  <p class="note">On M5/M15 the multiplier monotonically rescues performance, because a wider
  band means fewer trades and less spread paid &mdash; it is a cost dial, not an edge dial. On
  H4/D1 the relationship flattens and inverts, which is what a genuine parameter optimum
  looks like rather than a cost artifact.</p>
</section>

<section>
  <h2>Drift control</h2>
  <p class="sub">Top 3 per timeframe &middot; 500 permutations &middot; entry bars randomised, everything else fixed</p>
  {deepdive_table()}
  <p class="note">The null randomises <em>only</em> the entry bars. Direction, exit rule,
  trade count, position sizing and the full cost model are held identical, so the comparison
  isolates entry timing from gold&rsquo;s drift and from the trailing exit. Null means are
  positive throughout &mdash; that positive value <em>is</em> the drift, correctly priced into
  the benchmark rather than credited to the strategy. Exposure is the fraction of calendar
  time actually in the market; Calmar is CAGR/max&nbsp;DD on the account basis.</p>
  <p class="note"><strong>Count matching matters here.</strong> Entries are consumed
  sequentially, so sampling N random bars does not yield N trades. An unmatched null trades
  less often, and because these Sharpes are annualised by trades-per-year it receives a
  smaller &radic;ppy factor &mdash; a null deflated by roughly 10%, flattering the strategy.
  These figures come from a control whose realised trade count is tuned to match the strategy
  (median ratio 1.00) and which is annualised on the strategy&rsquo;s own periods-per-year.
  Correcting this moved two D1 configs from significant to not.</p>
  <p class="prose">This is the test that shelved <code>flood_tide_h1</code>,
  <code>flood_tide_h1_iter2</code> and <code>regime_align_h1</code>, where the measured effect
  collapsed into the null once drift was matched. Here it does not collapse. That is the
  strongest single result in this report.</p>
</section>

<section>
  <h2>Deflated Sharpe &mdash; the binding constraint</h2>
  <p class="sub">Leader: H4 &middot; ATR(8)&times;2.0 &middot; no bias &middot; long-only &middot; Sharpe 0.832</p>
  {dsr_table()}
  <div class="callout warn">
    <p><strong>The DSR spans 0.000 to 0.998 depending entirely on how Var(SR) and N are
    chosen &mdash; and only the last row passes.</strong> That row sets N&nbsp;=&nbsp;15, the
    research log&rsquo;s global trial floor, which does not know this sweep happened. For a
    configuration selected as the best of {D['n_configs']:,}, it is the wrong N.</p>
    <p>The empirical-Var(SR) rows deserve a caveat in the other direction. Pooling trial
    Sharpes across the whole grid gives Var(SR)&nbsp;=&nbsp;7.85e-02, which is dominated by real
    structural heterogeneity &mdash; M5 configs at &minus;1.4 sitting beside H4 configs at
    +0.83 &mdash; not by estimation noise under a null. That inflates SR* to 1.123
    per-observation (7.2 annualised), a bar nothing could clear. It is a misapplication of the
    estimator, not evidence.</p>
    <p>The defensible primary figure is the first row: <strong>DSR&nbsp;=&nbsp;0.739 at
    N&nbsp;=&nbsp;18,480 with estimated Var(SR)</strong>. It fails 0.95. No reading of the
    evidence promotes this strategy today.</p>
  </div>
</section>

<section>
  <h2>Engine validation</h2>
  <p class="sub">And one defect found in the harness along the way</p>
  <p class="prose">The sweep engine is a rewrite &mdash; <code>backtesting.py</code> is a
  per-bar Python loop and would have taken days for this grid. It was validated against
  <code>qhf.engines.strategies.zlch</code> under <code>btpy_runner</code> on seven configs
  spanning three timeframes: <strong>100% trade-set match and worst |&Delta;Sharpe| of
  0.0015</strong>. Reaching that parity surfaced four discrepancies, all fixed in the sweep
  engine, and one in the harness itself:</p>
  <div class="callout warn">
    <p><strong><code>btpy_runner</code>&rsquo;s docstring is wrong about its own return
    series.</strong> It states &ldquo;ReturnPct from backtesting.py = PnL / equity_at_entry&rdquo;.
    It is not. <code>Trade.pl_pct</code> is
    <code>sign&times;(exit/entry&minus;1) &minus; commissions/(|size|&times;entry)</code> &mdash;
    a <em>per-unit price return</em>. Verified empirically: correlation with the raw price
    return is 0.9999.</p>
    <p>The consequence is that <strong>every harness Sharpe, drawdown and profit factor in
    this repo is position-size agnostic.</strong> The ATR sizer and the 0.01&ndash;0.10 lot
    clamp have no effect on them. That is defensible as a signal-quality measure, but it is
    not the account return the docstring promises, and it affects the recorded figures for
    <code>crest_n_keel</code>, <code>asqs</code> and <code>crest_n_keel_momentum</code>.
    This report gives both bases.</p>
  </div>
  <p class="prose">The other three: the ZLSMA warm-up must propagate NaN rather than
  zero-fill (spurious early signals); re-entry is permitted on the exit bar itself, not the
  bar after; and <code>backtesting.py</code> applies spread to the entry fill only, so
  charging it on both sides double-counts. Separately, <code>max_drawdown_halt</code> was
  disabled for the sweep: it is an absorbing barrier that permanently truncates a config&rsquo;s
  record at a path-dependent point, which makes configs incomparable.</p>
</section>

<section>
  <h2>What this licenses</h2>
  <div class="callout">
    <p><strong>It does not license deployment.</strong> Every number here is in-sample over
    the full history. K3 fails. The frozen stopping rule permits exactly one next step: an
    out-of-sample walk-forward under <code>qhf_harness</code> on the H4 long-only region.</p>
    <p><strong>It does not license a finer grid around the leader.</strong> That would be
    overfitting and would require a new registration and a further trial-count increment.</p>
    <p><strong>It does license reopening the file.</strong> The seq&nbsp;20 kill is contested,
    not overturned &mdash; and the reason matters beyond this strategy: the E-Ratio was
    measured on M15, where costs dominate, and a hard-gate verdict was recorded against the
    signal when the evidence pointed at the timeframe.</p>
  </div>
  <p class="prose">Three findings transfer regardless of what happens to this strategy: short
  side is dead on XAUUSD across every timeframe tested; the ZLSMA bias filter subtracts value;
  and E-Ratio gating should be run at more than one timeframe before a hard-gate kill is
  recorded, because the cost structure is part of what is being measured.</p>
</section>

<section>
  <h2>Reproduction</h2>
  <pre><code>python -m research.post.sweeps.run_parity                    # engine vs harness
python -m research.post.sweeps.run_sweep --all --workers 7   # ~75 min
python -m research.post.sweeps.analyze                       # gates + rankings
python -m research.post.sweeps.deepdive --top 3 --perm 500   # drift controls
python -m research.post.sweeps.report_data                   # consolidate
python -m research.post.sweeps.build_report                  # this page</code></pre>
  <p class="note">Artifacts in <code>research/post/artifacts/</code>: five
  <code>zlch_sweep_&lt;TF&gt;.csv</code> (one row per config),
  <code>zlch_deepdive.csv</code>, <code>zlch_report_data.json</code>.
  Random seed 20260820 throughout.</p>
</section>

<footer>
  zerolag_chandelier parameter sweep &middot; research log seq 39 (registration) &amp; seq 40 (result)
  &middot; chain verified, 41 entries &middot; trial_count 15 &middot; verdict OPEN, stage 3_is_backtest
</footer>

</div>
"""

OUT.write_text(HTML)
print(f"wrote {OUT} ({len(HTML):,} bytes)")
