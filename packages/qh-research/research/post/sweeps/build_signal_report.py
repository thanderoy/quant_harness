"""research.post.sweeps.build_signal_report — report for the pre-stage signal sweeps.

One page covering flood_tide, avwap_sweep_reclaim and avwap_multibar_reclaim,
because they share an exit grid and the comparison between them is the point.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from research.post.sweeps.report_style import HEAD

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "research" / "data" / "signals"
OUT = DATA_DIR / "signal_sweep_report.html"

NICE = {"flood_tide": "flood_tide", "avwap_sweep_reclaim": "avwap_sweep_reclaim",
        "avwap_multibar_reclaim": "avwap_multibar_reclaim"}
PRIOR = {
    "flood_tide": "SHELVED at seq 32/34 on a regime-filtered E-Ratio null",
    "avwap_sweep_reclaim": "OPEN at seq 25/26; entry-only E-Ratio 0.806, p 0.942",
    "avwap_multibar_reclaim": "OPEN; successor to the sweep-reclaim variant",
}


def esc(s):
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
    return f'<span class="{"pos" if v > 0 else ("neg" if v < 0 else "muted")}">{v:+.{dp}f}</span>'


def surface_table(rows, keys, labels) -> str:
    head = "".join(f"<th>{esc(l)}</th>" for l in labels)
    head += ('<th class="num">Configs</th><th class="num">Median Sharpe</th>'
             '<th class="num">% positive</th><th class="num">Median trades</th>'
             '<th class="num">Best</th>')
    body = []
    for r in rows:
        tds = "".join(f"<td>{esc(r[k])}</td>" for k in keys)
        tds += (f'<td class="num">{int(r["n_configs"]):,}</td>'
                f'<td class="num hl">{signed(r["median_sharpe"])}</td>'
                f'<td class="num">{pct(r["pct_positive"])}</td>'
                f'<td class="num">{int(r["median_trades"] or 0):,}</td>'
                f'<td class="num">{signed(r.get("best_sharpe"))}</td>')
        body.append("<tr>" + tds + "</tr>")
    return ('<div class="scroll"><table><thead><tr>' + head
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")


def drift_table(per) -> str:
    head = ('<th>Signal</th><th class="num">Best config Sharpe</th>'
            '<th class="num">Random-entry null</th><th class="num">p</th>'
            '<th class="num">Realized/target</th><th class="num">Beats drift</th>')
    body = []
    for sig, d in per.items():
        c = d.get("drift_control") or {}
        if "error" in c or not c:
            body.append(f'<tr><td class="cfg">{esc(sig)}</td>'
                        f'<td class="num" colspan="5">{esc(c.get("error", "not run"))}</td></tr>')
            continue
        p = c.get("p_value")
        ok = bool(c.get("beats_drift"))
        body.append(
            f'<tr><td class="cfg">{esc(sig)}</td>'
            f'<td class="num hl">{signed(c.get("actual_sharpe"))}</td>'
            f'<td class="num">{num(c.get("null_mean"))}</td>'
            f'<td class="num"><span class="{"pos" if ok else "neg"}">{num(p)}</span></td>'
            f'<td class="num muted">{int(c.get("median_realized") or 0):,}'
            f'/{int(c.get("target_trades") or 0):,}</td>'
            f'<td class="num"><span class="pill {"pass" if ok else "fail"}">'
            f'{"YES" if ok else "no"}</span></td></tr>')
    return ('<div class="scroll"><table><thead><tr>' + head
            + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")


def per_signal_block(sig, d) -> str:
    b = d.get("best")
    c = d.get("drift_control") or {}
    beats = bool(c.get("beats_drift"))
    rows = [
        ("Timeframe", esc(d["timeframe"])),
        ("Configs swept", f"{d['n_configs']:,}"),
        ("Clearing 100-trade floor", f"{d['n_countable']:,} ({d['pct_countable']:.1f}%)"),
        ("Median trades / config", f"{d['median_trades']:.0f} (max {d['max_trades']:,})"),
        ("Median Sharpe", signed(d["median_sharpe"])),
        ("% configs positive", pct(d["pct_positive"])),
        ("Best countable Sharpe", signed(d.get("best_countable_sharpe"))),
        ("Beats random entry", '<span class="pill %s">%s</span>'
         % ("pass" if beats else "fail", "YES" if beats else "NO")),
        ("Prior status", esc(PRIOR.get(sig, ""))),
    ]
    tbl = "".join(f'<tr><td>{k}</td><td class="num">{v}</td></tr>' for k, v in rows)
    note = ""
    if not b:
        note = (f'<p class="note">{esc(d.get("note", ""))}</p>')
    return (f'<h3 style="margin-top:30px">{esc(NICE.get(sig, sig))}</h3>'
            f'<div class="scroll"><table><tbody>{tbl}</tbody></table></div>{note}')


def section(title, sub, *blocks) -> str:
    return (f"<section><h2>{esc(title)}</h2><p class=\"sub\">{esc(sub)}</p>"
            + "".join(blocks) + "</section>")


def _surface_controls_section() -> str:
    """The controls that decide flood_tide: TYPICAL configs, not the best one."""
    sc_p = DATA_DIR / "flood_tide_surface_controls.json"
    dsr_p = DATA_DIR / "flood_tide_median_dsr.json"
    if not sc_p.exists():
        return ""
    sc = json.loads(sc_p.read_text())
    dsr = json.loads(dsr_p.read_text()) if dsr_p.exists() else None
    head = ('<th>Config tested</th><th class="num">Sharpe</th>'
            '<th class="num">Random-entry null</th><th class="num">null p95</th>'
            '<th class="num">p</th><th class="num">Realized/target</th>')
    labels = {"median_ranked": "median-ranked config (bracket)",
              "median_trail": "median trail config"}
    body = []
    for k, v in sc.items():
        p_ = v.get("p_value")
        ok = bool(v.get("beats_drift"))
        body.append(
            f'<tr><td class="cfg">{esc(labels.get(k, k))}</td>'
            f'<td class="num hl">{signed(v.get("actual_sharpe"))}</td>'
            f'<td class="num">{num(v.get("null_mean"))}</td>'
            f'<td class="num muted">{num(v.get("null_p95"))}</td>'
            f'<td class="num"><span class="{"pos" if ok else "neg"}">{num(p_)}</span></td>'
            f'<td class="num muted">{int(v.get("median_realized") or 0):,}'
            f'/{int(v.get("target_trades") or 0):,}</td></tr>')
    tbl = ('<div class="scroll"><table><thead><tr>' + head
           + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>")

    dsr_block = ""
    if dsr:
        se = dsr["dsr"].get("estimated_se", {})
        rows = "".join(
            f'<tr><td class="num">{int(k):,}</td><td class="num">'
            f'<span class="{"pos" if isinstance(v, float) and v > 0.95 else "neg"}">'
            f'{num(v, 4) if isinstance(v, float) else esc(v)}</span></td></tr>'
            for k, v in sorted(se.items(), key=lambda kv: int(kv[0])))
        dsr_block = (
            f'<h3 style="margin-top:30px">Deflated Sharpe on that same median config</h3>'
            f'<div class="scroll"><table><thead><tr><th class="num">N trials</th>'
            f'<th class="num">DSR (estimated Var)</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>'
            f'<p class="note">Computed on the MEDIAN config '
            f'(<code>{esc(dsr["config"])}</code>, {dsr["n_trades"]:,} trades, '
            f'Sharpe {num(dsr["sharpe_px"])}), not the top of the grid, so it is '
            f'not the selection-inflated figure seq&nbsp;49 warns about. It still '
            f'fails 0.95 at grid scale.</p>')

    return section(
        "The control that actually settles flood_tide",
        "Drift null run on TYPICAL configs rather than the selected best",
        tbl,
        '<div class="callout warn">'
        '<p><strong>A typical flood_tide config beats its own drift-matched null, '
        'decisively.</strong> The median-ranked configuration earns +0.331 against '
        'a null of &minus;0.356 at p&nbsp;=&nbsp;0.000, with realised trade count '
        'matched to within 0.6%. The median trailing config earns +0.516 against '
        '+0.065 at p&nbsp;=&nbsp;0.013.</p>'
        '<p>This is the claim seq&nbsp;49 cannot touch, because nothing here was '
        'selected for being good &mdash; the median of a 3,744-config grid is a '
        'pre-specified robust statistic, not a cherry-pick. It is the first result '
        'in eleven strategies where a <em>typical</em> configuration, rather than '
        'the top of a ranking, clears a drift-matched control.</p>'
        '<p><strong>Correcting an earlier reading in this analysis:</strong> the '
        'best config&rsquo;s null was +0.262, and comparing that positive number '
        'against the surface median of +0.331 suggested the surface was mostly '
        'gold&rsquo;s uptrend. That comparison was invalid &mdash; a null is '
        'specific to the configuration it is computed for, because it inherits '
        'that config&rsquo;s trade count, direction and exit rule. Computed '
        'properly, the median config&rsquo;s own null is <em>negative</em>.</p>'
        '<p>What this does <strong>not</strong> establish: the effect is small '
        '(median Sharpe 0.331), everything here is in-sample over full history, '
        'and the DSR below still fails at grid scale. Real but small is a '
        'different failure from no edge &mdash; and it is the first of the '
        'second kind in this repo.</p></div>',
        dsr_block)


def build(D: dict) -> str:
    per = D["per_signal"]
    n = D["n_configs_total"]
    ft = per.get("flood_tide", {})
    ft_c = ft.get("drift_control") or {}
    ft_beats = bool(ft_c.get("beats_drift"))

    verdict = (
        "<p><strong>flood_tide clears the drift control.</strong> Its positive "
        "surface is not simply gold's uptrend re-expressed through a trailing "
        "stop, which is the obvious way this result could have been an "
        "artifact.</p>" if ft_beats else
        "<p><strong>flood_tide does not clear the drift control.</strong> A "
        "long-only breakout with a trailing stop on a secular bull instrument "
        "is positive from drift alone, and that is what the surface was "
        "measuring. The shelving decision at seq&nbsp;32/34 stands, now for a "
        "better-evidenced reason than the entry-only E-Ratio that produced "
        "it.</p>")

    parts = [
        f"""<header class="hero">
  <p class="eyebrow">Research log seq 48&ndash;51 &middot; In-sample &middot; {n:,} configurations</p>
  <h1>Three shelved signals, put through a full exit grid</h1>
  <p class="lede">flood_tide, avwap_sweep_reclaim and avwap_multibar_reclaim all
  have working signal generators and no exit logic, so they stalled at the
  signal-edge stage and were never swept. This asks the only question that
  matters for an entry with no exit: does <em>any</em> exit in a wide grid make
  it viable &mdash; and if one does, does it beat random entry timing?</p>
  <div class="meta">
    <span><b>Configs</b> {n:,}</span>
    <span><b>Clearing trade floor</b> {D['n_countable']:,}</span>
    <span><b>Surviving all gates</b> {D['n_survivors']:,}</span>
    <span><b>Exit grid</b> ATR bracket + ATR trail</span>
  </div>
