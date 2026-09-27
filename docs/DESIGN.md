# CluckTalk design

The engineering design behind CluckTalk. Code comments cite this file as `docs/DESIGN.md §N`.
**Status**: this document describes the target design. What actually works, with evidence, is recorded in the README and the eval table; nothing here claims a feature is finished.

## 1. Product
CluckTalk (Telugu subtitle "కోడి మిత్ర") is an Alexa+ add-on for small and medium Indian poultry farms (broiler and layer, 500–20,000 birds): a self-hosted MCP server plus an Agent Skill.
The farmer speaks English or Hinglish, often with busy hands. CluckTalk answers by voice (complete on a screenless device) and shows bilingual Telugu + English cards (MCP Apps) on screen devices.

Planned tool intents (one intent per tool, see §5): farm status per house, health triage (async), vet handoff, feed planning, profit forecast, sell-now-or-wait, farm memory, daily briefing, feed orders with confirmation, and "what can you do?".
Planned next (§13): farm profile (contract or independent), voice record book, contract earnings tracker, vaccination planner and vaccine-day coach.

## 2. Architecture

```
┌───────────────────────────────────────────────────────────────┐
│ Alexa+ Simulator (web app, plays the Alexa+ MCP client role)  │
│ Device mode: Headless (Echo Dot) | Screen (Show / Fire TV)    │
│ Shows "Still working…" for async tools · "Demo data" badge    │
└────────────────────────────┬──────────────────────────────────┘
                             │ MCP 2025-11-25, Streamable HTTP
                             ▼
┌───────────────────────────────────────────────────────────────┐
│ CluckTalk MCP server: FAST PATH (< 500 ms p95)                │
│ Validates input · reads precomputed state · returns           │
│ text_en/text_te + structuredContent + ui:// resourceUri       │
└───────────────┬──────────────────────────────┬────────────────┘
                │ reads                        │ enqueues jobs
                ▼                              ▼
┌───────────────────────────┐   ┌───────────────────────────────┐
│ State: briefings, checks, │◄──│ SLOW PATH: agents             │
│ sale plans, orders,       │   │ (health, feed & profit, ops), │
│ handoffs, idempotency     │   │ triggered by upload, schedule │
│ keys                      │   │ or new readings               │
└───────────────────────────┘   └───────────────────────────────┘
```
- Local mode: Python venv, in-process state, seeded demo data. Docker is optional and never required.
- Cloud mode (AWS): pay-per-use services only. OpenSearch Serverless is never used (CLAUDE.md Rule 1).
- Layering: `src/clucktalk/domain/` is pure, deterministic math with no I/O. The MCP tool layer formats its results, so voice and screen share one set of numbers (§6, cross-modal).

## 3. Fast path / slow path
- Amazon's integration guidance asks for an MCP round trip under **500 ms** and an interim "still working" message when work is slower. So no agent or LLM call runs inside a synchronous tool.
- Briefings are precomputed on a schedule or on new readings.
- Health triage is asynchronous: `start_health_check` returns a `check_id`, status `analyzing`, and an interim message; `get_health_check` returns the result.
- Orders and vet sends: propose → explicit "yes" → confirm, chained by IDs.
- Deterministic math (feed plan, profit forecast, sell-now-or-wait) runs directly on the fast path.

## 4. MCP transport security
1. Validate the `Origin` header on Streamable HTTP requests.
2. Bind to `127.0.0.1` in local mode; require an auth token whenever the server is reachable from other hosts.
3. Handle `Mcp-Session-Id` correctly; reject unknown sessions cleanly.

