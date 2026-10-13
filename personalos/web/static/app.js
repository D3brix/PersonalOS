"use strict";
/* PersonalOS local interface. Plain JavaScript, no dependencies, no external requests. */

// ---------------------------------------------------------------- session token
(function takeToken() {
  const m = location.hash.match(/t=([A-Za-z0-9_\-]+)/);
  if (m) {
    try { sessionStorage.setItem("pos-token", m[1]); } catch (e) { window.__posToken = m[1]; }
    history.replaceState(null, "", location.pathname + location.search);
  }
})();
function token() {
  try { return sessionStorage.getItem("pos-token") || window.__posToken || ""; } catch (e) { return window.__posToken || ""; }
}

// ---------------------------------------------------------------- helpers
const $ = (s, el = document) => el.querySelector(s);
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v; // only ever used with escaped/rendered content
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false)
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return el;
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const KIND_CLASS = { AUTHORITATIVE: "system", "VERIFIED NOTE": "note", RAW: "raw", INFERRED: "inferred", TRANSCRIPT: "transcript", "ARCHIVED DOC": "archived", INSTRUCTION: "instruction" };
const label = (text, kind) => h("span", { class: "label " + (kind || KIND_CLASS[text] || "note") }, text);

async function api(path, body) {
  const opts = { headers: { "X-PersonalOS-Token": token() } };
  if (body !== undefined) {
    opts.method = "POST";
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try { res = await fetch(path, opts); } catch (e) { throw new Error("PersonalOS is not reachable. Is `personalos ui` still running?"); }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `request failed (${res.status})`);
  return data;
}
function banner(msg, kind) {
  const b = $("#banner");
  if (!msg) { b.hidden = true; return; }
  b.className = "banner" + (kind === "info" ? " info" : "");
  b.textContent = msg;
  b.hidden = false;
}
function confirmDialog(title, text, okLabel = "Continue") {
  const d = $("#confirm");
  $("#confirm-title").textContent = title;
  $("#confirm-text").textContent = text;
  $("#confirm-ok").textContent = okLabel;
  d.returnValue = "";
  d.showModal();
  return new Promise((resolve) => d.addEventListener("close", () => resolve(d.returnValue === "ok"), { once: true }));
}
async function busy(btn, fn) {
  const old = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Working…";
  try { return await fn(); } finally { btn.disabled = false; btn.textContent = old; }
}

// ---------------------------------------------------------------- markdown (safe: everything is escaped first)
function inline(s) {
  s = esc(s);
  const codes = [];
  s = s.replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
  s = s.replace(/\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]+))?\]\]/g, (_, target, alias) =>
    `<button class="wikilink" data-wiki="${target.trim()}">${alias || target}</button>`);
  s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, t, u) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${t}</a>`);
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/(^|[^\w*])\*([^*\s][^*]*)\*/g, "$1<em>$2</em>")
       .replace(/(^|\W)_([^_\s][^_]*)_(?=\W|$)/g, "$1<em>$2</em>");
  s = s.replace(/«/g, "<mark>").replace(/»/g, "</mark>");
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[+i]}</code>`);
}
function markdown(text) {
  let src = String(text || "").replace(/\r\n/g, "\n");
  let out = "";
  const fm = src.match(/^---\n([\s\S]*?)\n---\n/);
  if (fm) { out += `<div class="front">${esc(fm[1])}</div>`; src = src.slice(fm[0].length); }
  const lines = src.split("\n");
  let i = 0, para = [];
  const flush = () => { if (para.length) { out += `<p>${inline(para.join(" "))}</p>`; para = []; } };
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      flush(); const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++; out += `<pre><code>${esc(buf.join("\n"))}</code></pre>`; continue;
    }
    let m;
    if ((m = line.match(/^(#{1,6})\s+(.*)$/))) { flush(); const n = Math.min(m[1].length + 1, 4); out += `<h${n}>${inline(m[2])}</h${n}>`; i++; continue; }
    if (/^\s*(---|\*\*\*)\s*$/.test(line)) { flush(); out += "<hr>"; i++; continue; }
    if (/^\s*>/.test(line)) {
      flush(); const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) buf.push(lines[i++].replace(/^\s*>\s?/, ""));
      out += `<blockquote>${inline(buf.join(" "))}</blockquote>`; continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line)) {
      flush(); const rows = [];
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(lines[i++]);
      const cells = (r) => r.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const body = rows.filter((r) => !/^\s*\|[\s:|-]+\|\s*$/.test(r));
      out += "<table>" + body.map((r, k) => "<tr>" + cells(r).map((c) => k === 0 ? `<th>${inline(c)}</th>` : `<td>${inline(c)}</td>`).join("") + "</tr>").join("") + "</table>";
      continue;
    }
    if (/^\s*([-*+]|\d+[.)])\s+/.test(line)) {
      flush(); const ordered = /^\s*\d/.test(line); const items = [];
      while (i < lines.length && /^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) {
        let item = lines[i++].replace(/^\s*([-*+]|\d+[.)])\s+/, "");
        while (i < lines.length && /^\s{2,}\S/.test(lines[i]) && !/^\s*([-*+]|\d+[.)])\s+/.test(lines[i])) item += " " + lines[i++].trim();
        items.push(`<li>${inline(item.replace(/^\[( |x)\]\s*/i, (_, x) => x.trim() ? "☑ " : "☐ "))}</li>`);
      }
      out += ordered ? `<ol>${items.join("")}</ol>` : `<ul>${items.join("")}</ul>`; continue;
    }
    if (!line.trim()) { flush(); i++; continue; }
    para.push(line.trim()); i++;
  }
  flush();
  return out;
}

