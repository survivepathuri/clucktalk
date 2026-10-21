# Devpost project description

Paste-ready text for the Devpost form, in form order. Every claim names the file or command it comes from in section 11. Nothing here has run on an Alexa+ device.

## 1. Project name

CluckTalk (కోడి మిత్ర; Kodi Mitra, 'Chicken Friend')

## 2. Tagline

Telugu-first MCP assistant for broiler farmers

## 3. Inspiration

A broiler farmer starts the day in the shed with busy hands. Birds died overnight, and the count, the feed left and the age of each shed sit in a notebook, in memory or in a phone gallery. With several sheds, a sudden rise in deaths in one of them is easy to miss until it is costly.

CluckTalk keeps those records in one place. It tells the farmer, in Telugu and English, what needs attention first, and it answers from the farmer's own records, not from a generic guess.

A broiler farmer gave feedback during the build: they want to ask by speaking and hear the answer in Telugu. Today the answers are written Telugu. The Simulator's microphone takes English, and spoken Telugu is not built.

## 4. What it does

A farmer can do five things.

1. Ask how each shed is doing. A card shows the status, with health items first.
2. Get a daily briefing: what needs attention today, in order.
3. Check sick birds. CluckTalk asks short questions and sets the urgency in code. It gives guidance for the vet, never a diagnosis or a dose. The vet summary is read back first, and the SMS is simulated.
4. Record the day: deaths, feed, weights, treatments. The record is read back and saved only after the farmer says yes.
5. Plan a sale or a feed order. The price is simulated.

The Alexa+ screen is simulated. My web app plays the Alexa+ client and speaks MCP to the real server. Its banner says: "Simulated Alexa+ screen. The backend is a real MCP server (Streamable HTTP)." The badge says "Demo data · mock host". The demo farm is fictional and has 3 houses.

## 5. How I built it

I built it alone with Claude Code. The server is a self-hosted MCP server (spec 2025-11-25, Streamable HTTP) written in Python with the official `mcp` SDK. It has 14 tools. Each tool returns English text, Telugu text and a structured result, and the four cards run in a sandboxed iframe. An Agent Skill (`skills/clucktalk/`) describes the tools and the safety rules. The data is kept in SQLite.

A tool answers from stored state and does not wait for a model. The safety rules are in code. The urgency is set by code, so a model could raise it and never lower it.

Tests: 3,486 automated tests (524 harness, 1,757 unit, 1,205 contract). CI runs them on Ubuntu and Windows with Python 3.12 and 3.13. The macOS job is manual.

Amazon Nova 2 Lite through the Bedrock Converse API is integrated in `src/clucktalk/agents/bedrock.py` and is off in the live demo and in the pilot. The demo shows "Demo rules (no AI model)". Four real calls ran on 2026-09-29, outside the server, in a separate AWS account. A run through the server on 17 October failed: it was throttled, because every Nova 2 Lite quota on that account is 0 (FL-031).

## 6. Challenges I ran into

- Cards did not show on the public demo. The card sandbox origin was built as `https://localhost:` with an empty port. The cards now load from a second origin under the demo's own host name, and the server checks that setting at start (FL-034, FL-037).
- A check that spoken numbers equal the numbers on the card failed on the briefing date, which is display-only text. I marked it as skipped, as for the other cards (FL-035).
- One CI job failed on Windows with Python 3.12 and passed on a re-run. It is an overlapping-request test, and I have not investigated it. It is still open (FL-036).
- I could not get Amazon's Local Inspector, so I wrote my own replay of the documented flow and said so (FL-024).

## 7. Accomplishments

Measured, each from a file in this repository:

- 14 tools and 3,486 automated tests (524 harness, 1,757 unit, 1,205 contract); the CI badge in `README.md` shows the latest run.
- 88 of 88 golden evaluation cases pass in mock mode (run of 2026-10-16).
- Server time for the slowest step is p95 about 25 ms, on localhost in mock mode (docs/RESULTS.md). This is not Amazon's 500 ms round trip.
- In the pilot, one farmer confirmed two daily records on 19 October.
- The friction log has 34 live entries (FL-001 to FL-037).

## 8. What I learned

Put the safety rules in code and let a model only raise an alert. Label every simulated number. Read-back and confirmation suit voice well. Check Bedrock quotas with a real call, not the model list.

## 9. What's next

Dairy, sheep and fish farming are planned, each needing its own vet-reviewed content. They are not started. Other next steps: Telugu speech in and out, a longer farmer pilot, a Telugu review by someone besides me, and a live AI run through the server.

## 10. How this meets each criterion

**Technical Implementation.** The server follows MCP 2025-11-25 over Streamable HTTP with 14 tools, and 29 protocol tests pass against it. The 3,486 tests and the 88 evaluation cases run without AWS. Limit: Nova is integrated but did not run through the server. Evidence: `docs/RESULTS.md` sections 1, 2 and 4; `python tasks.py verify`.

**Design.** The first screen has five starter tiles. Each answer comes in Telugu with the English under it ("Judge view"). Nothing is saved before a read-back and a yes, and every simulated number is labelled. Limit: no Telugu speech, and the layout is shown by screenshots only. Evidence: `docs/evidence/2026-10-18_judge_view/`; `tests/contract/test_simulator_starters.py`.

**Potential Impact.** The target is a broiler farmer who tracks several sheds by memory or notebook. One farmer used the pilot with two sheds and confirmed two records on 19 October. The next pilot would measure the time spent on daily records and whether deaths are noticed earlier; that is a plan, not a result. Yield, mortality, time saved and adoption are not measured. Evidence: `README.md` (Impact); `docs/JUDGES.md`.

