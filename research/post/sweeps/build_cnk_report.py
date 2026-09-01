"""research.post.sweeps.build_cnk_report — executive report for the crest_n_keel sweep.

Reads research/data/crest_n_keel/cnk_report_data.json and writes
cnk_sweep_report.html next to it.

    python -m research.post.sweeps.build_cnk_report
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from research.post.sweeps.report_style import HEAD

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "research" / "data" / "crest_n_keel"
OUT = DATA_DIR / "cnk_sweep_report.html"


def esc(s) -> str:
    return html.escape(str(s))


def num(x, dp=3, dash="—"):
    if x is None:
        return dash
    try:
        return f"{float(x):.{dp}f}"
    except (TypeError, ValueError):
        return esc(x)


def pct(x, dp=1, dash="—"):
    if x is None:
        return dash
    return f"{float(x):.{dp}f}%"


def signed(x, dp=3):
    if x is None:
        return '<span class="muted">—</span>'
    v = float(x)
    cls = "pos" if v > 0 else ("neg" if v < 0 else "muted")
    return f'<span class="{cls}">{v:+.{dp}f}</span>'


def cfg_label(r) -> str:
    """One-line config description, mode-aware."""
    if r.get("mode") == "momentum":
        return (f"hma{r['hma_period']} atr{r['atr_period']} "
                f"trail{num(r['trail_mult'], 1)} minATR{num(r['min_atr'], 1)}")
    return (f"hma{r['hma_period']} atr{r['atr_period']} k{r['stoch_k']} "
            f"z{int(r['oversold'])}/{int(r['overbought'])} "
            f"sl{num(r['sl_mult'], 1)} tp{num(r['tp_mult'], 1)} "
            f"minATR{num(r['min_atr'], 1)}")


def rank_table(rows, highlight="sharpe_px") -> str:
    cols = [("timeframe", "TF"), ("mode", "Mode"), ("_cfg", "Config"),
            ("direction", "Dir"), ("n_trades", "Trades"), ("sharpe_px", "Sharpe"),
            ("max_dd_px", "Max DD"), ("profit_factor_px", "PF"),
            ("win_rate", "Win"), ("cagr_acct", "CAGR")]
    head = "".join(
        f'<th class="num">{esc(lbl)}</th>' if k not in ("timeframe", "mode", "_cfg", "direction")
        else f"<th>{esc(lbl)}</th>" for k, lbl in cols)
    body = []
    for r in rows:
        tds = []
        for k, _ in cols:
            hl = ' class="num hl"' if k == highlight else ' class="num"'
            if k == "timeframe":
                tds.append(f'<td class="tf">{esc(r[k])}</td>')
            elif k == "mode":
                tds.append(f"<td>{esc(r[k])}</td>")
            elif k == "_cfg":
                tds.append(f'<td class="cfg">{esc(cfg_label(r))}</td>')
            elif k == "direction":
                tds.append(f"<td>{esc(r[k])}</td>")
            elif k == "n_trades":
                tds.append(f'<td class="num">{int(r[k]):,}</td>')
            elif k == "sharpe_px":
                tds.append(f"<td{hl}>{signed(r[k])}</td>")
            elif k in ("max_dd_px", "win_rate"):
                v = r[k]
                tds.append(f"<td{hl}>{pct(100 * v) if v is not None else '—'}</td>")
            elif k == "cagr_acct":
                v = r[k]
                tds.append(f"<td{hl}>{pct(100 * v) if v is not None else '—'}</td>")
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


def control_table(rows) -> str:
    head = ('<th>TF</th><th>Mode</th><th>Dir</th><th class="num">Trades</th>'
            '<th class="num">Actual</th><th class="num">Null mean</th>'
            '<th class="num">Null p95</th><th class="num">p</th>'
            '<th class="num">Realized/target</th>')
    body = []
    for r in rows:
        p = r.get("p_value")
        pcls = "pos" if (p is not None and p < 0.05) else "neg"
        body.append(
            "<tr>"
            f'<td class="tf">{esc(r.get("timeframe"))}</td>'
            f'<td>{esc(r.get("mode"))}</td><td>{esc(r.get("direction"))}</td>'
            f'<td class="num">{int(r.get("n_trades") or 0):,}</td>'
            f'<td class="num hl">{signed(r.get("actual_sharpe"))}</td>'
            f'<td class="num">{num(r.get("null_mean"))}</td>'
            f'<td class="num">{num(r.get("null_p95"))}</td>'
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
        a = d_emp.get(str(n), {})
        b = d_se.get(str(n), {})

        def fmt(x):
            if "dsr" not in x:
                return '<span class="muted">—</span>'
            v = float(x["dsr"])
            cls = "pos" if v > 0.95 else "neg"
            return f'<span class="{cls}">{v:.4f}</span>'

        body.append(f'<tr><td class="num">{n:,}</td>'
                    f'<td class="num">{fmt(a)}</td><td class="num">{fmt(b)}</td></tr>')
    return ('<div class="scroll"><table><thead><tr>' + head
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")


def k2_table(rows) -> str:
    head = ('<th>TF</th><th>Mode</th><th>Dir</th><th class="num">Calmar</th>'
            '<th class="num">Buy &amp; hold Calmar</th><th class="num">Beats passive</th>')
    body = []
    for r in rows:
        ok = bool(r.get("beats_bh"))
        cls = "pos" if ok else "neg"
        body.append(
            "<tr>"
            f'<td class="tf">{esc(r.get("timeframe"))}</td>'
            f'<td>{esc(r.get("mode"))}</td><td>{esc(r.get("direction"))}</td>'
            f'<td class="num hl"><span class="{cls}">{num(r.get("calmar"), 2)}</span></td>'
            f'<td class="num muted">{num(r.get("bh_calmar"), 2)}</td>'
            f'<td class="num"><span class="pill {"pass" if ok else "fail"}">'
            f'{"YES" if ok else "no"}</span></td></tr>')
    return ('<div class="scroll"><table><thead><tr>' + head
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")


def k_rows(ks) -> str:
    out = []
    for k in ks:
        state = "pass" if k["passed"] else "fail"
        label = "PASS" if k["passed"] else "FAIL"
        out.append(
            f'<div class="krow {state}"><div class="kid">{esc(k["id"])}</div>'
            f'<div><h3>{esc(k["title"])}</h3><p>{k["body"]}</p></div>'
            f'<div class="kstate"><span class="pill {state}">{label}</span></div></div>')
    return '<div class="kgrid">' + "".join(out) + "</div>"


def section(title, sub, *blocks) -> str:
    return (f"<section><h2>{esc(title)}</h2><p class=\"sub\">{esc(sub)}</p>"
            + "".join(blocks) + "</section>")


def _tf_order(rows, key="timeframe"):
    order = {"M5": 0, "M15": 1, "H1": 2, "H4": 3, "D1": 4}
    return sorted(rows, key=lambda r: (order.get(r.get(key), 9), r.get("mode", "")))


def hero(D, narrative) -> str:
    lead = D.get("leader") or {}
    return f"""<header class="hero">
  <p class="eyebrow">Research log seq 44 &middot; In-sample &middot; {D['n_configs_total']:,} configurations</p>
  <h1>crest_n_keel: pullback versus momentum, across the whole grid</h1>
  <p class="lede">{narrative['lede']}</p>
  <div class="meta">
    <span><b>Configs</b> {D['n_configs_total']:,}</span>
    <span><b>Clearing trade floor</b> {D['n_countable']:,}</span>
    <span><b>Surviving all gates</b> {D['n_survivors']:,} ({num(D['survival_rate_pct'], 2)}%)</span>
    <span><b>Leader</b> {esc(lead.get('timeframe', '—'))} {esc(lead.get('mode', ''))}
      {esc(lead.get('direction', ''))} &middot; Sharpe {num(lead.get('sharpe_px'))}</span>
    <span><b>Engine parity</b> |&Delta;Sharpe| 0.0031, 100% entry match</span>
  </div>
