// CluckTalk Simulator page: the device side of the Alexa+ client role.
// Voice in (browser speech recognition, en-IN) or text -> /api/turn (mock host: rules + MCP tools/call) ->
// spoken answer (browser speech synthesis) + on Echo Show the MCP App card, hosted per the MCP Apps spec 2026-01-26.
"use strict";

const SPEC_VERSION = "2026-01-26";
const PRESETS = {
  "show-1024x600": { w: 1024, h: 600, kind: "show", platform: "web" },
  "show-960x600": { w: 960, h: 600, kind: "show", platform: "web" },
  "show-960x480": { w: 960, h: 480, kind: "show", platform: "web" },
  "phone-390x844": { w: 390, h: 844, kind: "phone", platform: "mobile" },
};
const $ = (id) => document.getElementById(id);
const state = {
  device: "show", preset: "show-1024x600", theme: "dark", sound: true, delay: 0, photo: "", strictCsp: false, busy: false,
  interimAfter: 1000, turnNo: 0, card: null, server: null,
};
window.__clucktalk = { turns: [] };   // read-only record of turns (for automated end-to-end checks)

// ------------------------------------------------------------------ layout: device frame at true CSS size
function applyPreset() {
  const p = PRESETS[state.preset];
  const screen = $("screen"), bezel = $("bezel"), scaler = $("scaler");
  screen.style.width = p.w + "px"; screen.style.height = p.h + "px";
  bezel.classList.toggle("phone", p.kind === "phone");
  $("show-wrap").classList.toggle("phone", p.kind === "phone");
  const pad = p.kind === "phone" ? 14 : 22;
  const fullW = p.w + 2 * pad, fullH = p.h + 2 * pad;
  const avail = Math.min(window.innerWidth - 32, 1180);
  const scale = Math.min(1, avail / fullW);
  bezel.style.transform = `scale(${scale})`;
  scaler.style.width = fullW * scale + "px"; scaler.style.height = fullH * scale + "px";
  if (state.card) state.card.sendContext({ containerDimensions: { width: p.w, height: p.h }, platform: p.platform });
}
window.addEventListener("resize", applyPreset);

function showView(id) {
  for (const v of ["home", "asked", "native", "cardhost"]) $(v).hidden = v !== id;
}

// ------------------------------------------------------------------ speech out
let voice = null;
function pickVoice() {
  const vs = window.speechSynthesis ? speechSynthesis.getVoices() : [];
  voice = vs.find((v) => v.lang === "en-IN" && v.localService) || vs.find((v) => v.lang === "en-IN")
    || vs.find((v) => /^en[-_]/.test(v.lang) && v.localService) || vs.find((v) => /^en/.test(v.lang)) || null;
}
if (window.speechSynthesis) { pickVoice(); speechSynthesis.onvoiceschanged = pickVoice; }
function speak(text) {
  return new Promise((resolve) => {
    if (!state.sound || !text) return resolve();
    if (!window.speechSynthesis) { note("This browser cannot speak answers; read the transcript."); return resolve(); }
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-IN"; if (voice) u.voice = voice;
    setRing("speaking");
    u.onend = u.onerror = () => { setRing(""); resolve(); };
    speechSynthesis.speak(u);
  });
}

// ------------------------------------------------------------------ speech in
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec = null;
function setupMic() {
  const mic = $("mic");
  if (!SR) { mic.disabled = true; note("Voice input isn't available in this browser. Type your question instead."); return; }
  mic.addEventListener("click", () => {
    if (rec) { rec.stop(); return; }
    rec = new SR(); rec.lang = "en-IN"; rec.interimResults = true; rec.maxAlternatives = 1;
    let finalText = "";
    rec.onstart = () => { mic.classList.add("on"); listening(true); note(""); };
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) finalText += e.results[i][0].transcript; else interim += e.results[i][0].transcript;
      }
      $("text").value = (finalText + interim).trim();
    };
    rec.onerror = (e) => {
      const why = {
        "not-allowed": "Microphone permission was denied. Allow it in the browser, or type instead.",
        "service-not-allowed": "Voice input is blocked in this browser. Type instead.",
        "network": "Voice input uses the browser's online speech service, which isn't reachable. Type instead.",
        "no-speech": "I didn't hear anything. Tap the microphone and speak, or type instead.",
        "audio-capture": "No microphone was found. Type instead.",
      }[e.error] || "Voice input stopped (" + e.error + "). Type instead.";
      note(why);
    };
    rec.onend = () => {
      mic.classList.remove("on"); listening(false); rec = null;
      if (finalText.trim()) ask(finalText.trim(), "voice");
    };
    rec.start();
  });
}
function listening(on) {
  $("listenbar").classList.toggle("on", on && state.device === "show");
  setRing(on ? "listening" : "");
}
function setRing(mode) { $("ring").className = "ring" + (mode ? " " + mode : ""); }
function note(text) { $("voice-note").textContent = text; }