// ---------------------------------------------------------------- reader
async function openReader(loader) {
  const r = $("#reader");
  r.hidden = false;
  $("#reader-body").innerHTML = '<p class="muted">Loading…</p>';
  try {
    const d = await loader();
    $("#reader-label").replaceChildren(label(d.label || "VERIFIED NOTE"));
    $("#reader-title").textContent = d.title || (d.path || d.rel || "").split(/[\\/]/).pop();
    $("#reader-meta").textContent = `${d.rel || d.path} · modified ${d.date || d.modified}` + (d.redactions ? ` · ${d.redactions} secret-like strings hidden` : "");
    const body = $("#reader-body");
    if (d.kind === "transcript") body.replaceChildren(h("pre", { class: "transcript" }, d.text));
    else body.innerHTML = markdown(d.text);
    if (d.truncated) body.append(h("p", { class: "muted" }, "Shortened. Open the file to read the rest."));
    if (d.stale) body.prepend(h("p", { class: "muted" }, "This file changed since it was indexed. Update the index in Maintenance."));
    body.scrollTop = 0;
  } catch (e) {
    $("#reader-body").replaceChildren(h("p", { class: "banner" }, e.message));
  }
}
const openNote = (rel) => openReader(() => api(`/api/note?rel=${encodeURIComponent(rel)}`));
const openHit = (hit) => hit.rel && hit.kind !== "transcript"
  ? openNote(hit.rel)
  : openReader(() => api(`/api/show?path=${encodeURIComponent(hit.path)}&loc=${encodeURIComponent(hit.loc || "")}`));
document.addEventListener("click", async (ev) => {
  const w = ev.target.closest(".wikilink");
  if (!w) return;
  ev.preventDefault();
  const d = await api(`/api/resolve?name=${encodeURIComponent(w.dataset.wiki)}`).catch(() => ({}));
  if (d.rel) openNote(d.rel); else banner(`No note named “${w.dataset.wiki}” yet.`, "info");
});

// ---------------------------------------------------------------- views
const views = {};
const title = (t, sub) => [h("h1", {}, t), sub ? h("p", { class: "sub" }, sub) : null];
const noteItem = (n, extra) => h("div", { class: "item", tabindex: "0", role: "button", onclick: () => openNote(n.rel), onkeydown: (e) => e.key === "Enter" && openNote(n.rel) },
  h("span", { class: "note-icon" }),
  h("div", { class: "grow" }, h("div", { class: "t" }, n.title), h("div", { class: "s" }, n.summary || n.rel)),
  extra || null, h("span", { class: "muted mono" }, n.modified));

