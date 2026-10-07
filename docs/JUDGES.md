# A one-page guide for judges

CluckTalk (కోడి మిత్ర) is a self-hosted **MCP server** (Streamable HTTP, spec 2025-11-25) for Alexa+, with a simulated Alexa+ web experience, for Indian broiler farmers. It tracks a shed's deaths, feed and health checks, and tells the farmer in English and Telugu what needs attention first. Nothing here has run on an Alexa+ device; the Simulator plays the client role.

## Run it: three commands, no AWS account, no Docker

Windows (cmd; on Linux or macOS use `python3`). Python 3.12 or 3.13.

```
python tasks.py setup     :: creates .venv, installs the pinned dependencies
python tasks.py verify    :: one table of what you can check, about 30 seconds (it starts its own temporary server)
python tasks.py serve     :: the MCP server at http://127.0.0.1:8765/mcp with a fictional demo farm (leave it running)
```

`verify` starts its own temporary server, so it does not need `serve`. `serve` is needed only to call the tools yourself (minute 2). For the Simulator in a browser (Echo Show and Echo Dot modes, cards, a panel showing the exact MCP calls), run `python tasks.py run` instead of `serve`; it opens http://127.0.0.1:8766/. Everything runs on seeded, fictional data in mock mode and shows a "Demo data" badge.

## Five minutes, in this order

1. **Minute 1: run `verify`** and read the table. Then open `docs/RESULTS.md` (test counts, the golden evals, mutation checks, protocol conformance, latency, readiness, the independent reviews). The table and most of that page are generated from this machine's own runs; the mutation checks and the reviews are copied by hand from the builder's log, and the page says so.
2. **Minute 2: see the tool calls.** With `serve` running, `npx @modelcontextprotocol/inspector@2.8.0 --cli http://127.0.0.1:8765/mcp --method tools/list` lists the 14 tools. Or `python tasks.py inspector-replay` replays the flow Amazon documents for its Local Inspector against a temporary copy of the server (our replay; the Local Inspector itself was not run).
3. **Minute 3: ask the Simulator** "How is shed two doing?" Then say "5 birds died in shed 1". It reads the number back and saves nothing until you say yes.
4. **Minute 4: the safety rules.** `docs/SAFETY_MATRIX.md` has one row per rule: where it came from, where it is in the code, which tests pin it, a before and after example, and which thresholds are general guidance that may not fit a given farm.
5. **Minute 5: the limits.** The claims table in the README (section "What is verified, unverified and simulated") says for each claim whether it is verified, simulated, unverified or not built, with the file or command that shows it.

## Where things are

| What | Where |
|---|---|
| The 14 MCP tools | `src/clucktalk/server/tools/` (one file per feature; registered in `src/clucktalk/server/app.py`) |
| The Alexa+ Simulator (simulation source) | `src/clucktalk/simulator/` (the page is in `src/clucktalk/simulator/static/`) |
| Safety rules in code | `src/clucktalk/domain/` (`status.py`, `triage.py`, `follow_up.py`, `thresholds.py`) |
| Golden evals | `data/eval/golden_cases.json`, results in `docs/EVALS.md` |
| The architecture | `docs/ARCHITECTURE.md`; the full design is `docs/DESIGN.md` |
| What the pilot is | `docs/PILOT_RUNBOOK_WINDOWS.md` (a link was shared with one farmer on 7 October 2026; usage numbers pending) |
| Friction with the platforms we used | `FRICTION_LOG.md`, `FEATURE_REQUESTS.md`, `docs/PRODUCT_FEEDBACK.md` |
| Security notes | `SECURITY.md` |
| The Agent Skill | `skills/clucktalk/` |

## Known limits, in plain words

- **Not on an Alexa+ device.** No Alexa+ device, Alexa speech or Amazon review was involved. Alexa composes its own speech, so what it says can differ from our sentences.
- **Not built:** OAuth 2.1 with PKCE, Protected Resource Metadata, a remote HTTPS URL for the Alexa+ add-on, security and data policies (`docs/ALEXA_READINESS.md`, `docs/PRODUCTION_PATH.md`).
- **Latency numbers** are server times on localhost in mock mode. Amazon's 500 ms is a round trip including the network, so we do not claim to meet it end to end.
- **Simulated:** prices, sensors, the supplier, SMS and payments, and the whole demo farm.
- **No veterinary or agronomic review.** The thresholds are general guidance or the builder's heuristics (`docs/SAFETY_MATRIX.md`). No tool gives a medicine or a dose.
- **Telugu:** 86 of 433 strings reviewed by the builder, a native Telugu speaker; 347 pending (including the pilot page); no independent review. No Telugu voice was tested through Alexa+ (`docs/TELUGU_REVIEW.md`).
- **In demo mode a shed with no alert is still described as doing well;** pilot mode says "no alert from the checks I can make".
- **Live AI** (Amazon Bedrock Nova 2 Lite) is off by default; the server's live path was not verified end to end here.
- **The farmer pilot** is hosted on the builder's own PC through a free tunnel. A pilot link was shared with one farmer on 7 October 2026; usage numbers are pending (`docs/RESULTS.md`, section 9).