## 5. Tool contract rules
Based on Amazon's Alexa+ MCP tool, schema and data design guidance.
1. One tool = one customer intent; no overlaps. The description says when to call it, why, and what it returns.
2. One-shot extraction: accept all constraints in one call.
3. Declare only what you honor. Output matches `outputSchema`; no undeclared fields.
4. Always return something. Errors are structured (`isError: true`) with a customer-safe message and one next step: spoken English in `content`, English + Telugu in `_meta["clucktalk/error"]`, and no `structuredContent` (MCP 2025-11-25: structured results must conform to `outputSchema`). Never speak codes, tool names, JSON, or IDs.
5. Stable IDs chain tools (`house_id`, `check_id`, `sale_plan_id`, `proposal_id`, `order_id`, `handoff_id`), alongside human labels ("House 2", "the first one").
6. Synonyms in enums and descriptions: `BV-300/BV300/Babcock`, `Cobb 430/Cobb`, `shed/house/kotam`, `dana/feed`, `bech do/sell`, and Hinglish numbers.
7. Independent parameters: a correction changes one field.
8. Every tool in `tools/list` works; no placeholders.
9. Payload hygiene: only our own content.
10. Personalize from farm memory.

Every tool result carries `text_en` + `text_te` + `structuredContent`, plus `_meta.ui.resourceUri` when a card exists.

## 6. Behavior requirements
Mapped from Amazon's Alexa+ add-on functional requirements.

| Area | Design | Verified by |
|---|---|---|
| Context & continuity | Field-level updates; "start over"; expiry message | Golden cases |
| Error handling | Safe errors, one next step, interim message, service-down message | Contract tests + injected failures |
| Device availability | Every core flow works headless; screen-only features say so | Suite run in both device modes |
| Onboarding | `get_help`; the documented invocation examples work | Golden cases |
| Transaction flow | Price breakdown (base, GST, delivery, total); explicit "yes"; duplicate detection; modify one field; cancel with confirmation; status; receipt; amount re-validated; idempotency | Lifecycle test |
| Voice-only | At most 5 options; read-back + "yes"; never refer to a screen | Headless golden cases |
| Cross-modal | Spoken numbers equal card numbers; English and Telugu speak the same numbers; no stale card | Scoped automated check per finding / house (`tests/crossmodal.py`) |
| Visual | No blank cards; legible; touch = voice; key info above the fold | Screenshot review + accessibility check |
| Tool validation | Schemas, validation, error contract, stable IDs, synonyms | Contract suite |

Not applicable: account linking, search/discovery, video playback.

## 7. Safety rules
1. **Fail loud, never fake.** Works correctly > visible fallback with warning > clear error. Never substitute sample data when a real call fails. Mock mode only when `MOCK_BEDROCK=true` is set explicitly, with a visible "Demo data" badge.
2. **Simulated data is labeled.** Market rates, sensors, supplier, SMS, and payments are always shown as "Simulated".
3. **Health.** Triage language with confidence and a vet disclaimer. No drug names or doses. A suspected notifiable disease (e.g., avian influenza) gets no diagnosis: isolate, stop bird movement, report to a vet / the State Animal Husbandry Department, and offer a vet handoff.
4. **Human approval.** Orders and vet sends need propose → explicit "yes" → confirm, with idempotency keys and duplicate detection.
5. **Order limit.** An in-server check blocks unusually large orders. The limit is relative to the house's weekly feed use (a flat rupee cap would block normal orders for large houses). Exact rule: to be settled when the order flow is built.
6. **Honest numbers.** Only sourced figures (see §9), with the formula shown for computed impact numbers.
7. **Honest time.** "Today" is said only when the latest reading is from today; otherwise "in the latest count". A feed plan built on readings older than a day says so and asks the farmer to check the stock.
8. **Nothing unknown is called fine.** If no house can be checked, the farm level is `unknown`, never `ok`. A house that fails is listed with its reason; the others are still answered.
9. **No needless orders.** A reorder is suggested only when the projection shows a shortfall; costs are stated as before GST and delivery.

## 8. Language
- Voice in/out: English and Hinglish. Cards: Telugu + English.
- Fixed strings are pre-translated and reviewed by a native Telugu speaker; the card bundle ships Noto Sans Telugu.
- Farmer vocabulary is first class (§5 rule 6).
- Every Telugu string is listed next to its English in `docs/TELUGU_REVIEW.md` (generated by `scripts/telugu_review.py`),
  with its review status tracked per string: a new or changed string (either language) stays **pending** until a native
  speaker approves it. No pending Telugu strings may remain at submission (`telugu_review.py --require-none-pending`).

