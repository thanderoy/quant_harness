"use strict";

/* Harness Ledger — research terminal. Read-only views over /api/*. */

const $ = (s) => document.querySelector(s);
const state = { hyps: [], ledger: [], status: "", family: "", q: "", grep: "", open: null, details: {} };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function md(s) { return esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`(.+?)`/g, "<code>$1</code>"); }
function kindOf(label) {
  const l = String(label || "").toUpperCase();
  if (l === "DEAD" || l === "KILLED") return "dead";
  if (l === "VOID") return "void";
  if (l === "WITHDRAWN") return "withdrawn";
  if (l === "ALIVE" || l === "PROMOTED" || l === "DEPLOYED" || l === "PASS") return "alive";
  if (l === "OPEN" || l === "REGISTERED" || l === "ALIVE_POOLED_ONLY") return "waiting";
  return "shelved";
}
const desig = (seq) => `EXP-${String(seq).padStart(3, "0")}`;
const stamp = (ts) => String(ts || "").replace("T", " ").replace("Z", "").slice(0, 16);
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
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

/* ---------- header ---------- */
function renderBar(s) {
  $("#sync").textContent = `Last entry: ${stamp(s.last_timestamp)} UTC`;
  $("#vitals").innerHTML = `
    <span class="kv-i">Chain: <b class="${s.chain_ok ? "ok" : "bad"}">${s.chain_ok ? "VERIFIED" : "BROKEN"}</b></span><span class="sep">|</span>
    <span class="kv-i">Entries: <b>${s.n_entries}</b></span><span class="sep">|</span>
    <span class="kv-i">Head: <b>seq=${esc(s.last_seq)}</b></span><span class="sep">|</span>
    <span class="kv-i">Hash: <b>${esc(String(s.last_hash || "").slice(0, 12))}</b></span>
    <span class="kv-i push">trial_count(): <b class="ok">${s.trial_count}</b></span>`;
  $("#vitals").title = s.chain_message;
  $("#trial-big").textContent = s.trial_count;
  const chip = $("#chain-chip");
  chip.textContent = s.chain_ok ? "● chain ok" : "● chain broken";
  chip.classList.toggle("bad", !s.chain_ok);
  const types = Object.entries(s.by_event_type).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...types.map((t) => t[1]), 1);
  $("#types").innerHTML = types.map(([k, v]) => `<div class="ty-row"><span class="l">${esc(k.replace(/_/g, " "))}</span><span class="b"><i style="width:${(v / max) * 100}%"></i></span><span class="n">${v}</span></div>`).join("");
}