function hitCard(hit) {
  const head = hit.heading && hit.heading !== "frontmatter" ? h("span", { class: "hit-heading" }, "› " + hit.heading) : null;
  const when = hit.kind === "transcript" && hit.ts ? `conversation ${hit.ts}` : `modified ${hit.date}`;
  return h("div", { class: "card hit", tabindex: "0", role: "button", onclick: () => openHit(hit), onkeydown: (e) => e.key === "Enter" && openHit(hit) },
    h("div", { class: "hit-head" }, label(hit.label, hit.kind), h("span", { class: "hit-title" }, hit.title), head),
    h("div", { class: "hit-snip", html: esc(hit.snip.replace(/\s+/g, " ")).replace(/«/g, "<mark>").replace(/»/g, "</mark>") }),
    h("div", { class: "hit-meta" }, h("span", { class: "mono" }, hit.rel || hit.path), h("span", {}, when)));
}

views.search = async (root, params) => {
  const kinds = [["note", "Notes"], ["system", "System"], ["raw", "Raw"], ["archived", "Archived"], ["inferred", "AI memory"], ["transcript", "Conversations"]];
  const selected = new Set((params.get("kind") || "").split(",").filter(Boolean));
  const input = h("input", { type: "search", placeholder: "Search your memory…", value: params.get("q") || "", "aria-label": "Search", autofocus: true });
  const all = h("input", { type: "checkbox" });
  all.checked = params.get("all") === "1";
  const results = h("div");
  const chips = kinds.map(([k, t]) => h("button", { class: "chip", "aria-pressed": String(selected.has(k)), onclick: (e) => {
    selected.has(k) ? selected.delete(k) : selected.add(k);
    e.target.setAttribute("aria-pressed", String(selected.has(k))); run(); } }, t));
  let timer;
  input.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(run, 220); });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { clearTimeout(timer); run(); } });
  all.addEventListener("change", run);
  async function run() {
    const q = input.value.trim();
    const qs = new URLSearchParams({ v: "search" });
    if (q) qs.set("q", q);
    if (all.checked) qs.set("all", "1");
    if (selected.size) qs.set("kind", [...selected].join(","));
    history.replaceState(null, "", "?" + qs);
    if (!q) { results.replaceChildren(h("p", { class: "muted" }, "Active memory (your system layer, current notes and inbox) is searched first. Long-term memory is added when there are few results, or always with the switch above.")); return; }
    try {
      const d = await api(`/api/search?q=${encodeURIComponent(q)}&n=10${all.checked ? "&all=1" : ""}${selected.size ? "&kind=" + [...selected].join(",") : ""}`);
      const parts = [];
      if (d.mode === "OR" && (d.tier1.length || d.tier2.length)) parts.push(h("p", { class: "muted" }, "No note contained every word, so partial matches are shown."));
      parts.push(h("div", { class: "tier-title" }, h("h2", {}, "Active memory"), h("span", { class: "muted" }, `${d.tier1.length} results`)));
      parts.push(d.tier1.length ? h("div", { class: "list" }, d.tier1.map(hitCard)) : h("div", { class: "empty" }, "No matches in active memory."));
      if (d.tier2_searched || d.tier2.length) {
        parts.push(h("div", { class: "tier-title" }, h("h2", {}, "Long-term memory"), h("span", { class: "muted" }, d.tier2_searched ? `${d.tier2.length} results` : "title matches only")));
        parts.push(d.tier2.length ? h("div", { class: "list" }, d.tier2.map(hitCard)) : h("div", { class: "empty" }, "No matches in long-term memory."));
      }
      results.replaceChildren(...parts);
    } catch (e) { results.replaceChildren(h("div", { class: "banner" }, e.message)); }
  }
  root.append(...title("Search", "Most trustworthy sources first. Every result shows where it came from and how far to trust it."),
    h("div", { class: "search-box" }, input),
    h("div", { class: "row" }, h("div", { class: "chips" }, chips), h("span", { class: "spacer" }), h("label", { class: "check" }, all, "Always include long-term memory")),
    results);
  input.focus();
  run();
};

views.browse = async (root, params) => {
  const rel = params.get("rel") || "";
  const d = await api(`/api/tree?rel=${encodeURIComponent(rel)}`);
  const crumbs = h("div", { class: "crumbs" }, h("button", { onclick: () => go("browse") }, "Vault"));
  let acc = "";
  for (const part of rel.split("/").filter(Boolean)) {
    acc = acc ? `${acc}/${part}` : part;
    const target = acc;
    crumbs.append(h("span", { class: "muted" }, "/"), h("button", { onclick: () => go("browse", { rel: target }) }, part));
  }
  const items = [
    ...d.dirs.map((x) => h("div", { class: "item", tabindex: "0", role: "button", onclick: () => go("browse", { rel: x.rel }), onkeydown: (e) => e.key === "Enter" && go("browse", { rel: x.rel }) },
      h("span", { class: "folder-icon" }), h("div", { class: "grow" }, h("div", { class: "t" }, x.name)), h("span", { class: "muted" }, `${x.count} notes`))),
    ...d.notes.map((n) => noteItem(n)),
  ];
  root.append(...title("Knowledge", "Your vault as it is on disk. PersonalOS reads it; it never edits your notes."), crumbs,
    items.length ? h("div", { class: "card panel" }, items) : h("div", { class: "empty" }, "This folder is empty."));
};

