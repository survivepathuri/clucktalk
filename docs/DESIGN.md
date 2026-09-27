# CluckTalk design

The engineering design behind CluckTalk. Code comments cite this file as `docs/DESIGN.md §N`.
**Status**: this document describes the target design. What actually works, with evidence, is recorded in the README and the eval table; nothing here claims a feature is finished.

## 1. Product
CluckTalk (Telugu subtitle "కోడి మిత్ర") is an Alexa+ add-on for small and medium Indian poultry farms (broiler and layer, 500–20,000 birds): a self-hosted MCP server plus an Agent Skill.
The farmer speaks English or Hinglish, often with busy hands. CluckTalk answers by voice (complete on a screenless device) and shows bilingual Telugu + English cards (MCP Apps) on screen devices.

Planned tool intents (one intent per tool, see §5): farm status per house, health triage (async), vet handoff, feed planning, profit forecast, sell-now-or-wait, farm memory, daily briefing, feed orders with confirmation, and "what can you do?".

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
4. Always return something. Errors are structured (`isError: true`) with a customer-safe message and one next step. Never speak codes, tool names, JSON, or IDs.
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
| Cross-modal | Spoken numbers equal card numbers; no stale card | Automated diff of `text_en` vs `structuredContent` |
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

## 8. Language
- Voice in/out: English and Hinglish. Cards: Telugu + English.
- Fixed strings are pre-translated and reviewed by a native Telugu speaker; the card bundle ships Noto Sans Telugu.
- Farmer vocabulary is first class (§5 rule 6).

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
