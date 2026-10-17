# Submission text (draft)

Written for the Devpost fields, in the order of the form. Every claim points to a file or a command. Where something is not done or not known, it says **pending** or **not recorded**. Nothing here has run on an Alexa+ device. Counts and timings are generated in `docs/RESULTS.md`; the one count repeated here, the Telugu review sentence, is checked against `docs/TELUGU_REVIEW.md` by a test.

## Project name

CluckTalk (కోడి మిత్ర; Kodi Mitra, 'Chicken Friend')

## Tagline options (60 characters or fewer)

Locked tagline, the only one to use: **Telugu-first MCP assistant for broiler farmers** (45 characters).

## Opening sentence

CluckTalk is a self-hosted MCP server (spec 2025-11-25, Streamable HTTP), shown through a simulated Alexa+ web app and the MCP Inspector. It is built to help Indian broiler farmers keep their daily records and see which shed needs attention first, through a simulated Alexa+ web experience.

## Inspiration

India has a very large number of broiler farmers, and many of them run their sheds from memory, a notebook or a phone gallery. The numbers they need every day are scattered: how many birds died today, how old each shed is, how much feed is left, when to sell. When a farmer has several sheds, a small problem in one of them is easy to miss until it becomes an expensive one.

I have worked on broiler farms before, so I have seen this up close.

I built CluckTalk to put every shed in one place and make it easy to ask about. A farmer asks in Telugu, and the answer comes from his own records and his own declared schedule, not from a generic guess. The goal is fewer surprises, less guesswork on sale day, and more transparency in a business that runs on trust and memory.

I built it with input from a real broiler farmer. His feedback was clear: he wants to ask by speaking and to hear the answer back in Telugu. Today CluckTalk answers in written Telugu; the Simulator has a microphone button for English questions and reads English answers aloud when Sound is on. Asking by speaking in Telugu and hearing spoken Telugu replies are the next steps on the roadmap.

## What it does

- **Farm status and the daily briefing** (`get_farm_status`, `get_daily_briefing`): per shed, what needs attention first, health items always ahead of the rest, decided by code. A death spike from earlier in the week still shows.
- **A record book** (`log_daily_record`, `get_record_book`): the farmer gives deaths, feed, a weight sample or a treatment name; it is read back and saved only after an explicit yes. No medicine advice and no doses. In the pilot, a second number for the same day asks "add or replace" and never assumes.
- **Health triage and a vet handoff** (`start_health_check`, `get_health_check`, `prepare_vet_handoff`): guidance, never a diagnosis. Code sets the minimum urgency from the signs and the record book; a model can raise it and never lower it. A suspected reportable disease gets the fixed steps (isolate, stop bird movement, report). The vet message is a **simulated SMS**.
- **Follow-up** (`report_health_follow_up`): days after a flagged check, the next briefing asks how the shed is now. Anything other than "better" ends with "To be safe, contact your vet or doctor."
- **Feed and sale plans** (`plan_feed`, `plan_sale`): feed per shed; the best day to sell, with the price **simulated**. Not available for pilot houses, which have no cited growth curve.
- **Farm profile and contract terms** (`get_farm_profile`, `set_farm_mode`, `set_contract_terms`) and **help** (`get_help`).
- **The farmer's own rules.** An optional file holds a daily-deaths number and an outdoor-temperature reminder. They are the farmer's, written into the file by the builder from what the farmer said; entering them in the app is a roadmap item. Both only add reminders, and neither can lower an alert.
- **A Telugu phone page for a farmer pilot** (Telugu text, big yes and no buttons; there is no Telugu speech recognition and no spoken reply yet). A prototype, not Alexa+, not a veterinary service.

The safety rules, where each came from and which tests pin it: `docs/SAFETY_MATRIX.md`.

## How it uses the track technology

