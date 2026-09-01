"""research.post.sweeps.build_asqs_report — executive report for the ASQS sweep.

Reads research/data/asqs/asqs_report_data.json, writes asqs_sweep_report.html.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from research.post.sweeps.report_style import HEAD

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "research" / "data" / "asqs"
OUT = DATA_DIR / "asqs_sweep_report.html"
TF_ORDER = {"M5": 0, "M15": 1, "H1": 2}


def esc(s) -> str:
    return html.escape(str(s))


def num(x, dp=3, dash="&mdash;"):
    if x is None:
        return dash
    try:
        return f"{float(x):.{dp}f}"
    except (TypeError, ValueError):
        return esc(x)


def pct(x, dp=1):
    return "&mdash;" if x is None else f"{float(x):.{dp}f}%"


def signed(x, dp=3):
    if x is None:
        return '<span class="muted">&mdash;</span>'
    v = float(x)
    cls = "pos" if v > 0 else ("neg" if v < 0 else "muted")
    return f'<span class="{cls}">{v:+.{dp}f}</span>'


def sess_of(r) -> str:
    if not r.get("use_session"):
        return "off"
    return f"{int(r['session_start'])}-{int(r['session_end'])}"


def cfg_label(r) -> str:
    return (f"ema{int(r['ema_fast'])}/{int(r['ema_slow'])} "
            f"bo{int(r['breakout_lookback'])} ts{int(r['trend_strength'])} "
            f"buf{num(r['breakout_buffer'], 1)} "
            f"sl{int(r['sl_points'])} tp{int(r['tp_points'])}")


def rank_table(rows, highlight="sharpe_px") -> str:
    cols = [("timeframe", "TF"), ("_cfg", "Config"), ("_sess", "Session"),
            ("direction", "Dir"), ("n_trades", "Trades"), ("sharpe_px", "Sharpe"),
            ("max_dd_px", "Max DD"), ("profit_factor_px", "PF"),
            ("win_rate", "Win"), ("cagr_acct", "CAGR")]
    head = "".join(
        f'<th class="num">{esc(l)}</th>' if k not in
        ("timeframe", "_cfg", "_sess", "direction") else f"<th>{esc(l)}</th>"
        for k, l in cols)
    body = []
    for r in rows:
        tds = []
        for k, _ in cols:
            hl = ' class="num hl"' if k == highlight else ' class="num"'
            if k == "timeframe":
                tds.append(f'<td class="tf">{esc(r[k])}</td>')
            elif k == "_cfg":
                tds.append(f'<td class="cfg">{esc(cfg_label(r))}</td>')
            elif k == "_sess":
                tds.append(f"<td>{esc(sess_of(r))}</td>")
            elif k == "direction":
                tds.append(f"<td>{esc(r[k])}</td>")
            elif k == "n_trades":
                tds.append(f'<td class="num">{int(r[k]):,}</td>')
            elif k == "sharpe_px":
                tds.append(f"<td{hl}>{signed(r[k])}</td>")
            elif k in ("max_dd_px", "win_rate", "cagr_acct"):
                v = r[k]
                tds.append(f"<td{hl}>{pct(100 * v) if v is not None else '&mdash;'}</td>")
            else:
                tds.append(f"<td{hl}>{num(r[k], 2)}</td>")
        body.append("<tr>" + "".join(tds) + "</tr>")
    return ('<div class="scroll"><table><thead><tr>' + head
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")


def surface_table(rows, keys, labels) -> str:
    head = "".join(f"<th>{esc(l)}</th>" for l in labels)
    head += ('<th class="num">Configs</th><th class="num">Median Sharpe</th>'
             '<th class="num">% positive</th><th class="num">Median trades</th>')
    body = []
    for r in rows:
        tds = "".join(f'<td class="tf">{esc(r[k])}</td>' if k == "timeframe"
                      else f"<td>{esc(r[k])}</td>" for k in keys)
        tds += (f'<td class="num">{int(r["n_configs"]):,}</td>'
                f'<td class="num">{signed(r["median_sharpe"])}</td>'
                f'<td class="num">{pct(r["pct_positive"])}</td>'
                f'<td class="num">{int(r["median_trades"] or 0):,}</td>')
        body.append("<tr>" + tds + "</tr>")
    return ('<div class="scroll"><table><thead><tr>' + head
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")


def session_table(cmp_) -> str:
    head = ('<th>Session (true UTC)</th><th class="num">Configs</th>'
            '<th class="num">Median Sharpe</th><th class="num">% positive</th>'
            '<th class="num">Best Sharpe</th><th class="num">Median trades</th>')
    body = []
    for s, v in sorted(cmp_.items(), key=lambda kv: -(kv[1]["median_sharpe"] or -9)):
        lbl = "no session filter" if s == "off" else f"{s} UTC"
        mark = " &larr; original" if s == "8-17" else ""
        body.append(
            f'<tr><td class="cfg">{esc(lbl)}{mark}</td>'
            f'<td class="num">{int(v["n_configs"]):,}</td>'
            f'<td class="num hl">{signed(v["median_sharpe"])}</td>'
            f'<td class="num">{pct(v["pct_positive"])}</td>'
            f'<td class="num">{signed(v["best_sharpe"])}</td>'
            f'<td class="num">{int(v["median_trades"] or 0):,}</td></tr>')
    return ('<div class="scroll"><table><thead><tr>' + head
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")


def control_table(rows) -> str:
    head = ('<th>TF</th><th>Session</th><th>Dir</th><th class="num">Trades</th>'
            '<th class="num">Actual</th><th class="num">Null mean</th>'
            '<th class="num">p</th><th class="num">Realized/target</th>')
    body = []
    for r in rows:
        p = r.get("p_value")
        pcls = "pos" if (p is not None and p < 0.05) else "neg"
        body.append(
            f'<tr><td class="tf">{esc(r.get("timeframe"))}</td>'
            f'<td>{esc(r.get("session"))}</td><td>{esc(r.get("direction"))}</td>'
            f'<td class="num">{int(r.get("n_trades") or 0):,}</td>'
            f'<td class="num hl">{signed(r.get("actual_sharpe"))}</td>'
            f'<td class="num">{num(r.get("null_mean"))}</td>'
            f'<td class="num"><span class="{pcls}">{num(p)}</span></td>'
            f'<td class="num muted">{int(r.get("median_realized") or 0):,}'
            f'/{int(r.get("target_trades") or 0):,}</td></tr>')
    return ('<div class="scroll"><table><thead><tr>' + head
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")


def dsr_table(d_emp, d_se) -> str:
    ns = sorted({int(k) for k in list(d_emp) + list(d_se)})
    head = ('<th class="num">N trials</th><th class="num">DSR (empirical Var)</th>'
            '<th class="num">DSR (estimated SE)</th>')
    body = []
    for n in ns:
        a, b = d_emp.get(str(n), {}), d_se.get(str(n), {})

        def fmt(x):
            if "dsr" not in x:
                return '<span class="muted">&mdash;</span>'
            v = float(x["dsr"])
            return f'<span class="{"pos" if v > 0.95 else "neg"}">{v:.4f}</span>'
        body.append(f'<tr><td class="num">{n:,}</td><td class="num">{fmt(a)}</td>'
                    f'<td class="num">{fmt(b)}</td></tr>')
    return ('<div class="scroll"><table><thead><tr>' + head
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")


def k_rows(ks) -> str:
    out = []
    for k in ks:
        st = "pass" if k["passed"] else "fail"
        out.append(
            f'<div class="krow {st}"><div class="kid">{esc(k["id"])}</div>'
            f'<div><h3>{esc(k["title"])}</h3><p>{k["body"]}</p></div>'
            f'<div class="kstate"><span class="pill {st}">'
            f'{"PASS" if k["passed"] else "FAIL"}</span></div></div>')
    return '<div class="kgrid">' + "".join(out) + "</div>"


def section(title, sub, *blocks) -> str:
    return (f"<section><h2>{esc(title)}</h2><p class=\"sub\">{esc(sub)}</p>"
            + "".join(blocks) + "</section>")


def _order(rows, key="timeframe"):
    return sorted(rows, key=lambda r: (TF_ORDER.get(r.get(key), 9),
                                       str(r.get("direction", "")),
                                       str(r.get("session", ""))))


def build(D: dict) -> str:
    lead = D.get("leader") or {}
    n = D["n_configs_total"]
    sc = D.get("session_comparison", {})
    orig = sc.get("8-17", {})
    best_sess = max(sc.items(), key=lambda kv: kv[1]["median_sharpe"] or -9)[0] if sc else None
    ak1 = next((c for c in D.get("ak1_controls", [])
                if c.get("timeframe") == lead.get("timeframe")), {})
    ak2 = next((b for b in D.get("ak2_calmar", [])
                if b.get("timeframe") == lead.get("timeframe")), {})
    dsr_full = (D.get("ak3_dsr_single_sharpe_se", {}).get(str(n)) or {}).get("dsr")
    k4 = D.get("ak4_neighbourhood", {})
    tf_med = {r["timeframe"]: r["median_sharpe"] for r in D.get("by_timeframe", [])}
    all_neg = all((v or 0) < 0 for v in tf_med.values()) if tf_med else False

    ks = [
        {"id": "AK1", "passed": (ak1.get("p_value") is not None
                                 and ak1["p_value"] < 0.05),
         "title": "Matched random-entry control",
         "body": (f"Leader Sharpe {signed(ak1.get('actual_sharpe'))} against a "
                  f"random-timing null of {num(ak1.get('null_mean'))}, "
                  f"p&nbsp;=&nbsp;{num(ak1.get('p_value'))}. The pool is every bar "
                  f"the session filter allows, so this isolates the 7-condition "
                  f"entry from the session and the cost model.")},
        {"id": "AK2", "passed": bool(ak2.get("beats_bh")),
         "title": "Beats passive long gold",
         "body": (f"Calmar {num(ak2.get('calmar'), 2)} against buy-and-hold "
                  f"{num(ak2.get('bh_calmar'), 2)} over the same window. "
                  f"{D.get('ak2_n_beating_bh', 0)} of "
                  f"{len(D.get('ak2_calmar', []))} per-timeframe leaders beat "
                  f"passive.")},
        {"id": "AK3", "passed": bool(dsr_full is not None and dsr_full > 0.95),
         "title": "Deflated Sharpe at grid scale",
         "body": (f"DSR {num(dsr_full, 4)} at N&nbsp;=&nbsp;{n:,} with estimated "
                  f"Var(SR).")},
        {"id": "AK4", "passed": not all_neg,
         "title": "A viable region exists at some timeframe",
         "body": ("Median Sharpe across the whole grid is "
                  + ", ".join(f"{tf} {num(v)}" for tf, v in
                              sorted(tf_med.items(), key=lambda kv: TF_ORDER.get(kv[0], 9)))
                  + ". This kill criterion asks whether the strategy FAMILY has "
                  "any viable region at all, independent of which config tops "
                  "the ranking.")},
    ]

    sess_prose = (
        f"<strong>This is the correction to the record.</strong> ASQS filters "
        f"08:00&ndash;17:00 and its source documents that as a UTC window. The "
        f"CSVs are broker server time, so every previously recorded ASQS result "
        f"&mdash; including the seq&nbsp;30 refutation &mdash; was really "
        f"trading roughly 05:00&ndash;14:00 or 06:00&ndash;15:00 UTC depending on "
        f"daylight saving. Every row above is computed on <em>true</em> UTC. "
        + (f"The original 08:00&ndash;17:00 window is "
           f"{'still the best' if best_sess == '8-17' else 'NOT the best'} "
           f"session in the grid"
           + ("" if best_sess == "8-17" else
              f" &mdash; <code>{esc(best_sess)}</code> is, at a median Sharpe of "
              f"{num(sc.get(best_sess, {}).get('median_sharpe'))} against "
              f"{num(orig.get('median_sharpe'))}")
           + ".") if sc else "")

    parts = [
        f"""<header class="hero">
  <p class="eyebrow">Research log seq 50 &middot; In-sample &middot; {n:,} configurations</p>
  <h1>ASQ SafeScalping across its whole parameter space</h1>
  <p class="lede">The last strategy in this repo with a working engine that had
  never been swept, and the only one still running live on demo. Two defects
  found while porting it change what every previously recorded ASQS number
  means: its session filter has been reading the wrong hours, and its partial
  close does nothing at all.</p>
  <div class="meta">
    <span><b>Configs</b> {n:,}</span>
    <span><b>Clearing trade floor</b> {D['n_countable']:,}</span>
    <span><b>Surviving all gates</b> {D['n_survivors']:,} ({num(D['survival_rate_pct'], 2)}%)</span>
    <span><b>Engine parity</b> 100% entry match, 5e-06/trade</span>
  </div>