views.inbox = async (root) => {
  const d = await api("/api/inbox");
  const t = h("input", { type: "text", placeholder: "Title (optional)", maxlength: "80" });
  const txt = h("textarea", { placeholder: "Capture an idea, a link, a thought… it goes to your inbox as a new note.", maxlength: "20000" });
  const btn = h("button", { class: "btn primary", type: "submit" }, "Save to inbox");
  const form = h("form", { class: "card", onsubmit: async (e) => {
    e.preventDefault();
    if (!txt.value.trim()) return txt.focus();
    await busy(btn, async () => {
      try {
        const r = await api("/api/capture", { text: txt.value, title: t.value || null });
        banner(`Saved as ${r.created}`, "info");
        render();
      } catch (err) { banner(err.message); }
    });
  } }, h("div", { class: "list" }, t, txt, h("div", { class: "row end" }, h("span", { class: "muted spacer" }, "Passwords and keys are refused. Use a password manager for those."), btn)));
  root.append(...title("Inbox", `Unprocessed captures in ${d.folder}/. Sort them with the Inbox Workflow during your weekly review.`), form,
    h("h2", {}, `${d.notes.length} waiting`),
    d.notes.length ? h("div", { class: "card panel" }, d.notes.map((n) => noteItem(n))) : h("div", { class: "empty" }, "Inbox zero."));
  txt.focus();
};

views.projects = async (root) => {
  const d = await api("/api/projects");
  const order = Object.keys(d.groups).sort((a, b) => (a !== "active") - (b !== "active") || a.localeCompare(b));
  root.append(...title("Projects", "Grouped by the status: line in each project's frontmatter."),
    order.length ? h("div", { class: "columns" }, order.map((s) => h("div", {},
      h("div", { class: "col-head" }, h("span", {}, s), h("span", { class: "muted" }, d.groups[s].length)),
      h("div", { class: "card panel" }, d.groups[s].map((n) => noteItem(n))))))
      : h("div", { class: "empty" }, "No projects yet. Create a note in your projects folder with a status: line."));
};

views.goals = async (root) => {
  const d = await api("/api/goals");
  const focus = await api("/api/resolve?name=Current_Focus").catch(() => ({}));
  root.append(...title("Goals", "From your system layer. Edit the file in your vault; PersonalOS shows it as it is."));
  if (d.missing) root.append(h("div", { class: "empty" }, `No goals file at ${d.rel}.`));
  else root.append(h("div", { class: "card md", html: markdown(d.text) }), h("p", { class: "muted mono" }, `${d.rel} · modified ${d.modified}`));
  if (focus.rel) root.append(h("p", {}, h("button", { class: "btn", onclick: () => openNote(focus.rel) }, "Open current focus")));
};

views.archive = async (root) => {
  const d = await api("/api/archive");
  const stats = d.tier2.map((g) => h("div", { class: "card stat" }, h("div", { class: "n" }, g.files), h("div", { class: "k" }, `${g.kind} · ${g.origin} · ${(g.bytes / 1e6).toFixed(1)} MB`)));
  root.append(...title("Archive", "Long-term memory: still searchable, out of the way of active work."),
    h("div", { class: "grid" }, stats.length ? stats : h("div", { class: "empty" }, "Nothing in long-term memory yet.")),
    h("h2", {}, "Archived notes"),
    d.notes.length ? h("div", { class: "card panel" }, d.notes.map((n) => noteItem(n))) : h("div", { class: "empty" }, "No archived notes yet. Move finished projects here."),
    h("p", { class: "muted" }, "Archive location: ", h("span", { class: "mono" }, d.archive_root)));
};

