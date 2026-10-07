# Submission text (draft)

Written for the Devpost fields, in the order of the form. Every claim points to a file or a command. Where something is not done or not known, it says **pending** or **not recorded**. Nothing here has run on an Alexa+ device. Counts and timings are generated in `docs/RESULTS.md`; the one count repeated here, the Telugu review sentence, is checked against `docs/TELUGU_REVIEW.md` by a test.

## Project name

CluckTalk (కోడి మిత్ర)

## Tagline options (60 characters or fewer)

1. A voice farm manager for broiler farmers, built on MCP
2. Poultry records by voice, read back and saved on a yes
3. Telugu and English farm help, safety decided in code

## Opening sentence

CluckTalk is a self-hosted MCP server (Streamable HTTP, spec 2025-11-25) for Alexa+, with a simulated Alexa+ web experience, that is built to help Indian broiler farmers keep their daily records and see which shed needs attention first.

## Inspiration

A broiler farmer counts the dead birds each morning with busy hands, often with no screen in reach. The numbers that matter, a sudden spike, the total losses so far and the moment to call the vet, are easy to miss on a busy morning, and most farm tools expect typing in English. CluckTalk is an attempt at something a farmer can tell in their own language, that reads every number back before saving it, and that never pretends to be a vet.

## What it does

- **Farm status and the daily briefing** (`get_farm_status`, `get_daily_briefing`): per shed, what needs attention first, health items always ahead of the rest, decided by code. A death spike from earlier in the week still shows.
- **A voice record book** (`log_daily_record`, `get_record_book`): the farmer says deaths, feed, a weight sample or a treatment name; it is read back and saved only after an explicit yes. No medicine advice and no doses. In the pilot, a second number for the same day asks "add or replace" and never assumes.
- **Health triage and a vet handoff** (`start_health_check`, `get_health_check`, `prepare_vet_handoff`): guidance, never a diagnosis. Code sets the minimum urgency from the signs and the record book; a model can raise it and never lower it. A suspected reportable disease gets the fixed steps (isolate, stop bird movement, report). The vet message is a **simulated SMS**.
- **Follow-up** (`report_health_follow_up`): days after a flagged check, the next briefing asks how the shed is now. Anything other than "better" ends with "To be safe, contact your vet or doctor."
- **Feed and sale plans** (`plan_feed`, `plan_sale`): feed per shed; the best day to sell, with the price **simulated**. Not available for pilot houses, which have no cited growth curve.
- **Farm profile and contract terms** (`get_farm_profile`, `set_farm_mode`, `set_contract_terms`) and **help** (`get_help`).
- **The farmer's own rules.** An optional file holds a daily-deaths number and an outdoor-temperature reminder. They are the farmer's, written into the file by the builder from what the farmer said; entering them in the app is a roadmap item. Both only add reminders, and neither can lower an alert.
- **A Telugu phone page for a farmer pilot** (typed or voice-typed Telugu, big yes and no buttons). A prototype, not Alexa+, not a veterinary service.

The safety rules, where each came from and which tests pin it: `docs/SAFETY_MATRIX.md`.

## How it uses the track technology

- **The MCP server.** `src/clucktalk/server/app.py` builds the server with the official `mcp` Python SDK (2.2.0) and serves it over Streamable HTTP at `/mcp`; it implements MCP 2025-11-25 and also negotiates three older versions. Conformance tests: `tests/contract/test_protocol_conformance.py`.
- **The 14 tools:** `get_farm_status`, `plan_feed`, `plan_sale`, `get_daily_briefing`, `start_health_check`, `get_health_check`, `prepare_vet_handoff`, `report_health_follow_up`, `log_daily_record`, `get_record_book`, `get_farm_profile`, `set_farm_mode`, `set_contract_terms`, `get_help`. Each returns `text_en`, `text_te` and a structured result, plus `_meta.ui.resourceUri` when a card exists. Four MCP Apps cards are built (`src/clucktalk/server/cards/`).
- **The simulated Alexa+ experience.** `src/clucktalk/simulator/` is a local web app that plays the Alexa+ client role: Echo Show and Echo Dot modes, voice and text, and a panel that shows the exact MCP wire. It is not Amazon's tool and no Alexa+ device is involved.
- **How a call flows.** The farmer's words reach the Simulator's rule-based intent layer, which picks a tool (`src/clucktalk/simulator/intents.py`). A raw JSON-RPC `tools/call` goes to `/mcp` (`src/clucktalk/simulator/mcp_client.py`). The tool validates the input, reads precomputed state (no model call inside a tool) and returns the result. A change is proposed first: the result is a read-back with `status: needs_confirmation` and a `proposal_id`; only the same tool called again with that id and `answer: "yes"` applies it. The design is in `docs/DESIGN.md` (sections 3, 5 and 5.1) and `docs/ARCHITECTURE.md`.
- **Our own checks of the documented flow:** `python tasks.py inspector-replay` replays the flow documented on Amazon's Local Inspector page against a temporary server; `python tasks.py readiness` checks the requirements that can be checked locally. Both are ours, not Amazon's; the Local Inspector itself was not run (FL-024).
- **An Agent Skill** for operating the server from a coding agent: `skills/clucktalk/`.