### 8.1 Telugu glossary (native-speaker review, 2026-09-27)
New Telugu strings must use these words; existing strings were changed to match.

| Concept | Use | Not |
|---|---|---|
| Shed / house | షెడ్ (plural షెడ్లు) | పెడ్ |
| Feed conversion ratio | FCR | దాణా మార్పిడి నిష్పత్తి |
| Call the vet | డాక్టర్‌కి ఫోన్ చేయండి | పశువైద్యుడిని సంప్రదించండి |
| Simulated price | అంచనా ధర (డెమో) | సిమ్యులేటెడ్ ధర |
| Flock / batch | బ్యాచ్ | మంద |
| Feed plan | ఫీడ్ ప్లాన్ | దాణా ప్రణాళిక |
| Feed (every use: ఫీడ్ నిల్వ, ఫీడ్ బస్తాలు, స్టార్టర్ ఫీడ్; inflected ఫీడ్‌ను, ఫీడ్‌కు) | ఫీడ్ | దాణా |
| Chickens / birds | కోళ్లు (ల్ల; e.g. కోళ్లలో) | కోళ్ళు (ళ్ళ) |
| English prompt to name a shed | "by shed number" / "Say a shed number", matching the Telugu | "by name" / "Name a shed" |
| Ask about a specific shed | షెడ్ నంబర్ చెప్పి అడగండి / షెడ్ నంబర్ చెప్పండి | పేరుతో అడగండి / షెడ్ పేరు చెప్పండి |

## 9. Data and provenance
- Every number and threshold has a source in `docs/SOURCES.md`; each threshold in code carries its provenance.
- Breed reference data is cited, never reproduced in full (e.g., Ross 308: weekly checkpoints only).
- Where no public reference exists (e.g., a Cobb 430 performance table), CluckTalk refuses the comparison instead of inventing targets.
- Cumulative mortality: farms under 5% were more profitable than those over 10% (jebas.org, 2023), which sets the watch / alert thresholds.

## 10. Local demo mode
- From `git clone` to the first card in at most 5 commands: `python tasks.py setup`, then `python tasks.py run`.
- Mock mode with seeded, clearly fictional demo data. The seed is generated relative to "today", so the demo tells the same story on any day it is run.
- `python tasks.py eval-fast` reproduces the eval table without AWS.

## 11. Naming
The product name lives in one config constant (`APP_NAME` in `src/clucktalk/config.py`), so a rename is a one-line change.

## 12. Known pitfalls and countermeasures
| Pitfall | Countermeasure | Enforced by |
|---|---|---|
| Wrong or old protocol version / transport | 2025-11-25 + Streamable HTTP; version stated in README; Inspector transcript saved | Contract test on `initialize` |
| Tools that return nothing or malformed errors | Always a structured result or `isError` | Contract tests |
| Schema parameters the server ignores | "Declare only what you honor" review | Independent review |
| Overlapping or vague tool descriptions | One intent per tool; tool-selection golden cases | Golden suite |
| LLM inside a tool → over 500 ms | Fast/slow path (§3) | Latency tests |
| "See the screen" spoken on a headless device | Headless mode tests | Golden suite |
| Spoken vs card numbers differ | Automated cross-modal diff | Contract tests |
| Missing `Origin` validation / exposed local server | §4 | Security test |
| Order executes without "yes" / duplicates | Proposal IDs, idempotency, duplicate detection | Lifecycle test |
| Medical over-claiming | §7 rule 3 | Guardrails + golden safety cases |
| Simulated data presented as real | "Simulated" labels | Review + golden cases |
| Poor Telugu quality | Native-speaker review of fixed strings | Review |

## 13. Planned: farm modes, record book, earnings, vaccination
Status: designed, not built. Each follows §5–§7; the rules below are specific to these features.

### 13.1 Farm profile: contract or independent
Most Indian broiler farms grow birds under contract: the integrator supplies chicks, feed, medicines and vet services and markets the birds; the farmer provides the shed and labour and is paid a growing charge linked to FCR and mortality (see `docs/SOURCES.md`).
- `mode: contract | independent`, set by the farmer with read-back and "yes".
- Contract mode: no sale planning and no feed purchasing. A low-stock answer offers a **feed request to the supervisor** (propose → "yes" → send; the message service is simulated and labeled).
- Independent mode: sell-now-or-wait and feed orders with confirmation.

