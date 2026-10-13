"use strict";
// The farmer's phone page (Step 51 part C). Telugu text in, Telugu text out. Every word on it comes from /api/pilot/ui
// (the server's i18n), every write is read back and confirmed with a tap on the yes button first, and the chips send an
// id and numbers, never a sentence.
const $ = (id) => document.getElementById(id);
let ui = null;
let busy = false;
let acked = false; // nothing runs until the one-screen notice has been acknowledged

// One stable id per device (not per tab), so a restart of the browser finds the same conversation. It is only a random
// label for the server's per-session memory: it holds no data and is not the token. Without localStorage (a private
// window) it falls back to this tab, and without any storage to a fresh id.
const ID_FORM = /^[A-Za-z0-9_-]{16,64}$/;
function newId() {
  const bytes = new Uint8Array(18);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => "abcdefghijklmnopqrstuvwxyz0123456789"[b % 36]).join("");
}
function sessionId() {
  try {
    let id = localStorage.getItem("ct_device");
    if (id && ID_FORM.test(id)) return id;
    id = newId();
    localStorage.setItem("ct_device", id);
    return id;
  } catch (e) {
    try {
      let id = sessionStorage.getItem("ct_session");
      if (id && ID_FORM.test(id)) return id;
      id = newId();
      sessionStorage.setItem("ct_session", id);
      return id;
    } catch (e2) {
      return "tab" + Math.random().toString(36).slice(2).padEnd(16, "0");
    }
  }
}
const SESSION = sessionId();

