"use strict";

/* Harness Ledger — read-only views over /api/*. No writes, no state on the server. */

const $ = (sel) => document.querySelector(sel);
const LEDGER_PAGE = 30;
const state = { hyps: [], kind: "", q: "", ledger: [], etype: "", ledgerAll: false };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function md(s) {
  return esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`(.+?)`/g, "<code>$1</code>");
}
function kindOf(label) {
  const l = String(label || "").toUpperCase();
  if (l === "DEAD" || l === "KILLED") return "dead";
  if (l === "VOID") return "void";
  if (l === "WITHDRAWN") return "withdrawn";
  if (l === "ALIVE" || l === "PROMOTED" || l === "DEPLOYED" || l === "PASS") return "alive";
  if (l === "OPEN" || l === "REGISTERED" || l === "ALIVE_POOLED_ONLY") return "waiting";
  return "shelved";
}
const KIND_NAMES = { dead: "Dead", void: "Void", withdrawn: "Withdrawn", waiting: "Open / waiting", alive: "Alive", shelved: "Shelved / other" };
const KIND_VARS = { dead: "--dead", void: "--void", withdrawn: "--withdrawn", waiting: "--accent", alive: "--alive", shelved: "--shelved" };
function pill(label) {
  return `<span class="pill" data-k="${kindOf(label)}">${esc(label)}</span>`;
}
function day(ts) { return ts ? String(ts).slice(0, 10) : ""; }
function fmt(v) {
  if (typeof v !== "number") return esc(v);
  if (v === 0) return "0";
  const a = Math.abs(v);
  if (a >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (a >= 1) return v.toFixed(3).replace(/\.?0+$/, "");
  return v.toPrecision(3);
}
async function get(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

/* ---------- theme ---------- */
const THEMES = ["system", "light", "dark"];
function applyTheme(t) {
  if (t === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  $("#theme").textContent = t[0].toUpperCase() + t.slice(1);
}
function initTheme() {
  let t = "system";
  try { t = localStorage.getItem("hl-theme") || "system"; } catch (_) { /* storage blocked */ }
  applyTheme(THEMES.includes(t) ? t : "system");
  $("#theme").addEventListener("click", () => {
    const cur = document.documentElement.dataset.theme || "system";
    const next = THEMES[(THEMES.indexOf(cur) + 1) % THEMES.length];
    applyTheme(next);
    try { localStorage.setItem("hl-theme", next); } catch (_) { /* storage blocked */ }
  });
}

/* ---------- header ---------- */
function renderVitals(s) {
  const chain = s.chain_ok
    ? `<span class="chain-ok">verified</span>`
    : `<span class="chain-bad">BROKEN</span>`;
  $("#vitals").innerHTML = `
    <div class="vital"><span class="k">Hash chain</span><span class="v">${chain}</span></div>
    <div class="vital"><span class="k">Entries</span><span class="v">${s.n_entries} <small>to seq=${esc(s.last_seq)}</small></span></div>
    <div class="vital"><span class="k">trial_count()</span><span class="v">${s.trial_count}</span></div>
    <div class="vital"><span class="k">Last entry</span><span class="v"><small>${esc(day(s.last_timestamp))}</small></span></div>`;
  $("#vitals").title = s.chain_message;
  const types = Object.entries(s.by_event_type).sort((a, b) => b[1] - a[1]);
  $("#types").innerHTML = types.map(([k, v]) => `<dt>${esc(k.replace(/_/g, " "))}</dt><dd>${v}</dd>`).join("");
}

/* ---------- status ---------- */
function phaseState(status) {
  if (status.startsWith("✅")) return ["done", "Done"];
  if (status.startsWith("▶")) return ["active", "Active"];
  if (status.startsWith("⏸")) return ["paused", "Paused"];
  return ["", "—"];
}
function renderStatus(st) {
  if (!st.available) { $("#headline").textContent = "docs/STATUS.md not found."; return; }
  $("#headline").innerHTML = md(st.headline);
  $("#phases").innerHTML = st.phases.map((p) => {
    const [k, name] = phaseState(p.status);
    const body = p.status.replace(/^[✅▶⏸️\s]+/u, "");
    return `<li class="phase" data-state="${k}">
      <span class="p-id">Phase ${esc(p.phase)}</span>
      <span class="p-scope">${md(p.scope)}</span>
      <span class="p-state">${name}</span>
      <details><summary>Detail</summary><p>${md(body)}</p></details>
    </li>`;
  }).join("");
}

/* ---------- hypotheses ---------- */
function pGauge(h) {
  const p = h.decisive_value, thr = h.decisive_threshold;
  if (typeof p !== "number") return `<span class="dash">—</span>`;
  const pos = (x) => Math.min(1, Math.max(0, (Math.log10(Math.max(x, 1e-3)) + 3) / 3)) * 100;
  const pass = typeof thr === "number" && p < thr;
  return `<div class="pgauge" title="${esc(h.decisive_stream)} = ${p}${typeof thr === "number" ? ` (threshold ${thr})` : ""}">
    <span class="pv">${p.toFixed(3)}</span>
    <span class="track">${typeof thr === "number" ? `<span class="thr" style="left:${pos(thr)}%"></span>` : ""}
      <span class="dot ${pass ? "pass" : "fail"}" style="left:${pos(p)}%"></span></span>
  </div>`;
}
function renderChips() {
  const counts = {};
  state.hyps.forEach((h) => { const k = kindOf(h.label); counts[k] = (counts[k] || 0) + 1; });
  const order = ["dead", "void", "withdrawn", "waiting", "alive", "shelved"].filter((k) => counts[k]);
  const chip = (k, name, n) => `<button type="button" class="chip" data-kind="${k}" aria-pressed="${state.kind === k}">${esc(name)} <span class="n">${n}</span></button>`;
  $("#chips").innerHTML = chip("", "All", state.hyps.length) + order.map((k) => chip(k, KIND_NAMES[k], counts[k])).join("");
}
function renderHyps() {
  const q = state.q.trim().toLowerCase();
  const rows = state.hyps.filter((h) =>
    (!state.kind || kindOf(h.label) === state.kind) &&
    (!q || [h.title, h.hypothesis_id, h.family, h.market].join(" ").toLowerCase().includes(q)));
  $("#hyp-count").textContent = `${rows.length} of ${state.hyps.length}`;
  $("#hyp-body").innerHTML = rows.length ? rows.map((h) => `
    <tr tabindex="0" data-id="${esc(h.hypothesis_id)}">
      <td class="num">${h.registered_seq}</td>
      <td><div class="t-title">${esc(h.title)}</div><div class="t-id">${esc(h.hypothesis_id)} · ${esc(h.timeframe || "")} ${esc(h.market || "")}</div></td>
      <td class="t-family">${esc(h.family || "—")}</td>
      <td>${pill(h.label)}${h.withdrawn_by ? `<div class="t-id">by seq=${h.withdrawn_by}</div>` : ""}</td>
      <td>${pGauge(h)}</td>
      <td class="num">${h.trials}</td>
    </tr>`).join("") : `<tr><td colspan="6" class="empty">No hypothesis matches.</td></tr>`;
  renderChips();
}

/* ---------- trials chart ---------- */
function niceMax(n) { const step = n <= 10 ? 2 : n <= 40 ? 5 : 10; return Math.ceil(n / step) * step || step; }
function renderTrials(points) {
  if (!points.length) { $("#trials-chart").innerHTML = `<p class="empty">No trials yet.</p>`; return; }
  const kindById = Object.fromEntries(state.hyps.map((h) => [h.hypothesis_id, kindOf(h.label)]));
  const W = 900, H = 260, L = 40, R = 64, T = 16, B = 30;
  const t = points.map((p) => Date.parse(p.timestamp));
  const t0 = Math.min(...t), t1 = Math.max(...t, t0 + 864e5);
  const yMax = niceMax(points[points.length - 1].total);
  const x = (v) => L + ((v - t0) / (t1 - t0)) * (W - L - R);
  const y = (v) => T + (1 - v / yMax) * (H - T - B);
  let d = `M${x(t[0])},${y(0)}`;
  points.forEach((p, i) => { d += ` V${y(p.total)}`; if (i < points.length - 1) d += ` H${x(t[i + 1])}`; });
  const end = x(t[t.length - 1]);
  const area = `${d} V${y(0)} Z`;
  const yt = []; const step = yMax <= 10 ? 2 : yMax <= 40 ? 5 : 10;
  for (let v = 0; v <= yMax; v += step) yt.push(v);
  const months = []; const m = new Date(t0); m.setUTCDate(1); m.setUTCHours(0, 0, 0, 0); m.setUTCMonth(m.getUTCMonth() + 1);
  while (m.getTime() <= t1) { months.push(m.getTime()); m.setUTCMonth(m.getUTCMonth() + 1); }
  const fmtM = (ms) => new Date(ms).toLocaleString("en-US", { month: "short", timeZone: "UTC" }) + (new Date(ms).getUTCMonth() === 0 ? ` ${new Date(ms).getUTCFullYear()}` : "");
  const dots = points.map((p, i) => {
    const k = kindById[p.hypothesis_id] || "shelved";
    return `<circle class="mark" cx="${x(t[i])}" cy="${y(p.total)}" r="4.5" style="fill:var(${KIND_VARS[k]})" data-id="${esc(p.hypothesis_id)}"><title>seq=${p.seq} · ${esc(p.hypothesis_id)} · +${p.added} → ${p.total} (${day(p.timestamp)})</title></circle>`;
  }).join("");
  const last = points[points.length - 1];
  $("#trials-chart").innerHTML = `
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cumulative trial count over time, now ${last.total}">
      <g class="grid">${yt.map((v) => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`).join("")}</g>
      <path class="area" d="${area}"/>
      <path class="step" d="${d}"/>
      <g class="axis">${yt.map((v) => `<text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${v}</text>`).join("")}
        ${months.map((ms) => `<text x="${x(ms)}" y="${H - 8}" text-anchor="middle">${fmtM(ms)}</text>`).join("")}</g>
      ${dots}
      <g class="end"><text x="${end + 10}" y="${y(last.total) + 4}">N=${last.total}</text></g>
    </svg>
    <div class="legend">${["dead", "void", "withdrawn", "waiting", "alive", "shelved"].map((k) => `<span><i style="--c:var(${KIND_VARS[k]})"></i>${KIND_NAMES[k]}</span>`).join("")}<span>· colour is each hypothesis's verdict today</span></div>`;
  $("#trials-chart").querySelectorAll(".mark").forEach((c) => c.addEventListener("click", () => openHyp(c.dataset.id)));
}

/* ---------- ledger ---------- */
function renderLedger() {
  const all = state.ledger.filter((e) => !state.etype || e.event_type === state.etype).slice().reverse();
  const rows = state.ledgerAll ? all : all.slice(0, LEDGER_PAGE);
  $("#ledger-body").innerHTML = rows.map((e) => `
    <tr class="${e.withdrawn_by ? "struck" : ""}">
      <td class="num">${e.seq}</td>
      <td class="when">${esc(day(e.timestamp))}</td>
      <td class="etype">${esc(e.event_type)}</td>
      <td class="subj">${esc(e.title || "")}<span class="t-id">${esc(e.hypothesis_id)}</span></td>
      <td>${pill(e.withdrawn_by ? "WITHDRAWN" : e.label)}</td>
      <td class="num">${e.trials ? "+" + e.trials : ""}</td>
      <td class="hash" title="prev ${esc(e.prev_hash)}&#10;this ${esc(e.entry_hash)}">${esc((e.prev_hash || "genesis").slice(0, 7))} → <b>${esc(e.entry_hash.slice(0, 7))}</b></td>
    </tr>`).join("");
  const btn = $("#ledger-more");
  btn.hidden = all.length <= LEDGER_PAGE;
  btn.textContent = state.ledgerAll ? "Show latest only" : `Show all ${all.length}`;
}
function renderEtypes() {
  const types = [...new Set(state.ledger.map((e) => e.event_type))].sort();
  $("#etype").innerHTML = `<option value="">All event types</option>` + types.map((t) => `<option value="${esc(t)}">${esc(t.replace(/_/g, " "))}</option>`).join("");
}

/* ---------- sidebar ---------- */
function renderPending(list) {
  $("#pending").innerHTML = list.length ? list.map((p) => `
    <div class="wait">
      <div class="days">${p.days_remaining}<small>days to the earliest look</small></div>
      <div class="t">${esc(p.title)}</div>
      <div class="meta">seq=${p.registered_seq} · look ≥ ${esc(p.earliest_run)} · ${p.min_intervals} intervals each</div>
      <ol>${p.before_the_look.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
    </div>`).join("") : `<p class="count">Nothing is waiting.</p>`;
}
function renderArtifacts(list) {
  $("#artifacts").innerHTML = list.map((a) => `<li><button type="button" data-name="${esc(a.name)}" title="${a.bytes.toLocaleString()} bytes · ${esc(a.modified)}">${esc(a.name)}</button></li>`).join("");
}

/* ---------- drawer ---------- */
let lastFocus = null;
function openDrawer(html) {
  lastFocus = document.activeElement;
  $("#drawer-body").innerHTML = html;
  $("#drawer").classList.add("open");
  $("#drawer").setAttribute("aria-hidden", "false");
  $("#scrim").hidden = false;
  $("#close").focus();
}
function closeDrawer() {
  $("#drawer").classList.remove("open");
  $("#drawer").setAttribute("aria-hidden", "true");
  $("#scrim").hidden = true;
  if (lastFocus) lastFocus.focus();
}
function isNumMap(o) { const v = Object.values(o); return v.length > 0 && v.every((x) => typeof x === "number"); }
function isObsMap(o) { const v = Object.values(o); return v.length > 0 && v.every((x) => x && typeof x === "object" && typeof x.observed === "number"); }
function bars(obj, withP) {
  const entries = Object.entries(obj).map(([k, v]) => [k, withP ? v.observed : v, withP ? v.p : null]);
  const max = Math.max(...entries.map((e) => Math.abs(e[1])), 1e-12);
  const signed = entries.some((e) => e[1] < 0);
  return `<div class="bars">${entries.map(([k, v, p]) => {
    const w = (Math.abs(v) / max) * (signed ? 50 : 100);
    const left = signed ? (v < 0 ? 50 - w : 50) : 0;
    return `<span class="lab">${esc(k)}</span>
      <span class="bar">${signed ? `<span class="zero"></span>` : ""}<span class="fill ${v < 0 ? "neg" : ""}" style="left:${left}%;width:${w}%"></span></span>
      <span class="val">${fmt(v)}${p != null ? ` <span class="dash">p ${fmt(p)}</span>` : ""}</span>`;
  }).join("")}</div>`;
}
function renderMetrics(m, decisive, thr) {
  if (!m || !Object.keys(m).length) return "";
  let out = "", scalars = [], rest = {};
  for (const [k, v] of Object.entries(m)) {
    if (k === "streams" && v && typeof v === "object") {
      out += `<div class="sub-h">streams</div><table class="kv"><tbody>${Object.entries(v).map(([s, p]) => {
        const dec = s === decisive;
        const pass = dec && typeof thr === "number" && typeof p === "number" ? (p < thr ? " · passes" : " · fails") : "";
        return `<tr><td class="mono">${esc(s)}${dec ? " <strong>(decisive)</strong>" : ""}</td><td class="num">${fmt(p)}${esc(pass)}</td></tr>`;
      }).join("")}</tbody></table>`;
    } else if (v && typeof v === "object" && !Array.isArray(v) && isObsMap(v)) {
      out += `<div class="sub-h">${esc(k)}</div>${bars(v, true)}`;
    } else if (v && typeof v === "object" && !Array.isArray(v) && isNumMap(v) && Object.keys(v).length <= 24) {
      out += `<div class="sub-h">${esc(k)}</div>${bars(v, false)}`;
    } else if (v === null || typeof v !== "object") {
      scalars.push([k, v]);
    } else {
      rest[k] = v;
    }
  }
  if (scalars.length) out = `<table class="kv"><tbody>${scalars.map(([k, v]) => `<tr><td class="mono">${esc(k)}</td><td>${typeof v === "number" ? `<span class="mono">${fmt(v)}</span>` : esc(v)}</td></tr>`).join("")}</tbody></table>` + out;
  if (Object.keys(rest).length) out += `<details class="raw"><summary>More metrics</summary><pre>${esc(JSON.stringify(rest, null, 1))}</pre></details>`;
  return out;
}
async function openHyp(id) {
  let h;
  try { h = await get(`/api/hypothesis/${encodeURIComponent(id)}`); }
  catch (err) { openDrawer(`<p class="error">Could not load ${esc(id)}: ${esc(err.message)}</p>`); return; }
  const reg = h.events.find((e) => e.event_type === "hypothesis") || h.events[0];
  const row = state.hyps.find((x) => x.hypothesis_id === id) || {};
  const params = reg.parameters || {};
  const meta = [["Family", reg.family], ["Market", reg.market], ["Timeframe", reg.timeframe],
    ["Gate role", reg.edge_gate_role], ["Selection", reg.selection_rule], ["Registered", `seq=${reg.seq} · ${day(reg.timestamp)}`],
    ["Min decidable SR", reg.min_decidable_sharpe], ["Snapshot", reg.registry_snapshot]]
    .filter(([, v]) => v !== null && v !== undefined && v !== "");
  const events = h.events.map((e) => {
    const label = e.event_type === "hypothesis" ? "REGISTERED" : (e.withdrawn_by ? "WITHDRAWN" : e.label);
    return `<li class="event" data-k="${kindOf(label)}">
      <div class="e-head"><span class="e-seq">seq=${e.seq}</span><span class="e-when">${esc(e.timestamp)}</span>
        <span class="etype mono">${esc(e.event_type)}</span>${pill(label)}${e.counts_as_trial ? `<span class="mono dash">counts as a trial</span>` : ""}</div>
      ${e.withdrawn_by ? `<p class="struck-note">This reading was withdrawn by seq=${e.withdrawn_by}.</p>` : ""}
      ${e.note ? `<p class="note">${esc(e.note)}</p>` : ""}
      ${renderMetrics(e.metrics, params.decisive_stream, params.decisive_threshold)}
    </li>`;
  }).join("");
  const withdrawals = (h.withdrawing_records || []).map((r) => `
    <div class="block"><h4>Withdrawn by seq=${r.seq} · ${esc(r.hypothesis_id)}</h4><p>${esc(r.note)}</p>${renderMetrics(r.metrics)}</div>`).join("");
  openDrawer(`
    <div class="d-head">
      <div>${pill(row.label || reg.label)}</div>
      <h3 id="d-title">${esc(reg.title)}</h3>
      <span class="t-id">${esc(id)}</span>
    </div>
    <dl class="meta-grid">${meta.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>
    ${reg.mechanism ? `<div class="block"><h4>Mechanism</h4><p>${esc(reg.mechanism)}</p></div>` : ""}
    ${params.decisive_stream ? `<div class="block"><h4>Decides</h4><p><code>${esc(params.decisive_stream)}</code> &lt; ${esc(params.decisive_threshold)}${params.two_sided ? ", two-sided" : ""}.</p>${params.decisive_rationale ? `<p>${esc(params.decisive_rationale)}</p>` : ""}</div>` : ""}
    ${(reg.predictions || []).length ? `<div class="block"><h4>Predictions, as registered</h4><ul>${reg.predictions.map((p) => `<li>${esc(p)}</li>`).join("")}</ul></div>` : ""}
    ${reg.null_baseline_structure ? `<div class="block"><h4>Null</h4><p>${esc(reg.null_baseline_structure)}</p></div>` : ""}
    ${withdrawals}
    <div class="sub-h">History</div>
    <ol class="timeline">${events}</ol>
    ${Object.keys(params).length ? `<details class="raw"><summary>Registered parameters</summary><pre>${esc(JSON.stringify(params, null, 1))}</pre></details>` : ""}`);
}
async function openArtifact(name) {
  try {
    const a = await get(`/api/artifact/${encodeURIComponent(name)}`);
    const text = JSON.stringify(a, null, 1);
    openDrawer(`<div class="d-head"><h3 id="d-title">${esc(name)}</h3><span class="t-id">research/pre/artifacts</span></div>
      <pre>${esc(text.length > 200000 ? text.slice(0, 200000) + "\n… truncated" : text)}</pre>`);
  } catch (err) { openDrawer(`<p class="error">Could not load ${esc(name)}: ${esc(err.message)}</p>`); }
}

/* ---------- wiring ---------- */
function wire() {
  $("#chips").addEventListener("click", (ev) => {
    const b = ev.target.closest(".chip"); if (!b) return;
    state.kind = b.dataset.kind; renderHyps();
  });
  $("#q").addEventListener("input", (ev) => { state.q = ev.target.value; renderHyps(); });
  $("#hyp-body").addEventListener("click", (ev) => { const r = ev.target.closest("tr[data-id]"); if (r) openHyp(r.dataset.id); });
  $("#hyp-body").addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter" && ev.key !== " ") return;
    const r = ev.target.closest("tr[data-id]"); if (r) { ev.preventDefault(); openHyp(r.dataset.id); }
  });
  $("#etype").addEventListener("change", (ev) => { state.etype = ev.target.value; renderLedger(); });
  $("#ledger-more").addEventListener("click", () => { state.ledgerAll = !state.ledgerAll; renderLedger(); });
  $("#artifacts").addEventListener("click", (ev) => { const b = ev.target.closest("button[data-name]"); if (b) openArtifact(b.dataset.name); });
  $("#close").addEventListener("click", closeDrawer);
  $("#scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && $("#drawer").classList.contains("open")) closeDrawer(); });
}

async function load() {
  try {
    const [summary, hyps, ledger, trials, status, pending, artifacts] = await Promise.all(
      ["summary", "hypotheses", "ledger", "trials", "status", "pending", "artifacts"].map((p) => get(`/api/${p}`)));
    state.hyps = hyps; state.ledger = ledger;
    renderVitals(summary); renderStatus(status); renderHyps(); renderTrials(trials);
    renderEtypes(); renderLedger(); renderPending(pending); renderArtifacts(artifacts);
  } catch (err) {
    document.querySelector(".main").insertAdjacentHTML("afterbegin",
      `<p class="error">Could not reach the harness API (${esc(err.message)}). Is <code>python -m research.ui</code> still running?</p>`);
  }
}

initTheme();
wire();
load();
