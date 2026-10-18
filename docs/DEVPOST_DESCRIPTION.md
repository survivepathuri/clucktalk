# Devpost project description (draft)

**Telugu-first MCP assistant for broiler farmers**

English, first person. Every claim names the file or command it comes from in the source list at the end. Items only the builder can fill are marked `[FILL]`. Nothing here has run on an Alexa+ device.

## Inspiration

India has a very large number of broiler farmers, and many of them run their sheds from memory, a notebook or a phone gallery. The numbers they need every day are scattered: how many birds died today, how old each shed is, how much feed is left, when to sell. When a farmer has several sheds, a small problem in one of them is easy to miss until it becomes an expensive one.

I have worked on broiler farms before, so I have seen this up close.

I built CluckTalk to put every shed in one place and make it easy to ask about. A farmer asks in Telugu, and the answer comes from his own records and his own declared schedule, not from a generic guess. The goal is fewer surprises, less guesswork on sale day, and more transparency in a business that runs on trust and memory.

I built it with input from a real broiler farmer. His feedback was clear: he wants to ask by speaking and to hear the answer back in Telugu. Today CluckTalk answers in written Telugu; the Simulator has a microphone button for English questions and reads English answers aloud when Sound is on. Asking by speaking in Telugu and hearing spoken Telugu replies are the next steps on the roadmap.

## What it does

CluckTalk is a self-hosted MCP server (spec 2025-11-25, Streamable HTTP), shown through a simulated Alexa+ web app and the MCP Inspector. The Telugu subtitle is కోడి మిత్ర (Kodi Mitra, 'Chicken Friend'). It is entered on the Alexa+ track and uses the official `mcp` Python SDK and 14 tools. My Simulator is a web app: browser UI plus a backend MCP client that sends initialize (protocolVersion 2025-11-25), tools/list and tools/call to the MCP server over Streamable HTTP.

It gives a daily briefing that puts health items first, a record book (deaths, feed, weights, treatments) that is saved only after an explicit yes, health triage with a vet handoff (guidance, never a diagnosis or a dose; the vet message is a simulated SMS), a follow-up question days later, and feed and sale plans (the price is simulated). Each tool returns English text, Telugu text and structured data.

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
- Telugu wording: 470 of 476 strings were reviewed by me, a native Telugu speaker (single reviewer, not independent); 6 are pending, because the farmer-preferred wording for follow-up is still to be confirmed. On 2026-10-16 I personally read the 390 strings that were still pending and found them correct (single-reviewer self-review as a native Telugu speaker); I approved 384 and kept 6 follow-up strings pending until the farmer confirms his word. The counts: 470 approved + 6 pending = 476 strings, counted wherever they appear in the code (86 approved on 2026-09-27, 384 on 2026-10-16); the approvals file `data/i18n/telugu_approvals.json` holds 433 entries (80 + 353) because a repeated English+Telugu pair shares one approval.

## Accomplishments

14 tools, four MCP Apps cards, 3,481 automated tests (collected by `python tasks.py results`, see `docs/RESULTS.md` section 1; all passed in `python tasks.py check` on 2026-10-18), and 88 of 88 golden eval cases passing in mock mode on 2026-10-16. A safety matrix ties each rule to its source and tests. My friction log has 30 live entries (FL-001 to FL-033; three more numbers are merged stubs), and I wrote product feedback for the Amazon teams.

## What I learned

Put the safety rules in code and let a model only raise an alert. Label every simulated number. Read-back and confirmation suit voice well. Check Bedrock quotas with a real call, not the model list.

## What's next

Run the real farmer pilot, enter the farmer's own rules in the app, get the Telugu strings reviewed by someone besides me, run the live AI path through the server, and run Amazon's validation if access opens.

Built with a broiler farmer. The schedule, safety and language layers are not poultry-specific, so the next step is other livestock and aquaculture, each with its own vet-reviewed content.

> **PILOT RESULTS: TO FILL AFTER THE PILOT**
> Days: `[FILL]` · Records logged: `[FILL]` · Questions asked: `[FILL]` · One honest quote: `[FILL]` · What broke: `[FILL]`
> No farmer has used the pilot yet.

## Built with

Python 3.13, `mcp` 2.2.0, Model Context Protocol 2025-11-25 over Streamable HTTP, MCP Apps cards (vanilla HTML and JavaScript), Starlette 1.7.0, uvicorn 0.54.0, Pydantic 2.13.5, SQLite, Amazon Bedrock (Amazon Nova 2 Lite, Converse API), boto3 1.43.103, AWS Lightsail, AWS CLI 2.37.4, Caddy, Open-Meteo (optional, off by default), Noto Sans Telugu 2.005, Hypothesis, pytest, ruff, GitHub Actions, Claude Code.

## What I built during the submission window vs before

Pre-existing projects: none found. The first commit (`d1d1662`, 2026-09-27) holds only build scaffolding (task runner, secret and cost checks, version pins, license); the product code follows in later commits. The GitHub repository was created on 2026-09-30. A check on 2026-10-18 (`gh repo list`, and folder names on my machine) found no earlier repository and no earlier project folder for it. Commit titles use plan-day labels; the dates are the commit dates. It was built with Claude Code. I cannot say what code I wrote outside this history.

## Track and mini challenges

Alexa+ track. What runs on AWS: the Lightsail instance in Mumbai that hosts the farmer pilot. The pilot makes no Bedrock calls. Amazon Nova 2 Lite through Bedrock is integrated in the code and off by default; it was called live four times on 2026-09-29, outside the server, and a server-path live run is blocked by zero Nova quotas on the newer account (FL-031). Open Source mini challenge: undecided, no claim.

## Sources

Tools, versions, 14 tools: `submission.md`, `docs/VERSIONS.md`, `requirements.txt`. Bedrock code and tests: `src/clucktalk/agents/bedrock.py`, `tests/unit/test_agents.py`. Caps and ledger: `src/clucktalk/agents/budget.py`, `src/clucktalk/config.py`, `src/clucktalk/store/sqlite.py`. Live calls: `docs/AWS_SETUP.md` sections 5.2 and 5.3. Quotas and the verification step: `FRICTION_LOG.md` FL-014. Pilot mode: `src/clucktalk/config.py`, `deploy/cloud/bootstrap.sh`, `docs/CLOUD_PILOT.md`. Evals and results: `docs/EVALS.md`, `docs/RESULTS.md`. Never-lower test: `tests/unit/test_triage_rules.py`, `tests/unit/test_agents.py`.