// The farmer's link carries his token after a "#" (it never goes to a server or into a log). It is kept for this tab,
// taken out of the address bar, and sent as a bearer token with every call.
function token() {
  try {
    const m = /[#&]t=([A-Za-z0-9._~-]+)/.exec(location.hash);
    if (m) {
      sessionStorage.setItem("ct_token", m[1]);
      history.replaceState(null, "", location.pathname + location.search);
    }
    return sessionStorage.getItem("ct_token") || "";
  } catch (e) {
    return "";
  }
}
const TOKEN = token();
function auth(extra) {
  return TOKEN ? { ...extra, authorization: "Bearer " + TOKEN } : { ...extra };
}

const MAX_LOG = 6; // the newest answers only: an old one is never between the farmer and the newest

function el(tag, cls, text) {
  const e = document.createElement(tag);
  e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

// Keep the log short, then show the newest answer from its top (a long ALERT answer must not start out of sight).
function show(node) {
  const log = $("log");
  log.appendChild(node);
  const kids = Array.from(log.children);
  if (kids.length > MAX_LOG) log.replaceChildren(...kids.slice(-MAX_LOG));
  node.scrollIntoView({ block: node.offsetHeight > window.innerHeight * 0.6 ? "start" : "end" });
}

function say(text, cls) {
  if (!text) return;
  const p = document.createElement("p");
  p.className = "bubble " + (cls || "");
  p.textContent = text;
  p.lang = "te";
  // A warning carries its word too (a colour alone is not a signal): the CSS prints this attribute above the text.
  if ((cls || "").includes("warn")) p.setAttribute("data-tag", ui.strings.warn_tag.te);
  show(p);
}

// The sell answer: "...per kg ₹140 (paper rate ₹160 minus ₹20, your own rule)." The price is the first rupee amount
// before the bracket; it is shown big and the bracket small. Every character stays, in order, so nothing is lost.
const PRICE = /^([^₹(]*)(₹[0-9][0-9,]*(?:\.[0-9]+)?)([^(]*)(\([\s\S]*)$/;
function sayPrice(text) {
  const m = PRICE.exec(text);
  if (!m) return false;
  const p = el("p", "bubble");
  p.lang = "te";
  p.append(el("span", "lead", m[1]), el("span", "price", m[2]), el("span", "mid", m[3]), el("span", "rule", m[4]));
  show(p);
  return true;
}

// Which sheds are at ALERT, from what the answer already carries: the status lists its sheds with a level and the
// findings behind it; the briefing lists ranked items. Nothing is parsed out of the sentences.
function alertRows(sc) {
  if (!sc) return [];
  const rows = [];
  if (Array.isArray(sc.houses)) {
    sc.houses.filter((h) => h.level === "alert").forEach((h) => {
      const f = (h.findings || []).find((x) => x.level === "alert") || {};
      const today = h.latest_record_day === sc.as_of && Number.isInteger(h.deaths_latest);
      rows.push({ label: h.label_te, deaths: today ? h.deaths_latest : null, code: f.code, text: f.text_te });
    });
  } else if (Array.isArray(sc.items)) {
    sc.items.filter((i) => i.level === "alert" && i.label_te).forEach((i) => {
      if (!rows.some((r) => r.label === i.label_te)) rows.push({ label: i.label_te, deaths: null, code: i.category, text: i.text_te });
    });
  }
  return rows;
}

function alertBar(rows) {
  const bar = el("section", "alertbar");
  bar.setAttribute("role", "alert");
  rows.forEach((r) => {
    const row = el("div", "row");
    const icon = el("span", "icon", "⚠");
    icon.setAttribute("aria-hidden", "true");
    const head = el("div", "head");
    head.append(icon, el("span", "word", ui.strings.alert.te));
    const main = el("div", "main");
    main.append(el("span", "big", r.label || ""));
    if (r.deaths !== null) {
      const deaths = el("div", "deaths");
      deaths.append(el("span", "big", String(r.deaths)), el("span", "small", ui.strings.deaths_today.te));
      main.append(deaths);
    }
    row.append(head, main);
    // The vet line is only for the farmer's own daily limit (his rule says exactly that); any other alert shows its own text.
    const line = r.code === "daily_limit_exceeded" ? ui.strings.vet_today.te : r.text;
    if (line) row.append(el("p", "line", line));
    bar.appendChild(row);
  });
  return bar;
}

function setBusy(on) {
  busy = on;
  document.querySelectorAll("button, #text").forEach((el) => { el.disabled = on; });
}

function clearPicker() { $("picker").hidden = true; $("picker-body").replaceChildren(); }

function showChips(show) { $("chips").hidden = !show; $("ask").hidden = !show; }

function button(label, onClick, cls) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = label;
  if (cls) b.className = cls;
  b.addEventListener("click", onClick);
  return b;
}

async function post(body) {
  if (busy || !acked) return;
  setBusy(true);
  clearPicker();
  try {
    const r = await fetch("/api/turn", {
      method: "POST",
      headers: auth({ "content-type": "application/json" }),
      body: JSON.stringify({ device: "dot", lang: "te", session: SESSION, utterance: "", ...body }),
    });
    if (r.status === 401) return showFatal();
    if (!r.ok) throw new Error("HTTP " + r.status);
    render(await r.json());
  } catch (e) {
    say(ui.strings.error.te + " " + ui.strings.error_next.te, "warn");
    showReadBack(false);
  } finally {
    setBusy(false);
  }
}

function showReadBack(out) {
  const waiting = !!(out && out.awaiting_answer);
  $("readback").hidden = !waiting;
  showChips(!waiting);
  // The add-or-replace question: a plain yes is not offered, only add, replace or no.
  const choice = waiting && out.result && out.result.structuredContent && out.result.structuredContent.choice;
  document.querySelector(".pair").classList.toggle("three", !!choice);
  $("yes").hidden = !!choice;
  $("add").hidden = !choice;
  $("replace").hidden = !choice;
  if (waiting) {
    // Here he taps buttons: where the server's text ends "...say yes or no", the page says tap instead.
    let question = out.speech_te || out.speech;
    const say_ = ui.strings.say_suffix.te;
    if (question.endsWith(say_)) question = question.slice(0, -say_.length) + ui.strings.tap_suffix.te;
    $("readback-text").textContent = question;
    (choice ? $("add") : $("yes")).focus();
  }
}

function render(out) {
  if (out.kind === "choose") {
    showReadBack(false);
    return choose(out.choose.chip, out.choose.params || {});
  }
  const warn = out.is_error || out.kind === "fallback" || out.kind === "unavailable" || out.kind === "protocol_error";
  if (!out.awaiting_answer) {
    const text = out.speech_te || out.speech;
    const rows = out.kind === "tool" && !warn ? alertRows(out.result && out.result.structuredContent) : [];
    if (rows.length) show(alertBar(rows));
    const isSale = out.intent && out.intent.tool === "plan_sale" && !warn;
    if (!(isSale && sayPrice(text))) say(text, warn ? "warn" : "");
  }
  showReadBack(out);
}

function pickHouse(cb) {
  const body = $("picker-body");
  body.replaceChildren();
  ui.houses.forEach((h) => body.appendChild(button(h.label_te, () => cb(h.number))));
  $("picker").hidden = false;
}

function title(text) { $("picker-title").textContent = text; }

function choose(chip, params) {
  if (!acked) return;
  const label = ui.chips[chip] ? ui.chips[chip].te : "";
  title(label);
  if (chip === "status" || chip === "briefing" || chip === "help" || chip === "sale") {
    return post({ chip, params });
  }
  if (!ui.houses.length) { say(ui.strings.error.te + " " + ui.strings.error_next.te, "warn"); return; }
  if (!params.house) return pickHouse((house) => choose(chip, { ...params, house }));
  if (chip === "no_deaths") return post({ chip, params: { house: params.house } });
  if (chip === "deaths") {
    if (params.count === undefined) return askCount(label, params);
    return post({ chip, params: { house: params.house, count: params.count } });
  }
  if (chip === "follow_up") {
    if (!params.outcome) return askOutcome(params);
    return post({ chip, params: { house: params.house, outcome: params.outcome } });
  }
  if (chip === "health") return askSigns(label, params);
}

function askCount(label, params) {
  const body = $("picker-body");
  body.replaceChildren();
  const input = document.createElement("input");
  input.type = "number";
  input.inputMode = "numeric";
  input.min = "0";
  input.max = "100000";
  input.step = "1";
  input.setAttribute("aria-label", label);
  const go = button(label, () => {
    const n = Number(input.value);
    if (input.value !== "" && Number.isInteger(n) && n >= 0 && n <= 100000) {
      post({ chip: "deaths", params: { house: params.house, count: n } });
    }
  }, "big");
  body.append(input, go);
  $("picker").hidden = false;
  input.focus();
}

function askOutcome(params) {
  const body = $("picker-body");
  body.replaceChildren();
  Object.entries(ui.outcomes).forEach(([key, t]) =>
    body.appendChild(button(t.te, () => post({ chip: "follow_up", params: { house: params.house, outcome: key } }))));
  $("picker").hidden = false;
}

function askSigns(label, params) {
  const body = $("picker-body");
  body.replaceChildren();
  const chosen = new Set();
  ui.signs.forEach((s) => {
    const b = button(s.label_te, () => {
      if (chosen.has(s.code)) chosen.delete(s.code); else chosen.add(s.code);
      b.classList.toggle("on", chosen.has(s.code));
      b.setAttribute("aria-pressed", String(chosen.has(s.code)));
    });
    b.setAttribute("aria-pressed", "false");
    body.appendChild(b);
  });
  body.appendChild(button(label, () => {
    if (chosen.size) post({ chip: "health", params: { house: params.house, signs: Array.from(chosen) } });
  }, "big"));
  $("picker").hidden = false;
}

// No token (or a wrong one): the only thing to do is open the original link again.
function showFatal() {
  $("fatal").hidden = false;
  $("app").hidden = true;
  $("notice-screen").hidden = true;
}

function isAcked() {
  try {
    return localStorage.getItem("ct_ack") === ui.notice_version;
  } catch (e) {
    return false; // no storage: ask every time rather than assume
  }
}

function enterApp() {
  acked = true;
  $("notice-screen").hidden = true;
  $("app").hidden = false;
}

function showNotice() {
  $("notice-title").textContent = ui.strings.notice_title.te;
  $("notice-list").replaceChildren(...ui.notice_items.map((t) => {
    const li = document.createElement("li");
    li.textContent = t.te;
    li.lang = "te";
    return li;
  }));
  $("ack").textContent = ui.strings.ack.te;
  $("ack").addEventListener("click", () => {
    try { localStorage.setItem("ct_ack", ui.notice_version); } catch (e) { /* asked again next time */ }
    enterApp();
  });
  $("notice-screen").hidden = false;
  $("app").hidden = true;
}

async function start() {
  try {
    const r = await fetch("/api/pilot/ui", { headers: auth({}) });
    if (r.status === 401) return showFatal();
    if (!r.ok) throw new Error("HTTP " + r.status);
    ui = await r.json();
  } catch (e) {
    document.body.textContent = "CluckTalk: " + e.message;
    return;
  }
  $("text").placeholder = ui.strings.placeholder.te;
  $("text").setAttribute("aria-label", ui.strings.placeholder.te);
  $("send").textContent = ui.strings.send.te;
  $("yes").textContent = ui.strings.yes.te;
  $("no").textContent = ui.strings.no.te;
  $("add").textContent = ui.strings.add.te;
  $("replace").textContent = ui.strings.replace.te;
  $("readback-head").textContent = ui.strings.readback.te;
  Object.entries(ui.chips).forEach(([key, t]) => $("chips").appendChild(button(t.te, () => choose(key, {}))));
  $("yes").addEventListener("click", () => post({ chip: "yes" }));
  $("no").addEventListener("click", () => post({ chip: "no" }));
  $("add").addEventListener("click", () => post({ chip: "add" }));
  $("replace").addEventListener("click", () => post({ chip: "replace" }));
  $("ask").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const text = $("text").value.trim();
    if (!text || !acked) return;
    say(text, "you");
    $("text").value = "";
    post({ utterance: text });
  });
  if (isAcked()) enterApp(); else showNotice();
}
start();