// ------------------------------------------------------------------ transcript
function say(who, cls, text) {
  const t = $("transcript");
  const empty = t.querySelector(".empty"); if (empty) empty.remove();
  const p = document.createElement("p"); p.className = cls;
  const b = document.createElement("span"); b.className = "who"; b.textContent = who;
  p.append(b, document.createTextNode(text)); t.append(p); t.scrollTop = t.scrollHeight;
}

// ------------------------------------------------------------------ cross-modal check (docs/DESIGN.md §6)
// A leading "-" is part of the number (so plan_sale's negative day-by-day figures match as one token, not a
// split "-42,630" -> stray "630"), but only when it is a minus sign, not an ID separator ("house-2" must stay
// unmatched): excluded when preceded by a word/dot char directly, or by a word/dot char then "-".
const NUM = /(?<![\w.]|[\w.]-)-?\d[\d,]*(?:\.\d+)?/g;
function namesOf(obj, out = new Set()) {
  if (Array.isArray(obj)) obj.forEach((v) => namesOf(v, out));
  else if (obj && typeof obj === "object") for (const [k, v] of Object.entries(obj)) { if (k === "breed" && typeof v === "string") out.add(v); namesOf(v, out); }
  return out;
}
function numbersIn(text, names) {
  for (const n of [...names].sort((a, b) => b.length - a.length)) text = text.split(n).join(" ");
  return [...text.matchAll(NUM)].map((m) => Math.round(parseFloat(m[0].replace(/,$/, "").replace(/,/g, "")) * 1e6) / 1e6);
}
function valuesOf(obj, out = new Set()) {
  if (Array.isArray(obj)) obj.forEach((v) => valuesOf(v, out));
  else if (obj && typeof obj === "object") Object.values(obj).forEach((v) => valuesOf(v, out));
  else if (typeof obj === "number") out.add(Math.round(obj * 1e6) / 1e6);
  return out;
}
function fieldAt(obj, path) { return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj); }
function crossModal(result, cardText, fields) {
  const sc = result.structuredContent;
  const spokenText = (result.content || []).filter((c) => c.type === "text").map((c) => c.text).join(" ");
  const names = namesOf(sc || {});
  let backing;
  if (sc) backing = valuesOf(sc);
  else {  // error card: its numbers must come from the error message itself
    const meta = (result._meta || {})["clucktalk/error"] || {};
    backing = new Set(numbersIn([spokenText, ...Object.values(meta)].join(" "), names));
  }
  const cardNums = numbersIn(cardText, names), spoken = numbersIn(spokenText, names);
  const cardSet = new Set(cardNums);
  const unbacked = [...new Set(cardNums.filter((n) => !backing.has(n)))];
  const missing = [...new Set(spoken.filter((n) => !cardSet.has(n)))];
  // Each big KPI value must equal the exact field it claims to show (not just any number in the result).
  const wrongField = (fields || []).filter((f) => {
    const want = fieldAt(sc, f.path);
    const got = parseFloat(String(f.shown).replace(/,/g, ""));
    return typeof want !== "number" || Math.abs(got - want) > 1e-9;
  }).map((f) => `${f.path}=${f.shown}`);
  return { ok: !unbacked.length && !missing.length && !wrongField.length, cardCount: cardNums.length,
    spokenCount: spoken.length, fieldCount: (fields || []).length, unbacked, missing, wrongField };
}