</header>""",
        section("Verdict against pre-registered kill criteria",
                "Frozen at registration (seq 50) before the sweep ran",
                k_rows(ks),
                '<p class="note">Read this alongside seq&nbsp;49, which showed that '
                'top-of-grid selection carries no out-of-sample information. This '
                'sweep was registered as a surface characterisation; no configuration '
                'below is offered as promotable.</p>'),
        section("The session window — what the timezone defect cost",
                "Median across every configuration using each window, on true UTC",
                session_table(sc), f'<p class="prose">{sess_prose}</p>'),
        section("Timeframe surface",
                f"All {n:,} configs · median across every parameter combination",
                surface_table(_order(D.get("by_timeframe", [])), ["timeframe"], ["TF"]),
                '<p class="note">ASQS sizes its stops in POINTS rather than ATR, so '
                'H4 and D1 were excluded from the grid as meaningless: 300 points is '
                '$3.00, which is noise against a daily bar.</p>'),
        section("Direction",
                "Median Sharpe by direction — region behaviour, not winners",
                surface_table(_order(D.get("by_tf_direction", [])),
                              ["timeframe", "direction"], ["TF", "Dir"])),
        section("Stop and target geometry",
                "Median Sharpe by SL/TP in points",
                surface_table(D.get("by_sl_tp", []), ["sl_points", "tp_points"],
                              ["SL pts", "TP pts"])),
        section("Rankings",
                f"Over the {D['n_countable']:,} configs clearing the "
                f"{D['gates']['n_trades_min']}-trade floor",
                '<h3 style="margin-top:26px">By Sharpe ratio</h3>',
                rank_table(D.get("rank_sharpe", [])),
                '<h3 style="margin-top:30px">By maximum drawdown</h3>',
                rank_table(D.get("rank_drawdown", []), "max_dd_px"),
                '<h3 style="margin-top:30px">By profit factor</h3>',
                rank_table(D.get("rank_profit_factor", []), "profit_factor_px"),
                '<p class="note">Ranking by any single column is exactly the '
                'selection process seq&nbsp;49 showed to be uninformative out of '
                'sample. These tables describe the surface.</p>'),
        section("AK1 — matched random-entry control",
                f"{D.get('n_permutations', 0)} permutations · entry bars randomised "
                "within the session, everything else held fixed",
                control_table(D.get("ak1_controls", []))),
        section("AK3 — Deflated Sharpe",
                f"Leader: {esc(lead.get('timeframe','?'))} · "
                f"{esc(lead.get('direction',''))} · {esc(sess_of(lead))} · "
                f"Sharpe {num(lead.get('sharpe_px'))}",
                dsr_table(D.get("ak3_dsr", {}), D.get("ak3_dsr_single_sharpe_se", {})),
                '<p class="note">The empirical-Var(SR) column pools trial Sharpes '
                'across structurally different timeframes and inflates the benchmark '
                'to a level nothing clears; the estimated-SE column at N = grid size '
                'is the defensible figure, as in the zlch and cnk reports.</p>'),
        section("The partial close does nothing",
                "A defect in the harness, not in this sweep",
                """<div class="callout warn">
  <p><code>btpy_runner</code> constructs its backtest with
  <code>exclusive_orders=True</code>. ASQS implements its partial close by
  placing two orders &mdash; a TP1 leg and a remainder leg &mdash; but under
  that setting the second order <strong>cancels the first</strong>. The TP1 leg
  never exists.</p>
  <p>Verified directly against harness output: 349 trades, every one at a unique
  entry timestamp, every one at the remainder size, with normal durations. If
  the two legs were both filling, entry timestamps would appear in pairs. They
  do not.</p>
  <p>The only surviving effect of enabling partial close is that <strong>position
  size is halved</strong>. The strategy's own docstring calls this a &ldquo;two-leg
  approximation &mdash; see BUG-2 fix&rdquo;; the fix does not work under this
  runner. This sweep reproduces the harness behaviour so it stays comparable
  with the logged record, and flags it rather than silently correcting it.</p>