</header>""",
        section("The control that decides it",
                "Matched random-entry null · entry bars randomised, exit, direction, "
                "trade count, sizing and costs held identical",
                drift_table(per),
                f'<div class="callout warn">{verdict}'
                '<p>This is the load-bearing test, not the ranking. Per seq&nbsp;49, '
                'topping a grid carries no out-of-sample information; what survives '
                'is the surface statistic and whether it beats a drift-matched null. '
                'A long-only breakout on XAUUSD will look profitable from the '
                'instrument alone, so a positive median Sharpe means nothing until '
                'it clears this.</p></div>'),
        _surface_controls_section(),
        section("Surface by signal",
                f"Median across every exit configuration for each entry",
                surface_table(D["by_signal"], ["signal"], ["Signal"])),
        section("Which exit family?",
                "The question these signals existed to answer",
                surface_table(D["by_signal_exit"], ["signal", "exit_family"],
                              ["Signal", "Exit"]),
                '<p class="note">CLAUDE.md is explicit that a reclaim or '
                'mean-reversion entry is <em>designed</em> to be carried by an '
                'asymmetric exit, so a flat entry-only diagnostic is expected and is '
                'not grounds to reject the idea. Sweeping the exit is therefore the '
                'test these signals were owed, and it is why they sat unresolved.</p>'),
        section("Direction", "Median Sharpe by signal and direction",
                surface_table(D["by_signal_direction"], ["signal", "direction"],
                              ["Signal", "Dir"]),
                '<p class="note">flood_tide is long-only upstream, so its '
                '<code>both</code> and <code>long</code> rows are identical by '
                'construction &mdash; the short mask is empty. That is correct '
                'behaviour, not duplicated data.</p>'),
        section("Per signal", "Detail, prior status, and what the control says",
                *[per_signal_block(s, d) for s, d in per.items()]),
        section("What this licenses", "",
                f'<div class="callout">{verdict}'
                '<p><strong>No configuration here is promotable.</strong> Every '
                'number is in-sample over full history, and seq&nbsp;49 established '
                'that selecting the top of a grid carries no out-of-sample '
                'information on this instrument. The defensible output is the '
                'surface description and the drift verdict per signal.</p></div>'),
        section("Reproduction", "",
                "<pre><code>python -m research.post.sweeps.run_signal_sweep --all --workers 7\n"
                "python -m research.post.sweeps.signal_analyze\n"
                "python -m research.post.sweeps.build_signal_report</code></pre>",
                '<p class="note">Artifacts in <code>research/data/signals/</code>. '
                'Exit machinery is <code>cnk_engine.simulate</code> unchanged and '
                'already parity-validated, so costs, sizing and both return bases '
                'match the zlch / ebb / cnk / asqs sweeps and the numbers are '
                'directly comparable. Bars loaded with <code>tz="server_eet"</code>.</p>'),
        f'<footer>Pre-stage signal sweeps &middot; {n:,} configurations &middot; '
        f'flood_tide / avwap_sweep_reclaim / avwap_multibar_reclaim &middot; '
        f'read with seq 49</footer>',
    ]
    return ('<title>Shelved signals, swept</title>' + HEAD
            + '<div class="wrap">' + "".join(parts) + "</div>")


def main() -> int:
    D = json.loads((DATA_DIR / "signal_report_data.json").read_text())
    out = build(D)
    OUT.write_text(out)
    print(f"wrote {OUT} ({len(out):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