**Quality of the Idea.** The idea is a helper a farmer can ask in Telugu that answers from the farmer's own records and does not diagnose. Code sets the urgency, and the reply is guidance for the vet. The schedule, safety and language layers are not poultry-specific, but other species are only planned. Evidence: `docs/SAFETY_MATRIX.md`; `tests/unit/test_triage_rules.py`.

## 11. Where to verify each claim

| Claim | Where to check it |
|---|---|
| 14 tools, MCP 2025-11-25 | `docs/RESULTS.md` sections 1 and 4; `python tasks.py verify` |
| 3,486 tests (524, 1,757, 1,205) | `docs/RESULTS.md` section 1; the line at the top of `README.md` |
| CI is green | The CI badge at the top of `README.md`; the GitHub Actions page |
| 88 of 88 golden cases | `docs/EVALS.md`; `docs/RESULTS.md` section 2 |
| p95 about 25 ms, localhost, mock mode | `docs/RESULTS.md` section 5 |
| Nova integrated, four calls on 2026-09-29, off in demo and pilot | `src/clucktalk/agents/bedrock.py`; `docs/AWS_SETUP.md` sections 5.2 and 5.3; `FRICTION_LOG.md` FL-031 |
| Pilot: two sheds, two records, 19 October | `docs/RESULTS.md` section 9; `submission.md` |
| No diagnosis or dose | `docs/SAFETY_MATRIX.md`; `tests/unit/test_triage_rules.py` |
| Friction entries FL-034 to FL-037 | `docs/DEV_NOTES.md`; `FRICTION_LOG.md` |

## 12. Impact metrics

**Measured:** 3,486 automated tests; server time p95 about 25 ms for the slowest step, on localhost in mock mode; two daily records confirmed by one farmer in the pilot on 19 October.

**Not yet measured:** yield, mortality, time saved, adoption. One day of pilot data cannot show any of them.

**Scale, honestly:** records are kept per house (shed), not per bird. The demo farm has 3 houses and the pilot has 2 sheds. Nothing has been tested on a large farm.

## 13. Built with

Python 3.13, `mcp` 2.2.0, Model Context Protocol 2025-11-25 over Streamable HTTP, MCP Apps cards (vanilla HTML and JavaScript), Starlette 1.7.0, uvicorn 0.54.0, Pydantic 2.13.5, SQLite, Amazon Bedrock (Amazon Nova 2 Lite, Converse API), boto3 1.43.103, AWS Lightsail, AWS CLI 2.37.4, Caddy, Open-Meteo (optional, off by default), Noto Sans Telugu 2.005, Hypothesis, pytest, ruff, GitHub Actions, Claude Code.

## 14. Testing instructions

Open https://demo.13-127-66-28.sslip.io/ in a desktop browser. No sign-in. Tap one of the five starter tiles (farm status, when to sell, health check, daily briefing, help) and read the card. Judge view is on by default and shows the English under each Telugu answer. Type a question, for example "How is shed two doing?". Open "Developer panel" to see the MCP request and response. The farm is fictional demo data. I tested only in Chromium-based browsers; Firefox and Safari (WebKit) were not tested. The farmer's Telugu phone page is not on the public demo. Nova is off ("Demo rules (no AI model)").

## 15. Product feedback

Amazon Bedrock, Nova 2 Lite. Used for: triage and briefing slow paths via Converse; the pilot runs with it off. Worked well: four real calls on 29 Sep 2026 succeeded: 2,342 input and 106 output tokens, $0.000000. Needs work: models showed available while every quota was 0, then an account-verification error blocked the first call (FL-014); ThrottlingException says only "Too many requests" (FL-031). Onboarding: about 2 hours of work to unblock the first call (quota and account verification, solved with Claude Code's help); the account was created on 28 September and the first successful calls were on 29 September. Build again: yes, with invocation logging from day one.

Amazon Lightsail. Used for: hosting the farmer pilot on one Mumbai instance (Ubuntu 24.04, static IP, about $7 a month, paid by card). Worked well: the deploy and verify scripts ran twice on the real server, and the app, HTTPS proxy and backup timer came back after a reboot. Needs work: port 443 is closed on a new instance; the instance name cannot be changed; the console key download is a one-time secret (FL-030); memory under real load is untested. Onboarding: about 5 hours from creating the instance to the first deploy. Build again: yes.

Alexa+ MCP documentation and my Simulator. Used for: building an MCP server to the published guidance (QuickStart, 10 Jul; Local Inspector, 3 Aug); I wrote my own Simulator because I could not run on Alexa+. Worked well: the QuickStart gave the transport, the auth checklist and the 500 ms target. Needs work: no self-serve way to run the Alexa AI CLI or Local Inspector (FL-024); no stated protocolVersion (FL-026); no card size, CSP or font guidance (FL-009). Onboarding: about 2 hours reading the docs; I never tested on real Alexa+. Build again: yes, I would build for MCP again.

AWS CLI and boto3 on Windows. Used for: Identity Center sign-in, plan and quota checks, a hello call to Bedrock, and the live client in my code. Worked well: no access keys were needed, and I read the Converse request shapes in the installed botocore model before any paid call. Needs work: the CLI crashed on Windows while saving a reply with an emoji and left a truncated file (FL-019); a billing error did not name the setting to change (FL-015); an aws login profile needed botocore[crt] (FL-032). Onboarding: about 60 minutes from install to a working aws sts get-caller-identity.

## 16. Pre-existing projects

None found. The first commit (`d1d1662`, 2026-09-27) holds only build scaffolding (task runner, secret and cost checks, version pins, license); the product code follows in later commits. The GitHub repository was created on 2026-09-30. It was built with Claude Code.

## 17. Disclosure

Video narration: AI-generated voice (Gemini TTS).
