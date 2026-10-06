"use strict";
// The farmer's phone page (Step 51 part C). Telugu text in, Telugu text out. Every word on it comes from /api/pilot/ui
// (the server's i18n), every write is read back and confirmed with a tap on the yes button first, and the chips send an
// id and numbers, never a sentence.
const $ = (id) => document.getElementById(id);
let ui = null;
let busy = false;

function sessionId() {
  try {
    let id = sessionStorage.getItem("ct_session");
    if (id && /^[A-Za-z0-9_-]{16,64}$/.test(id)) return id;
    const bytes = new Uint8Array(18);
    crypto.getRandomValues(bytes);
    id = Array.from(bytes, (b) => "abcdefghijklmnopqrstuvwxyz0123456789"[b % 36]).join("");
    sessionStorage.setItem("ct_session", id);
    return id;
  } catch (e) {
    return "tab" + Math.random().toString(36).slice(2).padEnd(16, "0");
  }
}
const SESSION = sessionId();

function say(text, cls) {
  if (!text) return;
  const p = document.createElement("p");
  p.className = "bubble " + (cls || "");
  p.textContent = text;
  p.lang = "te";
  $("log").appendChild(p);
  p.scrollIntoView({ block: "end" });
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
  if (busy) return;
  setBusy(true);
  clearPicker();
  try {
    const r = await fetch("/api/turn", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ device: "dot", lang: "te", session: SESSION, utterance: "", ...body }),
    });
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
  if (waiting) {
    $("readback-text").textContent = out.speech_te || out.speech;
    $("yes").focus();
  }
}

function render(out) {
  if (out.kind === "choose") {
    showReadBack(false);
    return choose(out.choose.chip, out.choose.params || {});
  }
  const warn = out.is_error || out.kind === "fallback" || out.kind === "unavailable" || out.kind === "protocol_error";
  if (!out.awaiting_answer) say(out.speech_te || out.speech, warn ? "warn" : "");
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

async function start() {
  try {
    const r = await fetch("/api/pilot/ui");
    if (!r.ok) throw new Error("HTTP " + r.status);
    ui = await r.json();
  } catch (e) {
    document.body.textContent = "CluckTalk: " + e.message;
    return;
  }
  $("notice").textContent = ui.strings.notice.te;
  $("yes").textContent = ui.strings.yes.te;
  $("no").textContent = ui.strings.no.te;
  $("readback-head").textContent = ui.strings.readback.te;
  Object.entries(ui.chips).forEach(([key, t]) => $("chips").appendChild(button(t.te, () => choose(key, {}))));
  $("yes").addEventListener("click", () => post({ chip: "yes" }));
  $("no").addEventListener("click", () => post({ chip: "no" }));
  $("ask").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const text = $("text").value.trim();
    if (!text) return;
    say(text, "you");
    $("text").value = "";
    post({ utterance: text });
  });
}
start();