// ------------------------------------------------------------------ MCP Apps host bridge (one per card)
function sandboxOrigin() {
  const other = location.hostname === "localhost" ? "127.0.0.1" : "localhost";
  return `${location.protocol}//${other}:${location.port}`;
}
const resourceCache = new Map();
async function loadResource(uri, entry) {
  if (resourceCache.has(uri)) return resourceCache.get(uri);
  const r = await fetch("/api/resource?uri=" + encodeURIComponent(uri));
  const body = await r.json();
  if (!r.ok) throw new Error(body.error || "resource read failed");
  if (entry) entry.exchanges(body.exchanges, "resources/read " + uri);
  resourceCache.set(uri, body.content);
  return body.content;
}

class CardHost {
  constructor({ content, tool, args, result, entry }) {
    this.content = content; this.tool = tool; this.args = args; this.result = result; this.entry = entry;
    this.origin = sandboxOrigin(); this.initialized = false; this.nextId = 1; this.pending = new Map();
    const csp = ((content._meta || {}).ui || {}).csp || {};
    this.frame = document.createElement("iframe");
    this.frame.setAttribute("sandbox", "allow-scripts allow-same-origin");   // spec: the proxy needs both
    this.frame.setAttribute("title", "CluckTalk card");
    this.frame.src = `${this.origin}/sandbox?csp=${encodeURIComponent(JSON.stringify(csp))}${state.strictCsp ? "&strict=1" : ""}`;
    this.onMessage = (e) => this.handle(e);
    window.addEventListener("message", this.onMessage);
    $("cardhost").replaceChildren(this.frame);
    entry.line("kv", `card: ${content.uri} in sandbox ${this.origin} (CSP: ${state.strictCsp ? "strict spec default" : "spec default + font-src data:"}${Object.keys(csp).length ? " + declared " + JSON.stringify(csp) : ""})`);
    // No blank cards (fail loud): if the card has not rendered in time, say so and show the text answer.
    this.watchdog = setTimeout(() => {
      if (this.rendered || state.card !== this) return;
      entry.line("bad", "card did not render within 3 s (sandbox or handshake failed): showing the text answer instead");
      if (this.onFail) this.onFail();
    }, 3000);
  }
  post(msg) { if (this.frame.contentWindow) this.frame.contentWindow.postMessage(msg, this.origin); }
  respond(id, result) { this.post({ jsonrpc: "2.0", id, result }); }
  fail(id, code, message) { this.post({ jsonrpc: "2.0", id, error: { code, message } }); }
  request(method, params, timeoutMs) {
    const id = "h" + this.nextId++;
    this.post({ jsonrpc: "2.0", id, method, params });
    return new Promise((resolve) => {
      this.pending.set(id, resolve);
      setTimeout(() => { if (this.pending.delete(id)) resolve(null); }, timeoutMs || 1000);
    });
  }
  sendContext(partial) { if (this.initialized) this.post({ jsonrpc: "2.0", method: "ui/notifications/host-context-changed", params: partial }); }
  hostContext() {
    const p = PRESETS[state.preset];
    return {
      toolInfo: { tool: this.tool }, theme: state.theme, displayMode: "inline", availableDisplayModes: ["inline"],
      containerDimensions: { width: p.w, height: p.h }, locale: "en-IN", timeZone: "Asia/Kolkata",
      userAgent: "CluckTalk Simulator", platform: p.platform, deviceCapabilities: { touch: true, hover: p.kind !== "phone" },
    };
  }
  async handle(e) {
    if (e.origin !== this.origin || e.source !== this.frame.contentWindow) return;
    const m = e.data;
    if (!m || m.jsonrpc !== "2.0") return;
    if (m.id != null && m.method === undefined) { const r = this.pending.get(m.id); if (r) { this.pending.delete(m.id); r(m.result); } return; }
    switch (m.method) {
      case "ui/notifications/sandbox-proxy-ready":
        this.post({ jsonrpc: "2.0", method: "ui/notifications/sandbox-resource-ready",
          params: { html: this.content.text, csp: ((this.content._meta || {}).ui || {}).csp, permissions: ((this.content._meta || {}).ui || {}).permissions } });
        break;
      case "ui/initialize":
        this.entry.line("kv", `card → ui/initialize (appInfo: ${JSON.stringify(m.params && m.params.appInfo)}, protocol ${m.params && m.params.protocolVersion})`);
        this.respond(m.id, {
          protocolVersion: SPEC_VERSION, hostInfo: { name: "CluckTalk Simulator", version: "0.1.0" },
          hostCapabilities: { serverTools: {}, serverResources: {}, logging: {} }, hostContext: this.hostContext(),
        });
        break;
      case "ui/notifications/initialized":   // spec: nothing may be sent to the view before this
        this.initialized = true;
        this.post({ jsonrpc: "2.0", method: "ui/notifications/tool-input", params: { arguments: this.args } });
        this.post({ jsonrpc: "2.0", method: "ui/notifications/tool-result", params: this.result });
        break;
      case "tools/call": case "resources/read": {
        const t0 = performance.now();
        try {
          const r = await fetch("/api/view-request", { method: "POST", headers: { "content-type": "application/json" },
            body: JSON.stringify({ method: m.method, params: m.params, card_uri: this.content.uri }) });
          const body = await r.json();
          if (!r.ok || body.error) { this.fail(m.id, (body.error && body.error.code) || -32000, (body.error && body.error.message) || "failed"); break; }
          const entry = startEntry(`tap on card → ${m.method} ${m.params.name || m.params.uri} ${JSON.stringify(m.params.arguments || {})}`);
          entry.line("kv", `MCP round trip ${body.mcp_ms} ms · tap to answer ${Math.round(performance.now() - t0)} ms`);
          entry.exchanges(body.exchanges, m.method);
          if (body.response.error) { this.post({ jsonrpc: "2.0", id: m.id, error: body.response.error }); break; }
          this.result = body.response.result; this.entry = entry;   // the card now shows this result
          this.respond(m.id, body.response.result);
        } catch (err) { this.fail(m.id, -32000, String(err)); }
        break;
      }
      case "ui/request-display-mode": this.respond(m.id, { mode: "inline" }); break;
      case "ping": this.respond(m.id, {}); break;
      case "ui/notifications/size-changed": break;   // fixed container on every preset: nothing to resize
      case "notifications/message": {
        const d = (m.params && m.params.data) || {};
        if (d.event === "rendered") {
          this.rendered = true;
          const x = crossModal(this.result, d.text || "", d.fields);
          this.entry.crossModal = x;
          this.entry.line(x.ok ? "ok" : "bad", x.ok
            ? `cross-modal ✓ all ${x.spokenCount} spoken numbers are on the card; all ${x.cardCount} card numbers are in the tool result; ${x.fieldCount} KPI values equal their fields (${d.view} view)`
            : `cross-modal ✗ spoken but not on card: [${x.missing}] · on card but not in result: [${x.unbacked}] · KPI ≠ field: [${x.wrongField}]`);
          if (!x.ok) console.error("cross-modal mismatch", x);
        } else {
          const cls = { info: "kv", warning: "warn" }[m.params.level] || "bad";
          this.entry.line(cls, `card log (${m.params.level}): ${JSON.stringify(d)}`);
          if (cls === "bad") console.error("card error", d);
        }
        break;
      }
      default:
        if (m.id != null) this.fail(m.id, -32601, `${m.method} is not supported by this simulator`);
    }
  }
  async teardown() {   // spec: tell the view before tearing it down; wait briefly for its answer
    clearTimeout(this.watchdog);
    if (this.initialized) await this.request("ui/resource-teardown", { reason: "new turn" }, 300);
    window.removeEventListener("message", this.onMessage);
    this.frame.remove();
  }
}