### 13.2 Voice record book
- One utterance, all fields (§5 rule 2): deaths, feed used (bags or kg), weight sample, medicine or vaccine given. Farmer vocabulary includes Hinglish (*mar gaye* died, *dana* feed, *bori* bag, *teeka* vaccine, *dawai* medicine).
- Nothing is saved until the farmer hears it read back and says "yes"; a correction changes one field (§5 rule 7); proposals carry IDs and are idempotent.
- The record book becomes the primary data source; a bilingual batch-end summary can be handed to the company.

### 13.3 Contract earnings tracker
- Projected growing charges come only from the contract terms the farmer enters: base rate per kg, standard FCR, mortality allowance, incentive and deduction rates. No company's terms are built in; any example is labeled as an example with its source and year.
- Deterministic fast-path math with the formula shown; sensitivity answers such as "one more percent mortality costs about ₹X"; always labeled "estimate from your contract terms".

### 13.4 Vaccination planner and vaccine-day coach
- The schedule comes from the farmer's vet or integrator. Published schedules differ (and include doses), so CluckTalk ships only a labeled **example** template with sources and never hardcodes one.
- Reminders feed the daily briefing; a day-before checklist covers water sanitiser off, stabiliser ready, vaccine kept cold.
- The coach guides step by step by voice, works headless, keeps due times (stabiliser wait, drinking window) in session state, and resumes after an interruption. "Vaccination done" proposes a record-book entry (vaccine, house, time, batch/lot if given) with read-back and "yes".
- **Safety**: no dosages and no drug advice, ever; every instruction ends with "follow the vaccine label and your vet or company"; each guidance step cites its source. Timings that sources disagree on (water withholding, drinking window) are shown as ranges with sources, and the label wins.
- Golden safety case: "how many ml per bird?" gets no number, only a referral to the label and the vet or company.

## 14. MCP App cards
Built on the MCP Apps extension (`io.modelcontextprotocol/ui`, stable spec 2026-01-26) through the SDK's in-core `mcp.server.apps.Apps`.
- **Wiring**: a card-bearing tool carries `_meta.ui.resourceUri` in `tools/list` (spec: on the tool, not the result); the card is a `ui://` resource served as `text/html;profile=mcp-app` with `_meta.ui.prefersBorder: false`. Tools without a card declare none (§5 rule 3). Hosts without MCP Apps still get the full spoken answer in `content`.
- **Self-contained**: the spec's default CSP allows no network access, so each card is one HTML file: no external scripts, styles, fonts or requests. Source templates live in `ui/cards/`; `scripts/build_cards.py` inlines the font and the labels and writes the committed bundle to `src/clucktalk/server/cards/` (no Node or build step needed to run). A harness test fails if the bundle is out of date.
- **Protocol**: plain JSON-RPC over `postMessage` as the spec allows ("you don't need an SDK"): `ui/initialize` (`appInfo`, `appCapabilities`, `protocolVersion`) → `ui/notifications/initialized` → the host sends `tool-input` and `tool-result`. The card reports its size (`size-changed`), answers `ui/resource-teardown` and `ping`, and logs through `notifications/message`.
- **Cross-modal (§6)**: every number on a card is a value from the tool's `structuredContent`, formatted like the spoken answer (the card's `num()` mirrors `render.num`: Indian digit grouping, no trailing zeros). The card does no arithmetic on data, and finding sentences are the exact spoken sentences in English and Telugu. After each render the card reports its visible text and each big KPI value with the `structuredContent` field it shows; the host checks that every spoken number is on the card, every card number is in the tool result, and every KPI equals its own field. At load the card also checks its `num()` against `render.num` outputs embedded at build time and logs an error on any mismatch.
- **Honest time (§7 rule 7)**: when a shed's latest readings are not from today, the card dates them ("Latest readings: dd-mm-yyyy").
- **Visual**: status is an icon shape AND a word (OK ✓ circle, WATCH triangle, ALERT octagon, UNKNOWN ?), never colour alone. Key numbers are large (32–48 px); the least important line (breed, day, bird count) comes last so it is what drops below the fold on short screens. Checked at Amazon-documented Echo Show sizes (§15) and on a phone.
- **Bilingual**: English and Telugu side by side. Fixed labels are Python `Text` pairs in `clucktalk.server.cards` (reviewed per string, §8), with `{n}` slots for numbers so Telugu inflection ("{n}వ రోజు") is reviewed too. Noto Sans Telugu 2.005 (SIL OFL 1.1, `ui/fonts/`) is inlined; if a host's CSP blocks data: fonts, the card falls back to system Telugu fonts and logs a warning (FRICTION_LOG FL-007).
- **Demo data**: the server stamps its mode into the card at startup, so the "Demo data" badge shows on every card in demo mode, including error cards (which carry no `structuredContent`).
- **Touch = voice**: tapping a shed tile or "All sheds" makes the card call the same tool (`tools/call get_farm_status`) through the host; the answer equals what voice would give.
- **Errors**: an `isError` result renders the bilingual message and next step from `_meta["clucktalk/error"]`, never a blank card.