/* ---------- schematic ---------- */
function phaseState(status) {
  if (status.startsWith("✅")) return "done";
  if (status.startsWith("▶")) return "active";
  if (status.startsWith("⏸")) return "paused";
  return "unknown";
}
const STATE_TAG = { done: ["DONE", "var(--mint)"], active: ["ACTIVE", "#8fb6ff"], paused: ["PAUSED", "var(--amber)"], unknown: ["—", "var(--dim)"] };
function plain(s) { return String(s).replace(/\*\*|`/g, ""); }
function clip(s, n) { s = plain(s); return s.length > n ? s.slice(0, n - 1) + "…" : s; }
function module3d(x, y, hi) {
  const w = 74, h = 46, d = 9, l = x - w / 2, t = y - h / 2;
  const wire = hi ? "sx-wire-hi" : "sx-wire";
  let hatch = "";
  for (let i = l + 7; i < l + w - 2; i += 7) hatch += `<line class="${hi ? "sx-hatch-hi" : "sx-hatch"}" x1="${i}" y1="${t + 4}" x2="${i}" y2="${t + h - 4}"/>`;
  return `<g>
    <rect class="${wire}" x="${l}" y="${t}" width="${w}" height="${h}" style="fill:var(--void-bg)"/>
    ${hatch}
    <polygon class="${wire}" points="${l},${t} ${l + d},${t - d} ${l + w + d},${t - d} ${l + w},${t}"/>
    <polygon class="${wire}" points="${l + w},${t} ${l + w + d},${t - d} ${l + w + d},${t + h - d} ${l + w},${t + h}"/>
    <line class="${wire}" x1="${l - 16}" y1="${y}" x2="${l}" y2="${y}"/>
    <line class="${wire}" x1="${l + w + d}" y1="${y - d / 2}" x2="${l + w + d + 12}" y2="${y - d / 2}"/>
  </g>`;
}
function renderSchematic(st, pending, summary) {
  if (!st.available) { $("#schematic").innerHTML = `<p class="empty">docs/STATUS.md not found.</p>`; return; }
  $("#headline").innerHTML = md(st.headline);
  const P = st.phases, W = 880, H = 350, y = 182, x0 = 80, x1 = 780;
  const xs = P.map((_, i) => (P.length === 1 ? (x0 + x1) / 2 : x0 + (i * (x1 - x0)) / (P.length - 1)));
  const active = P.findIndex((p) => phaseState(p.status) === "active");
  $("#phase-note").textContent = `${P.filter((p) => phaseState(p.status) === "done").length}/${P.length} phases done`;
  let svg = `<line class="sx-pipe" x1="${xs[0] - 50}" y1="${y}" x2="${xs[xs.length - 1] + 60}" y2="${y}"/>`;
  P.forEach((p, i) => {
    const s = phaseState(p.status), hi = s === "active";
    svg += module3d(xs[i], y, hi);
    const up = i % 2 === 0, bw = 150, bh = 40;
    const bx = Math.max(6, Math.min(W - bw - 6, xs[i] - bw / 2 + (up ? -18 : 18)));
    const by = up ? 52 : H - 52 - bh;
    const ay = up ? y - 32 : y + 24;
    const ey = up ? by + bh : by;
    const ex = bx + (up ? bw - 22 : 22);
    const [tag, col] = STATE_TAG[s];
    svg += `<polyline class="sx-lead" points="${xs[i]},${ay} ${xs[i]},${(ay + ey) / 2} ${ex},${(ay + ey) / 2} ${ex},${ey}"/>
      <circle cx="${xs[i]}" cy="${ay}" r="2" style="fill:${col}"/>
      <rect class="${hi ? "sx-box-hi" : "sx-box"}" x="${bx}" y="${by}" width="${bw}" height="${bh}"/>
      <text class="sx-t" x="${bx + 8}" y="${by + 15}">PHASE ${esc(p.phase)}</text>
      <rect x="${bx + bw - 58}" y="${by + 6}" width="50" height="12" style="fill:${col};opacity:.16"/>
      <text class="sx-tag" x="${bx + bw - 33}" y="${by + 15}" text-anchor="middle" style="fill:${col}">${tag}</text>
      <text class="sx-s" x="${bx + 8}" y="${by + 31}">${esc(clip(p.scope, 24))}</text>
      <title>Phase ${esc(p.phase)} — ${esc(plain(p.scope))}: ${esc(plain(p.status))}</title>`;
  });
  const pend = pending[0];
  if (pend) {
    const ti = active >= 0 ? active : P.length - 1;
    const bx = W - 196, by = 8, tx = xs[ti] + 46;
    const done = Math.round(10 * observationFraction(pend));
    let segs = "";
    for (let k = 0; k < 10; k++) segs += `<rect x="${bx + 70 + k * 6}" y="${by + 24}" width="4" height="9" style="fill:${k < done ? "var(--mint)" : "#2a302f"}"/>`;
    svg += `<polyline class="sx-lead" points="${bx},${by + 16} ${tx + 10},${by + 16} ${tx},${y - 40}"/>
      <polygon points="${bx},${by} ${bx + 178},${by} ${bx + 190},${by + 12} ${bx + 190},${by + 40} ${bx},${by + 40}" style="fill:var(--void-bg);stroke:var(--ink-2)"/>
      <circle class="sx-pulse" cx="${bx + 12}" cy="${by + 13}" r="3"/>
      <text class="sx-t" x="${bx + 22}" y="${by + 16}">OBSERVING…</text>
      <text class="sx-s" x="${bx + 8}" y="${by + 32}">T-${pend.days_remaining}d</text>${segs}`;
  }
  svg += `<g class="sx-s"><text x="16" y="${H - 44}">:</text><text x="16" y="${H - 32}">head  seq=${esc(summary.last_seq)}</text>
    <text x="16" y="${H - 20}">N     ${summary.trial_count}</text><text x="16" y="${H - 8}">chain ${summary.chain_ok ? "ok" : "BROKEN"}</text></g>`;
  $("#schematic").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Programme phases and their status">${svg}</svg>`;
}