// ------------------------------------------------------------------ developer panel log
function startEntry(title) {
  const li = document.createElement("li");
  const t = document.createElement("div"); t.className = "t"; t.textContent = title; li.append(t);
  $("log").append(li);
  const entry = {
    title, crossModal: null,
    line(cls, text) { const d = document.createElement("div"); d.className = cls; d.textContent = text; li.append(d); },
    exchanges(list, label) {
      for (const x of list || []) {
        const det = document.createElement("details");
        const s = document.createElement("summary");
        s.textContent = `${x.request.method} · HTTP ${x.http_status} · ${x.ms} ms`;
        const pre = document.createElement("pre");
        pre.textContent = "→ " + JSON.stringify(x.request, null, 2) + "\n\n← " + JSON.stringify(x.response, trimHtml, 2);
        det.append(s, pre); li.append(det);
      }
    },
  };
  return entry;
}
function trimHtml(k, v) { return k === "text" && typeof v === "string" && v.length > 2000 ? v.slice(0, 300) + `… (${v.length.toLocaleString()} chars)` : v; }

// ------------------------------------------------------------------ one turn
async function ask(utterance, via) {
  if (state.busy || !utterance.trim()) return;
  state.busy = true; state.turnNo += 1;
  if (window.speechSynthesis) speechSynthesis.cancel();
  say("You: ", "you", utterance);
  $("text").value = "";
  const entry = startEntry(`#${state.turnNo} “${utterance}” (${via}, ${state.device === "show" ? "Echo Show" : "Echo Dot"})`);
  const record = { n: state.turnNo, utterance, device: state.device, via };
  window.__clucktalk.turns.push(record);

  // No stale card: the previous answer leaves the screen as soon as a new question is asked.
  if (state.card) { const old = state.card; state.card = null; old.teardown(); }
  $("asked-text").textContent = "“" + utterance + "”"; showView("asked");
  setRing("thinking");

  const t0 = performance.now();
  let interimShown = false;
  const interim = setTimeout(() => {
    interimShown = true;
    $("interim-show").hidden = state.device !== "show";
    entry.line("warn", `answer slower than ${state.interimAfter} ms: “Still working…” shown and spoken`);
    speak("Still working on it.");
  }, state.interimAfter);

  let body;
  try {
    const r = await fetch("/api/turn", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ utterance, device: state.device, simulate_delay_ms: state.delay, photo_ref: state.photo || null }) });
    body = await r.json();
    if (!r.ok) throw new Error(body.error || "HTTP " + r.status);
  } catch (err) {
    body = { kind: "unavailable", speech: "Sorry, the simulator could not reach its own backend. Please try again.", detail: String(err) };
  }
  clearTimeout(interim);
  $("interim-show").hidden = true;
  const turnMs = Math.round(performance.now() - t0);
  Object.assign(record, { kind: body.kind, intent: body.intent, speech: body.speech, turn_ms: turnMs, timing: body.timing, interim: interimShown });

  // developer panel
  if (body.intent) entry.line("kv", `intent: ${body.intent.tool} ${JSON.stringify(body.intent.arguments)} · rule: ${body.intent.rule}`);
  else entry.line("warn", `no tool matched (“${body.normalised || utterance}”) → host fallback, no MCP call`);
  const tm = body.timing || {};
  entry.line("kv", `MCP round trip ${tm.mcp_ms ?? "–"} ms · turn ${turnMs} ms` + (tm.simulated_delay_ms ? ` (includes +${tm.simulated_delay_ms} ms simulated delay)` : ""));
  if (body.detail) entry.line("bad", body.detail);
  entry.exchanges(body.exchanges, "tools/call");
  // A reconnect means a (possibly restarted) server: re-read card resources rather than reuse old copies.
  if ((body.exchanges || []).some((x) => x.request.method === "initialize")) resourceCache.clear();

  // screen
  if (state.device === "show") {
    if (body.card && body.result) {
      try {
        const content = await loadResource(body.card.uri, entry);
        state.card = new CardHost({ content, tool: body.card.tool, args: body.intent.arguments, result: body.result, entry });
        const failedCard = state.card;
        state.card.onFail = () => { if (state.card === failedCard) { state.card = null; failedCard.teardown(); showNative(body, true); } };
        record.card_uri = body.card.uri;
        record.entry = entry;
        showView("cardhost");
      } catch (err) {
        entry.line("bad", "card could not be loaded: " + err + " (text answer shown instead)");
        showNative(body);
      }
    } else {
      showNative(body);
    }
  }
  const speaker = body.kind === "tool" ? "CluckTalk: " : "Alexa: ";
  say(speaker, body.kind === "tool" ? "ct" : "host", body.speech);
  entry.line("kv", `spoken (${voice ? voice.name + ", " + voice.lang : "no voice"}): ${body.speech}`);
  $("dev-sum").textContent = `last turn ${turnMs} ms · MCP ${tm.mcp_ms ?? "–"} ms`;
  state.busy = false;
  await speak(body.speech);
  if (state.device === "dot") setRing("");
}

