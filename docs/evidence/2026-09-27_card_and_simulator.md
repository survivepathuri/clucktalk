# Evidence: farm-status MCP App card + Simulator, end to end (2026-09-27)

Everything below was run on Windows 11 Pro, Python 3.13.15, Chrome, demo data (`MOCK_BEDROCK=true`), with `python tasks.py run`
(MCP server on 127.0.0.1:8765, Simulator on 127.0.0.1:8766). The seeded demo farm is generated relative to "today",
so dates on the screenshots read 27-09-2026.

## 1. Wire transcript (curl, protocol 2025-11-25)

```
initialize  → protocolVersion "2025-11-25", serverInfo CluckTalk 0.1.0
              capabilities: experimental, prompts, resources, tools   (no "extensions" on 2025-11-25: FRICTION_LOG FL-008)
notifications/initialized → HTTP 202
tools/list  → get_farm_status _meta {"ui": {"resourceUri": "ui://clucktalk/farm-status.html"}}
              plan_feed      _meta null   (no card yet: declares none)
              get_help       _meta null
resources/read ui://clucktalk/farm-status.html
            → mimeType text/html;profile=mcp-app, _meta {"ui": {"prefersBorder": false}},
              387,055 chars (final build), starts '<!doctype html>', contains 'const SERVER_DEMO = true;'
```

## 2. End-to-end runs in the Simulator (browser, real MCP calls)

Each row: typed utterance → rule-based host → `tools/call` over HTTP → spoken answer (+ card on Echo Show).
"Cross-modal" is the host's runtime check after the card rendered: every spoken number is on the card, and every
number on the card is in the tool result.

| Utterance | Device | Tool (args) | MCP ms | Turn ms | Screen | Cross-modal |
|---|---|---|---|---|---|---|
| Alexa, ask CluckTalk how shed two is doing | Echo Show | get_farm_status {house: "shed two"} | 13.0 | 18 | shed card (ALERT) | ✓ |
| How's the farm today? | Echo Show | get_farm_status {} | 12.2 | 16 | farm card | ✓ (29 card numbers, 5 spoken) |
| Kotam teen kaisa hai? | Echo Show | get_farm_status {house: "kotam teen"} | 9.1 | 16 | shed 3 card (layer, OK) | ✓ |
| How is shed nine doing? | Echo Show | get_farm_status {house: "shed nine"} → isError | 8.6 | 14 | bilingual error card | ✓ |
| Feed plan for shed two | Echo Show | plan_feed {house: "shed two"} | 8.7 | 15 | text answer (no card for this tool yet) | n/a |
| What can you do? | Echo Show | get_help {} | 3.1 | 8 | text answer | n/a |
| Should I sell my birds now? | Echo Show | none (host fallback; plan_sale not built) | – | 4 | text answer | n/a |
| How is shed one doing? (+1,500 ms simulated delay) | Echo Show | get_farm_status {house: "shed one"} | 13.4 | 1,534 | "Still working…" shown and spoken, then card | ✓ |
| How is shed two doing? | Echo Dot | get_farm_status {house: "shed two"} | 14 | 34 | no card requested (`card: null`), full answer by voice | n/a |
| Tap on the Shed 1 tile (touch = voice) | Echo Show | card → host → tools/call get_farm_status {house: "house-1"} | 5.2 | 11 | shed 1 card | ✓ |

Card handshake seen in the developer panel: `ui/initialize` with `appInfo {"name":"CluckTalk farm status card"}`,
protocol 2026-01-26; sandbox origin `http://localhost:8766` (page on `127.0.0.1:8766`); CSP "spec default + font-src data:".
No "font" warning was logged, so the bundled Noto Sans Telugu loaded.

## 3. Screenshots (`2026-09-27_card_simulator/`)

| File | What it shows |
|---|---|
| 01_echo-show-1024x600_farm.png | Whole farm at 1024×600 (original Echo Show viewport, Amazon APL docs), everything above the fold |
| 02_echo-show-1024x600_shed2.png | Shed 2 (ALERT) at 1024×600: big numbers, 3 findings with icon + word in EN + TE |
| 03_tap-on-shed1-tile_1024x600.png | After tapping the Shed 1 tile: the card called the tool itself (touch = voice) |
| 04 / 05_echo-show-960x600_*.png | Farm / shed 2 at 960×600 dp (1280×800 px hub at 213 dpi) |
| 06_echo-show-960x480_farm.png | Farm at 960×480 dp (`hubLandscapeSmall` range, Echo Show 5 class) |
| 07_phone-390x844_farm.png | Phone (Alexa app) size, dark: tiles stack, worst shed first |
| 08_phone-390x844_shed2_light.png | Phone, light theme: status still readable without colour |
| 09_error-card_unknown-shed.png | "shed nine": bilingual message + next step, Demo badge still shown, never blank |
| 10_still-working.jpg | Slow answer: previous card gone (no stale content), question echoed, "Still working…" |
| 11_echo-dot_voice-only.jpg | Echo Dot mode: no screen, answer complete by voice (transcript shown outside the device) |
| 12_text-answer_plan-feed.png | A tool without a card on Echo Show: labeled text answer in EN + TE |
| 13_flow_voice-to-card-to-tap.gif | Typed question → shed card → tap "All sheds" → farm card → tap a shed |
| 14_card-watchdog_text-fallback.png | A deliberately broken card: after 3 s the host shows the labeled text answer and a red developer-panel line (never a blank screen) |

