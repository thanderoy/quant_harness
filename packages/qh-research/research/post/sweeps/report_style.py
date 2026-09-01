"""research.post.sweeps.report_style — shared HTML shell for the sweep reports.

One design system across every sweep report so results from different
hypotheses are visually comparable. Imported by build_report.py (zerolag
chandelier) and build_ebb_report.py (ebb_n_flow).
"""
from __future__ import annotations

HEAD = r"""<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root {
  --ground:#F5F7F9; --panel:#FFFFFF; --ink:#1B1F26; --ink-soft:#525C69;
  --ink-faint:#7C8794; --rule:#DDE2E8; --rule-soft:#EAEEF2;
  --accent:#0E5A63; --accent-soft:#E2EEEF;
  --pos:#2E7D57; --neg:#B03A26; --warn:#8F6A16;
  --pos-bg:#E4F0EA; --neg-bg:#F8E5E1;
  --shadow:0 1px 2px rgba(20,30,40,.06), 0 8px 24px -16px rgba(20,30,40,.28);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground:#121519; --panel:#181C22; --ink:#E4E8ED; --ink-soft:#A0AAB6;
    --ink-faint:#78838F; --rule:#282E36; --rule-soft:#20252C;
    --accent:#5FB3BC; --accent-soft:#163034;
    --pos:#5FB98B; --neg:#E0765E; --warn:#C79A3C;
    --pos-bg:#152A21; --neg-bg:#2C1A16;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -16px rgba(0,0,0,.7);
  }
}
:root[data-theme="dark"] {
  --ground:#121519; --panel:#181C22; --ink:#E4E8ED; --ink-soft:#A0AAB6;
  --ink-faint:#78838F; --rule:#282E36; --rule-soft:#20252C;
  --accent:#5FB3BC; --accent-soft:#163034;
  --pos:#5FB98B; --neg:#E0765E; --warn:#C79A3C;
  --pos-bg:#152A21; --neg-bg:#2C1A16;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 8px 24px -16px rgba(0,0,0,.7);
}
*,*::before,*::after { box-sizing:border-box; }
body {
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;
  font-size:16px; line-height:1.62; -webkit-font-smoothing:antialiased;
}
.wrap { max-width:1080px; margin:0 auto; padding:clamp(28px,5vw,72px) clamp(18px,4vw,40px) 96px; }
.prose { max-width:68ch; }
h1,h2,h3 { font-family:Newsreader,Georgia,serif; font-weight:600; text-wrap:balance; margin:0; letter-spacing:-.012em; }
h1 { font-size:clamp(2.1rem,4.6vw,3.15rem); line-height:1.08; }
h2 { font-size:clamp(1.4rem,2.5vw,1.85rem); line-height:1.2; }
h3 { font-size:1.02rem; font-family:"IBM Plex Sans",sans-serif; font-weight:600; letter-spacing:0; }
p { margin:0 0 1.05em; }
a { color:var(--accent); }
strong { font-weight:600; }
.eyebrow {
  font-family:"IBM Plex Mono",ui-monospace,monospace; font-size:.7rem;
  letter-spacing:.16em; text-transform:uppercase; color:var(--accent);
  margin:0 0 14px;
}
header.hero { border-bottom:2px solid var(--ink); padding-bottom:26px; margin-bottom:14px; }
.lede { font-size:1.13rem; color:var(--ink-soft); max-width:62ch; margin-top:18px; }
.meta {
  display:flex; flex-wrap:wrap; gap:6px 26px; margin-top:22px;
  font-family:"IBM Plex Mono",monospace; font-size:.74rem; color:var(--ink-faint);
}
.meta b { color:var(--ink-soft); font-weight:500; }
section { margin-top:56px; scroll-margin-top:20px; }
section > h2 { margin-bottom:6px; }
section > .sub {
  font-family:"IBM Plex Mono",monospace; font-size:.72rem; letter-spacing:.1em;
  text-transform:uppercase; color:var(--ink-faint); margin:0 0 22px;
}
.callout {
  background:var(--panel); border:1px solid var(--rule); border-left:3px solid var(--accent);
  border-radius:3px; padding:22px 26px; box-shadow:var(--shadow); margin:26px 0;
}
.callout p:last-child { margin-bottom:0; }
.callout.warn { border-left-color:var(--warn); }
/* verdict rows */
.kgrid { display:flex; flex-direction:column; gap:1px; background:var(--rule);
  border:1px solid var(--rule); border-radius:3px; overflow:hidden; box-shadow:var(--shadow); }
.krow { display:grid; grid-template-columns:56px 1fr auto; gap:18px; align-items:start;
  background:var(--panel); padding:18px 22px; }
.krow .kid { font-family:"IBM Plex Mono",monospace; font-size:.9rem; font-weight:600;
  color:var(--ink-faint); padding-top:1px; }
.krow.pass .kid { color:var(--pos); }
.krow.fail .kid { color:var(--neg); }
.krow h3 { margin:0 0 5px; }
.krow p { margin:0; font-size:.9rem; color:var(--ink-soft); }
.pill {
  display:inline-block; font-family:"IBM Plex Mono",monospace; font-size:.68rem;
  font-weight:600; letter-spacing:.07em; text-transform:uppercase;
  padding:3px 9px; border-radius:2px; white-space:nowrap;
}
.pill.pass { background:var(--pos-bg); color:var(--pos); }
.pill.fail { background:var(--neg-bg); color:var(--neg); }
/* tables */
.scroll { overflow-x:auto; border:1px solid var(--rule); border-radius:3px;
  background:var(--panel); box-shadow:var(--shadow); margin:20px 0 8px; }
table { border-collapse:collapse; width:100%; font-size:.845rem; }
thead th {
  position:sticky; top:0; background:var(--panel); text-align:left;
  font-family:"IBM Plex Mono",monospace; font-size:.68rem; font-weight:600;
  letter-spacing:.07em; text-transform:uppercase; color:var(--ink-faint);
  padding:12px 14px; border-bottom:1px solid var(--rule); white-space:nowrap;
}
tbody td { padding:9px 14px; border-bottom:1px solid var(--rule-soft); white-space:nowrap; }
tbody tr:last-child td { border-bottom:none; }
tbody tr:hover td { background:var(--accent-soft); }
.num { text-align:right; font-family:"IBM Plex Mono",monospace;
  font-variant-numeric:tabular-nums; }
th.num { text-align:right; }
.tf { font-family:"IBM Plex Mono",monospace; font-weight:600; color:var(--accent); }
.cfg { font-family:"IBM Plex Mono",monospace; font-size:.79rem; color:var(--ink-soft); }
.muted { color:var(--ink-faint); }
.pos { color:var(--pos); } .neg { color:var(--neg); }
td.hl { font-weight:600; color:var(--ink); background:var(--accent-soft); }
.barcell { position:relative; }
.bar { display:inline-block; width:52px; height:7px; margin-left:9px;
  background:var(--rule-soft); border-radius:1px; vertical-align:middle; position:relative; }
.bt { position:absolute; top:0; bottom:0; left:0; border-radius:1px; }
.bt.pos { background:var(--pos); } .bt.neg { background:var(--neg); }
.note { font-size:.82rem; color:var(--ink-faint); max-width:74ch; margin:10px 0 0; }
.note code, code { font-family:"IBM Plex Mono",monospace; font-size:.86em;
  background:var(--rule-soft); padding:1px 5px; border-radius:2px; }
pre { background:var(--panel); border:1px solid var(--rule); border-radius:3px;
  padding:16px 18px; overflow-x:auto; font-family:"IBM Plex Mono",monospace;
  font-size:.8rem; line-height:1.65; box-shadow:var(--shadow); }
pre code { background:none; padding:0; }
ul { padding-left:1.15em; margin:0 0 1.05em; }
li { margin-bottom:.5em; }
footer { margin-top:72px; padding-top:22px; border-top:1px solid var(--rule);
  font-family:"IBM Plex Mono",monospace; font-size:.72rem; color:var(--ink-faint); }
@media (max-width:620px) {
  .krow { grid-template-columns:44px 1fr; }
  .krow .kstate { grid-column:2; }
}
@media (prefers-reduced-motion:reduce) { * { animation:none!important; transition:none!important; } }
</style>"""
