# Devpost project description (draft)

English, first person. Every claim names the file or command it comes from in the source list at the end. Items only the builder can fill are marked `[FILL]`. Nothing here has run on an Alexa+ device.

## Inspiration

A broiler farmer counts the dead birds each morning with busy hands, often with no screen in reach. A sudden spike, the total losses so far and the moment to call the vet are easy to miss, and most farm tools expect typing in English. I wanted something a farmer can tell in their own language, that reads every number back before saving it, and that never pretends to be a vet.

`[FILL: my own words about the farmer I know and the diary he keeps. Not written by Claude.]`

## What it does

CluckTalk (కోడి మిత్ర) is a self-hosted MCP server for the Alexa+ track: spec 2025-11-25, Streamable HTTP, the official `mcp` Python SDK, 14 tools. The farmer page calls it over the wire as a real MCP client.

It gives a daily briefing that puts health items first, a voice record book (deaths, feed, weights, treatments) that is saved only after a spoken yes, health triage with a vet handoff (guidance, never a diagnosis or a dose; the vet message is a simulated SMS), a follow-up question days later, and feed and sale plans (the price is simulated). Each tool returns English text, Telugu text and structured data.

I have not run it on real Alexa+. The Alexa+ developer tools are preview for select partners and I found no way to apply. As I read the Devpost FAQ (https://amazonappdev2026.devpost.com/details/faqs), testing on real Alexa+ is not required, and a web simulator that I build myself and that acts as a real MCP client meets the requirement. So I tested it through my own Simulator. The Simulator picks tools with rule-based matchers.

## How I built it

I built it alone with Claude Code, in Python 3.13 with Starlette, uvicorn, SQLite and Pydantic. A tool answers from stored state and does not wait for a model. Two tools, `start_health_check` and `get_daily_briefing`, hand a job to a background worker, and that worker is the only code that can call a model.

Amazon Nova 2 Lite through the Bedrock Converse API is wired for those two agents but is off by default. It answers closed-list questions only. My code sets the minimum urgency, so the model can raise it and never lower it. The integration is wired and covered by tests with a botocore Stubber, and I made a few one-off live calls on 2026-09-29. I have not run it end to end through the server.

The demo and the Lightsail pilot use a rule-based stand-in labelled "AI: off", and pilot mode forces `MOCK_BEDROCK=true`. The pilot makes no Bedrock calls. A live call is capped at 100 a day and one every 4 seconds, and every call is written to a ledger. A script fails the build if anything refers to OpenSearch Serverless, because it bills for always-on capacity.

The cloud pilot runs on one AWS Lightsail server in Mumbai, with the sample farm until the real farm is switched in.

## Challenges

- A new AWS account showed Nova 2 Lite as available while every Bedrock quota was 0. After two Support cases, the first call was refused with "account is currently being verified", and it worked on retry about two hours later (FL-014).
- Claude models stayed blocked by a missing Anthropic Marketplace agreement and, for Sonnet 5, a quota of 0, so Nova 2 Lite is the only model I ran.
- I could not get Amazon's Local Inspector, so I wrote my own replay of the documented flow and said so (FL-024). I did not run the Local Inspector.
- Writing triage wording that is never a diagnosis and that no model can talk down.
- Telugu wording: 470 of 476 strings were reviewed by me, a native Telugu speaker (single reviewer, not independent); 6 are pending, because the farmer-preferred wording for follow-up is still to be confirmed.

## Accomplishments

14 tools, four MCP Apps cards, 3,403 automated tests (all passed in `python tasks.py check` on 2026-10-16), and 88 of 88 golden eval cases passing in mock mode on 2026-10-16. A safety matrix ties each rule to its source and tests. My friction log has 27 live entries (FL-001 to FL-030, three merged), and I wrote product feedback for the Amazon teams.

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

The submission window opened on 2026-08-31 `[FILL: confirm]`. The first commit is dated 2026-09-27 and there were 135 commits on 2026-10-16, before the audit-fix commits (`git rev-list --count HEAD`), so everything in the repository's history falls inside the window. I did not find an earlier repository, and I cannot say what code I wrote outside this history.

## Track and mini challenges

Alexa+ track. Mini challenges: AWS Builder, claimed only for what runs on AWS: the Lightsail instance in Mumbai that hosts the cloud pilot. The pilot makes no Bedrock calls, and Amazon Nova 2 Lite is not part of this claim (it is wired but off by default, and was called live only in four one-off calls outside the server). Open Source: undecided, no claim.

## Sources

Tools, versions, 14 tools: `submission.md`, `docs/VERSIONS.md`, `requirements.txt`. Bedrock code and tests: `src/clucktalk/agents/bedrock.py`, `tests/unit/test_agents.py`. Caps and ledger: `src/clucktalk/agents/budget.py`, `src/clucktalk/config.py`, `src/clucktalk/store/sqlite.py`. Live calls: `docs/AWS_SETUP.md` sections 5.2 and 5.3. Quotas and the verification step: `FRICTION_LOG.md` FL-014. Pilot mode: `src/clucktalk/config.py`, `deploy/cloud/bootstrap.sh`, `docs/CLOUD_PILOT.md`. Evals and results: `docs/EVALS.md`, `docs/RESULTS.md`. Never-lower test: `tests/unit/test_triage_rules.py`, `tests/unit/test_agents.py`.