## How we built it

- **Built with Claude Code**, in sessions over the build dates in `docs/RESULTS.md` (section 8). Which model version each session used is not recorded. Every feature followed the same loop: tests first, one command that runs lint, format, tests, an OpenSearch-Serverless check and a secret scan (`python tasks.py check`), golden evals, and a review by a fresh agent that read the code cold (`docs/INDEPENDENT_REVIEW.md`). From Step 48 on, each feature also got a mutation check.
- **AWS pieces actually used, live:** Amazon Bedrock Runtime `converse` with **Amazon Nova 2 Lite** in us-east-1, a handful of one-off calls from the AWS CLI and boto3 (a hello call, then two forced-tool-choice spike calls on text and a tiny synthetic image; the second one misread a colour, FL-020). They are listed in `docs/AWS_SETUP.md` sections 5.2 and 5.3, and their cost there is under two tenths of a cent at third-party prices that were not confirmed on AWS's own price page. Also used: AWS Service Quotas and AWS Support cases, because the new account's Bedrock inference quotas were all 0 (FL-014), and an IAM Identity Center role for the CLI (FL-015).
- **Mocked:** every AI answer in the demo, in the golden evals and in the tests (`MOCK_BEDROCK=true`, shown by a "Demo data" badge). The server's live-AI path (the triage and briefing agents on a live model) was **not** verified end to end here. Nothing was deployed to AWS; no Lambda, no Polly, no Knowledge Base. OpenSearch Serverless is never used, and a script checks that (`scripts/check_no_aoss.py`).
- **Other tools:** Python 3.13, SQLite, the `mcp` SDK, Starlette and uvicorn, Hypothesis, pytest, ruff, GitHub Actions. Versions: `docs/VERSIONS.md`; licenses: `NOTICE`.

## How we trust it