views.maintenance = async (root) => {
  const [st, rep] = await Promise.all([api("/api/status"), api("/api/reports")]);
  const out = h("div");
  const showReport = (text) => out.replaceChildren(h("div", { class: "card md", html: markdown(text) }));
  const b1 = h("button", { class: "btn primary", onclick: () => busy(b1, async () => {
    try { const r = await api("/api/index", {}); banner(`Index updated: ${r.stats.added} added, ${r.stats.updated} updated, ${r.stats.removed} removed.`, "info"); } catch (e) { banner(e.message); }
  }) }, "Update index");
  const b2 = h("button", { class: "btn", onclick: () => busy(b2, async () => {
    try { const r = await api("/api/maintain", {}); banner(`Report saved: ${r.file}`, "info"); showReport(r.report); } catch (e) { banner(e.message); }
  }) }, "Run maintenance");
  const b3 = h("button", { class: "btn ghost danger", onclick: async () => {
    if (!(await confirmDialog("Rebuild the index?", "The search index is deleted and rebuilt from your files. Your notes are not touched. This can take a while for large archives.", "Rebuild"))) return;
    busy(b3, async () => { try { const r = await api("/api/index", { rebuild: true, confirm: true }); banner(`Rebuilt: ${r.stats.added} files indexed.`, "info"); } catch (e) { banner(e.message); } });
  } }, "Rebuild index");
  root.append(...title("Maintenance", "Maintenance archives new AI conversations, updates the index and suggests tidy-ups. It never changes a note."),
    h("div", { class: "grid" },
      h("div", { class: "card stat" }, h("div", { class: "n" }, st.files), h("div", { class: "k" }, "files indexed")),
      h("div", { class: "card stat" }, h("div", { class: "n" }, st.inbox), h("div", { class: "k" }, "inbox notes")),
      h("div", { class: "card stat" }, h("div", { class: "n" }, (st.last_index || "never").replace("T", " ").slice(0, 16)), h("div", { class: "k" }, "last index update"))),
    h("div", { class: "row", style: null }, b1, b2, b3), out,
    h("h2", {}, "Recent operations"),
    rep.ops.length ? h("div", { class: "card panel" }, h("table", {}, h("tr", {}, h("th", {}, "When"), h("th", {}, "Operation"), h("th", {}, "Result")),
      rep.ops.map((o) => h("tr", {}, h("td", { class: "mono" }, o.ts.replace("T", " ")), h("td", {}, o.op),
        h("td", { class: "detail" }, Object.entries(o).filter(([k, v]) => !["ts", "op"].includes(k) && typeof v !== "object").map(([k, v]) => `${k}=${v}`).join(", "))))))
      : h("div", { class: "empty" }, "No operations yet."));
  out.style.marginTop = "16px";
  if (rep.latest) showReport(rep.latest);
};

views.health = async (root) => {
  const table = h("div");
  async function load(deep) {
    const d = await api("/api/health" + (deep ? "?deep=1" : ""));
    const fails = d.checks.filter((c) => c.status === "FAIL").length, warns = d.checks.filter((c) => c.status === "WARN").length;
    table.replaceChildren(
      h("p", {}, fails ? `${fails} problem(s) need attention.` : warns ? `Working, with ${warns} warning(s).` : "Everything is healthy."),
      h("div", { class: "card panel" }, h("table", {}, h("tr", {}, h("th", {}, "Status"), h("th", {}, "Check"), h("th", {}, "Detail")),
        d.checks.map((c) => h("tr", {}, h("td", {}, h("span", { class: `status-pill ${c.status}` }, c.status)), h("td", {}, c.check), h("td", { class: "detail" }, c.detail))))));
  }
  const deep = h("button", { class: "btn", onclick: () => busy(deep, () => load(true)) }, "Verify archive files too");
  root.append(...title("Health", "The same checks as `personalos doctor`."), h("div", { class: "row" }, deep), table);
  await load(false);
};