function showNative(body, cardFailed) {
  $("native-note").textContent = cardFailed
    ? "text answer · the card could not be shown (see developer panel)"
    : "text answer · this answer has no card";
  $("native-en").textContent = body.speech;
  const sc = body.result && body.result.structuredContent;
  const meta = body.result && body.result._meta && body.result._meta["clucktalk/error"];
  $("native-te").textContent = (sc && sc.text_te) || (meta && [meta.message_te, meta.next_step_te].join(" ")) || "";
  showView("native");
}

// ------------------------------------------------------------------ controls
function setDevice(device) {
  state.device = device;
  document.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.device === device)));
  $("show-wrap").hidden = device !== "show";
  $("dot-wrap").hidden = device !== "dot";
  if (device === "dot" && state.card) { const old = state.card; state.card = null; old.teardown(); showView("home"); }
}
document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => setDevice(b.dataset.device)));
$("sound").addEventListener("click", () => {
  state.sound = !state.sound;
  $("sound").setAttribute("aria-pressed", String(state.sound));
  $("sound").textContent = state.sound ? "🔊 Sound on" : "🔇 Sound off";
  if (!state.sound && window.speechSynthesis) speechSynthesis.cancel();
});
$("ask").addEventListener("submit", (e) => { e.preventDefault(); ask($("text").value, "typed"); });
document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => ask(c.textContent, "typed")));
$("dev-toggle").addEventListener("click", () => {
  const open = $("dev").dataset.open !== "true";
  $("dev").dataset.open = String(open); $("dev-body").hidden = !open; $("dev-toggle").setAttribute("aria-expanded", String(open));
});
$("preset").addEventListener("change", (e) => { state.preset = e.target.value; applyPreset(); });
$("theme").addEventListener("change", (e) => {
  state.theme = e.target.value; $("screen").dataset.theme = state.theme;
  if (state.card) state.card.sendContext({ theme: state.theme });
});
$("delay").addEventListener("change", (e) => { state.delay = Number(e.target.value); });
$("photo").addEventListener("change", (e) => { state.photo = e.target.value; });
$("csp").addEventListener("change", (e) => { state.strictCsp = e.target.value === "strict"; });  // applies to the next card