- **The MCP server.** `src/clucktalk/server/app.py` builds the server with the official `mcp` Python SDK (2.2.0) and serves it over Streamable HTTP at `/mcp`; it implements MCP 2025-11-25 and also negotiates three older versions. Conformance tests: `tests/contract/test_protocol_conformance.py`.
- **The 14 tools:** `get_farm_status`, `plan_feed`, `plan_sale`, `get_daily_briefing`, `start_health_check`, `get_health_check`, `prepare_vet_handoff`, `report_health_follow_up`, `log_daily_record`, `get_record_book`, `get_farm_profile`, `set_farm_mode`, `set_contract_terms`, `get_help`. Each returns `text_en`, `text_te` and a structured result, plus `_meta.ui.resourceUri` when a card exists. Four MCP Apps cards are built (`src/clucktalk/server/cards/`).
- **The simulated Alexa+ experience.** `src/clucktalk/simulator/` is a web app: browser UI plus a backend MCP client that sends initialize (protocolVersion 2025-11-25), tools/list and tools/call to the MCP server over Streamable HTTP. It plays the Alexa+ client role: Echo Show and Echo Dot modes, voice and text, and a panel that shows the exact MCP wire. The browser page only calls the Simulator's own backend; the backend is the MCP client (README, "How the Simulator speaks MCP", with file and line references and a captured exchange). It is not Amazon's tool and no Alexa+ device is involved.
- **How a call flows.** The farmer's words reach the Simulator's rule-based intent layer, which picks a tool (`src/clucktalk/simulator/intents.py`). A raw JSON-RPC `tools/call` goes to `/mcp` (`src/clucktalk/simulator/mcp_client.py`). The tool validates the input, reads stored state and never waits for a model (two tools, `start_health_check` and `get_daily_briefing`, hand a job to a background worker that can call the model when live AI is chosen; the tool answers from stored state) and returns the result. A change is proposed first: the result is a read-back with `status: needs_confirmation` and a `proposal_id`; only the same tool called again with that id and `answer: "yes"` applies it. The design is in `docs/DESIGN.md` (sections 3, 5 and 5.1) and `docs/ARCHITECTURE.md`.
- **Our own checks of the documented flow:** `python tasks.py inspector-replay` replays the flow documented on Amazon's Local Inspector page against a temporary server; `python tasks.py readiness` checks the requirements that can be checked locally. Both are ours, not Amazon's; the Local Inspector itself was not run (FL-024).
- **An Agent Skill** for operating the server from a coding agent: `skills/clucktalk/`.

## How we built it

- **Built with Claude Code**, in sessions over the build dates in `docs/RESULTS.md` (section 8). Which model version each session used is not recorded. Every feature followed the same loop: tests first, one command that runs lint, format, tests, an OpenSearch-Serverless check and a secret scan (`python tasks.py check`), golden evals, and a review by a fresh agent that read the code cold (`docs/INDEPENDENT_REVIEW.md`). From Step 48 on, each feature also got a mutation check.
- **AWS pieces actually used, live:** Amazon Bedrock Runtime `converse` with **Amazon Nova 2 Lite** in us-east-1, a handful of one-off calls from the AWS CLI and boto3 (four live calls on 2026-09-29: a hello call run twice, then two forced-tool-choice spike calls on text and a tiny synthetic image; the second one misread a colour, FL-020). They are listed in `docs/AWS_SETUP.md` sections 5.2 and 5.3, and their cost there is under two tenths of a cent at third-party prices that were not confirmed on AWS's own price page. Also used: AWS Service Quotas and AWS Support cases, because the new account's Bedrock inference quotas were all 0 (FL-014), and an IAM Identity Center role for the CLI (FL-015).
- **Mocked:** every AI answer in the demo, in the golden evals and in the tests (`MOCK_BEDROCK=true`, shown by a "Demo data" badge). The server's live-AI path (the triage and briefing agents on a live model) was **not** verified end to end here. Only the Lightsail cloud pilot was deployed to AWS (since 13 October 2026, with the sample farm file and the rule-based test model, no Bedrock calls); no Lambda, no Polly, no Knowledge Base. OpenSearch Serverless is never used, and a script checks that (`scripts/check_no_aoss.py`). That sentence is about the pilot host only. **Amazon Nova 2 Lite through the Bedrock Converse API is a real integration in the code** (`src/clucktalk/agents/bedrock.py`): it is the live engine for the health-triage and daily-briefing agents, which ask it only closed-list questions, and code sets the minimum urgency so the model can raise it and never lower it. It is covered by tests with a botocore Stubber and was exercised in the one-off calls of 2026-09-29, but it has not been run end to end through the server (four attempts through the server on 2026-10-17 were all throttled: every Nova 2 Lite quota on the newer AWS account is 0, FL-031), and the demo and the Lightsail pilot do not use it (they use a rule-based stand-in labelled "AI: off"; pilot mode forces `MOCK_BEDROCK=true`).
- **Other tools:** Python 3.13, SQLite, the `mcp` SDK, Starlette and uvicorn, Hypothesis, pytest, ruff, GitHub Actions. Versions: `docs/VERSIONS.md`; licenses: `NOTICE`.

## How we trust it

