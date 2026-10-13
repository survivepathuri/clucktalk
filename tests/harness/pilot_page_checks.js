"use strict";
// Runs the farmer's phone page (pilot.js) against a small hand-made DOM and a fake server, and prints one line of JSON:
// {"scenario name": "ok" | "what went wrong"}. tests/harness/test_pilot_page_behaviour.py reads it. No library, no browser:
// this checks the page's own logic (acknowledge first, the token, the device id, the add or replace buttons), not its looks.
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const STATIC = path.join(__dirname, "..", "..", "src", "clucktalk", "simulator", "static");
const HTML = fs.readFileSync(path.join(STATIC, "pilot.html"), "utf8");
const SCRIPT = fs.readFileSync(path.join(STATIC, "pilot.js"), "utf8");

class El {
  constructor(tag, id) {
    this.tagName = tag; this.id = id || ""; this.hidden = false; this.disabled = false; this.textContent = "";
    this.children = []; this.listeners = {}; this.attrs = {}; this.className = ""; this.value = ""; this.type = "";
    const self = this;
    this.classes = new Set();
    this.classList = {
      toggle(name, on) { const want = on === undefined ? !self.classes.has(name) : !!on; want ? self.classes.add(name) : self.classes.delete(name); return want; },
      contains(name) { return self.classes.has(name); },
    };
  }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  appendChild(c) { this.children.push(c); return c; }
  append(...cs) { cs.forEach((c) => this.children.push(c)); }
  replaceChildren(...cs) { this.children = [...cs]; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  focus() {}
  scrollIntoView() {}
  async fire(type, ev) { for (const fn of this.listeners[type] || []) await fn(ev || { preventDefault() {} }); }
}

function makeStorage(broken) {
  const m = new Map();
  return {
    getItem(k) { if (broken) throw new Error("blocked"); return m.has(k) ? m.get(k) : null; },
    setItem(k, v) { if (broken) throw new Error("blocked"); m.set(k, String(v)); },
    map: m,
  };
}

const flush = async () => { for (let i = 0; i < 12; i++) await new Promise((r) => setImmediate(r)); };

function ui(extra) {
  const t = (s) => ({ en: s, te: "te:" + s });
  return {
    strings: { notice: t("voice"), yes: t("Yes"), no: t("No"), add: t("Add"), replace: t("Replace"), readback: t("Is this right?"),
      error: t("error"), error_next: t("next"), notice_title: t("Before you start"), ack: t("I understand"),
      not_understood: t("nu"), nothing_pending: t("np"), not_started: t("ns"), badge: t("badge"),
      alert: t("ALERT"), deaths_today: t("Deaths today"), vet_today: t("Take the birds to the vet today"), warn_tag: t("Note"),
      placeholder: t("Write here"), send: t("Send"), say_suffix: { en: "say it.", te: "say it." }, tap_suffix: { en: "tap it.", te: "tap it." } },
    chips: { help: t("Help"), status: t("Status"), deaths: t("Deaths") },
    outcomes: {}, signs: [], houses: [{ number: 1, label_te: "H1" }],
    notice_items: ["a", "b", "c", "d", "e", "f", "g"].map(t), notice_version: "v1", ...(extra || {}),
  };
}

async function boot(opts = {}) {
  const els = new Map();
  const all = [];
  const reg = (tag, id, hidden) => { const e = new El(tag, id); e.hidden = hidden; els.set(id, e); all.push(e); return e; };
  for (const m of HTML.matchAll(/<(\w+)[^>]*\bid="([^"]+)"([^>]*)>/g)) reg(m[1], m[2], /\bhidden\b/.test(m[0]));
  const pair = new El("div", ""); pair.classes.add("pair");
  const created = [];
  const calls = [];
  const local = opts.local || makeStorage(opts.brokenLocal);
  const session = opts.session || makeStorage(false);
  const replaced = [];
  const uiBody = opts.ui || ui();
  const document = {
    getElementById: (id) => els.get(id) || null,
    querySelector: (sel) => (sel === ".pair" ? pair : null),
    querySelectorAll: () => [...all, ...created].filter((e) => e.tagName === "button" || e.id === "text"),
    createElement: (tag) => { const e = new El(tag); created.push(e); return e; },
    body: { textContent: "" },
  };
  const sandbox = {
    document, localStorage: local, sessionStorage: session, console, setTimeout, Math, JSON, Number, Set, Array, Uint8Array, Object, String,
    crypto: { getRandomValues: (a) => { for (let i = 0; i < a.length; i++) a[i] = (i * 7 + 3) % 256; return a; } },
    location: { hash: opts.hash || "", pathname: "/", search: "" },
    history: { replaceState: (...a) => replaced.push(a) },
    fetch: async (url, init) => {
      calls.push({ url, init: init || {} });
      if (url === "/api/pilot/ui") return opts.uiStatus && opts.uiStatus !== 200 ? { ok: false, status: opts.uiStatus, json: async () => ({}) } : { ok: true, status: 200, json: async () => uiBody };
      const reply = opts.turn ? opts.turn(JSON.parse(init.body)) : { status: 200, body: { kind: "tool", speech_te: "answer", speech: "answer" } };
      return { ok: reply.status === 200, status: reply.status, json: async () => reply.body };
    },
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(SCRIPT, sandbox);
  await flush();
  return { els, all, created, calls, local, session, replaced, pair, turns: () => calls.filter((c) => c.url === "/api/turn") };
}

const chipButtons = (p) => p.els.get("chips").children;
const scenarios = {};
const eq = (a, b, what) => { if (a !== b) throw new Error(`${what}: expected ${JSON.stringify(b)}, got ${JSON.stringify(a)}`); };

scenarios.nothing_runs_before_the_notice_is_acknowledged = async () => {
  const p = await boot();
  eq(p.els.get("notice-screen").hidden, false, "notice shown");
  eq(p.els.get("app").hidden, true, "app hidden");
  for (const chip of chipButtons(p)) await chip.fire("click");  // every chip, including the ones that open a picker
  eq(p.els.get("picker").hidden, true, "a picker opened before the acknowledgement");
  eq(p.els.get("picker-body").children.length, 0, "a picker was filled before the acknowledgement");
  await p.els.get("ask").fire("submit");
  p.els.get("text").value = "text";
  await p.els.get("ask").fire("submit");
  eq(p.els.get("log").children.length, 0, "the typed text was echoed before the acknowledgement");
  eq(p.els.get("text").value, "text", "the typed text was taken before the acknowledgement");
  for (const id of ["yes", "no", "add", "replace"]) await p.els.get(id).fire("click");
  await flush();
  eq(p.turns().length, 0, "turns sent before the acknowledgement");
};

scenarios.the_notice_has_all_seven_items_and_one_big_button = async () => {
  const p = await boot();
  eq(p.els.get("notice-list").children.length, 7, "items");
  eq(p.els.get("notice-list").children[0].textContent, "te:a", "first item text is the Telugu");
  eq(p.els.get("ack").textContent, "te:I understand", "button");
  eq(p.els.get("notice-title").textContent, "te:Before you start", "title");
};

scenarios.acknowledging_opens_the_page_and_is_remembered_per_device = async () => {
  const p = await boot();
  await p.els.get("ack").fire("click");
  eq(p.els.get("notice-screen").hidden, true, "notice hidden");
  eq(p.els.get("app").hidden, false, "app shown");
  eq(p.local.map.get("ct_ack"), "v1", "remembered");
  await chipButtons(p)[0].fire("click");
  await flush();
  eq(p.turns().length, 1, "a chip works after the acknowledgement");
  const again = await boot({ local: p.local });
  eq(again.els.get("notice-screen").hidden, true, "not shown again");
  eq(again.els.get("app").hidden, false, "app open at once");
};

scenarios.new_wording_asks_again = async () => {
  const local = makeStorage(false);
  local.setItem("ct_ack", "an older version");
  const p = await boot({ local });
  eq(p.els.get("notice-screen").hidden, false, "asked again");
  eq(p.els.get("app").hidden, true, "app closed");
};

scenarios.without_local_storage_it_asks_every_time_and_still_works = async () => {
  const p = await boot({ brokenLocal: true });
  eq(p.els.get("notice-screen").hidden, false, "shown");
  await p.els.get("ack").fire("click");
  eq(p.els.get("app").hidden, false, "app shown after the tap");
};

scenarios.the_token_is_read_from_the_fragment_removed_and_sent = async () => {
  const p = await boot({ hash: "#t=SECRETTOKEN-0123456789-abcdefghij" });
  eq(p.replaced.length, 1, "address cleaned");
  eq(p.replaced[0][2], "/", "address keeps its path");
  eq(p.session.map.get("ct_token"), "SECRETTOKEN-0123456789-abcdefghij", "kept for this tab");
  eq([...p.local.map.values()].some((v) => v.includes("SECRETTOKEN")), false, "token not in local storage");
  await p.els.get("ack").fire("click");
  await chipButtons(p)[0].fire("click");
  await flush();
  for (const c of p.calls) eq(c.init.headers.authorization, "Bearer SECRETTOKEN-0123456789-abcdefghij", "header on " + c.url);
};

scenarios.no_token_means_the_open_your_link_message = async () => {
  const p = await boot({ uiStatus: 401 });
  eq(p.els.get("fatal").hidden, false, "message shown");
  eq(p.els.get("notice-screen").hidden, true, "no notice");
  eq(p.els.get("app").hidden, true, "no app");
  eq(p.turns().length, 0, "no turn");
};

scenarios.a_401_on_a_turn_shows_the_message_too = async () => {
  const p = await boot({ turn: () => ({ status: 401, body: {} }) });
  await p.els.get("ack").fire("click");
  await chipButtons(p)[0].fire("click");
  await flush();
  eq(p.els.get("fatal").hidden, false, "message shown");
  eq(p.els.get("app").hidden, true, "app hidden");
};

scenarios.the_question_shows_add_and_replace_and_hides_the_plain_yes = async () => {
  const choice = { kind: "tool", awaiting_answer: true, speech_te: "q", speech: "q", result: { structuredContent: { choice: { existing_deaths: 3, new_deaths: 2, total_if_added: 5 } } } };
  const p = await boot({ turn: (b) => (b.chip === "yes" ? { status: 200, body: { kind: "tool", awaiting_answer: true, speech_te: "r", result: { structuredContent: {} } } } : { status: 200, body: choice }) });
  await p.els.get("ack").fire("click");
  await chipButtons(p)[0].fire("click");
  await flush();
  eq(p.els.get("readback").hidden, false, "question shown");
  eq(p.els.get("yes").hidden, true, "plain yes hidden");
  eq(p.els.get("add").hidden, false, "add shown");
  eq(p.els.get("replace").hidden, false, "replace shown");
  eq(p.pair.classes.has("three"), true, "three-button layout");
  await p.els.get("add").fire("click");
  await flush();
  const last = JSON.parse(p.turns().pop().init.body);
  eq(last.chip, "add", "the add tap sends the add chip");
};

scenarios.an_ordinary_read_back_shows_yes_and_no_only = async () => {
  const p = await boot({ turn: () => ({ status: 200, body: { kind: "tool", awaiting_answer: true, speech_te: "r", result: { structuredContent: {} } } }) });
  await p.els.get("ack").fire("click");
  await chipButtons(p)[0].fire("click");
  await flush();
  eq(p.els.get("yes").hidden, false, "yes shown");
  eq(p.els.get("add").hidden, true, "add hidden");
  eq(p.els.get("replace").hidden, true, "replace hidden");
  eq(p.pair.classes.has("three"), false, "two-button layout");
};

scenarios.the_device_id_is_kept_and_sent_as_the_session = async () => {
  const p = await boot();
  const id = p.local.map.get("ct_device");
  if (!/^[A-Za-z0-9_-]{16,64}$/.test(id || "")) throw new Error("no good device id: " + id);
  await p.els.get("ack").fire("click");
  await chipButtons(p)[0].fire("click");
  await flush();
  eq(JSON.parse(p.turns()[0].init.body).session, id, "session is the device id");
  const again = await boot({ local: p.local });
  eq(again.local.map.get("ct_device"), id, "same id after a restart");
};

scenarios.the_device_id_falls_back_to_the_tab_without_local_storage = async () => {
  const p = await boot({ brokenLocal: true });
  const id = p.session.map.get("ct_session");
  if (!/^[A-Za-z0-9_-]{16,64}$/.test(id || "")) throw new Error("no fallback id: " + id);
};

// ---- Commit A (appearance): the red ALERT bar, the price, tagged warnings, one notice, a short log, tap not say ----
const textOf = (e) => [e.textContent || "", ...e.children.map(textOf)].join(" ").replace(/\s+/g, " ").trim();
const rawText = (e) => (e.textContent || "") + e.children.map(rawText).join("");
const flat = (e) => [e, ...e.children.flatMap(flat)];
const withClass = (root, name) => flat(root).filter((e) => (e.className || "").split(/\s+/).includes(name));
const logEl = (p) => p.els.get("log");
async function open(turn, extra) {
  const p = await boot({ turn, ...(extra || {}) });
  await p.els.get("ack").fire("click");
  return p;
}
const status = (sc, speech) => () => ({ status: 200, body: { kind: "tool", speech_te: speech || "te status text", speech: "status text", result: { structuredContent: sc } } });
const house = (level, extra) => ({ number: 1, label_te: "H1", level, latest_record_day: "2026-10-13", deaths_latest: 7, findings: [], ...(extra || {}) });
const ALERT_SC = { as_of: "2026-10-13", level: "alert", houses: [house("alert", { findings: [{ code: "daily_limit_exceeded", level: "alert", text_te: "limit text te" }] }), house("ok", { number: 2, label_te: "H2", deaths_latest: 1 })] };

scenarios.an_alert_status_gets_one_red_bar_with_icon_word_shed_deaths_and_the_vet_line_and_the_rest_below = async () => {
  const p = await open(status(ALERT_SC));
  await chipButtons(p)[1].fire("click"); await flush();
  const bars = withClass(logEl(p), "alertbar");
  eq(bars.length, 1, "one bar (only the ALERT shed)");
  const text = textOf(bars[0]);
  for (const want of ["te:ALERT", "H1", "7", "te:Deaths today", "te:Take the birds to the vet today"]) if (!text.includes(want)) throw new Error(`bar lacks ${want}: ${text}`);
  if (text.includes("H2")) throw new Error("the OK shed is in the bar: " + text);
  eq(bars[0].attrs.role, "alert", "role");
  if (withClass(bars[0], "icon").length !== 1) throw new Error("no icon in the bar");
  const kids = logEl(p).children;
  eq(kids.indexOf(bars[0]) < kids.findIndex((k) => k.textContent === "te status text"), true, "the bar comes before the full answer");
  eq(kids.some((k) => k.textContent === "te status text"), true, "the full answer is still shown below");
};

scenarios.the_bar_shows_only_the_alert_codes_own_text_when_it_is_not_the_farmers_death_limit = async () => {
  const sc = { as_of: "2026-10-13", level: "alert", houses: [house("alert", { findings: [{ code: "mortality_spike", level: "alert", text_te: "spike te" }] })] };
  const p = await open(status(sc));
  await chipButtons(p)[1].fire("click"); await flush();
  const text = textOf(withClass(logEl(p), "alertbar")[0]);
  if (!text.includes("spike te")) throw new Error("the finding text is missing: " + text);
  if (text.includes("te:Take the birds to the vet today")) throw new Error("the vet line is only for the farmer's own limit: " + text);
};

scenarios.the_bar_is_never_shown_on_ok_or_watch_or_without_houses = async () => {
  for (const sc of [
    { as_of: "2026-10-13", level: "ok", houses: [house("ok")] },
    { as_of: "2026-10-13", level: "watch", houses: [house("watch", { findings: [{ code: "daily_deaths_rule", level: "watch", text_te: "w" }] })] },
    { as_of: "2026-10-13", level: "ok", items: [{ level: "watch", category: "x", label_te: "H1", text_te: "w" }] },
    {},
  ]) {
    const p = await open(status(sc));
    await chipButtons(p)[1].fire("click"); await flush();
    eq(withClass(logEl(p), "alertbar").length, 0, "no bar for " + JSON.stringify(sc).slice(0, 60));
  }
  const p = await open(() => ({ status: 200, body: { kind: "fallback", speech_te: "nu" } }));
  await chipButtons(p)[1].fire("click"); await flush();
  eq(withClass(logEl(p), "alertbar").length, 0, "no bar on a fallback");
};

scenarios.the_briefings_alert_items_get_the_bar_too = async () => {
  const sc = { as_of: "2026-10-13", level: "alert", items: [{ level: "alert", category: "daily_limit_exceeded", label_te: "H1", text_te: "item text te" }, { level: "watch", category: "x", label_te: "H2", text_te: "w" }] };
  const p = await open(status(sc));
  await chipButtons(p)[1].fire("click"); await flush();
  const bars = withClass(logEl(p), "alertbar");
  eq(bars.length, 1, "one bar");
  const text = textOf(bars[0]);
  for (const want of ["te:ALERT", "H1", "te:Take the birds to the vet today"]) if (!text.includes(want)) throw new Error(`bar lacks ${want}: ${text}`);
  if (text.includes("H2")) throw new Error("the WATCH item is in the bar: " + text);
};

scenarios.a_deaths_count_from_another_day_is_not_shown_as_todays = async () => {
  const sc = { as_of: "2026-10-13", level: "alert", houses: [house("alert", { latest_record_day: "2026-10-12", findings: [{ code: "mortality_spike", level: "alert", text_te: "spike te" }] })] };
  const p = await open(status(sc));
  await chipButtons(p)[1].fire("click"); await flush();
  const text = textOf(withClass(logEl(p), "alertbar")[0]);
  if (text.includes("te:Deaths today")) throw new Error("yesterday's number shown as today's: " + text);
};

const SALE = "te your price: per kg ₹140 (paper rate ₹160 minus ₹20, your own rule).";
const sale = (speech, tool) => () => ({ status: 200, body: { kind: "tool", intent: { tool: tool || "plan_sale" }, speech_te: speech, speech: speech, result: { structuredContent: {} } } });

scenarios.the_sell_price_is_one_big_number_and_the_rule_line_is_small_and_nothing_is_lost = async () => {
  const p = await open(sale(SALE));
  await chipButtons(p)[1].fire("click"); await flush();
  const prices = withClass(logEl(p), "price");
  eq(prices.length, 1, "one big number");
  eq(prices[0].textContent, "₹140", "the big number is the price, not the paper rate or the deduction");
  const rules = withClass(logEl(p), "rule");
  eq(rules.length, 1, "one rule line");
  eq(rules[0].textContent.startsWith("(paper rate ₹160"), true, "the rule line is the bracket");
  const bubble = logEl(p).children.find((k) => withClass(k, "price").length);
  eq(rawText(bubble), SALE, "every character is still there, in order");
};

scenarios.the_sell_question_and_other_answers_get_no_price_emphasis = async () => {
  for (const [speech, tool] of [["te ask: say paper rate 160 and I will work out your price.", "plan_sale"], ["te price ₹140 (rule ₹20)", "get_farm_status"], ["te bad rate: say it in rupees, like paper rate 160.", "plan_sale"]]) {
    const p = await open(sale(speech, tool));
    await chipButtons(p)[1].fire("click"); await flush();
    eq(withClass(logEl(p), "price").length, 0, "no emphasis for: " + speech);
  }
};

scenarios.a_warning_has_a_word_and_an_icon_marker_not_only_a_colour_and_your_own_words_have_none = async () => {
  const p = await open(() => ({ status: 200, body: { kind: "fallback", speech_te: "nu text" } }));
  await chipButtons(p)[1].fire("click"); await flush();
  const warn = logEl(p).children.find((k) => k.textContent === "nu text");
  eq((warn.className || "").includes("warn"), true, "warn class");
  eq(warn.attrs["data-tag"], "te:Note", "the warning carries its word");
  p.els.get("text").value = "typed";
  await p.els.get("ask").fire("submit"); await flush();
  const you = logEl(p).children.find((k) => k.textContent === "typed");
  eq(you.attrs["data-tag"], undefined, "the farmer's own words carry no tag");
};

scenarios.the_notice_text_is_on_the_screen_once_and_not_in_a_strip_under_the_header = async () => {
  const items = ["a", "b", "c", "d", "voice", "f", "g"].map((x) => ({ en: x, te: "te:" + x }));  // the real list holds the voice-typing sentence
  const p = await boot({ ui: ui({ notice_items: items }) });
  if (HTML.includes('id="notice"')) throw new Error("the voice-typing strip is still in the page");
  const copies = [...p.els.values(), ...flat(p.els.get("notice-list"))].filter((e) => e.textContent === "te:voice");
  eq(copies.length, 1, "the notice sentence appears once");
};

scenarios.the_input_has_a_telugu_placeholder_and_the_send_button_a_word = async () => {
  const p = await boot();
  eq(p.els.get("text").placeholder, "te:Write here", "placeholder");
  eq(p.els.get("send").textContent, "te:Send", "send button label");
};

scenarios.the_log_keeps_only_the_newest_answers = async () => {
  const p = await open(status({}, "answer"));
  for (let i = 0; i < 12; i++) { await chipButtons(p)[1].fire("click"); await flush(); }
  eq(logEl(p).children.length <= 6, true, "log length " + logEl(p).children.length);
  eq(logEl(p).children.length > 0, true, "the newest answer is there");
};

scenarios.a_read_back_says_tap_where_the_server_text_says_say_and_is_unchanged_otherwise = async () => {
  const q = (t) => () => ({ status: 200, body: { kind: "tool", awaiting_answer: true, speech_te: t, result: { structuredContent: {} } } });
  let p = await open(q("House 1: 7 died. To save, yes, otherwise no say it."));
  await chipButtons(p)[0].fire("click"); await flush();
  eq(p.els.get("readback-text").textContent, "House 1: 7 died. To save, yes, otherwise no tap it.", "say became tap");
  p = await open(q("House 1: 7 died. Other wording."));
  await chipButtons(p)[0].fire("click"); await flush();
  eq(p.els.get("readback-text").textContent, "House 1: 7 died. Other wording.", "unchanged without the suffix");
};

(async () => {
  const out = {};
  for (const [name, fn] of Object.entries(scenarios)) {
    try { await fn(); out[name] = "ok"; } catch (e) { out[name] = String(e && e.message || e); }
  }
  console.log(JSON.stringify(out));
})();