Screens 01–09 are zoomed captures of the device frame rendered at its true CSS size (device pixel ratio 1).

## 4. Tests and latency

- `python tasks.py check` → PASSED: lint, format, 21 harness, 145 unit, 78 contract, AOSS, secret scan.
- New tests: `tests/contract/test_card.py` (7), `tests/contract/test_simulator.py` (22), `tests/unit/test_cards.py` (5, one
  runs the card's own `num()` in Node against the server formatter and is skipped visibly when Node is absent),
  `tests/unit/test_simulator_host.py` (25), `tests/harness/test_build_cards.py` (2).
- `scripts/latency_report.py -n 200` (localhost HTTP, no network/TLS hop):

| Call | n | p50 ms | p95 ms | max ms |
|---|---|---|---|---|
| tools/call get_farm_status (whole farm) | 200 | 5.0 | 6.2 | 8.4 |
| tools/call get_farm_status (shed two) | 200 | 3.0 | 3.7 | 4.4 |
| tools/call get_farm_status (unknown shed: error path, isError checked) | 200 | 2.1 | 2.8 | 3.8 |
| tools/call plan_feed (shed two) | 200 | 2.8 | 3.6 | 6.4 |
| tools/call plan_feed (whole farm) | 200 | 4.1 | 4.9 | 5.2 |
| tools/call get_help | 200 | 2.2 | 3.2 | 3.7 |
| resources/read farm-status card (~387 KB) | 200 | 7.4 | 8.4 | 10.9 |
| Simulator turn: text → rule → tools/call → answer (backend) | 200 | 5.4 | 6.4 | 7.2 |

All p95 values are far below the 500 ms budget. These are loopback numbers; a cloud deployment adds network time.

## 5. Independent review (CLAUDE.md Rule 11) and fixes

A fresh agent reviewed the card and Simulator cold against docs/DESIGN.md §5–§7, §12 and the MCP Apps spec, and ran
the suite plus the card's `num()` in Node. Findings (2 Medium, 9 Low, 1 tracked risk) and what changed:

| # | Finding | Fix | Verified by |
|---|---|---|---|
| 1 | Medium: a card that fails to load stays blank or on "Loading" | Host watchdog (3 s → labeled text answer + red panel line); the card shows the bilingual generic error if `ui/initialize` fails | Browser: broken card planted → screenshot 14 |
| 2 | Medium: card-side cross-modal untested; the check accepted any number in the result | The card self-tests `num()` against `render.num` fixtures embedded at build time; a Node test runs the card's `num()`; each KPI carries `data-field` and the host checks it against that exact field | Unit tests; browser runs show "N KPI values equal their fields" |
| 3 | Low→Medium later: API reachable from the sandbox origin | API POST needs Origin = the requested host and a JSON body (415 otherwise); sandbox CSP adds `form-action 'none'` and `frame-ancestors` (Simulator page only); proxy requires the exact port | Contract tests |
| 4 | A card could call any tool | A card may only call the tool that owns it (`resourceUri` match) | Contract tests |
| 5 | `render.num(-0.5)` dropped the sign | Sign handled apart from the integer part | Unit test |
| 6 | Finding tags English only | Tags show EN + TE | Screenshot 02 |
| 7 | Stale readings could look like today's | The card shows "Latest readings: dd-mm-yyyy" when a shed's data is not from today | Code path only: all demo readings are from today |
| 8 | 960×480 farm card scrolled | Tighter short-screen rules | Screenshot 06 (no scrollbar) |
| 9 | Bad request bodies gave 500s; protocol errors worded as "not responding" | 400 for malformed bodies; separate "couldn't do that" wording for JSON-RPC errors | Contract tests (400); protocol-error path not triggered |
| 10 | Browser card cache could go stale | Cleared whenever the host re-initializes the MCP session | Code review |
| 11 | Error view without `_meta` had no Telugu; cancel had no next step; latency script counted errors as success | Generic reviewed Telugu + next step; latency rows fail on an unexpected `isError` | Latency run above |
| 12 | Risk: strict hosts may block the inlined font | Already FRICTION_LOG FL-007; fallback + warning in the card | Not claimed to work on Alexa+ until verified there |

Mutation check of the fixes (scratch script, byte-exact restore, `-B`): **8/8** deliberate regressions caught (sign loss,
Western grouping in the card, dropped decimals in the card, any-tool taps, non-JSON bodies, sandbox-origin API calls,
missing `form-action`, unvalidated bodies).

## 6. Not verified in this run (honest limits)

- **Microphone input**: the mic button uses Chrome's `webkitSpeechRecognition` (en-IN), which needs microphone permission
  and Google's online speech service. The automated browser run used the text box; a spoken utterance was not tested.
- **Speech output**: runs used "Sound off" for automation. The page picked "Microsoft David (en-US)" because no en-IN voice
  is installed on this machine; installing an English (India) Windows voice makes it pick en-IN.
- **A real Alexa+ device or the Alexa app**: not available locally. Card sizes follow Amazon's APL viewport docs; Alexa+
  publishes no MCP App container size (FRICTION_LOG FL-009).
- **A host with the spec's strict default CSP** (no `font-src`): the card's fallback to system Telugu fonts and its warning
  were not exercised, because the Simulator follows the reference host's `font-src 'self' data:`.
- **Telugu card labels**: 26 new strings are pending native-speaker review (`docs/TELUGU_REVIEW.md` §1).
- **"Latest readings" date on stale sheds**: all demo readings are from today, so this card path was not rendered.