</header>"""


def verdict_section(D, narrative) -> str:
    return section(
        "Verdict against pre-registered kill criteria",
        "Frozen at registration (seq 44) before any timeframe beyond D1/H4 was read",
        k_rows(narrative["k"]),
        f'<p class="note">{narrative["k_note"]}</p>')


def build(D: dict, narrative: dict) -> str:
    gates = D["gates"]
    gate_txt = (f"&ge;{gates['n_trades_min']} trades, "
                f"PF&nbsp;&ge;&nbsp;{gates['profit_factor_min']:.2f}, "
                f"max&nbsp;DD&nbsp;&le;&nbsp;{gates['max_dd_max']:.0%}, "
                f"Sharpe&nbsp;&gt;&nbsp;{gates['sharpe_min']:g}")
    parts = [
        hero(D, narrative),
        section("The headline: mode beats parameters",
                f"All {D['n_configs_total']:,} configs \u00b7 median across every combination",
                surface_table(_tf_order(D["by_tf_mode"]), ["timeframe", "mode"],
                              ["TF", "Mode"]),
                f'<p class="note">{narrative["mode_note"]}</p>',
                f'<p class="prose">{narrative["mode_prose"]}</p>'),
        verdict_section(D, narrative),
        section("The timeframe surface",
                f"Median Sharpe across every parameter combination at each timeframe",
                surface_table(_tf_order(D["by_timeframe"]), ["timeframe"], ["TF"]),
                f'<p class="note">Survivors pass all four gates: {gate_txt}.</p>',
                f'<p class="prose">{narrative["tf_prose"]}</p>'),
        section("Direction",
                "Median Sharpe by direction \u2014 region behaviour, not winners",
                '<h3 style="margin-top:26px">Pooled across timeframes</h3>',
                surface_table(D["by_mode_direction"], ["mode", "direction"],
                              ["Mode", "Dir"]),
                '<h3 style="margin-top:30px">Per timeframe \u2014 the evidence for P2</h3>',
                surface_table(_tf_order(D["by_tf_mode_direction"]),
                              ["timeframe", "mode", "direction"], ["TF", "Mode", "Dir"]),
                f'<p class="note">{narrative["dir_note"]}</p>'),
        section("Rankings",
                f"Over the {D['n_countable']:,} configs clearing the {gates['n_trades_min']}-trade floor",
                '<h3 style="margin-top:26px">By Sharpe ratio</h3>',
                rank_table(D["rank_sharpe"], "sharpe_px"),
                '<h3 style="margin-top:30px">By maximum drawdown</h3>',
                rank_table(D["rank_drawdown"], "max_dd_px"),
                '<h3 style="margin-top:30px">By win rate</h3>',
                rank_table(D["rank_win_rate"], "win_rate"),
                '<h3 style="margin-top:30px">By profit factor</h3>',
                rank_table(D["rank_profit_factor"], "profit_factor_px"),
                f'<p class="note">{narrative["rank_note"]}</p>'),
        section("Per-timeframe, per-mode leaders",
                "Best config in each cell \u2014 the candidates the controls are run against",
                rank_table(D["tf_mode_leaders"], "sharpe_px")),
        section("K1 — matched random-entry control",
                f"{D['n_permutations']} permutations \u00b7 entry bars randomised, "
                "direction, exits, sizing and costs held fixed",
                control_table(D["k1_controls"]),
                f'<p class="note">{narrative["k1_note"]}</p>',
                f'<p class="prose">{narrative["k1_prose"]}</p>'),
        section("K2 — against passive long gold",
                f"{D['k2_n_beating_bh']} of {len(D['k2_calmar'])} per-cell leaders "
                "beat buy-and-hold on Calmar over the identical window",
                k2_table(D["k2_calmar"]),
                f'<p class="note">{narrative["k2_note"]}</p>'),
        section("K3 — Deflated Sharpe",
                narrative["dsr_sub"],
                dsr_table(D.get("k3_dsr", {}), D.get("k3_dsr_single_sharpe_se", {})),
                f'<div class="callout warn">{narrative["dsr_callout"]}</div>'),
        section("K4 — is the leader a plateau or a spike?",
                f"{D['k4_neighbourhood']['n_neighbours']} one-step grid neighbours",
                rank_table(D["k4_neighbourhood"]["rows"], "sharpe_px"),
                f'<p class="note">{narrative["k4_note"]}</p>'),
        section("Engine validation", "The sweep engine is a rewrite, not the harness",
                f'<p class="prose">{narrative["engine_prose"]}</p>'),
        section("What this licenses", "",
                f'<div class="callout">{narrative["licenses"]}</div>',
                f'<p class="prose">{narrative["transfer"]}</p>'),
        section("Reproduction", "",
                "<pre><code>python -m research.post.sweeps.run_cnk_parity\n"
                "python -m research.post.sweeps.run_cnk_sweep --all --workers 7\n"
                "python -m research.post.sweeps.cnk_analyze\n"
                "python -m research.post.sweeps.build_cnk_report</code></pre>",
                f'<p class="note">{narrative["repro_note"]}</p>'),
        f'<footer>{narrative["footer"]}</footer>',
    ]
    return ('<title>crest_n_keel sweep</title>' + HEAD
            + '<div class="wrap">' + "".join(parts) + "</div>")


def main() -> int:
    D = json.loads((DATA_DIR / "cnk_report_data.json").read_text())
    from research.post.sweeps.cnk_narrative import narrative
    html_out = build(D, narrative(D))
    OUT.write_text(html_out)
    print(f"wrote {OUT} ({len(html_out):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
