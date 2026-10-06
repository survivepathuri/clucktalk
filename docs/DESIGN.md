# CluckTalk design

The engineering design behind CluckTalk. Code comments cite this file as `docs/DESIGN.md §N`.
**Status**: this document describes the target design. What actually works, with evidence, is recorded in the README and the eval table; nothing here claims a feature is finished.

## 1. Product
CluckTalk (Telugu subtitle "కోడి మిత్ర") is an Alexa+ add-on for small and medium Indian **broiler** farms
(500–20,000 birds): a self-hosted MCP server plus an Agent Skill. **Broiler-first** (decided 2026-09-29): the
first build and the demo target broiler farmers only. The domain layer still supports layer flocks generically
(§13.1's `HouseKind.LAYER`, egg-production status and feed planning), and nothing here removes that code, but the
seeded demo farm, `get_help`, and the video use broiler houses only. Layer farming is a README roadmap item.
The farmer speaks English or Hinglish, often with busy hands. CluckTalk answers by voice (complete on a screenless device) and shows bilingual Telugu + English cards (MCP Apps) on screen devices.

Planned tool intents (one intent per tool, see §5): farm status per house, health triage (async), vet handoff, feed planning, sell-day plan, farm memory, daily briefing, feed orders with confirmation, and "what can you do?".
Planned next (§13): farm profile (contract or independent, **built**), voice record book, contract earnings tracker (**terms storage built**, the full tracker with sensitivity/what-if is later), vaccination planner and vaccine-day coach.

## 2. Architecture

```
┌───────────────────────────────────────────────────────────────┐
│ Alexa+ Simulator (web app, plays the Alexa+ MCP client role)  │
│ Device mode: Headless (Echo Dot) | Screen (Show / Fire TV)    │
│ Shows "Still working…" for async tools · "Demo data" badge    │
└────────────────────────────┬──────────────────────────────────┘
                             │ MCP 2025-11-25 (Streamable HTTP)
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
- Changes (farm mode, records, orders, supervisor requests, vet sends): propose → explicit "yes" → apply, chained by a `proposal_id` passed back to the same tool (§5.1).
- Deterministic math (feed plan, profit forecast, sell-now-or-wait) runs directly on the fast path.

## 4. MCP transport security
1. Validate the `Origin` header on Streamable HTTP requests. Allowed: the server's own two loopback origins, plus any exact origins listed in `CLUCKTALK_ALLOWED_ORIGINS` (never `*`; refused at config load). CORS headers are sent only for those extra origins (exact origin echoed, `Vary: Origin`, `Mcp-Session-Id` exposed, no credentials), by a layer outside the Origin and bearer checks so a preflight is answered; any other Origin still gets 403 with no CORS headers. The bind stays 127.0.0.1.
2. Bind to `127.0.0.1` in local mode; require an auth token whenever the server is reachable from other hosts.
3. Handle `Mcp-Session-Id` correctly; reject unknown sessions cleanly.
4. **Protocol version, as observed (Step 48A; `tests/contract/test_protocol_conformance.py` pins it, `python tasks.py probe-protocol-version` reproduces it).** `initialize` is answered with the version the client asked for when the SDK knows it (2025-11-25, 2025-06-18, 2025-03-26 and 2024-11-05 are each answered with themselves); an unknown or newer body version (e.g. 2026-07-28) is answered with 2025-11-25. **Decision (2026-10-04): keep this; no floor is enforced.** The server implements MCP 2025-11-25 over Streamable HTTP; for compatibility the SDK also negotiates 2025-06-18, 2025-03-26 and 2024-11-05 (see `python tasks.py probe-protocol-version`); we do not enforce a minimum version. Documented limitations: it accepts a missing or different `MCP-Protocol-Version` header on an established session, and a POST without an `Accept` header returns 406 (examined in Step 48B part C: the SDK builds a transport for it and discards it at once, so no session is left open; `tests/contract/test_concurrency.py`). Also pinned there: two overlapping requests with the same JSON-RPC id in one session leave one unanswered (a client bug, the other requests and the session keep working); sessions a client never ends live until the SDK's idle timeout (30 minutes), at most 10,000 at once (SDK defaults, not set by us). A later request's `MCP-Protocol-Version` header is not compared with the negotiated version; only a header outside the handshake set is refused (400). POST needs an `Accept` that allows JSON (a missing header or `text/event-stream` alone is 406); GET needs `text/event-stream`; DELETE without a session is 400, with an unknown or already-ended session 404. Whether these are right for Alexa+ is not verified; the server behaviour was deliberately not changed.
5. **Robustness tests (Step 48B).** `tests/unit/test_property_follow_up_sequences.py` replays random sequences of health checks, answers, death records, vet handoffs and demo-clock moves (Hypothesis, derandomized, no deadline) and asserts the safety invariants after every event, plus named scenarios; `tests/contract/test_fuzz_inputs.py` sends malformed, oversized and odd input over HTTP (never a 500, no traceback or file path, no state change on an error answer, server healthy after); `tests/contract/test_concurrency.py` covers simultaneous confirms, simultaneous health checks, 50 parallel `initialize` calls and what rejected requests leave behind. Findings pinned there: **F1** a body that parses as JSON but is not a JSON-RPC request got the SDK's 400 with pydantic's validation text and an `errors.pydantic.dev` link, and **F2** an unknown method was echoed back in the error's `data` (1 MB in, 1 MB out): both fixed in Step 48C, they now get a short fixed JSON-RPC error from `ProtocolErrorGate` in `server/app.py` (`tests/contract/test_protocol_errors.py`), and since Step 48D so does a body that is not JSON (400, the JSON-RPC "Parse error", no library text); reported and not changed: **F3** a request id that is an object, a list or a float is accepted with an empty 202; **F4** the shed-name reader ignores symbols and non-Latin words, so `shed -1` lands on shed 1 (never on a different shed); **F5** two overlapping requests with the same JSON-RPC id in one session leave one unanswered (or, on some runs, answered 500 by the SDK). The briefing and the farm status once differed on `safety.vet_contact_advised` for the same death spike; fixed in Step 48C (both read the same facts, `tests/contract/test_safety_agreement.py`). Request bodies of 10 MB or more get 413.
6. **Known SDK behaviors (Step 48C).** Four things the `mcp` 2.2.0 SDK, or our shed-name reader, does that a reader might not expect; each is pinned by a test, so an SDK upgrade that changes one fails a test. (F3) A JSON-RPC id that is an object, a list or a decimal number is accepted with an empty `202`, like a notification, and nothing is saved. (F4) The shed-name reader (`domain/houses.py`) keeps only plain letters and digits, so `shed -1` and `🐔 1` resolve to shed 1, never to a different shed; a name with two different numbers is refused. (F5) Two overlapping requests with the same id in one session leave one unanswered, for at least 40 seconds, or on some runs answered 500 "Session terminated before the request completed" (SDK message; friction entry FL-011); the session and other requests keep working. (Sessions) At most 10,000 sessions, and a session nobody ends is closed after 30 minutes idle; both are SDK defaults we do not set.
7. **Self-checks for the Alexa+ review (Step 49), all ours and none Amazon's.** `python tasks.py inspector-replay` (scripts/inspector_replay.py) starts the server on a temporary state file and replays the flow documented on Amazon's Local Inspector page: `initialize` with protocolVersion 2025-06-18 and clientInfo `addon-local-inspector`, `Accept: application/json` only, the initialized notification, `tools/list`, `resources/read` for every `ui://` resource and a `tools/call` for every tool with schema-valid arguments from a fixture; it prints a step table and p50 and p95 per step over 20 rounds. The Local Inspector itself was not run (FL-024). `python tasks.py readiness [--write-doc]` (scripts/readiness.py) checks the documented requirements that can be checked locally (endpoint, tool definitions, overlapping descriptions, error text with a next step, `ui://` resources, latency from the replay, the declared screen size classes, a placeholder add-on listing in `docs/addon-package/addon.json` against the documented field limits) and lists what it cannot check (OAuth 2.1 with PKCE, Protected Resource Metadata, a remote HTTPS URL, security and data policies); it never uses a certification word and writes `docs/ALEXA_READINESS.md` from the same data. `python tasks.py verify` (scripts/verify.py) is the one-command table for a judge (about 30 seconds, a fast subset of the tests, not the full suites). Tool information refreshes on Alexa+ only when the add-on is deployed again; nothing here tests that.
8. **Weather reminders (Step 50W-B).** The farmer's own outdoor-temperature rules (`weather_rules.json`: latitude, longitude, and rules with stat min or max, comparator below or above, a Celsius threshold, a window in hours, his own note and an example flag) are matched against an hourly forecast by the pure `domain/weather.py` (equal to the threshold is not a match; it never raises). `server/weather.py` holds the port: `MockForecast` (deterministic, SIMULATED, a daily curve from 16 to 33 degrees), the one opt-in Open-Meteo adapter (hourly `temperature_2m` only, no key, a timeout of at most 3 seconds, a 30 minute cache that records the fetch time, "unavailable" on any failure, never raises into a tool) and the rules loader (no file means off: nothing built, no network possible). The briefing and the farm status end with one line per matched rule, after all health and safety text (`weather_parts` in `tools/farm_status.py`); the status adds a separate optional `weather_reminders` list that is absent when off. Hard limits that held: no new MCP tool (14 tools, same names and descriptions), no schema change, no card or bundle change, 7 new farmer-facing strings (Telugu drafts pending review), and weather feeds nothing: levels, safety, reason codes and vet advice are computed before and without it, checked by a property test and by a recorded byte-for-byte baseline with the feature off. The only tools/list difference is the optional `weather_reminders` property in the status's output schema. Mock lines carry the existing "Demo data" prefix and the "Simulated" source label; the two labels the brief named would have been 2 more strings (9 > 7). The 20 to 30 degree target inside the shed is not stored or compared with anything; a forecast is an outdoor value for one point. The farmer's rule is relayed and not yet confirmed; the window and stat in the example file are example settings. Entering rules by voice would need a new tool (a roadmap item).

## 5. Tool contract rules
Based on Amazon's Alexa+ MCP tool, schema and data design guidance.
1. One tool = one customer intent; no overlaps. The description says when to call it, why, and what it returns.
   Descriptions never claim real-time or live data, and a tool with simulated data says so: `plan_sale` says its market price is a simulated value, not a real market quote, that a rate the farmer states is used as given, and that the result text says "Simulated" (Step 47C, a test pins it).
   `get_farm_status` is "how is it doing right now" (numbers plus the shed's open check or follow-up) and `get_daily_briefing` is "what to do first today" (a ranked list); each description names the other tool for the other job (review finding M8, a test pins it).
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

### 5.1 Confirmation pattern (one pattern for every change)
Every tool that changes something uses this pattern and no other: farm mode, contract terms, record-book entries, feed orders, feed requests to the supervisor, vet handoffs. There are no separate confirm tools.
1. **Propose**: the farmer's request calls the action's own tool with its arguments and no `proposal_id`. Nothing changes. The result reads the change back in full by voice, with `status: "needs_confirmation"`, a `proposal_id` and its expiry (10 minutes).
2. **Answer**: the host asks the farmer. It calls the **same tool** with the same arguments plus `proposal_id` and `answer: "yes"` on yes (haan, avunu) or `answer: "no"` on no (nahi, vaddu). A card tap never stands in for a spoken "yes" (§15).
3. **Apply only an exact match**: the change is applied only if the proposal exists, belongs to this farm and this tool, is pending and unexpired, and the arguments equal what was read back. If the arguments differ, nothing changes and a new read-back is returned (a correction is a new proposal).
4. **Idempotent**: repeating a confirmed `proposal_id` returns the same outcome and never applies twice. An expired, cancelled or superseded proposal changes nothing, says so, and returns a fresh read-back.
5. **One pending proposal per farm and tool**: a new proposal supersedes the older one.
6. **Audit trail**: proposals stay in the state store with their payload, status and timestamps.

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
4. **Human approval.** Every change needs propose → explicit "yes" → apply, per the one confirmation pattern (§5.1): proposal IDs, idempotency and duplicate detection.
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
- Third-party licenses: `NOTICE` is generated by `python tasks.py notices` from the installed package metadata (the project's MIT license first, then each pinned package's name, version and declared license); a harness test fails if a pinned package is missing from it. No license text is typed by hand.

## 10. Local demo mode
- From `git clone` to the first card in at most 5 commands: `python tasks.py setup`, then `python tasks.py run`.
- Mock mode with seeded, clearly fictional demo data. The seed is generated relative to "today", so the demo tells the same story on any day it is run.
- `python tasks.py eval-fast` reproduces the eval table without AWS.

## 11. Naming
The product name lives in one config constant (`APP_NAME` in `src/clucktalk/config.py`), so a rename is a one-line change.

## 12. Known pitfalls and countermeasures
| Pitfall | Countermeasure | Enforced by |
|---|---|---|
| Wrong or old protocol version / transport | Implements 2025-11-25 over Streamable HTTP (older versions negotiated by the SDK, no floor); version stated in README; Inspector transcript saved | Contract test on `initialize` |
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
Status: §13.1 mode switching and contract-terms storage are built (plus `plan_sale`, §16); §13.2's voice record book is fully built, including Simulator and golden-case wiring; everything else here is designed, not built. Each follows §5–§7; the rules below are specific to these features.

### 13.1 Farm profile: contract or independent
Most Indian broiler farms grow birds under contract: the integrator supplies chicks, feed, medicines and vet services and markets the birds; the farmer provides the shed and labour and is paid a growing charge linked to FCR and mortality (see `docs/SOURCES.md`).
- `mode: contract | independent`, set by the farmer with read-back and "yes" (§5.1): `get_farm_profile`, `set_farm_mode` (built). The demo farm starts as independent; `python tasks.py reset-demo --contract` (planned, 8 Oct) seeds a contract-mode demo scenario for the video.
- Contract mode: no sale planning and no feed purchasing. Feed answers name the bags to ask the supervisor for, with no price (the company supplies feed). `plan_sale` (§16, built) shows FCR and, once terms are saved, the growing charge instead of a market-price recommendation. Sending a **feed request to the supervisor** (propose → "yes" → send; simulated, labeled) is planned.
- Contract terms (base rate, standard FCR, incentive and deduction rates: four numbers) are entered by the farmer with `set_contract_terms` (**built**: storage only, via the confirmation pattern; the full Contract Earnings Tracker with sensitivity answers is §13.3, planned).
- Independent mode: `plan_sale` (built, §16) and feed orders with confirmation (order/confirm flow planned).
- State lives in a local SQLite file behind a `Store` interface (`clucktalk.store`), so a cloud store can replace it; `python tasks.py reset-demo --yes` restores the seeded story (every developer message that says to run it says `--yes`, since without it only the list is printed; it only lists the files with sizes and record counts; a state file not marked as a demo-clock file is moved to `.local/backups` with a timestamp, never deleted; only the demo-clock file is deleted).

### 13.2 Voice record book
- One utterance, all fields (§5 rule 2): deaths, feed used (bags or kg), weight sample, medicine or vaccine given. Farmer vocabulary includes Hinglish (*mar gaye* died, *dana* feed, *bori* bag, *teeka* vaccine, *dawai* medicine).
- Nothing is saved until the farmer hears it read back and says "yes" (§5.1); a correction changes one field (§5 rule 7); proposals carry IDs and are idempotent. Medicines and vaccines are stored by name and note only, never with a dose.
- **Built**: `log_daily_record` (one tool, the §5.1 confirmation pattern) and `get_record_book` (read-only, today, every house). `clucktalk.domain.records.merge_daily_record` layers what's given this call onto *whatever is currently on file for that day* — the farmer's own earlier log if there is one, else the seed's own synthetic value for that day, never a blank record (§5 rule 7; a first partial log, e.g. deaths only, must not zero out a day's real feed). `day` defaults to today; backfill to any day on or after the house's placement is allowed. A deaths count is bounded against every *other* day on file, not just the earlier ones (a backdated correction can overflow the days after it too); a medicine/vaccine name or note that looks dose-shaped (`DOSE_PATTERN`: a number+unit, "dose", "twice daily", …) is rejected rather than silently stored (`DoseNotAllowed`) — advisory wording alone isn't enough for a real host's free-text fields.
- **Built**: `clucktalk.server.farm_state.overlay_records` — every snapshot, a house's seed-generated records are replaced day-for-day by whatever is in the store; re-applied fresh on every call (never cached) so a record logged a moment ago is never served stale. This makes the record book every tool's primary data source (`get_farm_status`, `plan_feed`, `plan_sale` all read through it automatically — no changes needed in those tools).
  - **Known limitation**: the demo seed is generated fresh relative to "today" (§10), so a house's placed_on..as_of window *slides forward* as real days pass — the same calendar day is reinterpreted as an earlier age in the bird's life once "today" advances. A logged record's raw values (deaths, feed, treatments) persist correctly and keep affecting trailing-window figures (e.g. `deaths_7d`) even after the window slides, which is what the "three days later" cross-session demo proves; a logged day that has fallen entirely out of the new window is silently dropped from the overlay rather than crashing the `House` invariant. Age-dependent comparisons (weight-vs-curve, feed-vs-curve) for an old logged day would use the *reinterpreted* age, not the age at logging time — a structural property of the sliding-seed design, not a record-book bug, and not yet resolved.
- **Built**: Simulator intents (`clucktalk.simulator.intents.record_fields`, English + Hinglish: *mar gaye/mare* died, *bori* bag, *teeka/tika* vaccine, *dawai* medicine) and golden `eval-fast` cases for both tools. A stated quantity (not just the word "feed"/"bags") is what tells a report apart from a question, so an existing plan_feed query is never mis-routed. Feed given in kg is converted to bags before the call (the tool's own contract stays bags-only, matching `plan_feed`); a weight without a stated bird count is still sent through so the tool's own clarifying question is heard, rather than the host silently dropping the report; a dose-shaped word before "vaccine"/"medicine" is never guessed as if it were the treatment's name.
- The record book becomes the primary data source; a bilingual batch-end summary can be handed to the company.

### 13.3 Contract earnings tracker
- Projected growing charges come only from the contract terms the farmer enters: base rate per kg, standard FCR, incentive and deduction rates. A mortality allowance was dropped on 2026-10-01 because no calculation used it (it would be shown only if a rule for it is built). No company's terms are built in; any example is labeled as an example with its source and year. **Storage built** (`set_contract_terms`, `ContractTerms.rate_per_kg`, used by `plan_sale` §16); the dedicated tracker tool below (sensitivity, what-if) is planned for 8 Oct.
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
- **Cross-modal (§6)**: every number on a card is a value from the tool's `structuredContent`, formatted like the spoken answer (the card's `num()` mirrors `render.num`: Indian digit grouping, no trailing zeros). The card does no arithmetic on data, and finding sentences are the exact spoken sentences in English and Telugu. **In the Simulator**, which speaks the
tool's own text, the card sentence therefore equals the spoken one. **On Alexa+** the assistant composes its own speech
from `structuredContent` and the tool descriptions, so its wording may differ from the card's; the card still shows
the tool's sentence, and how Alexa words it is not verified on a device. After each render the card reports its visible text and each big KPI value with the `structuredContent` field it shows; the host checks that every spoken number is on the card, every card number is in the tool result, and every KPI equals its own field. At load the card also checks its `num()` against `render.num` outputs embedded at build time and logs an error on any mismatch.
- **Honest time (§7 rule 7)**: when a shed's latest readings are not from today, the card dates them ("Latest readings: dd-mm-yyyy").
- **Visual**: status is an icon shape AND a word (OK ✓ circle, WATCH triangle, ALERT octagon, UNKNOWN ?), never colour alone. Key numbers are large (32–48 px); the least important line (breed, day, bird count) comes last so it is what drops below the fold on short screens. Checked at Amazon-documented Echo Show sizes (§15) and on a phone.
- **Bilingual**: English and Telugu side by side. Fixed labels are Python `Text` pairs in `clucktalk.server.cards` (reviewed per string, §8), with `{n}` slots for numbers so Telugu inflection ("{n}వ రోజు") is reviewed too. Noto Sans Telugu 2.005 (SIL OFL 1.1, `ui/fonts/`) is inlined; if a host's CSP blocks data: fonts, the card falls back to system Telugu fonts and logs a warning (FRICTION_LOG FL-007).
- **Demo data**: the server stamps its mode into the card at startup, so the "Demo data" badge shows on every card in demo mode, including error cards (which carry no `structuredContent`).
- **Follow-up on the cards (§18)**: a briefing slide for a follow-up item has its own icon (a circular arrow) AND the word "Follow-up" beside the level icon and word. The farm-status tile and the shed detail view show a chip: the state as icon AND word, the briefing's own level words (due = WATCH for a watch check, ALERT for an urgent or reportable one; escalated = ALERT; lapsed = UNKNOWN, because no answer came and so nothing is known; never "reminder", since nothing reminds anyone), with English, a visible " · " and Telugu in the chip head (also in plain text), then the spoken sentence verbatim from `follow_up.text_en/te`. Only "Follow-up" is a new Telugu label. Scheduled and closed show no chip. The chip is inside the tile, so a tap opens the existing detail view; the tile's accessible name includes the sentence. The days number is the one in the sentence, so in the Simulator a card cannot disagree with the voice (on Alexa+ the assistant words its own answer). **Not built**: a follow-up row on the health-check card (it needs a new output field and would touch more than 12 non-test files; the day 0 sentence already shows there through `text_en`). The sale card is unchanged except for the demo-clock marker.
- **Demo-clock marker**: when the server's demo clock is on (§18), every card shows a second badge "Demo clock: +N days". It comes from `_meta["clucktalk/demo_clock"]` on the tool result (not from `structuredContent`, whose output schema is closed) and is marked `data-xm-skip`, so the "+N" is not mistaken for a farm number. When the clock is off the card is exactly as before.
- **Touch = voice**: tapping a shed tile or "All sheds" makes the card call the same tool (`tools/call get_farm_status`) through the host; the answer equals what voice would give.
- **Errors**: an `isError` result renders the bilingual message and next step from `_meta["clucktalk/error"]`, never a blank card.

## 15. Simulator (plays the Alexa+ client role)
A local web app (`python tasks.py run`, http://127.0.0.1:8766/) standing in for an Alexa+ device and host while no Alexa+ device can load the add-on locally.
- **Device modes**: Echo Show (voice + card) and Echo Dot (voice only: no card is requested or rendered; answers must be complete by voice). Screen presets from Amazon's APL docs: 1024×600 (original Echo Show viewport, 160 dpi), 960×600 dp (1280×800 px hub at 213 dpi), 960×480 dp (inside the `hubLandscapeSmall` range, Echo Show 5 class), plus a 390×844 phone (typical size, not from Amazon docs) for the Alexa app. Alexa+ does not publish MCP App container sizes (FRICTION_LOG FL-009), so cards are responsive.
- **Screen size classes (declared for the Alexa+ review, Step 49).** Two classes: **10 inches and below** and **11 inches and above**. The cards are one self-contained HTML file with a fluid, mostly single-column layout and media rules for a short wide screen and for a narrow one. Tested sizes (`docs/evidence/2026-09-27_card_and_simulator.md`): 1024×600, 960×600 and 960×480 (Echo Show class, from Amazon's APL docs) and a 390×844 phone viewport, all in the 10-inch-and-below class. **11 inches and above: no screenshot or test at that class exists.** The layout is fluid, so it should scale, but that is not verified, and no Alexa+ device has loaded the cards.
- **Voice**: input via the browser's speech recognition (en-IN) with a text box fallback; Chrome's recogniser is an online service, so voice input is the one part of demo mode that needs the network, and errors say so. Output via the browser's speech synthesis (an en-IN voice when installed); Amazon Polly replaces it in live mode (AWS setup task).
- **Host (mock mode)**: a rule-based intent matcher (`clucktalk.simulator.intents`) picks the tool and passes the farmer's shed words through unchanged; the server resolves them. No rule → a host fallback sentence and no MCP call.
- **Yes / no (§5.1)**: after a read-back (`status: "needs_confirmation"`), the host remembers that one tool call and its `proposal_id`. Only a whole-utterance answer (yes, haan, avunu / no, nahi, vaddu) is sent, as the same tool with `proposal_id` + `answer`. Any other utterance drops the pending read-back; a yes with nothing pending makes no tool call. The live host (Bedrock Converse tool use) is not built; live mode refuses to start.
- **MCP client**: raw JSON-RPC over Streamable HTTP, protocol 2025-11-25, advertising the Apps extension; the developer panel shows every request and response with timings.
- **Card hosting per the spec**: a web host MUST render views through a sandbox proxy on a different origin. The page runs on one loopback name and loads `/sandbox` from the other (127.0.0.1 ↔ localhost), with `sandbox="allow-scripts allow-same-origin"`. The proxy's CSP header is the spec's restrictive default plus declared https origins only, plus `font-src 'self' data:` as in the ext-apps reference host (FL-007). A developer-panel control (**Card CSP (fonts)**, or `?csp=strict`) switches to a strict host: the spec default only, fonts only from declared `resourceDomains`, so a card's font fallback can be tested (docs/evidence/2026-09-28_strict_csp.md). The proxy CSP also sets `form-action 'none'` and `frame-ancestors` (the Simulator page only), and the proxy accepts only the page on its own port. Messages are origin-checked in both directions. A card may only ask the host to forward `tools/call` of **the tool that owns the card** (so a tap can never stand in for a spoken "yes") and `resources/read` of `ui://` resources.
- **No blank cards**: if a card has not rendered within 3 s, the host shows the labeled text answer and logs the failure; a card whose `ui/initialize` fails shows the bilingual generic error.
- **Continuity rules**: the previous card is torn down (`ui/resource-teardown`) as soon as a new question is asked, so no stale card stays on screen. A turn slower than 1 s shows and speaks "Still working…"; a developer-panel control adds a labeled simulated delay to demonstrate it.
- **Security**: binds 127.0.0.1; Host header must be one of the two loopback names; POST API calls must come from the page's own origin (Origin equals the requested host) with a JSON body.

## 16. Sale-day plan (`plan_sale`, built 2026-09-29)
For each broiler shed, for today (d=0) through +10 days (clipped at the cited Ross 308 growth table's last day):
weight (the shed's own latest weigh-in, scaled forward along the curve's shape; the curve alone only when no
weigh-in exists yet, `weight_basis="breed_target"`, stated openly), feed cost (reusing `plan_feed`'s own
actual-vs-target scaling, so the two tools agree), and expected mortality loss (the trailing 7-day daily rate, or
the trailing 3-day rate if it is higher, "rising"). From these: the day's marginal profit, the best day (highest
cumulative net vs selling today), and the break-even day (the first day an extra day's feed cost, plus mortality
loss, exceeds the value of the weight it adds).
- **Independent farms**: the best day and the ₹ difference vs today; a break-even sentence once one falls inside
  the horizon. At most 3 days are spoken (today, the best day, the break-even day), and every spoken number is
  also in `structuredContent` (§6, cross-modal). Live-bird price is simulated and labeled, or the farmer's own
  stated rate for that call only (never stored).
- **Contract farms (§13.1, §13.3)**: no market price or ₹ profit number is ever shown (a contract farmer is not
  paid the open-market rate). Instead: how FCR rises with each extra day, and — once the farmer has saved
  `set_contract_terms` — the growing charge for the flock that day, computed only from the farmer's own saved
  rate (`ContractTerms.rate_per_kg`, floored at ₹0), as evidence for asking the supervisor to lift the birds on
  time. Never a named company's rate (§7 rule 6).
- **Not for layers**: `NotSoldByWeight` (a live sale needs a weight-vs-price comparison, which egg layers don't
  have in this model); layer flocks stay supported generically in the domain layer (§1), just not through this
  tool or the current demo farm.
- **Card** (`ui://clucktalk/sale-plan.html`): a per-day bar chart (best day outlined, break-even day-marked with a
  dashed line), tap a shed (whole-farm view) to see its own chart; bilingual, same build pipeline as farm-status
  (`scripts/build_cards.py`).

## 17. Golden eval suite (`python tasks.py eval-fast`, v0 built 2026-09-29)
A small, real (not simulated) set of cases in `data/eval/golden_cases.json`, each a real `tools/call` over HTTP
against a freshly started mock-mode server, checked against literal field values or text substrings
(`scripts/eval_fast.py`). Writes `docs/EVALS.md` with a real pass/fail count; never fakes a score (Rule 6).
v0 covers a handful of read-only, single-call cases (farm status, feed reorder, and `plan_sale`'s before /
at / after break-even and rising-mortality stories); contract-mode's multi-step confirmation flow is covered by
the contract test suite instead, since this runner is single-call by design. The suite has 78 cases
(the table in `docs/EVALS.md` is the count; a harness test keeps this number equal to it). Multi-step cases (`steps`, `save`,
`poll_until`) and model-fixture cases (`model_fixture`, `tests/fakes.py`) came with the agents (§18); a case marked
`fresh_state` runs on a server of its own, so its answer cannot depend on what earlier cases changed.
Build session 4 (2026-10-01) added 13 cases (44 in all): 11 for the follow-up (better closes; same, worse and not sure
escalate; a record-book death spike overrides "better"; no answer lapses and never reads as better; a relapse after
"better"; "worse" after a vet handoff escalates again; shed / kotam / house phrases; haan / nahi / avunu / vaddu) and 2 for
`set_contract_terms` (the four-number read-back; the retired `mortality_allowance_pct` argument is refused). To make them
possible a step may carry runner-only keys: `demo_days_later` (moves the demo clock, in process), `say` (a sentence run
through the Simulator's own intent rules, no model; it must pick the tool the step names), `answer_word` (haan, avunu,
nahi, vaddu turned into yes / no by the same rules) and `expect_error` (the call must be refused). An unknown step key
fails the case instead of being ignored. No MCP tool or argument can reach the demo clock. One deliberate break per
group was run and the matching case failed each time (see PROGRESS).
The Session 5 review fixes added 7 more: an urgent and a reportable check keep their warning the next day (briefing),
a reportable check, a due follow-up and an escalated one change the farm-status level (never "doing well"), and a
"worse" / "not sure" after a vet handoff and a newer check still ends with the vet line. Step 47B added 2 for
review finding H3 (an urgent check stays visible, with its warning, after a newer lower check).

## 18. Agents (Health Triage built 2026-09-29; Daily Briefing built 2026-09-30; Flock Follow-up: tool, briefing, farm status, the day 0 sentence, the demo clock, golden evals and the briefing / farm-status cards built 2026-10-01; health-check card row not built)
The model decides; code speaks. An agent runs on the slow path (§3) and asks a model for **one forced tool call
whose input is closed lists only** (no free-text field). Code owns every number, every sentence (English and
Telugu templates), every citation, and a deterministic **safety floor** the model can raise but never lower.
- **Engines** (`clucktalk.agents`): demo mode (`MOCK_BEDROCK=true`, the default) uses each agent's deterministic
  rules, labelled "Demo rules (no AI model)"; live AI (the synthetic demo farm + Amazon Nova via the Bedrock
  `Converse` API, boto3) starts only when `MOCK_BEDROCK=false` is set explicitly with `BEDROCK_MODEL_ID` and
  `AWS_REGION`. Live calls: `temperature 0`, per-agent `maxTokens`, at most 15 per minute, a daily cap of at most
  100 (configurable lower), counted from a call ledger in the state store that also records each call's real
  token usage. Cap reached: the rules answer, labelled "Today's AI limit is reached". Model failure: said
  plainly, never an invented result.
- **Farmer free text** (e.g. `symptoms`) is prompt data only: line breaks, control characters, angle brackets and
  the delimiter's own name are removed, it is capped at 300 characters and sent inside one `<farmer_words>` block
  the system prompt marks as "data, not instructions". It is never spoken back or put in a vet summary.
- **Health Triage** (`start_health_check`, `get_health_check`, `prepare_vet_handoff`):
  - Signs are a closed list (coughing ... sudden deaths). The floor (`clucktalk.domain.triage.floor_urgency`): a
    red-flag sign (head swelling, blue/purple comb or wattles, twisted neck, paralysis/drooping wings) with
    sudden deaths or a record-book death spike gives `notifiable_suspect`; a red flag or deaths alone give
    `urgent` (DAHD: report every unusual sickness or death); other signs give `watch`. Sources: `docs/SOURCES.md`.
    Words with no sign mapped also give `urgent`: code can't read them, so it never calls them "not urgent" and
    says it couldn't match them ("so to be safe").
  - A check still `analyzing` after 2 minutes is failed for good: the agent then makes no model call, and a reply
    that arrives later is ledgered (`late`) but never turns the check `ready`. A failed check's AI label says no AI
    answered. A billed reply without the tool call is ledgered with its real token usage.
  - `birds_affected` above the shed's live birds is left out of the prompt, and the answer says so with both numbers.
  - `notifiable_suspect` is answered at once, with no model call: no category named (no diagnosis), and fixed
    steps: stop movement, separate sick birds, do not cut open dead birds, report today to a vet or the nearest
    government veterinary centre; vet handoff offered.
  - Otherwise the check is `analyzing` (the start answers at once, and a floor of `urgent` is spoken right away);
    the agent job picks urgency, at most 3 broad problem areas with confidence, and at most 5 husbandry checks
    (never a treatment). One retry on an invalid reply; at most two calls per check and 40 per day.
  - Every result ends "This is guidance, not a diagnosis. Your vet decides any treatment."
  - `prepare_vet_handoff` follows §5.1: a read-back of the case summary (record-book numbers, reported signs,
    triage level), sent only after "yes", always as a **Simulated SMS** to a demo contact.
  - **Photo input (placeholder, not yet validated on real photos)**, step 1B: `start_health_check` takes an optional
    `photo_ref`, one of three labelled placeholder images (`docs/assets/`, `clucktalk.domain.photos`; see
    `docs/SOURCES.md`). It is stored with the check and shown as attached ("PLACEHOLDER - not a real photo"), and the
    answer says it was not analyzed and did not change the result. It is never sent to any model, never lowers or raises
    the urgency, and never appears in the vet summary. A photo alone is not a report: signs or words are still needed.
    Reading photos with Nova (image block, closed-list findings that may only add signs) is not built; FL-020 says it
    must be tested on real, licensed photos first. The Simulator dev panel attaches a placeholder to the next check.
  - **Triage card** (`ui/cards/health_check.html`, served for `start_health_check` and `get_health_check`): urgency as an
    icon and a word, the signs, what they fit, what to check first, the AI label, the placeholder-photo tile, sources;
    "Check again" (the card's own read-only tool) while a check runs. All sentences and numbers come from the tool result.

- **Daily Briefing** (`get_daily_briefing`, built 2026-09-30; `clucktalk.domain.briefing`, `clucktalk.agents.briefing`,
  `clucktalk.server.tools.briefing`, card `ui/cards/briefing.html`):
  - **What it returns**: at most 5 ranked items (`MAX_ITEMS`), each with its English and Telugu sentence, level
    (alert / watch / reminder), house, the numbers behind it, and whether it is pinned or simulated. By voice the top 3
    are read and "more" (`more: true`) reads the rest; the screen is a carousel of the same items.
  - **What it reads** (all on the fast path, in a few milliseconds): the record book (with logged records overlaid on
    the seed) through `house_status` findings, feed cover (`plan_feed`), each house's latest stored health check,
    `plan_sale`, and which houses have no record today. Nothing is fetched and no model is called inside the tool.
  - **Facts and order** (`rules_order`): a fact is `<category>:<house>`. Health facts are **pinned** above everything:
    today's death spike, a death spike logged earlier in the trailing week (`recent_logged_spike`, the "three days
    later" recall), a high cumulative mortality (any level), and a stored health check that said watch or worse. **Every**
    health fact is pinned, at any level (Rule 11 review 2026-09-30). Among them a suspected reportable disease is first,
    then an urgent check, then the mortality alerts. A check's urgency is the model's answer, or, while it runs or after
    it failed, the code floor (the level `get_health_check` speaks; the item says "not finished"). An urgent or
    suspected-reportable item carries the same "check the birds, call your vet" step as a death alert. A **suspected
    reportable disease stays** (even under a newer routine, running or failed check) until a vet handoff for it was
    confirmed or 7 days pass; any other check counts only as the house's latest, for 3 days. The rest are ordered by
    level, then kind, then house. The trailing week, the 3-day and 7-day windows and the 3-day sale window are
    CluckTalk's own heuristics, not sourced figures.
  - **Sale item**: only when `plan_sale` puts the best day within 3 days. It names a day, is labelled "simulated
    estimate" and carries no rupee figure (so contract mode cannot leak the simulated price).
  - **"More" and the AI order**: the split between the first three and the rest always comes from the rules order,
    so "more" (items 4 and 5, rules order, the AI ignored) is exactly what the first answer promised, whatever the AI
    has stored since. The AI order only re-orders the non-health items **inside the first three**; on a farm whose
    first three are all health items it changes nothing you can see. Known trade-off, not solved here.
  - **A damaged stored ordering** (unreadable JSON, not a list of ids) is logged, the rules order is shown with the
    label "saved AI ordering was unreadable", and a new ordering is prepared. The tool never fails on it.
  - **The model's part**: it is offered only the non-pinned ids and may return one list of them (`rank_briefing`,
    `additionalProperties: false`: no text field). A reply naming an unknown or pinned id, a duplicate, or an extra field
    is rejected; one retry; then the rules order stands and the answer says the AI ordering did not finish. `apply_order`
    keeps pinned facts first and never drops a fact. The prompt holds only ids, categories, levels and numbers: no
    farmer text ever reaches it.
  - **Slow path**: the tool applies a stored ordering when its fact fingerprint still matches, otherwise it answers with
    the rules order (labelled "AI ordering is still preparing") and queues one job (at most one per minute per set of
    facts). A new day or any changed number makes the stored ordering stale. Demo mode (`MOCK_BEDROCK=true`) queues no
    job and labels itself "Demo rules (no AI model)". Live: 2 calls a run, 16 a day for this agent, `maxTokens` 400, the
    global cap and throttle apply; cap reached is labelled. The briefing is prepared on the first call after a change, not
    at server start (the first answer of a day is the rules order).
  A farmer's health-check job runs in a priority lane of its own, so a slow briefing job never holds it up.
  - **Safety**: no medicine, drug or dose (a scan test covers every result); an open triage item ends with the
    "guidance, not a diagnosis" line; simulated data is labelled; new Telugu strings are pending native review.

- **Flock Follow-up** (`report_health_follow_up`; `clucktalk.domain.follow_up`, `clucktalk.server.tools.follow_up`; built
  2026-10-01). Days after a health check flagged a shed, the farmer says how it is now. **No model is involved**: the
  state of a follow-up is plain code over stored data and the day, and the host's own assistant is the only thing that
  may interpret the farmer's words into one of four values. It shows up when the farmer next asks (the briefing and the
  farm status, and their cards; the health-check card has no follow-up row), and nothing is pushed: there is no verified
  way for an add-on to remind a farmer.
  - **Tool**: `report_health_follow_up(house, outcome, check_id?, proposal_id?, answer?)`; `outcome` is exactly one of
    `better`, `same`, `worse`, `not_sure`. No free-text argument; unknown arguments are refused (strict list, as for
    `set_contract_terms`). One confirmation pattern (§5.1): the first call reads the answer back and saves nothing; only
    "yes" appends one row to `follow_up_answers` (append-only: the store has no update or delete). A repeated "yes" is a
    replay, even after the follow-up has since closed or a handoff ended it. Annotations as the other write tools.
  - **Which check**: the one named, else the open check of the HIGHEST urgency on the shed that has a follow-up to
    answer, the newest among equals (so a newer, lower check never takes the answer away from an urgent or reportable
    one that is still open; a newer check of equal or higher urgency takes the older one over anyway). An answer is taken
    from the day after the check (a same-day "better" must not close a follow-up that was never asked). A second
    "better" on a closed follow-up has nothing to add and is an error; "same", "worse" or "not sure" still reopens it.
  - **State** (`follow_up_state`, a pure function; the date is a parameter, never read from a clock): none, scheduled,
    due (3 days after a "watch" check, 1 day after an "urgent" or suspected reportable one), lapsed (7 days after due, for a watch check;
    never read as "better"; an unanswered urgent or reportable one escalates instead, see M5 below), closed, escalated, superseded. The windows are our own rules, not sourced figures, defined
    in one place. The most severe answer ever given wins (better < same < not sure < worse), so a later answer can never
    lower an earlier one. "Better" only closes the follow-up; it never lowers or clears the check's urgency, and it
    never closes a suspected reportable disease that has no confirmed vet handoff.
  - **Escalation**: "same", "worse", "not sure", or a death spike in the record book since the check (the same spike
    definition as the status and the briefing, for that shed only, on days after the check) escalate. The saved row
    records whether the record book showed a spike (the domain's own verdict, not the farmer's words), and the read-back
    says plainly when that means it is recorded as not better. Escalation is spoken as "To be safe, contact your vet
    or doctor." and the existing `prepare_vet_handoff` is offered as a separate step with its own "yes" (only while no
    handoff was sent for that check: there is one handoff per check, so after a handoff the escalation line is spoken
    without a second offer); this tool never sends anything. **Every not-better outcome ("worse", "same", "not sure", or a
    "better" recorded as not better) ends with that line, in the read-back and after the "yes", even after a vet handoff
    and even when a newer check of equal or higher urgency exists; "Done." alone is never spoken for it** (review
    finding H4).
  - **An unanswered urgent or reportable follow-up does not lapse (review finding M5, Step 47C).** With no answer and
    no confirmed vet handoff, once the 7-day window after the due day has passed, the follow-up of an urgent check or a
    suspected reportable disease is ESCALATED (reason code `reportable_without_vet_handoff`, the one code for "still
    needs a vet"; no new string: the existing escalation sentence with the vet line) instead of LAPSED. It stays until an
    answer closes it ("better" closes an urgent one; an unhanded reportable one stays), a vet handoff is confirmed, or a
    newer check of equal or higher urgency takes it over. The rule is `_unanswered_past_lapse` in `domain/follow_up.py`;
    the briefing, the farm status and the cards read the state it produces, and a sweep test (every urgency, every
    day) checks that they agree. A watch check keeps the 7-day lapse.
  - **The structured `safety` field (review finding M6, stage 1, Step 47C).** `get_daily_briefing` and `get_farm_status`
    carry `safety: {level: OK|WATCH|ALERT|UNKNOWN, reason_codes: [...], vet_contact_advised}` in `structuredContent` on
    every successful answer (an error result has no `structuredContent` by design). One shared helper
    (`server/tools/safety.py`) derives it only from rules that already exist, and (Step 48C) from the SAME facts for both
    tools: `facts_for` gathers the briefing facts of the farm (or of the one shed asked about) and `item_needs_safety_step`
    is the one "contact the vet" rule, so for the same farm state the briefing and the farm status agree on
    `vet_contact_advised`, `level` and `reason_codes`. The level is the card's own level word, raised to the facts' level
    when a (non-simulated) fact is higher, so it equals the card level and cannot be lower than the rules behind it. Since
    Step 48D a death spike logged on an earlier day this week (`recent_logged_spike`) is on the shed's status card too: an
    ALERT finding with the briefing's own sentence (`recent_spike_text`, no new wording), the ALERT level sentence and the
    existing vet step, so the card, the safety field and the briefing agree. The simulated sale window is a market hint:
    it is on the briefing card (watch) and never raises the status card or its safety level; the codes are the fact
    categories, health urgency and follow-up state; `vet_contact_advised` is the closing-step rule or an escalated
    follow-up. Alexa+ composes its own speech, so this exists for a host to
    surface urgency and we do not claim Alexa+ uses it. Stage 2 (not built) is the health-check and follow-up tools.
  - **An unknown house name is cleaned and shortened before it is spoken (review finding L2, Step 47C).** The error
    "I couldn't find a shed called X" says X through `spoken_name` in `domain/errors.py`: markup removed, only letters and
    digits of any script (with their combining marks), single spaces, at most 24 characters; control characters, emoji and
    punctuation become a space and invisible formatting characters are dropped. The real shed labels in the next step
    are untouched. When nothing is left (an empty or emoji-only name) the sentence is still spoken with an empty name,
    because no name-free string exists yet: a name-free "I couldn't find that shed" could replace the echo after native
    review of its Telugu.
  - **A spike logged on the day of the check** counts when the check did not already know it (review finding H2,
    approved 2026-10-03, no schema change): the check stores the latest count it saw (`latest_record_day`,
    `deaths_latest`), and the check-day record is news when the check saw no count for that day or fewer deaths than
    the record has now. A spike the check already contained, and any spike before the check day, is not news.
    **Remaining limit:** a spike logged after a same-day vet handoff is not caught by the follow-up (the handoff
    ends what came before it, and a same-day record cannot be told apart from the handoff's own day); the separate
    "N birds died yesterday" briefing item still shows it.
  - **A vet handoff ends what came before it, not what comes after it.** After a handoff for a check the follow-up shows
    as handled until something new is said or logged. A "worse", "same" or "not sure" given AFTER the handoff (or a death
    spike on a day after it) escalates again; a "better" after it is accepted and only closes. An answer at the very
    instant of the handoff counts as before it (the usual order is the answer, then the handoff it led to). A farmer
    whose check got a handoff is therefore never told "no health check is waiting" while the birds get worse.
  - **When an escalated follow-up stops showing**: only when a newer check of equal or higher urgency exists on that
    shed, or a vet handoff for that very check is confirmed and nothing worse was said since. A newer check of lower
    urgency never hides it. **The same holds for every follow-up of an urgent check or a suspected reportable disease,
    escalated or not (review finding H3, approved 2026-10-01)**: it stays visible, still as the one item carrying the
    check's warning plus the question, until "better" closes it (under the existing safety conditions), a newer check
    of equal or higher urgency exists, the vet handoff is confirmed, or (for a watch check only) the 7-day lapse; a "worse", "same" or "not
    sure" for it is always accepted. On the day of the check, before the follow-up is due, the briefing's own rule
    keeps the urgent check for the usual 3 days behind a newer lower one too (the two rules, `_superseded` and
    `_check_to_show`, change together). A watch check's follow-up is still taken over by any newer check on the shed.
  - **Surfaces** (all computed on the fast path from stored checks, answers, handoffs, the record book and the date):
    - *Daily briefing*: an escalated follow-up (even when the briefing's own check rule hid its check) or a due,
      unanswered one is one pinned item for that shed. It replaces the shed's open health-check item (never both), is never
      lower in priority than the check was (a reportable suspect 4, an urgent check 3, an escalated watch check 3), and
      the list stays at 5 items. **For an urgent check or a suspected reportable disease the one item starts with the
      check's own sentence ("your health check yesterday said: needs a vet today" / "...signs of a possible reportable
      disease") and then asks the question or says "To be safe...", and the vet closing line stays** (review finding B1:
      the question is added to the warning, never substituted for it). "Due" is a question ("How are the birds now: better, the same, or worse?"); escalated
      ends with "To be safe, contact your vet or doctor." The number of days since the check is worked out from the date,
      never typed ("1 day ago", "3 days ago").
    - *Farm status*: each shed has a `follow_up` field (state, urgency, days ago, due day, outcome, reasons, whether a
      handoff was sent, and the spoken sentence) and ONE spoken sentence when it is due, escalated or lapsed (a lapsed one
      says no answer came, never "better"). Scheduled and closed ones have the field but are not spoken. **The shed's
      level takes the briefing's own level for its health item** (urgent or reportable: ALERT; a watch check: at least
      WATCH; an escalated follow-up: ALERT; a due follow-up: at least WATCH), so the tile, the farm badge and the
      spoken line never say "doing well" while the briefing has a health item for that shed (review finding H1). A shed
      that is not OK because of an open check says why in the check's own sentence (`open_health_check` carries the
      number it speaks), and an urgent or reportable one adds the vet closing line. The briefing and the status read one
      shared per-shed health item (`health_fact`), so their levels agree.
    - *Day 0*: a new health check ends with "The next briefing, in about N days, will ask how this shed is doing." N is
      the named window for the check's urgency; nothing proactive is promised.
  - **Demo clock** (for the video's "three days later" and the golden cases): `CLUCKTALK_DEMO_DAYS_LATER=N` (0 to 30), or
    `python tasks.py serve|run --demo-days-later N`. It shifts the injected `today` and `now` of the farm source by whole
    days (`DemoClock` in `server/farm_state.py`; real time is read only in `now_ist`, a test enforces it); nothing stored
    is rewritten. **It uses a separate state file** (`Settings.demo_clock_state_path`, a sibling of the live file named
    `<live stem>_demo_clock.sqlite3`, by default `.local/clucktalk_demo_clock.sqlite3`, created fresh and marked in its `meta` table), never the live file: the live
    file is not opened while the clock is on (a test hashes it before and after), a demo-clock file is refused without
    the clock and a live file is refused with it, both with a clear error and nothing written, and `python tasks.py
    reset-demo` clears both files. `python tasks.py demo-three-days` (scripts/demo_three_days.py) builds that file for the "three days later" recording by making real MCP calls over HTTP (day 0 clock: a watch check on shed one, an urgent check on shed two; day 1 clock: the "worse" answer on shed two), refuses live mode and an existing demo-clock file, and prints the serve command at +3 and the basic-host URLs. No record is ever invented. **Honest scope: it shifts follow-up and briefing dates
    only.** The seeded farm is rebuilt for the shifted date, so flock ages, the record-book entries and the sale plan do
    not move, and the video must not present it as time passing for the flock. It is **never an MCP tool** (a test checks that no
    tool name or argument looks like it, and that sending such an argument changes nothing), is **refused in live mode**
    (`MOCK_BEDROCK` not true: a clear `ConfigError`), and is off by default (then the output is unchanged). While on,
    every tool result (errors too) carries `_meta["clucktalk/demo_clock"]` = days, "Demo clock: +N days" and its Telugu;
    the server prints `DEMO CLOCK: +N days` at startup; the cards show a badge (§14). The eval runner moves the same clock
    in process between steps (§17).
  - **Safety**: no medicine, dose, sample, lab, reassurance or rearing wording (a scan test covers every result); new
    Telugu strings are pending native review. The Simulator's rule-based intents are the only tested way of mapping
    spoken phrases (including Hinglish such as "theek hai" or "pata nahi") onto the four values; how the real Alexa+
    assistant maps them is **not verified**.

## 19. Pilot (stage 1, built 2026-10-06; not yet run on a server)

One live link that a farmer uses himself for a few days, in Telugu on his phone, and the same build later shown to
judges as a separate instance. Runbook and templates: `docs/PILOT_RUNBOOK.md` and `deploy/`. **Not Alexa+**: Alexa+ India
has no Telugu, so this is the Simulator's own phone page; output is Telugu text (no Telugu audio exists), no cards.

- **Mode** (`CLUCKTALK_MODE=pilot`, `clucktalk.config`): the farmer's own farm file instead of the demo seed
  (`clucktalk.pilot`: house number, birds placed, placement date; unknown fields such as names or places are refused),
  **no synthetic history at all** (`PilotFarmSource`; logged records are added, `overlay_adds_days`), `demo_data` false so no
  answer says "Demo data", badge "Pilot (real farm, prototype)". The demo is unchanged. The two instances can never share a
  state file: a pilot needs its own `.sqlite3` whose name contains the instance name and which is outside the demo's
  folder; a demo refuses a state file with "pilot" in its name; a pilot reads weather and rule files only from explicit paths.
- **No bird weights in the pilot** (the weight target is a breed curve that does not describe his birds): `log_daily_record`
  refuses a weight with the existing "no verified growth standard" wording (said about "your birds"), nothing is proposed or
  stored. His houses have no breed, so feed and sale plans say there is no growth standard for them.
- **His own daily deaths rule** (`daily_deaths_rule.json`, `clucktalk.domain.daily_deaths`): deaths that day divided by the
  live birds at the start of the day, times 1000, **strictly greater** than his number (exact decimal arithmetic) adds a WATCH
  fact. It can only raise a shed to WATCH (`max(existing, WATCH)`); it never lowers a level or removes vet advice (a property
  test); his note comes last, after all health and safety text. No file: byte-identical output. The file is re-read when it
  changes; if it becomes unreadable the answer says so. His value (2 per 1000) was relayed, not confirmed in writing.
- **Telugu input** (`simulator/intents_te.py`, vocabulary in `telugu_words.json`): typed Telugu (his keyboard's voice typing
  speaks; no browser speech change), NFC, Telugu digits and number words (0 to 20, tens, 100, 1000, compounds), 8 actions;
  a number it cannot read is never guessed; a health check is chips only. The English normaliser no longer shreds Telugu.
- **Every write is read back first**: the server's proposal flow, or the host's own read-back for starting a health check;
  a tap on the big yes or no button, or a typed yes, answers it; a stray yes with nothing waiting does nothing. One
  conversation per browser session (the old global pending state is gone); chips send an id and numbers, never a sentence.
- **Hardening** (`simulator/app.py`, `Hardening`): a bearer token on every API call (constant-time compare against every
  configured token), exact hostname and https origin, an 8 KB body cap, a per-token rate limit (wrong tokens limited too), a
  session cap, a kill switch file or variable checked at each request, `/healthz`, logs without words, and anonymous
  counters (`clucktalk.usage`; `python tasks.py pilot-stats --usage FILE`).
- **Not done / not verified**: no cloud account was touched; the page was not run in a real phone browser; speech accuracy in a
  shed is untested; the Telugu is a draft pending native review (every line is pending in `docs/TELUGU_REVIEW.md`).

### 19.1 Review fixes (Step 52, after an independent review of 0bd9905)

- **Same-day deaths are never silently added or replaced.** The farmer counts once each morning and the count belongs to
  *today's* date (Asia/Kolkata), so a second number for a house that already has deaths for that day is most likely a
  correction. On the pilot farm the read-back shows the old and the new number and asks add (the total is shown) or replace
  (the old value that goes is shown); `log_daily_record` has a new optional `deaths_choice` ("add" or "replace") and the
  answer carries `choice` (existing, new, total if added) only for that question. A plain yes does not answer it (the same
  question stays open); a total above the birds is refused by the existing check. The first log of a day, other days, and the
  demo are unchanged. A shed with no alert is described as "no alert from the checks I can make", never "doing well".
- **Pilot access**: the MCP server refuses to start in pilot mode without a strong token (and the farmer's token must differ);
  a new session makes room by dropping the least recently used one (never a 503) and the page keeps one device id in
  `localStorage`; the card routes and the English demo page are not served on a pilot host; every pilot answer carries a
  Content-Security-Policy (`default-src 'self'; frame-ancestors 'none'`), `Referrer-Policy: no-referrer` and `nosniff`; `/healthz`
  says only ok (200) or not ok (503); an unreachable MCP server is not described with its address to the client.
- **Telugu matcher**: a polite word after yes, no, add or replace is accepted; "no deaths" only when the negation follows the
  death word and there is no number, otherwise it is asked again; any minus sign makes the input not understood.
- **First open**: one screen with seven items (test and not a veterinary service; for a sick bird call his vet; an alert is a
  reminder, not a diagnosis; the targets are general numbers; voice typing goes to the keyboard's speech service; what is stored and who
  can read it; deletion at any time), acknowledged with one big button before anything works, remembered per device and asked
  again when the wording changes. A page without a token shows "Open your original link". The page's logic is tested in Node
  against a hand-made DOM (`tests/harness/pilot_page_checks.js`); it is not a browser test.
- **Data**: `deaths_before_pilot` per house (0 up to the birds placed) is used for live birds, the room for new deaths and
  cumulative mortality; an impossible value stops the start.
- **Operations**: the backup script writes a stamp only after an integrity-checked copy, `pilot-stats --backups DIR` shows the
  age and warns after 26 hours; the runbook creates the backup folder, moves stale journal files aside on restore, lists every copy to
  delete, and spells out token rotation; the units add ProtectProc, ProcSubset, PrivateUsers, RestrictSUIDSGID, LockPersonality and
  more. `MemoryDenyWriteExecute` and `SystemCallFilter` were skipped on purpose (they can stop a Python service starting).