## 15. Simulator (plays the Alexa+ client role)
A local web app (`python tasks.py run`, http://127.0.0.1:8766/) standing in for an Alexa+ device and host while no Alexa+ device can load the add-on locally.
- **Device modes**: Echo Show (voice + card) and Echo Dot (voice only: no card is requested or rendered; answers must be complete by voice). Screen presets from Amazon's APL docs: 1024×600 (original Echo Show viewport, 160 dpi), 960×600 dp (1280×800 px hub at 213 dpi), 960×480 dp (inside the `hubLandscapeSmall` range, Echo Show 5 class), plus a 390×844 phone (typical size, not from Amazon docs) for the Alexa app. Alexa+ does not publish MCP App container sizes (FRICTION_LOG FL-009), so cards are responsive.
- **Voice**: input via the browser's speech recognition (en-IN) with a text box fallback; Chrome's recogniser is an online service, so voice input is the one part of demo mode that needs the network, and errors say so. Output via the browser's speech synthesis (an en-IN voice when installed); Amazon Polly replaces it in live mode (AWS setup task).
- **Host (mock mode)**: a rule-based intent matcher (`clucktalk.simulator.intents`) picks the tool and passes the farmer's shed words through unchanged; the server resolves them. No rule → a host fallback sentence and no MCP call. The live host (Bedrock Converse tool use) is not built; live mode refuses to start.
- **MCP client**: raw JSON-RPC over Streamable HTTP, protocol 2025-11-25, advertising the Apps extension; the developer panel shows every request and response with timings.
- **Card hosting per the spec**: a web host MUST render views through a sandbox proxy on a different origin. The page runs on one loopback name and loads `/sandbox` from the other (127.0.0.1 ↔ localhost), with `sandbox="allow-scripts allow-same-origin"`. The proxy's CSP header is the spec's restrictive default plus declared https origins only, plus `font-src 'self' data:` as in the ext-apps reference host (FL-007). The proxy CSP also sets `form-action 'none'` and `frame-ancestors` (the Simulator page only), and the proxy accepts only the page on its own port. Messages are origin-checked in both directions. A card may only ask the host to forward `tools/call` of **the tool that owns the card** (so a tap can never stand in for a spoken "yes") and `resources/read` of `ui://` resources.
- **No blank cards**: if a card has not rendered within 3 s, the host shows the labeled text answer and logs the failure; a card whose `ui/initialize` fails shows the bilingual generic error.
- **Continuity rules**: the previous card is torn down (`ui/resource-teardown`) as soon as a new question is asked, so no stale card stays on screen. A turn slower than 1 s shows and speaks "Still working…"; a developer-panel control adds a labeled simulated delay to demonstrate it.
- **Security**: binds 127.0.0.1; Host header must be one of the two loopback names; POST API calls must come from the page's own origin (Origin equals the requested host) with a JSON body.