/* ---------- census + trials + window ---------- */
function renderStats() {
  const c = { dead: 0, void: 0, withdrawn: 0, waiting: 0, alive: 0, shelved: 0 };
  state.hyps.forEach((h) => { c[kindOf(h.label)]++; });
  const box = (k, n, l) => `<div class="stat" data-k="${k}"><span class="n">${n}</span><span class="l">${l}</span></div>`;
  $("#stats").innerHTML = box("", state.hyps.length, "Registered") + box("dead", c.dead, "Dead") +
    box("void", c.void + c.withdrawn, "Void / wdn") + box("open", c.waiting + c.alive, "Open") +
    `<p class="dim" style="grid-column:1/-1;margin:0;font-size:11px">shelved ${c.shelved} · alive ${c.alive} · withdrawn ${c.withdrawn} · void ${c.void}</p>`;
}
function renderTrials(points) {
  if (!points.length) { $("#trials-chart").innerHTML = `<p class="empty">No trials yet.</p>`; return; }
  const W = 440, H = 150, L = 26, R = 40, T = 10, B = 20;
  const t = points.map((p) => Date.parse(p.timestamp));
  const t0 = Math.min(...t), t1 = Math.max(...t, t0 + 864e5);
  const top = points[points.length - 1].total, yMax = Math.ceil(top / 10) * 10 || 10;
  const x = (v) => L + ((v - t0) / (t1 - t0)) * (W - L - R);
  const y = (v) => T + (1 - v / yMax) * (H - T - B);
  let d = `M${x(t[0])},${y(0)}`;
  points.forEach((p, i) => { d += ` V${y(p.total)}`; if (i < points.length - 1) d += ` H${x(t[i + 1])}`; });
  const area = `${d} V${y(0)} Z`;
  let grid = "";
  for (let v = 0; v <= yMax; v += 10) grid += `<line class="c-grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="c-ax" x="${L - 6}" y="${y(v) + 3}" text-anchor="end">${v}</text>`;
  const m = new Date(t0); m.setUTCDate(1); m.setUTCHours(0, 0, 0, 0); m.setUTCMonth(m.getUTCMonth() + 1);
  const months = []; while (m.getTime() <= t1) { months.push(m.getTime()); m.setUTCMonth(m.getUTCMonth() + 1); }
  const step = Math.max(1, Math.ceil(months.length / 6));
  months.filter((_, i) => i % step === 0).forEach((ms) => {
    const dt = new Date(ms);
    grid += `<text class="c-ax" x="${x(ms)}" y="${H - 5}" text-anchor="middle">${String(dt.getUTCDate()).padStart(2, "0")}/${String(dt.getUTCMonth() + 1).padStart(2, "0")}</text>`;
  });
  const dots = points.map((p, i) => `<circle class="c-dot" r="2.6" cx="${x(t[i])}" cy="${y(p.total)}" data-id="${esc(p.hypothesis_id)}"><title>seq=${p.seq} ${esc(p.hypothesis_id)} +${p.added} → ${p.total}</title></circle>`).join("");
  const ex = x(t[t.length - 1]);
  $("#trials-chart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Cumulative trials over time, now ${top}">
    <defs><linearGradient id="g-mint" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#74e3c1" stop-opacity=".45"/><stop offset="1" stop-color="#74e3c1" stop-opacity="0"/></linearGradient></defs>
    ${grid}<path d="${area}" fill="url(#g-mint)"/><path class="c-line" d="${d}"/>${dots}
    <text class="c-end" x="${ex + 6}" y="${y(top) + 3}">${top}</text></svg>`;
  $("#trials-chart").querySelectorAll(".c-dot").forEach((c) => c.addEventListener("click", () => focusExp(c.dataset.id)));
}
function observationFraction(p) {
  const h = state.hyps.find((x) => x.hypothesis_id === p.hypothesis_id);
  const start = Date.parse(h ? h.registered_at : Date.now()), end = Date.parse(p.earliest_run + "T00:00:00Z");
  return Math.min(1, Math.max(0, (Date.now() - start) / Math.max(1, end - start)));
}
function renderWindow(list) {
  if (!list.length) { $("#pending").innerHTML = `<p class="win dim">&gt; No observation is scheduled.</p>`; return; }
  $("#pending").innerHTML = list.map((p) => {
    const f = observationFraction(p), on = Math.round(f * 40);
    const segs = Array.from({ length: 40 }, (_, i) => `<i class="${i < on ? "on" + (i < on - 1 ? "" : " soft") : ""}"></i>`).join("");
    return `<div class="win">
      <div class="win-top"><span class="t">${esc(desig(p.registered_seq))} · COT OOS</span><span class="pct">${(f * 100).toFixed(1)}%</span></div>
      <div class="segs" aria-label="${(f * 100).toFixed(1)}% of the wait elapsed">${segs}</div>
      <dl class="win-meta">
        <dt>Window opens</dt><dd>${esc(p.earliest_run)} · T-${p.days_remaining}d</dd>
        <dt>Sample</dt><dd>${p.min_intervals} reports per instrument, after ${esc(p.in_sample_last_report)}</dd>
        <dt>Looks</dt><dd>1 — no interim run</dd>
      </dl>
      <ul class="checklist">${p.before_the_look.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>
    </div>`;
  }).join("");
}

/* ---------- experiment table ---------- */
function pMeter(h) {
  const p = h.decisive_value, a = h.decisive_threshold;
  if (typeof p !== "number") return `<span class="dash">—</span>`;
  const on = Math.round(Math.min(1, Math.max(0, -Math.log10(Math.max(p, 1e-3)) / 3)) * 10);
  const pass = typeof a === "number" && p < a;
  return `<span class="pm ${pass ? "pass" : ""}" title="${esc(h.decisive_stream)}"><span class="bars">${Array.from({ length: 10 }, (_, i) => `<i class="${i < on ? "on" : ""}"></i>`).join("")}</span><span class="v">${p.toFixed(3)}</span>${typeof a === "number" ? `<span class="a">/α ${a}</span>` : ""}</span>`;
}
function renderFilters() {
  const kinds = [...new Set(state.hyps.map((h) => h.label))].sort();
  $("#status-filter").innerHTML = `<option value="">All statuses</option>` + kinds.map((k) => `<option value="${esc(k)}">${esc(k)}</option>`).join("");
  const fams = [...new Set(state.hyps.map((h) => h.family).filter(Boolean))].sort();
  $("#family-filter").innerHTML = `<option value="">All families</option>` + fams.map((f) => `<option value="${esc(f)}">${esc(f)}</option>`).join("");
}
function renderExps() {
  const q = state.q.trim().toLowerCase();
  const rows = state.hyps.filter((h) => (!state.status || h.label === state.status) && (!state.family || h.family === state.family) &&
    (!q || [h.title, h.hypothesis_id, h.family, h.market, desig(h.registered_seq)].join(" ").toLowerCase().includes(q)));
  $("#exp-body").innerHTML = rows.length ? rows.map((h) => {
    const k = kindOf(h.label), open = state.open === h.hypothesis_id;
    return `<tr class="row" tabindex="0" data-id="${esc(h.hypothesis_id)}" aria-expanded="${open}">
      <td class="desig"><span class="car">›</span>${desig(h.registered_seq)}</td>
      <td><span class="ttl">${esc(h.title)}</span><span class="hid">${esc(h.hypothesis_id)}</span></td>
      <td class="fam">${esc(h.family || "—")}</td>
      <td><span class="st" data-k="${k}">${esc(h.label)}</span>${h.withdrawn_by ? `<span class="hid">by seq=${h.withdrawn_by}</span>` : ""}</td>
      <td>${pMeter(h)}</td>
      <td class="num">${h.trials}</td>
      <td class="when">${esc(String(h.registered_at).slice(0, 10))}</td>
    </tr>${open ? `<tr class="detail"><td colspan="7">${detailHtml(h)}</td></tr>` : ""}`;
  }).join("") : `<tr><td colspan="7" class="empty">&gt; No experiment matches.</td></tr>`;
}
function eventLabel(e) { return e.event_type === "hypothesis" ? "REGISTERED" : (e.withdrawn_by ? "WITHDRAWN" : e.label); }
function detailHtml(h) {
  const d = state.details[h.hypothesis_id];
  if (!d) return `<div class="det"><p class="act dim">&gt; loading…</p></div>`;
  const reg = d.events.find((e) => e.event_type === "hypothesis") || d.events[0];
  const cells = [["Objective", reg.mechanism], ["Market", reg.market], ["Timeframe", reg.timeframe], ["Gate role", reg.edge_gate_role],
    ["Selection", reg.selection_rule], ["Min decidable SR", reg.min_decidable_sharpe]].filter(([, v]) => v !== null && v !== undefined && v !== "");
  const lines = d.events.map((e) => {
    const lab = eventLabel(e), k = kindOf(lab);
    const note = e.note ? ` — ${esc(e.note.length > 220 ? e.note.slice(0, 219) + "…" : e.note)}` : "";
    return `<li><span class="ts">[${esc(stamp(e.timestamp))}]</span> <span class="sq">seq=${e.seq}</span> ${esc(e.event_type)} <span class="k-${k}">${esc(lab)}</span>${note}</li>`;
  }).concat((d.withdrawing_records || []).map((r) => `<li><span class="ts">[${esc(stamp(r.timestamp))}]</span> <span class="sq">seq=${r.seq}</span> audit <span class="k-withdrawn">WITHDRAWS</span> — ${esc(r.note.slice(0, 220))}${r.note.length > 220 ? "…" : ""}</li>`)).join("");
  return `<div class="det">
    <div class="det-grid">${cells.map(([k, v]) => `<div><b>${esc(k)}:</b><span>${esc(v)}</span></div>`).join("")}</div>
    <div class="act"><h4>Activity log</h4><ul class="lines">${lines}</ul></div>
  </div>`;
}
async function toggleExp(id) {
  state.open = state.open === id ? null : id;
  renderExps();
  if (!state.open) return;
  try {
    if (!state.details[id]) state.details[id] = await get(`/api/hypothesis/${encodeURIComponent(id)}`);
  } catch (err) {
    state.details[id] = null;
    $("#assess-body").innerHTML = `<p class="err">&gt; ${esc(err.message)}</p>`;
    return;
  }
  if (state.open === id) renderExps();
  renderAssess(id);
}
function focusExp(id) {
  state.status = ""; state.family = ""; state.q = "";
  $("#status-filter").value = ""; $("#family-filter").value = ""; $("#q").value = "";
  if (state.open !== id) toggleExp(id);
  document.querySelector(`#exp-body tr[data-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: "center", behavior: "smooth" });
}

/* ---------- assessment ---------- */
function isObs(o) { const v = Object.values(o || {}); return v.length > 0 && v.every((x) => x && typeof x === "object" && typeof x.observed === "number"); }
function isNum(o) { const v = Object.values(o || {}); return v.length > 0 && v.length <= 16 && v.every((x) => typeof x === "number"); }
function ibars(obj, obs) {
  const rows = Object.entries(obj).map(([k, v]) => [k, obs ? v.observed : v, obs ? v.p : null]);
  const max = Math.max(...rows.map((r) => Math.abs(r[1])), 1e-12), signed = rows.some((r) => r[1] < 0);
  return `<div class="ibars">${rows.map(([k, v, p]) => {
    const w = (Math.abs(v) / max) * (signed ? 50 : 100), left = signed ? (v < 0 ? 50 - w : 50) : 0;
    return `<span class="lab">${esc(k)}</span><span class="tr">${signed ? `<span class="z"></span>` : ""}<span class="f ${v < 0 ? "neg" : ""}" style="left:${left}%;width:${w}%"></span></span><span class="val">${fmt(v)}${p != null ? ` <span class="dash">p ${fmt(p)}</span>` : ""}</span>`;
  }).join("")}</div>`;
}
function renderAssess(id) {
  const h = state.hyps.find((x) => x.hypothesis_id === id), d = state.details[id];
  if (!h || !d) return;
  const reg = d.events.find((e) => e.event_type === "hypothesis") || d.events[0];
  const last = d.events[d.events.length - 1];
  const m = last.metrics || {}, params = reg.parameters || {};
  $("#assess-id").textContent = desig(h.registered_seq);
  const fields = [["Experiment", h.hypothesis_id], ["Family", h.family || "—"], ["Stage", h.stage],
    ["Registered", `seq=${h.registered_seq}`], ["Latest", `seq=${h.latest_seq}`], ["Trials", h.trials]];
  const p = h.decisive_value, a = h.decisive_threshold;
  const on = typeof p === "number" ? Math.round(Math.min(1, -Math.log10(Math.max(p, 1e-3)) / 3) * 10) : 0;
  const quote = [
    `<p><b>Status:</b> <span class="k-${kindOf(h.label)}">${esc(h.label)}</span>${h.withdrawn_by ? ` — withdrawn by seq=${h.withdrawn_by}` : ""}</p>`,
    h.decisive_stream ? `<p><b>Decides:</b> ${esc(h.decisive_stream)} &lt; ${esc(a)}${params.two_sided ? ", two-sided" : ""}</p>` : "",
    typeof p === "number" ? `<p><b>Observed:</b> <span class="risk">${Array.from({ length: 10 }, (_, i) => `<i class="${i < on ? "on" : ""}"></i>`).join("")}</span>${fmt(p)} → ${typeof a === "number" ? (p < a ? "passes the stream" : "fails the stream") : "no threshold recorded"}</p>` : "",
    m.reason ? `<p><b>Reason:</b> ${esc(m.reason)}</p>` : "",
  ].join("");
  let breakdown = "";
  for (const [k, v] of Object.entries(m)) {
    if (k === "streams" || !v || typeof v !== "object" || Array.isArray(v)) continue;
    if (isObs(v)) { breakdown = `<div class="dim">${esc(k)}</div>${ibars(v, true)}`; break; }
    if (isNum(v) && !breakdown) breakdown = `<div class="dim">${esc(k)}</div>${ibars(v, false)}`;
  }
  const streams = m.streams && typeof m.streams === "object" ? `<table class="streams"><tbody>${Object.entries(m.streams).map(([s, v]) =>
    `<tr><td>${esc(s)}${s === h.decisive_stream ? " <span class=\"k-alive\">◆</span>" : ""}</td><td class="num">${fmt(v)}</td></tr>`).join("")}</tbody></table>` : "";
  const art = typeof m.artifact === "string" ? m.artifact.split("/").pop() : "";
  $("#assess-body").innerHTML = `
    <dl class="as-grid">${fields.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}</dl>
    <div class="quote">${quote}</div>
    ${streams}${breakdown}
    <div class="btns">
      <button type="button" class="btn" id="btn-raw">Raw entries</button>
      <button type="button" class="btn primary" id="btn-art" ${art ? `data-name="${esc(art)}"` : "disabled"}>${art ? "Open artifact" : "No artifact"}</button>
    </div>`;
  $("#btn-raw").addEventListener("click", () => openViewer(`${desig(h.registered_seq)} · ${h.hypothesis_id}`, d));
  if (art) $("#btn-art").addEventListener("click", () => openArtifact(art));
}

/* ---------- research log terminal ---------- */
function logLine(e) {
  const lab = e.withdrawn_by ? "WITHDRAWN" : e.label;
  return { struck: !!e.withdrawn_by,
    text: `[${stamp(e.timestamp)}] seq=${e.seq} ${e.event_type} ${e.hypothesis_id} ${lab} ${e.trials ? "+" + e.trials : ""} ${(e.prev_hash || "genesis").slice(0, 6)}→${e.entry_hash.slice(0, 6)}`,
    html: `<span class="ts">[${esc(stamp(e.timestamp))}]</span> <span class="sq">seq=${e.seq}</span> <span class="ty">${esc(e.event_type)}</span> ${esc(e.hypothesis_id)} <span class="k-${kindOf(lab)}">${esc(lab)}</span>${e.trials ? ` <span class="tr">+${e.trials} trial</span>` : ""} <span class="hs">${esc((e.prev_hash || "genesis").slice(0, 6))}→${esc(e.entry_hash.slice(0, 6))}</span>` };
}
function renderTerm() {
  const g = state.grep.trim().toLowerCase();
  const lines = state.ledger.map(logLine).filter((l) => !g || l.text.toLowerCase().includes(g));
  const term = $("#term");
  term.innerHTML = lines.map((l) => `<div class="ln${l.struck ? " struck" : ""}">${l.html}</div>`).join("") +
    `<div class="ln cursor">${g ? `<span class="ts">${lines.length} match${lines.length === 1 ? "" : "es"}</span> ` : ""}</div>`;
  term.scrollTop = term.scrollHeight;
}

/* ---------- artifacts viewer ---------- */
let lastFocus = null;
function openViewer(title, obj) {
  lastFocus = document.activeElement;
  const text = typeof obj === "string" ? obj : JSON.stringify(obj, null, 1);
  $("#viewer-title").textContent = title;
  $("#viewer-body").textContent = text.length > 300000 ? text.slice(0, 300000) + "\n… truncated" : text;
  $("#viewer").classList.add("open"); $("#viewer").setAttribute("aria-hidden", "false"); $("#scrim").hidden = false;
  $("#viewer-close").focus();
}
function closeViewer() {
  $("#viewer").classList.remove("open"); $("#viewer").setAttribute("aria-hidden", "true"); $("#scrim").hidden = true;
  if (lastFocus) lastFocus.focus();
}
async function openArtifact(name) {
  try { openViewer(name, await get(`/api/artifact/${encodeURIComponent(name)}`)); }
  catch (err) { openViewer(name, `> ${err.message}`); }
}
function renderArts(list) {
  $("#art-count").textContent = `${list.length} files`;
  $("#arts").innerHTML = list.map((a) => `<li><button type="button" data-name="${esc(a.name)}" title="${a.bytes.toLocaleString()} bytes · ${esc(a.modified)}">${esc(a.name)}</button></li>`).join("");
}

/* ---------- wiring ---------- */
function wire() {
  $("#status-filter").addEventListener("change", (e) => { state.status = e.target.value; renderExps(); });
  $("#family-filter").addEventListener("change", (e) => { state.family = e.target.value; renderExps(); });
  $("#q").addEventListener("input", (e) => { state.q = e.target.value; renderExps(); });
  $("#grep").addEventListener("input", (e) => { state.grep = e.target.value; renderTerm(); });
  $("#exp-body").addEventListener("click", (e) => { const r = e.target.closest("tr.row"); if (r) toggleExp(r.dataset.id); });
  $("#exp-body").addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const r = e.target.closest("tr.row"); if (r) { e.preventDefault(); toggleExp(r.dataset.id); }
  });
  $("#arts").addEventListener("click", (e) => { const b = e.target.closest("button[data-name]"); if (b) openArtifact(b.dataset.name); });
  $("#viewer-close").addEventListener("click", closeViewer);
  $("#scrim").addEventListener("click", closeViewer);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && $("#viewer").classList.contains("open")) closeViewer(); });
}

async function load() {
  try {
    const [summary, hyps, ledger, trials, status, pending, arts] = await Promise.all(
      ["summary", "hypotheses", "ledger", "trials", "status", "pending", "artifacts"].map((p) => get(`/api/${p}`)));
    state.hyps = hyps; state.ledger = ledger;
    renderBar(summary); renderStats(); renderSchematic(status, pending, summary); renderTrials(trials);
    renderWindow(pending); renderFilters(); renderExps(); renderTerm(); renderArts(arts);
    if (hyps.length) toggleExp(hyps[0].hypothesis_id);
  } catch (err) {
    $("main").insertAdjacentHTML("afterbegin", `<p class="err">&gt; Cannot reach the harness API (${esc(err.message)}). Is <code>python -m research.ui</code> running?</p>`);
  }
}

wire();
load();