views.integrations = async (root) => {
  const d = await api("/api/integrations");
  const cards = d.integrations.map((it) => {
    const sw = h("button", { class: "switch", role: "switch", "aria-checked": String(it.enabled), "aria-label": `Enable ${it.name}` });
    sw.addEventListener("click", async () => {
      const enable = !it.enabled;
      if (!(await confirmDialog(`${enable ? "Enable" : "Disable"} ${it.name}?`, enable ? it.description : "Its settings are switched off. Your data, archives and notes are kept.", enable ? "Enable" : "Disable"))) return;
      try { const r = await api("/api/integrations", { name: it.name, enabled: enable, confirm: true }); banner(r.messages.join(" · "), "info"); render(); } catch (e) { banner(e.message); }
    });
    const status = Object.entries(it.status || {});
    return h("div", { class: "card" },
      h("div", { class: "toggle" }, h("div", {}, h("div", { class: "hit-title" }, it.name.replace("_", " ")), h("div", { class: "muted" }, it.description)), sw),
      status.length ? h("dl", { class: "kv", style: null }, status.flatMap(([k, v]) => [h("dt", {}, k.replace(/_/g, " ")), h("dd", { class: "mono" }, String(v))])) : null);
  });
  root.append(...title("Integrations", "All optional. PersonalOS works on its own; integrations only add sources or ways for assistants to search."), h("div", { class: "list" }, cards));
};

views.settings = async (root) => {
  const s = await api("/api/settings");
  const num = (v, min, max) => h("input", { type: "number", value: v, min, max });
  const limit = num(s.search.limit, 1, 50), stale = num(s.maintenance.stale_days, 1, 3650), promote = num(s.maintenance.promote_min_hits, 1, 100);
  const logq = h("input", { type: "checkbox" });
  logq.checked = !!s.privacy.log_queries;
  const save = h("button", { class: "btn primary", onclick: async () => {
    if (!(await confirmDialog("Save settings?", "These settings are written to your configuration file.", "Save"))) return;
    try {
      await api("/api/settings", { confirm: true, changes: [
        { key: "search.limit", value: +limit.value }, { key: "maintenance.stale_days", value: +stale.value },
        { key: "maintenance.promote_min_hits", value: +promote.value }, { key: "privacy.log_queries", value: logq.checked }] });
      banner("Settings saved.", "info");
    } catch (e) { banner(e.message); }
  } }, "Save");
  const kv = (k, v) => [h("dt", {}, k), h("dd", { class: "mono" }, v || "—")];
  root.append(...title("Settings", "Storage locations are changed from the command line (`personalos config set`) so they are never moved by accident."),
    h("div", { class: "card" }, h("dl", { class: "kv" },
      kv("Config file", s.config_file), kv("Vault", s.vault), kv("Index and logs", s.data_dir), kv("Archive drive", s.archive_dir || "none (single-drive mode)"),
      kv("UI port", String(s.ui.port)), kv("Folders", Object.entries(s.folders).map(([k, v]) => `${k}=${v}`).join("  ")))),
    h("h2", {}, "Search and maintenance"),
    h("div", { class: "card" }, h("div", { class: "form-grid" },
      h("label", {}, "Results per tier", limit), h("label", {}, "Suggest archiving projects untouched for (days)", stale),
      h("label", {}, "Suggest promoting long-term notes used (times / 30 days)", promote)),
      h("p", {}, h("label", { class: "check" }, logq, "Keep search words in the local usage log (used for suggestions; never leaves this computer)")),
      h("div", { class: "row end" }, save)));
};

// ---------------------------------------------------------------- router
function go(view, extra) {
  const qs = new URLSearchParams({ v: view, ...(extra || {}) });
  history.pushState(null, "", "?" + qs);
  render();
}
async function render() {
  const params = new URLSearchParams(location.search);
  const view = views[params.get("v")] ? params.get("v") : "search";
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  const root = $("#view");
  root.replaceChildren();
  banner(null);
  if (!token()) { banner("No session key. Start PersonalOS with `personalos ui` and use the link it prints."); return; }
  try { await views[view](root, params); } catch (e) { banner(e.message); }
  api("/api/status").then((s) => {
    $("#inbox-count").textContent = s.inbox || "";
    $("#foot").textContent = `v${s.version} · ${s.mode} · local only`;
  }).catch(() => {});
}
document.getElementById("nav").addEventListener("click", (e) => {
  const a = e.target.closest("a[data-view]");
  if (!a) return;
  e.preventDefault();
  go(a.dataset.view);
});
$("#reader-close").addEventListener("click", () => { $("#reader").hidden = true; });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#reader").hidden && !$("#confirm").open) $("#reader").hidden = true;
  if (e.key === "/" && !/INPUT|TEXTAREA/.test(document.activeElement.tagName)) { e.preventDefault(); go("search"); }
});
window.addEventListener("popstate", render);
render();