// URL options make screenshots reproducible, e.g. ?device=show&preset=phone-390x844&dev=1&sound=0
function applyQuery() {
  const q = new URLSearchParams(location.search);
  if (q.get("device") === "dot") setDevice("dot");
  if (PRESETS[q.get("preset")]) { state.preset = q.get("preset"); $("preset").value = state.preset; }
  if (q.get("theme") === "light") { state.theme = "light"; $("theme").value = "light"; $("screen").dataset.theme = "light"; }
  if (q.get("sound") === "0") $("sound").click();
  if (q.get("csp") === "strict") { state.strictCsp = true; $("csp").value = "strict"; }
  if (q.get("dev") === "1") $("dev-toggle").click();
}

function tick() {
  const d = new Date();
  $("clock").textContent = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

async function connect() {
  try {
    const r = await fetch("/api/state");
    const s = await r.json();
    state.server = s; state.interimAfter = s.interim_after_ms;
    const tools = s.tools.map((t) => `  ${t.name}${t.resourceUri ? "  → card " + t.resourceUri : ""}`).join("\n");
    $("conn").textContent = s.connected
      ? `MCP server: ${s.server_info.name} ${s.server_info.version} at ${s.mcp_url}\nProtocol 2025-11-25 · MCP Apps ${SPEC_VERSION} · mode: ${s.mode}\nTools:\n${tools}`
      : `MCP server not reachable at ${s.mcp_url}. Start it (python tasks.py run) — the first question will retry.`;
  } catch (err) {
    $("conn").textContent = "Simulator backend not reachable: " + err;
  }
}

setupMic(); applyQuery(); applyPreset(); showView("home"); tick(); setInterval(tick, 10000); connect();
