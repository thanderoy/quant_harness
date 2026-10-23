"use strict";

/* Harness Ledger — research terminal. One page per rail tab, rendered
   client-side from read-only /api/* views. Nothing here writes anywhere. */

const $ = (s, el = document) => el.querySelector(s);
const D = { ready: false, details: {} };
const PAGES = {
  "/": ["overview", "Overview", renderOverview],
  "/experiments": ["experiments", "Experiments", renderExperiments],
  "/divisions": ["divisions", "Divisions", renderDivisions],
  "/trials": ["trials", "Trial load", renderTrials],
  "/observation": ["observation", "Observation", renderObservation],
  "/log": ["log", "Log", renderLog],
  "/protocols": ["protocols", "Protocols", renderProtocols],
  "/artifacts": ["artifacts", "Artifacts", renderArtifacts],
};
const exp = { status: "", family: "", q: "" };
const logf = { grep: "", type: "" };

/* ---------- helpers ---------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function md(s) { return esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`(.+?)`/g, "<code>$1</code>"); }
function plain(s) { return String(s ?? "").replace(/\*\*|`/g, ""); }
function kindOf(label) {
  const l = String(label || "").toUpperCase();
  if (l === "DEAD" || l === "KILLED") return "dead";
  if (l === "VOID") return "void";
  if (l === "WITHDRAWN") return "withdrawn";
  if (l === "ALIVE" || l === "PROMOTED" || l === "DEPLOYED" || l === "PASS") return "alive";
  if (l === "OPEN" || l === "REGISTERED" || l === "ALIVE_POOLED_ONLY") return "waiting";
  return "shelved";
}
const KIND_NAME = { dead: "Dead", void: "Void", withdrawn: "Withdrawn", waiting: "Open", alive: "Alive", shelved: "Shelved" };
const desig = (seq) => `EXP-${String(seq).padStart(3, "0")}`;
const stamp = (ts) => String(ts || "").replace("T", " ").replace("Z", "").slice(0, 16);
const day = (ts) => String(ts || "").slice(0, 10);
function fmt(v) {
  if (typeof v !== "number") return esc(v);
  if (v === 0) return "0";
  const a = Math.abs(v);
  if (a >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (a >= 1) return v.toFixed(3).replace(/\.?0+$/, "");
  return v.toPrecision(3);
}
const icon = (name, cls = "") => `<svg class="ic ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const st = (label) => `<span class="st" data-k="${kindOf(label)}">${esc(label)}</span>`;
async function get(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} answered HTTP ${r.status}`);
  return r.json();
}
async function detail(id) {
  if (!D.details[id]) D.details[id] = await get(`/api/hypothesis/${encodeURIComponent(id)}`);
  return D.details[id];
}
function frame(title, iconName, body, right = "") {
  return `<section class="frame"><div class="f-head">${icon(iconName, "sm")}<h2>${esc(title)}</h2>${right ? `<span class="r">${right}</span>` : ""}</div>${body}</section>`;
}
function head(title, sub) {
  return `<header class="p-head"><h1 class="p-title">${esc(title)}</h1>${sub ? `<p class="p-sub">${sub}</p>` : ""}</header>`;
}
function census() {
  const c = { dead: 0, void: 0, withdrawn: 0, waiting: 0, alive: 0, shelved: 0 };
  D.hyps.forEach((h) => { c[kindOf(h.label)]++; });
  return c;
}
function pend() { return D.pending[0]; }
function waitFraction(p) {
  const h = D.hyps.find((x) => x.hypothesis_id === p.hypothesis_id);
  const s = Date.parse(h ? h.registered_at : Date.now()), e = Date.parse(`${p.earliest_run}T00:00:00Z`);
  return Math.min(1, Math.max(0, (Date.now() - s) / Math.max(1, e - s)));
}

/* ---------- router ---------- */
function go(href, push = true) {
  const url = new URL(href, location.origin);
  if (push) history.pushState({}, "", url.pathname + url.search);
  render();
}
function render() {
  const route = PAGES[location.pathname];
  const [key, name, fn] = route || ["", "Not found", renderNotFound];
  document.querySelectorAll(".rail a[data-page]").forEach((a) => {
    if (a.dataset.page === key) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  $("#crumb").textContent = `/ ${name.toLowerCase()}`;
  document.title = key === "overview" ? "Harness Ledger" : `${name} · Harness Ledger`;
  const view = $("#view");
  if (!D.ready) { view.innerHTML = `<div class="page"><div class="skel"><i></i><i></i><i></i><i></i></div></div>`; return; }
  try { view.innerHTML = `<div class="page">${fn(new URLSearchParams(location.search))}</div>`; }
  catch (err) { view.innerHTML = `<div class="page"><p class="err">This page failed to render: ${esc(err.message)}</p></div>`; }
  afterRender[key]?.();
  window.scrollTo(0, 0);
}
const afterRender = {};

/* ---------- overview ---------- */
function renderOverview() {
  const s = D.summary, c = census(), p = pend();
  const bold = (D.status.headline.match(/\*\*(.+?)\*\*/) || [, "No status recorded."])[1];
  const [lead, ...rest] = bold.replace(/\.$/, "").split(";");
  const stmt = rest.length ? rest.join(";").trim() : lead;
  const tile = (href, ic, k, big, unit, foot) => `
    <a class="tile" href="${href}" data-nav>
      <span class="t-top">${icon(ic)}<span class="k">${k}</span></span>
      <span class="big">${big}${unit ? `<small>${unit}</small>` : ""}</span>
      <span class="t-foot"><span>${foot}</span><span class="go">Open &gt;&gt;&gt;</span></span>
    </a>`;
  return `
    <section class="p-head">
      <span class="k">[ ${esc(rest.length ? lead.trim() : "Programme status")} ]</span>
      <h1 class="hero-stmt">${esc(stmt)}<em>.</em></h1>
      <div class="hero-meta"><span class="lbl">Updated ${esc(day(D.status.headline.slice(0, 10)) || day(s.last_timestamp))}</span>
        <details class="more"><summary>Progress report</summary><p class="p-sub">${md(D.status.headline.replace(/^[\d-]+ — /, ""))}</p></details></div>
    </section>
    <div class="cells tiles">
      ${tile("/experiments", "experiments", "Experiments", D.hyps.length, "registered", `${c.dead} dead · ${c.void + c.withdrawn} void or withdrawn · ${c.waiting + c.alive} open`)}
      ${tile("/trials", "trials", "Trial load", s.trial_count, "trials", "Sets the Deflated Sharpe haircut")}
      ${tile("/log", "chain", "Integrity", s.chain_ok ? "OK" : "BROKEN", "chain", `${s.n_entries} entries · head seq=${s.last_seq}`)}
      ${p ? tile("/observation", "observation", "Next observation", `T-${p.days_remaining}`, "days", `COT out of sample · opens ${esc(p.earliest_run)}`) : tile("/observation", "observation", "Next observation", "—", "", "Nothing scheduled")}
    </div>
    ${frame("Programme schematic", "schematic", `<div class="schem">${schematic()}</div>`, `<span class="lbl">${D.status.phases.filter((x) => phaseState(x.status) === "done").length}/${D.status.phases.length} phases done</span>`)}`;
}
function phaseState(s) {
  if (s.startsWith("✅")) return "done";
  if (s.startsWith("▶")) return "active";
  if (s.startsWith("⏸")) return "paused";
  return "unknown";
}
const TAG = { done: ["DONE", "#74e3c1"], active: ["ACTIVE", "#ececea"], paused: ["PAUSED", "#e8b24a"], unknown: ["—", "#5f6865"] };
function clip(s, n) { s = plain(s); return s.length > n ? s.slice(0, n - 1) + "…" : s; }
function module3d(x, y, hi) {
  const w = 74, h = 46, d = 9, l = x - w / 2, t = y - h / 2, c = hi ? " hi" : "";
  let hatch = "";
  for (let i = l + 7; i < l + w - 2; i += 7) hatch += `<line class="sx-h${c}" x1="${i}" y1="${t + 4}" x2="${i}" y2="${t + h - 4}"/>`;
  return `<rect class="sx-w${c}" x="${l}" y="${t}" width="${w}" height="${h}"/>${hatch}
    <polygon class="sx-w${c}" points="${l},${t} ${l + d},${t - d} ${l + w + d},${t - d} ${l + w},${t}"/>
    <polygon class="sx-w${c}" points="${l + w},${t} ${l + w + d},${t - d} ${l + w + d},${t + h - d} ${l + w},${t + h}"/>`;
}
function schematic() {
  const P = D.status.phases, W = 900, H = 330, y = 170, x0 = 90, x1 = 790, p = pend();
  if (!P.length) return `<p class="empty-state">No phase table in docs/STATUS.md.</p>`;
  const xs = P.map((_, i) => (P.length === 1 ? (x0 + x1) / 2 : x0 + (i * (x1 - x0)) / (P.length - 1)));
  const active = P.findIndex((q) => phaseState(q.status) === "active");
  let svg = `<line class="sx-pipe" x1="${xs[0] - 60}" y1="${y}" x2="${xs[xs.length - 1] + 70}" y2="${y}"/>`;
  P.forEach((q, i) => {
    const s = phaseState(q.status), hi = s === "active", [tag, col] = TAG[s];
    svg += module3d(xs[i], y, hi);
    const up = i % 2 === 0, bw = 156, bh = 42;
    const bx = Math.max(6, Math.min(W - bw - 6, xs[i] - bw / 2 + (up ? -18 : 18)));
    const by = up ? 46 : H - 46 - bh, ay = up ? y - 32 : y + 24, ey = up ? by + bh : by, ex = bx + (up ? bw - 22 : 22);
    svg += `<polyline class="sx-lead" points="${xs[i]},${ay} ${xs[i]},${(ay + ey) / 2} ${ex},${(ay + ey) / 2} ${ex},${ey}"/>
      <rect x="${xs[i] - 2}" y="${ay - 2}" width="4" height="4" fill="${col}"/>
      <rect class="sx-box${hi ? " hi" : ""}" x="${bx}" y="${by}" width="${bw}" height="${bh}"/>
      <text class="sx-t" x="${bx + 9}" y="${by + 16}">PHASE ${esc(q.phase)}</text>
      <text class="sx-tag" x="${bx + bw - 9}" y="${by + 16}" text-anchor="end" fill="${col}">[ ${tag} ]</text>
      <text class="sx-s" x="${bx + 9}" y="${by + 32}">${esc(clip(q.scope, 26).toUpperCase())}</text>
      <title>Phase ${esc(q.phase)} — ${esc(plain(q.scope))}</title>`;
  });
  if (p) {
    const ti = active >= 0 ? active : P.length - 1, bx = W - 200, by = 4, tx = xs[ti] + 46;
    const on = Math.round(10 * waitFraction(p));
    let segs = "";
    for (let k = 0; k < 10; k++) segs += `<rect x="${bx + 74 + k * 6}" y="${by + 25}" width="4" height="9" fill="${k < on ? "#74e3c1" : "#1f2524"}"/>`;
    svg += `<polyline class="sx-lead" points="${bx},${by + 17} ${tx + 10},${by + 17} ${tx},${y - 40}"/>
      <polygon points="${bx},${by} ${bx + 182},${by} ${bx + 194},${by + 12} ${bx + 194},${by + 42} ${bx},${by + 42}" fill="#000" stroke="#a5adaa"/>
      <rect class="sx-pulse" x="${bx + 9}" y="${by + 11}" width="6" height="6"/>
      <text class="sx-t" x="${bx + 22}" y="${by + 18}">OBSERVING…</text>
      <text class="sx-s" x="${bx + 9}" y="${by + 33}">T-${p.days_remaining}D</text>${segs}`;
  }
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Programme phases and their status">${svg}</svg>`;
}

/* ---------- experiments ---------- */
function pMeter(h) {
  const p = h.decisive_value, a = h.decisive_threshold;
  if (typeof p !== "number") return `<span class="dim">—</span>`;
  const on = Math.round(Math.min(1, Math.max(0, -Math.log10(Math.max(p, 1e-3)) / 3)) * 10);
  return `<span class="pm ${typeof a === "number" && p < a ? "pass" : ""}" title="${esc(h.decisive_stream)}"><span class="bars">${Array.from({ length: 10 }, (_, i) => `<i class="${i < on ? "on" : ""}"></i>`).join("")}</span><data value="${p}">${p.toFixed(3)}</data>${typeof a === "number" ? `<span class="a">α ${a}</span>` : ""}</span>`;
}
function filteredExps() {
  const q = exp.q.trim().toLowerCase();
  return D.hyps.filter((h) => (!exp.status || kindOf(h.label) === exp.status) && (!exp.family || h.family === exp.family) &&
    (!q || [h.title, h.hypothesis_id, h.family, desig(h.registered_seq)].join(" ").toLowerCase().includes(q)));
}
function expRows(sel) {
  const rows = filteredExps();
  if (!rows.length) return `<tr><td colspan="4"><div class="empty-state">${icon("experiments")}No experiment matches these filters.</div></td></tr>`;
  return rows.map((h) => `<tr tabindex="0" data-id="${esc(h.hypothesis_id)}" aria-selected="${h.hypothesis_id === sel}">
    <td class="desig">${desig(h.registered_seq)}</td>
    <td class="ttl">${esc(h.title)}</td>
    <td>${st(h.label)}</td>
    <td>${pMeter(h)}</td></tr>`).join("");
}
function renderExperiments(params) {
  const sel = params.get("exp") || "";
  const kinds = Object.keys(KIND_NAME).filter((k) => D.hyps.some((h) => kindOf(h.label) === k));
  const fams = [...new Set(D.hyps.map((h) => h.family).filter(Boolean))].sort();
  return `${head("Experiments", `${D.hyps.length} registered hypotheses, newest first. Select one to open its dossier.`)}
    <div class="tools">
      <label class="k" for="f-status">Status</label>
      <select class="field" id="f-status"><option value="">All</option>${kinds.map((k) => `<option value="${k}" ${exp.status === k ? "selected" : ""}>${KIND_NAME[k]}</option>`).join("")}</select>
      <label class="k" for="f-family">Family</label>
      <select class="field" id="f-family"><option value="">All</option>${fams.map((f) => `<option ${exp.family === f ? "selected" : ""}>${esc(f)}</option>`).join("")}</select>
      <label class="sr k" for="f-q">Search</label>
      <input class="field" id="f-q" type="search" placeholder="Search designation, title or id" value="${esc(exp.q)}" autocomplete="off">
    </div>
    <div class="split ${sel ? "" : "solo"}">
      <section class="frame"><div class="table-wrap"><table class="exp">
        <thead><tr><th>Designation</th><th>Experiment</th><th>Status</th><th>Decisive p</th></tr></thead>
        <tbody id="exp-body">${expRows(sel)}</tbody></table></div></section>
      ${sel ? `<aside class="frame dossier" id="dossier"><div class="f-body skel"><i></i><i></i><i></i></div></aside>` : ""}
    </div>`;
}
afterRender.experiments = () => {
  const sel = new URLSearchParams(location.search).get("exp");
  const rerow = () => { $("#exp-body").innerHTML = expRows(sel); };
  $("#f-status").addEventListener("change", (e) => { exp.status = e.target.value; rerow(); });
  $("#f-family").addEventListener("change", (e) => { exp.family = e.target.value; rerow(); });
  $("#f-q").addEventListener("input", (e) => { exp.q = e.target.value; rerow(); });
  const open = (tr) => go(tr.dataset.id === sel ? "/experiments" : `/experiments?exp=${encodeURIComponent(tr.dataset.id)}`);
  $("#exp-body").addEventListener("click", (e) => { const tr = e.target.closest("tr[data-id]"); if (tr) open(tr); });
  $("#exp-body").addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const tr = e.target.closest("tr[data-id]"); if (tr) { e.preventDefault(); open(tr); }
  });
  if (sel) fillDossier(sel);
};
function ibars(obj, obs) {
  const rows = Object.entries(obj).map(([k, v]) => [k, obs ? v.observed : v, obs ? v.p : null]);
  const max = Math.max(...rows.map((r) => Math.abs(r[1])), 1e-12), signed = rows.some((r) => r[1] < 0);
  return `<div class="ibars">${rows.map(([k, v, p]) => {
    const w = (Math.abs(v) / max) * (signed ? 50 : 100), left = signed ? (v < 0 ? 50 - w : 50) : 0;
    return `<span class="lab">${esc(k)}</span><span class="tr">${signed ? `<span class="z"></span>` : ""}<span class="f ${v < 0 ? "neg" : ""}" style="left:${left}%;width:${w}%"></span></span><span class="val">${fmt(v)}${p != null ? ` <span class="dim">p ${fmt(p)}</span>` : ""}</span>`;
  }).join("")}</div>`;
}
function breakdownOf(m) {
  for (const [k, v] of Object.entries(m || {})) {
    if (k === "streams" || !v || typeof v !== "object" || Array.isArray(v)) continue;
    const vals = Object.values(v);
    if (vals.length && vals.every((x) => x && typeof x === "object" && typeof x.observed === "number")) return [k, ibars(v, true)];
  }
  for (const [k, v] of Object.entries(m || {})) {
    if (k === "streams" || !v || typeof v !== "object" || Array.isArray(v)) continue;
    const vals = Object.values(v);
    if (vals.length && vals.length <= 16 && vals.every((x) => typeof x === "number")) return [k, ibars(v, false)];
  }
  return null;
}
async function fillDossier(id) {
  const box = $("#dossier"), h = D.hyps.find((x) => x.hypothesis_id === id);
  if (!box) return;
  if (!h) { box.innerHTML = `<div class="empty-state">${icon("assess")}No experiment named ${esc(id)}.</div>`; return; }
  let d;
  try { d = await detail(id); } catch (err) { box.innerHTML = `<p class="err">Could not load the dossier: ${esc(err.message)}</p>`; return; }
  if (!$("#dossier")) return;
  const reg = d.events.find((e) => e.event_type === "hypothesis") || d.events[0];
  const last = d.events[d.events.length - 1], m = last.metrics || {}, params = reg.parameters || {};
  const p = h.decisive_value, a = h.decisive_threshold, bd = breakdownOf(m);
  const art = typeof m.artifact === "string" ? m.artifact.split("/").pop() : "";
  const lines = d.events.map((e) => {
    const lab = e.event_type === "hypothesis" ? "REGISTERED" : (e.withdrawn_by ? "WITHDRAWN" : e.label);
    return `<li data-k="${kindOf(lab)}"><span class="h"><b>seq=${e.seq}</b><span>${esc(stamp(e.timestamp))}</span><span class="kc">${esc(lab)}</span></span>${e.note ? `<span>${esc(e.note.length > 260 ? e.note.slice(0, 259) + "…" : e.note)}</span>` : ""}</li>`;
  }).concat((d.withdrawing_records || []).map((r) => `<li data-k="withdrawn"><span class="h"><b>seq=${r.seq}</b><span>${esc(stamp(r.timestamp))}</span><span class="kc">WITHDRAWS</span></span><span>${esc(r.note.slice(0, 260))}${r.note.length > 260 ? "…" : ""}</span></li>`)).join("");
  box.innerHTML = `
    <div class="d-top"><span class="desig">${desig(h.registered_seq)}</span>${st(h.label)}<h3>${esc(h.title)}</h3><span class="lbl">${esc(h.hypothesis_id)}</span></div>
    <div class="d-sec"><dl class="dl">
      <div><dt>Family</dt><dd>${esc(h.family || "—")}</dd></div><div><dt>Market</dt><dd>${esc(reg.market || "—")}</dd></div>
      <div><dt>Registered</dt><dd>seq=${h.registered_seq} · ${esc(day(h.registered_at))}</dd></div><div><dt>Trials</dt><dd>${h.trials}</dd></div>
    </dl></div>
    <div class="d-sec verdict-line">
      ${h.decisive_stream ? `<span><b>Decides</b> ${esc(h.decisive_stream)} &lt; ${esc(a)}${params.two_sided ? ", two-sided" : ""}</span>` : `<span class="dim">No decisive stream was registered.</span>`}
      ${typeof p === "number" ? `<span><b>Observed</b> ${fmt(p)} — ${typeof a === "number" ? (p < a ? "passes the stream" : "fails the stream") : "no threshold"}</span>` : ""}
      ${m.reason ? `<span><b>Reason</b> ${esc(m.reason)}</span>` : ""}
      ${h.withdrawn_by ? `<span class="kc" data-k="withdrawn"><b>Withdrawn</b> by seq=${h.withdrawn_by}</span>` : ""}
    </div>
    ${bd ? `<div class="d-sec"><span class="k">${esc(bd[0].replace(/_/g, " "))}</span>${bd[1]}</div>` : ""}
    <div class="d-sec"><span class="k">Activity log</span><ul class="lines">${lines}</ul></div>
    <div class="d-sec">
      <details class="more"><summary>Registration</summary>
        ${reg.mechanism ? `<p class="p-sub">${esc(reg.mechanism)}</p>` : ""}
        ${(reg.predictions || []).length ? `<ul class="lines">${reg.predictions.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
        ${reg.null_baseline_structure ? `<p class="p-sub"><span class="k">Null</span> ${esc(reg.null_baseline_structure)}</p>` : ""}
      </details>
      <details class="more"><summary>Raw entries</summary><pre>${esc(JSON.stringify(d, null, 1))}</pre></details>
      <div class="d-actions">${art ? `<a class="btn primary" href="/artifacts?name=${encodeURIComponent(art)}" data-nav>${icon("artifacts", "sm")}Open artifact</a>` : `<button class="btn" type="button" disabled>No artifact</button>`}
        <a class="btn" href="/experiments" data-nav>Close</a></div>
    </div>`;
}

/* ---------- divisions ---------- */
function renderDivisions() {
  const fams = new Map();
  [...D.hyps].sort((a, b) => a.registered_seq - b.registered_seq).forEach((h) => {
    const f = h.family || "unassigned";
    if (!fams.has(f)) fams.set(f, []);
    fams.get(f).push(h);
  });
  const sectors = [...fams.entries()].map(([f, hs], i) => {
    const dead = hs.filter((h) => kindOf(h.label) === "dead").length;
    return `<article class="sector">
      <div class="s-code"><b>S-${String(i + 1).padStart(2, "0")}</b><span class="lbl">${hs.length} exp · ${dead} dead</span></div>
      <h3>${esc(f.replace(/_/g, " "))}</h3>
      <div class="cellrow">${hs.map((h) => `<a href="/experiments?exp=${encodeURIComponent(h.hypothesis_id)}" data-nav data-k="${kindOf(h.label)}" title="${desig(h.registered_seq)} · ${esc(h.label)} · ${esc(h.title)}" aria-label="${desig(h.registered_seq)} ${esc(h.label)}"></a>`).join("")}</div>
    </article>`;
  }).join("");
  const legend = Object.entries(KIND_NAME).map(([k, n]) => `<span class="st" data-k="${k}">${n}</span>`).join("");
  return `${head("Divisions", "Each sector is one family of mechanisms, in the order it was first registered. One cell per experiment; open a cell for its dossier.")}
    <div class="legend">${legend}</div>
    <div class="cells sectors">${sectors}</div>`;
}

/* ---------- trials ---------- */
function trialChart(points, W = 980, H = 330) {
  if (!points.length) return `<div class="empty-state">${icon("trials")}No trials yet.</div>`;
  const L = 38, R = 56, T = 18, B = 30;
  const t = points.map((p) => Date.parse(p.timestamp));
  const t0 = Math.min(...t), t1 = Math.max(...t, t0 + 864e5);
  const top = points[points.length - 1].total, yMax = Math.ceil(top / 10) * 10 || 10;
  const x = (v) => L + ((v - t0) / (t1 - t0)) * (W - L - R), y = (v) => T + (1 - v / yMax) * (H - T - B);
  let d = `M${x(t[0])},${y(0)}`;
  points.forEach((p, i) => { d += ` V${y(p.total)}`; if (i < points.length - 1) d += ` H${x(t[i + 1])}`; });
  let grid = "";
  for (let v = 0; v <= yMax; v += 10) grid += `<line class="c-grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="c-ax" x="${L - 8}" y="${y(v) + 3}" text-anchor="end">${v}</text>`;
  const m = new Date(t0); m.setUTCDate(1); m.setUTCHours(0, 0, 0, 0); m.setUTCMonth(m.getUTCMonth() + 1);
  while (m.getTime() <= t1) {
    grid += `<text class="c-ax" x="${x(m.getTime())}" y="${H - 8}" text-anchor="middle">${m.toLocaleString("en-US", { month: "short", timeZone: "UTC" }).toUpperCase()}</text>`;
    m.setUTCMonth(m.getUTCMonth() + 1);
  }
  const dots = points.map((p, i) => `<a href="/experiments?exp=${encodeURIComponent(p.hypothesis_id)}" data-nav><circle class="c-dot" r="3.2" cx="${x(t[i])}" cy="${y(p.total)}"><title>seq=${p.seq} · ${esc(p.hypothesis_id)} · +${p.added} → ${p.total}</title></circle></a>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cumulative trial count over time, now ${top}">${grid}
    <path class="c-area" d="${d} V${y(0)} Z"/><path class="c-line" d="${d}"/>${dots}
    <text class="c-end" x="${x(t[t.length - 1]) + 10}" y="${y(top) + 5}">N=${top}</text></svg>`;
}
function renderTrials() {
  const b = D.breakdown, rules = Object.entries(b.by_rule || {}).sort((x, y) => y[1] - x[1]);
  return `${head("Trial load", `Every hypothesis registered adds to <code>trial_count()</code>, and the Deflated Sharpe haircut grows with it. Today N = ${D.summary.trial_count}.`)}
    <div class="two">
      ${frame("Cumulative trials", "trials", `<div class="f-body chart">${trialChart(D.trials)}</div>`, `<span class="lbl">select a point for its dossier</span>`)}
      ${frame("By selection rule", "divisions", `<div class="f-body">${rules.map(([r, n]) => `<div class="rule-row"><span>${esc(r.replace(/_/g, " "))}</span><b>${n}</b></div>`).join("") || `<p class="dim">No breakdown.</p>`}
        ${(b.entries || []).length ? `<p class="lbl" style="margin-top:14px">Entries counting more than one</p>${b.entries.map((e) => `<div class="rule-row"><span>seq=${e.seq} · ${esc(e.hypothesis_id)}</span><b>${e.trials}</b></div>`).join("")}` : ""}</div>`)}
    </div>`;
}

/* ---------- observation ---------- */
function renderObservation() {
  const p = pend();
  if (!p) return `${head("Observation", "")}<div class="empty-state">${icon("observation")}No registered test is waiting for data.</div>`;
  const f = waitFraction(p), on = Math.round(f * 52);
  return `${head("Observation", `${esc(p.title)}. One look, taken once every instrument holds ${p.min_intervals} out-of-sample reports.`)}
    <div><div class="count">T-${p.days_remaining}<small>days to the window</small></div></div>
    ${frame("Wait elapsed", "observation", `<div class="f-body" style="display:grid;gap:12px">
      <div class="segs" role="img" aria-label="${(f * 100).toFixed(1)}% of the wait elapsed">${Array.from({ length: 52 }, (_, i) => `<i class="${i < on ? "on" : ""}"></i>`).join("")}</div>
      <dl class="dl"><div><dt>Registered</dt><dd>seq=${p.registered_seq}</dd></div><div><dt>Window opens</dt><dd>${esc(p.earliest_run)}</dd></div>
        <div><dt>In-sample ends</dt><dd>${esc(p.in_sample_last_report)}</dd></div><div><dt>Elapsed</dt><dd>${(f * 100).toFixed(1)}%</dd></div></dl></div>`)}
    ${frame("Before the look", "protocols", `<ul class="check">${p.before_the_look.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>`)}
    <p><a class="go" href="/experiments?exp=${encodeURIComponent(p.hypothesis_id)}" data-nav>Open the registration &gt;&gt;&gt;</a></p>`;
}

/* ---------- log ---------- */
function logLines() {
  const g = logf.grep.trim().toLowerCase();
  const rows = D.ledger.filter((e) => !logf.type || e.event_type === logf.type).map((e) => {
    const lab = e.withdrawn_by ? "WITHDRAWN" : e.label, k = kindOf(lab);
    const prev = (e.prev_hash || "genesis").slice(0, 6), cur = e.entry_hash.slice(0, 6);
    const text = `${stamp(e.timestamp)} seq=${e.seq} ${e.event_type} ${e.hypothesis_id} ${lab} ${prev} ${cur}`.toLowerCase();
    return { text, html: `<div class="ln${e.withdrawn_by ? " struck" : ""}"><span class="ts">[${esc(stamp(e.timestamp))}]</span> <span class="sq">seq=${e.seq}</span> ${esc(e.event_type)} ${esc(e.hypothesis_id)} <span class="kc" data-k="${k}">${esc(lab)}</span>${e.trials ? ` <span class="tr">+${e.trials}</span>` : ""} <span class="hs">${esc(prev)}→${esc(cur)}</span></div>` };
  }).filter((r) => !g || r.text.includes(g));
  return rows.map((r) => r.html).join("") + `<div class="ln cursor">${g ? `<span class="ts">${rows.length} matching line${rows.length === 1 ? "" : "s"}</span> ` : ""}</div>`;
}
function renderLog() {
  const s = D.summary, types = Object.entries(s.by_event_type).sort((a, b) => b[1] - a[1]), max = Math.max(...types.map((t) => t[1]), 1);
  return `${head("Log", "Every entry in the hash-chained research log, oldest first. An entry that a later record withdrew is dimmed.")}
    <div class="tools">
      <label class="sr" for="l-grep">Filter lines</label><input class="field" id="l-grep" type="search" placeholder="grep" value="${esc(logf.grep)}" autocomplete="off">
      <label class="k" for="l-type">Type</label>
      <select class="field" id="l-type"><option value="">All</option>${types.map(([t]) => `<option value="${esc(t)}" ${logf.type === t ? "selected" : ""}>${esc(t.replace(/_/g, " "))}</option>`).join("")}</select>
    </div>
    <div class="two">
      ${frame("Research log", "log", `<samp class="term" id="term" tabindex="0">${logLines()}</samp>`, `<span class="lbl">${s.n_entries} entries</span>`)}
      <div style="display:grid;gap:20px">
        ${frame("Chain head", "chain", `<div class="f-body"><dl class="dl" style="grid-template-columns:1fr">
          <div><dt>State</dt><dd class="kc" data-k="${s.chain_ok ? "alive" : "dead"}">${esc(s.chain_message)}</dd></div>
          <div><dt>Head</dt><dd>seq=${s.last_seq} · ${esc(stamp(s.last_timestamp))}</dd></div>
          <div><dt>Hash</dt><dd class="hash">${esc(s.last_hash)}</dd></div></dl></div>`)}
        ${frame("Composition", "divisions", `<div class="f-body">${types.map(([k, v]) => `<div class="ty-row"><span>${esc(k.replace(/_/g, " "))}</span><span class="b"><i style="width:${(v / max) * 100}%"></i></span><span class="n">${v}</span></div>`).join("")}</div>`)}
      </div>
    </div>`;
}
afterRender.log = () => {
  const term = $("#term"), redraw = () => { term.innerHTML = logLines(); term.scrollTop = term.scrollHeight; };
  term.scrollTop = term.scrollHeight;
  $("#l-grep").addEventListener("input", (e) => { logf.grep = e.target.value; redraw(); });
  $("#l-type").addEventListener("change", (e) => { logf.type = e.target.value; redraw(); });
};

/* ---------- protocols ---------- */
function renderProtocols() {
  const inv = D.status.invariants || [];
  return `${head("Protocols", "The architecture invariants from docs/STATUS.md. If a change would break one, that is the moment to stop.")}
    ${inv.length ? `<div class="cells protocols">${inv.map((t, i) => `<article class="proto"><b>${String(i + 1).padStart(2, "0")}</b><p>${md(t)}</p></article>`).join("")}</div>`
      : `<div class="empty-state">${icon("protocols")}No invariants section in docs/STATUS.md.</div>`}`;
}

/* ---------- artifacts ---------- */
function renderArtifacts(params) {
  const sel = params.get("name") || "";
  return `${head("Artifacts", `${D.artifacts.length} JSON results under research/pre/artifacts. Read-only.`)}
    <div class="two" style="grid-template-columns:minmax(240px,1fr) minmax(0,2.2fr)">
      ${frame("Files", "artifacts", `<ul class="arts">${D.artifacts.map((a) => `<li><button type="button" data-name="${esc(a.name)}" aria-current="${a.name === sel}"><span class="n">${esc(a.name)}</span><span class="m">${(a.bytes / 1024).toFixed(1)} KB · ${esc(day(a.modified))}</span></button></li>`).join("")}</ul>`)}
      ${frame(sel || "Viewer", "log", sel ? `<pre id="art-body">Loading…</pre>` : `<div class="empty-state">${icon("artifacts")}Select a file to read it.</div>`)}
    </div>`;
}
afterRender.artifacts = async () => {
  document.querySelectorAll(".arts button").forEach((b) => b.addEventListener("click", () => go(`/artifacts?name=${encodeURIComponent(b.dataset.name)}`)));
  const sel = new URLSearchParams(location.search).get("name");
  if (!sel) return;
  try {
    const a = await get(`/api/artifact/${encodeURIComponent(sel)}`), text = JSON.stringify(a, null, 1);
    if ($("#art-body")) $("#art-body").textContent = text.length > 300000 ? text.slice(0, 300000) + "\n… truncated" : text;
  } catch (err) { if ($("#art-body")) $("#art-body").textContent = `Could not load ${sel}: ${err.message}`; }
};

/* ---------- 404 ---------- */
function renderNotFound() {
  return `<section class="nf"><span class="k">[ 404 ]</span><h1 class="hero-stmt">No such page<em>.</em></h1>
    <p class="p-sub">${esc(location.pathname)} is not a page on this terminal.</p><p><a class="btn" href="/" data-nav>Back to overview</a></p></section>`;
}

/* ---------- boot ---------- */
function bootSeen() { try { return sessionStorage.getItem("hl-boot") === "1"; } catch (_) { return false; } }
function bootDone() {
  const b = $("#boot");
  b.classList.add("done");
  setTimeout(() => { b.hidden = true; }, 400);
  try { sessionStorage.setItem("hl-boot", "1"); } catch (_) { /* storage blocked */ }
}
function boot(lines) {
  const b = $("#boot");
  if (bootSeen() || matchMedia("(prefers-reduced-motion: reduce)").matches) { b.hidden = true; return; }
  const out = $("#boot-lines");
  let i = 0;
  const tick = () => {
    if (b.classList.contains("done")) return;
    if (i >= lines.length) { setTimeout(bootDone, 380); return; }
    const [txt, cls] = lines[i++];
    out.insertAdjacentHTML("beforeend", `<span class="${cls || ""}">${esc(txt)}</span>`);
    setTimeout(tick, 120);
  };
  b.addEventListener("click", bootDone);
  document.addEventListener("keydown", bootDone, { once: true });
  tick();
}

/* ---------- start ---------- */
async function start() {
  render();
  try {
    const keys = ["summary", "hypotheses", "ledger", "trials", "trial_breakdown", "status", "pending", "artifacts"];
    const [summary, hyps, ledger, trials, breakdown, status, pending, artifacts] = await Promise.all(keys.map((k) => get(`/api/${k}`)));
    Object.assign(D, { summary, hyps, ledger, trials, breakdown, status, pending, artifacts, ready: true });
    $("#chain-state").textContent = summary.chain_ok ? "Verified" : "Broken";
    $("#chain").classList.toggle("bad", !summary.chain_ok);
    $("#bar-n").textContent = summary.trial_count; $("#bar-n").value = summary.trial_count;
    boot([["Mounting research log"], [`${summary.n_entries} entries · head seq=${summary.last_seq}`],
      ["Verifying hash chain"], [summary.chain_message, summary.chain_ok ? "ok" : "bad"],
      [`trial_count() = ${summary.trial_count}`], ["Terminal ready", "ok"]]);
    render();
  } catch (err) {
    $("#boot").hidden = true;
    $("#view").innerHTML = `<div class="page"><p class="err">Cannot reach the harness API (${esc(err.message)}). Is <code>python -m research.ui</code> running?</p></div>`;
  }
}
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-nav]");
  if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  e.preventDefault();
  go(a.getAttribute("href"));
});
window.addEventListener("popstate", () => render());
start();