- **A safety matrix**, one row per rule with its source, code location, tests and a before and after example, and a plain mark for thresholds that are only general guidance: `docs/SAFETY_MATRIX.md`.
- **Generated results** (test counts, golden evals, mutation checks, protocol conformance, latency, readiness), and saved outputs of the self-check commands with their date and commit: `docs/RESULTS.md`, `docs/proof/`.
- **Independent reviews** by fresh agents after each main feature, and what they found and how it was fixed: `docs/INDEPENDENT_REVIEW.md`. They are not human audits (`SECURITY.md`).
- **A claims table** that marks each claim verified, simulated, unverified or not built, with the file or command that shows it: the README, section "What is verified, unverified and simulated".
- **What it does not show:** no veterinary or agronomic review of the thresholds, no Alexa+ device, and latency numbers that are server times on localhost in mock mode (Amazon's 500 ms is a round trip, so we do not claim to meet it end to end). Telugu: 86 of 433 strings reviewed by the builder, a native Telugu speaker; 347 pending (including the pilot page); no independent review.

## The farmer pilot

A pilot link was shared with one farmer on 7 October 2026; usage numbers are pending [PILOT NUMBERS: to be filled on <date> from python tasks.py pilot-stats].

Honest limits. The pilot is hosted on the builder's own Windows PC, published through a free tunnel; availability depends on that PC and its internet. The farmer's rules (a daily-deaths number) are the farmer's, written into the file by the builder from what the farmer said, and not yet confirmed in writing; entering them in the app is a roadmap item. Telugu: 86 of 433 strings reviewed by the builder, a native Telugu speaker; 347 pending (including the pilot page); no independent review. Nothing about uptime, speed or reliability has been measured. The plan: `docs/PILOT_RUNBOOK_WINDOWS.md`; the architecture and its limits: `docs/ARCHITECTURE.md`.

## Challenges

All are entries in `FRICTION_LOG.md` (the rest of our own tooling notes are in `docs/DEV_NOTES.md`).

- **No usable Bedrock quota on a new account.** Models reported AVAILABLE while every inference quota was 0, then a Marketplace agreement and an "account verification" gate blocked the first call, from 28 to 29 September (FL-014, FL-018).
- **No self-serve path to Amazon's validation tool.** The Alexa AI CLI and Local Inspector need a prerequisite we could not get, so we built a replay of the documented flow and a readiness checklist and said plainly that they are ours (FL-024).
- **Gaps in the Alexa+ docs.** No MCP App card size, supported messages, CSP or fonts (FL-009); no statement of which protocol version Alexa+ sends (FL-026); no word on proactive notifications (FL-017).
- **SDK surprises.** A request id used twice on one session is silently never answered (FL-011); the SDK drops the Apps extension from `initialize` on 2025-11-25 (FL-008); the Apps default CSP blocks even an inlined font (FL-007).
- **Our own tooling.** A card bundle that built differently on Windows and in CI because of line endings, and a local check that could not see it (FL-025); a shell tool that rewrote backslashes inside commands (FL-022).
- **Saying the safe thing.** Triage language that is never a diagnosis, never a dose, and that cannot be talked down by a model or by odd words (`docs/SAFETY_MATRIX.md`).

## What changed during the hackathon

The first commit is dated 2026-09-27 (`git log --reverse`). The commit counts per day are generated in `docs/RESULTS.md`, section 8. In order, from the history:

- **27 to 29 September:** the build harness and project rules; the domain layer with cited reference data and a fictional demo farm; the MCP server skeleton; `get_farm_status` and `plan_feed`; the Telugu glossary and the builder's own review, as a native Telugu speaker, of the Telugu strings that existed then (later strings are pending); the first card and the Simulator; the state store and the one confirmation pattern; `plan_sale`; the voice record book; the first live Bedrock call; the health triage agent.
- **30 September to 1 October:** the daily briefing; fixes from independent reviews; a CI workflow; the follow-up agent and the demo clock; the Agent Skill; a rewrite of the friction log.
- **3 to 4 October:** the structured safety field; protocol-conformance, property, fuzz and concurrency tests; `reset-demo`, `NOTICE`, `inspector-replay`, `readiness` and `verify`; weather reminders.
- **6 to 7 October:** the pilot mode, the farmer's own deaths rule, the Telugu page, hardening, the add-or-replace question, fixes from a review of the pilot, the Windows launcher and runbook, and this documentation set.

## Built with

Python 3.13, the MCP Python SDK (`mcp` 2.2.0), Model Context Protocol 2025-11-25 over Streamable HTTP, MCP Apps cards (vanilla HTML and JavaScript), Starlette, uvicorn, SQLite, Pydantic, Amazon Bedrock (Amazon Nova 2 Lite, a few live calls), the AWS CLI and boto3, Open-Meteo (optional, off by default), Noto Sans Telugu, Hypothesis, pytest, ruff, GitHub Actions, Claude Code. For the pilot: a free Tailscale Funnel.

## Amazon requirements

| Requirement | Status | Evidence |
|---|---|---|
| An MCP server or a simulated Alexa+ experience, with the simulation source in the repository and a demo that shows it working | **Done for the server and the simulation**; the demo video is **pending** | Server: `src/clucktalk/server/`. Simulation source: `src/clucktalk/simulator/`. Demo: `python tasks.py run` and `python tasks.py verify`; `docs/proof/`; `docs/evidence/2026-09-27_card_and_simulator.md` |
| The repository calls the track technology in code | **Done** | `src/clucktalk/server/app.py` (the MCP server over Streamable HTTP); `src/clucktalk/simulator/mcp_client.py` (the client side); `tests/contract/test_protocol_conformance.py` |
| A video under 3 minutes, public, in English | **Pending** | [VIDEO URL: pending; must be public, in English and under 3 minutes] |
| Product feedback per tool | **Partly done** | `docs/PRODUCT_FEEDBACK.md` is a skeleton: what we used and what needs work come from the friction log; the answers about what worked, onboarding and "would you build with it again" are marked TODO. `FRICTION_LOG.md`, `FEATURE_REQUESTS.md` |
| An open-source license | **Done** | `LICENSE` (MIT); `NOTICE` lists the dependencies' licenses |
| AWS Builder mini challenge: the server's live Bedrock path | **Pending** | Evidence of the server's live Bedrock path: pending; the entry will be withdrawn if it is not obtained by 11 October. Today there are only a handful of one-off calls outside the server (`docs/AWS_SETUP.md`, sections 5.2 and 5.3) |
| AWS Builder and Open Source mini challenge: the contribution | **Pending** | [CONTRIBUTION URL: pending] |
| AWS Builder and Open Source mini challenge: the second repository | **Pending** | [SECOND REPOSITORY URL: pending] |
| Running on an Alexa+ device, or passing Amazon's review | **Not done** | Not claimed anywhere; `docs/ALEXA_READINESS.md` lists what cannot be checked locally |
