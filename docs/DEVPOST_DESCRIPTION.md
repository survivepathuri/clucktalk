# Devpost project description (draft)

English, first person. Every claim names the file or command it comes from in the source list at the end. Items only the builder can fill are marked `[FILL]`. Nothing here has run on an Alexa+ device.

## Inspiration

A broiler farmer counts the dead birds each morning with busy hands, often with no screen in reach. A sudden spike, the total losses so far and the moment to call the vet are easy to miss, and most farm tools expect typing in English. I wanted something a farmer can tell in their own language, that reads every number back before saving it, and that never pretends to be a vet.

`[FILL: my own words about the farmer I know and the diary he keeps. Not written by Claude.]`

## What it does

CluckTalk (కోడి మిత్ర) is a self-hosted MCP server for the Alexa+ track: spec 2025-11-25, Streamable HTTP, the official `mcp` Python SDK, 14 tools. My Simulator is a web app: browser UI plus a backend MCP client that sends initialize (protocolVersion 2025-11-25), tools/list and tools/call to the MCP server over Streamable HTTP.

It gives a daily briefing that puts health items first, a voice record book (deaths, feed, weights, treatments) that is saved only after a spoken yes, health triage with a vet handoff (guidance, never a diagnosis or a dose; the vet message is a simulated SMS), a follow-up question days later, and feed and sale plans (the price is simulated). Each tool returns English text, Telugu text and structured data.

I have not run it on real Alexa+. The Alexa+ developer tools are preview for select partners and I found no way to apply. As I read the Devpost FAQ (https://amazonappdev2026.devpost.com/details/faqs), testing on real Alexa+ is not required, and a web simulator that I build myself and that acts as an MCP client meets the requirement. So I tested it through my own Simulator. The browser page itself only calls the Simulator's own backend; the backend is the MCP client (see "How the Simulator speaks MCP" in the README, with file and line references and a captured exchange). The Simulator picks tools with rule-based matchers.

## How I built it

I built it alone with Claude Code, in Python 3.13 with Starlette, uvicorn, SQLite and Pydantic. A tool answers from stored state and does not wait for a model. Two tools, `start_health_check` and `get_daily_briefing`, hand a job to a background worker, and that worker is the only code that can call a model.

Amazon Nova 2 Lite through the Bedrock Converse API is integrated in the code for those two agents and is off by default. It makes closed-list decisions only and never writes farmer-facing wording. My code sets the minimum urgency, so the model can raise it and never lower it. The integration is covered by tests with a botocore Stubber. Four live calls happened on 2026-09-29, outside the server. A live run through the server is blocked: on my newer AWS account every Nova 2 Lite quota is 0, and all four calls attempted on 2026-10-17 were throttled (FL-031).

The demo and the Lightsail pilot use a rule-based stand-in labelled "AI: off", and pilot mode forces `MOCK_BEDROCK=true`. The pilot makes no Bedrock calls. A live call is capped at 100 a day and one every 4 seconds, and every call is written to a ledger. A script fails the build if anything refers to OpenSearch Serverless, because it bills for always-on capacity.

The cloud pilot runs on one AWS Lightsail server in Mumbai, with the sample farm until the real farm is switched in. The demo farm is fictional. The example daily-deaths limit that demo mode uses (6 deaths a day up to age 29 days, 3 a day from age 30 days) comes from figures relayed by one broiler farmer; they are examples, not recommendations.

## Challenges

- A new AWS account showed Nova 2 Lite as available while every Bedrock quota was 0. After two Support cases, the first call was refused with "account is currently being verified", and it worked on retry about two hours later (FL-014). On my newer account, opened after I lost access to the first, every Nova 2 Lite quota was 0 again and all four server-path calls were throttled (FL-031).
- Claude models stayed blocked by a missing Anthropic Marketplace agreement and, for Sonnet 5, a quota of 0, so Nova 2 Lite is the only model I ran.
- I could not get Amazon's Local Inspector, so I wrote my own replay of the documented flow and said so (FL-024). I did not run the Local Inspector.
- Writing triage wording that is never a diagnosis and that no model can talk down.
- Telugu wording: 470 of 476 strings were reviewed by me, a native Telugu speaker (single reviewer, not independent); 6 are pending, because the farmer-preferred wording for follow-up is still to be confirmed.

## Accomplishments

14 tools, four MCP Apps cards, 3,405 automated tests (collected by `python tasks.py results`, see `docs/RESULTS.md` section 1; all passed in `python tasks.py check` on 2026-10-17), and 88 of 88 golden eval cases passing in mock mode on 2026-10-16. A safety matrix ties each rule to its source and tests. My friction log has 29 live entries (FL-001 to FL-032; three more numbers are merged stubs), and I wrote product feedback for the Amazon teams.

## What I learned

Put the safety rules in code and let a model only raise an alert. Label every simulated number. Read-back and confirmation suit voice well. Check Bedrock quotas with a real call, not the model list.

## What's next

Run the real farmer pilot, enter the farmer's own rules in the app, get the Telugu strings reviewed by someone besides me, run the live AI path through the server, and run Amazon's validation if access opens.

> **PILOT RESULTS: TO FILL AFTER THE PILOT**
> Days: `[FILL]` · Records logged: `[FILL]` · Questions asked: `[FILL]` · One honest quote: `[FILL]` · What broke: `[FILL]`
> No farmer has used the pilot yet.

## Built with

Python 3.13, `mcp` 2.2.0, Model Context Protocol 2025-11-25 over Streamable HTTP, MCP Apps cards (vanilla HTML and JavaScript), Starlette 1.7.0, uvicorn 0.54.0, Pydantic 2.13.5, SQLite, Amazon Bedrock (Amazon Nova 2 Lite, Converse API), boto3 1.43.103, AWS Lightsail, AWS CLI 2.37.4, Caddy, Open-Meteo (optional, off by default), Noto Sans Telugu 2.005, Hypothesis, pytest, ruff, GitHub Actions, Claude Code.

## What I built during the submission window vs before

Pre-existing projects: none for this repository. The submission window runs from 2026-08-31 to 2026-10-23. The first commit is dated 2026-09-27 (`git log --reverse`, commit `d1d1662`), so everything in the repository's history falls inside the window. I did not find an earlier repository, and I cannot say what code I wrote outside this history.

## Track and mini challenges

Alexa+ track. What runs on AWS: the Lightsail instance in Mumbai that hosts the farmer pilot. The pilot makes no Bedrock calls. Amazon Nova 2 Lite through Bedrock is integrated in the code and off by default; it was called live four times on 2026-09-29, outside the server, and a server-path live run is blocked by zero Nova quotas on the newer account (FL-031). Open Source mini challenge: undecided, no claim.

## Sources

Tools, versions, 14 tools: `submission.md`, `docs/VERSIONS.md`, `requirements.txt`. Bedrock code and tests: `src/clucktalk/agents/bedrock.py`, `tests/unit/test_agents.py`. Caps and ledger: `src/clucktalk/agents/budget.py`, `src/clucktalk/config.py`, `src/clucktalk/store/sqlite.py`. Live calls: `docs/AWS_SETUP.md` sections 5.2 and 5.3. Quotas and the verification step: `FRICTION_LOG.md` FL-014. Pilot mode: `src/clucktalk/config.py`, `deploy/cloud/bootstrap.sh`, `docs/CLOUD_PILOT.md`. Evals and results: `docs/EVALS.md`, `docs/RESULTS.md`. Never-lower test: `tests/unit/test_triage_rules.py`, `tests/unit/test_agents.py`.