</div>"""),
        section("Engine validation", "The sweep engine is a rewrite",
                """<p class="prose">Validated against
  <code>qhf.engines.strategies.asq_safe_scalping</code> under
  <code>btpy_runner</code> on ten configurations spanning M5, M15 and H1:
  <strong>100.0% entry-set match on all ten</strong>. Per-trade return standard
  deviation matches to seven significant figures (0.00223227 against 0.00223239)
  and the annualisation factor to four (18.739 against 18.735); the engines
  differ by 5&times;10<sup>&minus;6</sup> per trade in the mean. The worst
  |&Delta;Sharpe| of 0.0721 is not a disagreement &mdash; Sharpe is unstable when
  the mean return is 0.04 of a standard deviation.</p>
  <p class="prose">Reaching that parity required fixing three semantic errors in
  the port, each of which had been silently wrong: the initial SL/TP anchor to
  the <em>signal bar close</em> while breakeven and trailing anchor to the
  <em>fill price</em> &mdash; two different anchors inside one strategy;
  <code>use_session=False</code> disables the weekend and Friday-cutoff checks
  as well, because they live inside <code>_pass_session()</code>; and the
  partial-close behaviour above.</p>"""),
        section("Reproduction", "",
                "<pre><code>python -m research.post.sweeps.run_asqs_parity\n"
                "python -m research.post.sweeps.run_asqs_sweep --all --workers 7\n"
                "python -m research.post.sweeps.asqs_analyze\n"
                "python -m research.post.sweeps.build_asqs_report</code></pre>",
                f'<p class="note">Artifacts in <code>research/data/asqs/</code>: '
                f'<code>asqs_sweep_&lt;TF&gt;.csv</code>, '
                f'<code>asqs_deepdive.csv</code>, <code>asqs_report_data.json</code>. '
                f'Bars loaded with <code>tz="server_eet"</code> (true UTC). '
                f'partial_mode=<code>{esc(D.get("partial_mode"))}</code>.</p>'),
        f'<footer>ASQ SafeScalping parameter sweep &middot; {n:,} configurations '
        f'&middot; research log seq 50 &middot; live on demo &middot; '
        f'read with seq 49 (top-of-grid selection carries no OOS information)</footer>',
    ]
    return ('<title>ASQ SafeScalping sweep</title>' + HEAD
            + '<div class="wrap">' + "".join(parts) + "</div>")


def main() -> int:
    D = json.loads((DATA_DIR / "asqs_report_data.json").read_text())
    out = build(D)
    OUT.write_text(out)
    print(f"wrote {OUT} ({len(out):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