- **A safety matrix**, one row per rule with its source, code location, tests and a before and after example, and a plain mark for thresholds that are only general guidance: `docs/SAFETY_MATRIX.md`.
- **How long a judge's run takes:** In one clean-clone run on Windows 11 with Python 3.13, made by an independent audit run in a fresh context (same vendor model, not a third party), setup took 1 min 16 s and verify took 45 s. (the audit log is not in the repository; the machine and the run belong to that audit.)
- **Generated results** (test counts, golden evals, mutation checks, protocol conformance, latency, readiness), and saved outputs of the self-check commands with their date and commit: `docs/RESULTS.md`, `docs/proof/`.
- **Independent reviews** by fresh agents after each main feature, and what they found and how it was fixed: `docs/INDEPENDENT_REVIEW.md`. They are not human audits (`SECURITY.md`).
- **A claims table** that marks each claim verified, simulated, unverified or not built, with the file or command that shows it: the README, section "What is verified, unverified and simulated".
- **What it does not show:** no veterinary or agronomic review of the thresholds, no Alexa+ device, and latency numbers that are server times on localhost in mock mode (Amazon's 500 ms is a round trip, so we do not claim to meet it end to end). Telugu: 470 of 476 strings reviewed by the builder, a native Telugu speaker (single reviewer, not independent); 6 pending; the farmer-preferred wording for follow-up is still to be confirmed. On 2026-10-16 I personally read the 390 strings that were still pending and found them correct (single-reviewer self-review as a native Telugu speaker); I approved 384 and kept 6 follow-up strings pending until the farmer confirms his word. The counts: 470 approved + 6 pending = 476 strings, counted wherever they appear in the code (86 approved on 2026-09-27, 384 on 2026-10-16); the approvals file `data/i18n/telugu_approvals.json` holds 433 entries (80 + 353) because a repeated English+Telugu pair shares one approval.

## The farmer pilot

No farmer has used the pilot yet. The cloud pilot has been deployed since 13 October 2026 on one AWS Lightsail server in Mumbai (`docs/CLOUD_PILOT.md`), with the sample farm file; the real farm is not switched in. No pilot usage numbers recorded yet.

Honest limits. The AI on the pilot server is the rule-based stand-in (no Bedrock calls). The PC pilot through a free tunnel (`docs/PILOT_RUNBOOK_WINDOWS.md`) stays as a fallback, and its availability would depend on that PC and its internet. The farmer's rules (a daily-deaths number) are the farmer's, written into the file by the builder from what the farmer said, and not yet confirmed in writing; entering them in the app is a roadmap item. Telugu: 470 of 476 strings reviewed by the builder, a native Telugu speaker (single reviewer, not independent); 6 pending; the farmer-preferred wording for follow-up is still to be confirmed. Nothing about uptime, speed or reliability has been measured. The plan: `docs/PILOT_RUNBOOK_WINDOWS.md`; the architecture and its limits: `docs/ARCHITECTURE.md`.

## Challenges

All are entries in `FRICTION_LOG.md` (the rest of our own tooling notes are in `docs/DEV_NOTES.md`).

- **No usable Bedrock quota on a new account.** Models reported AVAILABLE while every inference quota was 0, then a Marketplace agreement and an "account verification" gate blocked the first call, from 28 to 29 September (FL-014, FL-018).
- **Zero Nova quotas on the newer account.** On the account opened after access to the first was lost, every Nova 2 Lite requests-per-minute and tokens-per-day quota was 0, so the four calls through the server on 2026-10-17 were all throttled (FL-031).
- **No self-serve path to Amazon's validation tool.** The Alexa AI CLI and Local Inspector need a prerequisite we could not get, so we built a replay of the documented flow and a readiness checklist and said plainly that they are ours (FL-024).
- **Gaps in the Alexa+ docs.** No MCP App card size, supported messages, CSP or fonts (FL-009); no statement of which protocol version Alexa+ sends (FL-026); no word on proactive notifications (FL-017).
- **SDK surprises.** A request id used twice on one session is silently never answered (FL-011); the SDK drops the Apps extension from `initialize` on 2025-11-25 (FL-008); the Apps default CSP blocks even an inlined font (FL-007).
- **Our own tooling.** A card bundle that built differently on Windows and in CI because of line endings, and a local check that could not see it (FL-025); a shell tool that rewrote backslashes inside commands (FL-022).
- **Saying the safe thing.** Triage language that is never a diagnosis, never a dose, and that cannot be talked down by a model or by odd words (`docs/SAFETY_MATRIX.md`).

## What changed during the hackathon

The first commit is dated 2026-09-27 (`git log --reverse`). The commit counts per day are generated in `docs/RESULTS.md`, section 8. In order, from the history:

- **27 to 29 September:** the build harness and project rules; the domain layer with cited reference data and a fictional demo farm; the MCP server skeleton; `get_farm_status` and `plan_feed`; the Telugu glossary and the builder's own review, as a native Telugu speaker, of the Telugu strings that existed then, and on 16 October of the later ones, all as one self-review (not independent); the follow-up wording is still pending; the first card and the Simulator; the state store and the one confirmation pattern; `plan_sale`; the voice record book; the first live Bedrock call; the health triage agent.
- **30 September to 1 October:** the daily briefing; fixes from independent reviews; a CI workflow; the follow-up agent and the demo clock; the Agent Skill; a rewrite of the friction log.
- **3 to 4 October:** the structured safety field; protocol-conformance, property, fuzz and concurrency tests; `reset-demo`, `NOTICE`, `inspector-replay`, `readiness` and `verify`; weather reminders.
- **6 to 7 October:** the pilot mode, the farmer's own deaths rule, the Telugu page, hardening, the add-or-replace question, fixes from a review of the pilot, the Windows launcher and runbook, and this documentation set.

Pre-existing projects: none found. The first commit (`d1d1662`, 2026-09-27) holds only build scaffolding (task runner, secret and cost checks, version pins, license); the product code follows in later commits. The GitHub repository was created on 2026-09-30. A check on 2026-10-18 (`gh repo list`, and folder names on my machine) found no earlier repository and no earlier project folder for it. Commit titles use plan-day labels; the dates are the commit dates. It was built with Claude Code. I cannot say what code I wrote outside this history.

## Built with

Python 3.13, the MCP Python SDK (`mcp` 2.2.0), Model Context Protocol 2025-11-25 over Streamable HTTP, MCP Apps cards (vanilla HTML and JavaScript), Starlette, uvicorn, SQLite, Pydantic, Amazon Bedrock (Amazon Nova 2 Lite, four live calls on 2026-09-29, outside the server), the AWS CLI and boto3, Open-Meteo (optional, off by default), Noto Sans Telugu, Hypothesis, pytest, ruff, GitHub Actions, Claude Code. For the pilot: a free Tailscale Funnel.

## Amazon requirements

| Requirement | Status | Evidence |
|---|---|---|
| An MCP server or a simulated Alexa+ experience, with the simulation source in the repository and a demo that shows it working | **Done for the server and the simulation**; the demo video is **pending** | Server: `src/clucktalk/server/`. Simulation source: `src/clucktalk/simulator/`. Demo: `python tasks.py run` and `python tasks.py verify`; `docs/proof/`; `docs/evidence/2026-09-27_card_and_simulator.md` |
| The repository calls the track technology in code | **Done** | `src/clucktalk/server/app.py` (the MCP server over Streamable HTTP); `src/clucktalk/simulator/mcp_client.py` (the client side); `tests/contract/test_protocol_conformance.py` |
| A video under 3 minutes, public, in English | **Pending** | [VIDEO URL: pending; must be public, in English and under 3 minutes] |
| Product feedback per tool | **Written**; the builder pastes it into the Devpost fields | `docs/PRODUCT_FEEDBACK.md` (long form with sources) and `docs/PRODUCT_FEEDBACK_DEVPOST.md` (ten paste-ready blocks): for each tool, what it was used for, what worked, what needs work, onboarding, and whether I would build with it again, plus the AWS services used and how. `FRICTION_LOG.md`, `FEATURE_REQUESTS.md` |
| An open-source license | **Done** | `LICENSE` (MIT); `NOTICE` lists the dependencies' licenses |
| AWS services used and how | **Lightsail hosts the farmer pilot; Nova 2 Lite through Bedrock is integrated in the code and off by default**. Four live calls happened on 2026-09-29, outside the server. A server-path live run is blocked by zero Nova quotas on the newer account (FL-031). Nova makes closed-list decisions and never writes farmer-facing wording. The pilot makes no Bedrock calls | Lightsail: `docs/CLOUD_PILOT.md`, `deploy/cloud/RUNBOOK.md`. Bedrock: `src/clucktalk/agents/bedrock.py`, `tests/unit/test_agents.py`; the one-off live calls of 2026-09-29: `docs/AWS_SETUP.md` sections 5.2 and 5.3; limits: `FRICTION_LOG.md` FL-014, FL-020, FL-031 |
| Open Source mini challenge: the contribution | **Undecided**; no claim is made | [CONTRIBUTION URL: pending] |
| Open Source mini challenge: the second repository | **Undecided**; no claim is made | [SECOND REPOSITORY URL: pending] |
| Running on an Alexa+ device, or passing Amazon's review | **Not done** | Not claimed anywhere; `docs/ALEXA_READINESS.md` lists what cannot be checked locally |
