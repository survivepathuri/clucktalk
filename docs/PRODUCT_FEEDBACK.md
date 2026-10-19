# Product feedback (final, 2026-10-19)

Experience claims come only from the builder's verdicts of 2026-10-19 (marked builder-reported) or from tagged evidence (file, FL number, commit, CI run, audit file). Where there is no verdict, the entry gives the facts only and says so.

The five parts: 1 Used for, 2 What worked well, 3 What needs work, 4 Onboarding, 5 Build again. FL numbers point to `FRICTION_LOG.md`, FR numbers to `FEATURE_REQUESTS.md`.

Not used in the submitted build: Polly, Lambda, DynamoDB, CloudFront, S3 Vectors, OpenSearch, SMS (the vet SMS is simulated). Tailscale is not part of this feedback: no farmer ever used the pilot through it (historical note in FL-027).

---

## AWS services: what was live and what was mocked

This matches `submission.md` ("How we built it") and `docs/AWS_SETUP.md` sections 5.2 and 5.3.

- **Live:** Amazon Bedrock Runtime `converse` with Amazon Nova 2 Lite (`us.amazon.nova-2-lite-v1:0`) in us-east-1, a handful of one-off calls from the AWS CLI and boto3: a hello call (run twice, because the AWS CLI truncated the first capture, FL-019), then two forced-tool-choice spike calls on text and a tiny synthetic image (the second one misread a colour, FL-020). Their cost in `docs/AWS_SETUP.md` is under two tenths of a cent at third-party prices that were not confirmed on AWS's own price page. Also used: AWS Service Quotas and AWS Support cases, because the new account's Bedrock inference quotas were all 0 (FL-014), and an IAM Identity Center role for the CLI (FL-015).
- **Mocked:** every AI answer in the demo, in the golden evals and in the tests (`MOCK_BEDROCK=true`, shown by a "Demo data" badge). The server's live-AI path (the triage and briefing agents on a live model) was **not** verified end to end: four attempts through the server on 2026-10-17 were all throttled, because every Nova 2 Lite quota on the newer AWS account is 0 (FL-031). Only the Lightsail cloud pilot was deployed to AWS (since 13 October 2026, with the sample farm file and the rule-based test model, no Bedrock calls); no Lambda, no Polly, no Knowledge Base. OpenSearch Serverless is never used, and a script checks that (`scripts/check_no_aoss.py`). This sentence is the one in `submission.md` (next bullet: the Lightsail pilot).
- **Live since 13 October 2026, Amazon Lightsail (cloud pilot):** one Lightsail instance in Mumbai (ap-south-1) with a static IP and the Lightsail firewall runs the pilot page and the MCP server with the sample farm file; the AI there is the rule-based test model (`MOCK_BEDROCK=true`, no Bedrock calls). The Lightsail entry has the details. No farmer has used it yet (`docs/CLOUD_PILOT.md`).
- **Read, not used (builder-reported, 7 October 2026):** the AWS App Runner documentation, which says App Runner stopped accepting new customers on 30 April 2026 and recommends ECS Express Mode; we used neither (FL-027).
- **AWS services summary:** Amazon Nova 2 Lite through Bedrock is integrated in the code and off by default; four live calls on 2026-09-29 outside the server; a server-path live run is blocked by zero Nova quotas on the newer account (FL-031); Lightsail in Mumbai hosts the farmer pilot; Nova makes closed-list decisions and never writes farmer-facing wording; the pilot makes no Bedrock calls. The services: Bedrock Runtime (Nova 2 Lite, four live calls), Service Quotas and AWS Support cases (quotas were 0, FL-014), IAM Identity Center for CLI sign-in (FL-012, FL-015), the Billing console and the Free Tier plan API (FL-013), and Lightsail for the pilot host. Monthly cost model, builder-reported: one Lightsail plan of about $7 a month, paid by card; the account has 0.00 USD credits (Free Tier API, 2026-10-19 audit). Bedrock cost so far: under two tenths of a cent (`docs/AWS_SETUP.md` section 5.2). Not used: Lambda, Polly, Knowledge Bases, AgentCore, S3 Vectors, OpenSearch Serverless.

---

## 1. Amazon Bedrock and Amazon Nova 2 Lite (Converse API)

1. **Used for:** We used Nova 2 Lite through the Converse API for the triage and daily-briefing slow paths (`src/clucktalk/agents/__init__.py:45`, `src/clucktalk/agents/bedrock.py:30`). The pilot runs with it off (mock mode; `MOCK_BEDROCK=true`). Nova 2 Lite is integrated and tested with real calls but switched off in the pilot.
2. **What worked well:** Four real calls on 29 Sep 2026 (`us.amazon.nova-2-lite-v1:0`, us-east-1, AWS CLI and Boto3) succeeded: 2,342 input and 106 output tokens, $0.000000 (CloudTrail and Cost Explorer of the account that made them, audit of 2026-10-19). The output looked good (builder-reported).
3. **What needs work:** FL-014 happened in the older account: models showed as available while every quota was 0, then an "account verification" error blocked the first call. Later we lost sign-in access to that account for a while and regained it on 2026-10-19 through the root user. `ThrottlingException` says only "Too many requests" (FL-031, a different account, 2026-10-17: Nova 2 Lite quotas 0 on a new account). Usage appeared in Cost Explorer only about a day later, and there were no CloudWatch Bedrock metrics or invocation logging until enabled. FR-006 asks for quota and verification state in `GetFoundationModelAvailability`.
4. **Onboarding:** About 2 hours of work to unblock the first call (quota and account verification, solved with Claude Code's help); the account was created on 28 September and the first successful calls were on 29 September (builder-reported, 2026-10-19; FL-014).
5. **Build again:** Yes, with invocation logging from day one (builder-reported).

## 2. Amazon Lightsail (pilot host)

1. **Used for:** We host the farmer pilot on one Lightsail instance in Mumbai (Ubuntu 24.04, static IP, about $7 a month), paid by card; the account shows 0.00 USD credits (Free Tier API, audit of 2026-10-19). It runs the farmer page and the MCP server with the rule-based test model (`docs/CLOUD_PILOT.md`).
2. **What worked well:** `deploy.ps1` ran twice and `verify.ps1 -Reboot` ran twice on the real server, all PASS apart from one intended WARN; the app, Caddy and the backup timer came back after a reboot (`docs/CLOUD_PILOT.md`, "What was tested").
3. **What needs work:** A new instance does not open port 443; we added it in the console firewall (`deploy/cloud/RUNBOOK.md`, section 0). An instance name cannot be changed after creation. The console key download is a one-time secret (FL-028, FL-030). About 460 MB of memory was free after the app started; memory under real load was not tested.
4. **Onboarding:** About 5 hours from creating the instance to the first deploy (builder-reported, 2026-10-19).
5. **Build again:** Yes (builder-reported, 2026-10-19).

## 3. Alexa+ MCP documentation and our Simulator

1. **Used for:** We built a self-hosted MCP server to Amazon's published Alexa+ guidance (QuickStart, 10 Jul; Local Inspector, 3 Aug; `docs/SOURCES.md`). We could not run on Alexa+, so we wrote our own Simulator as the stand-in client (`src/clucktalk/simulator/`). The Local Inspector and the Alexa AI CLI were not used (FL-024).
2. **What worked well:** The QuickStart gave the transport, the authentication checklist and the 500 ms target. The documented initialize flow can be replayed against our server with `python tasks.py inspector-replay`.
3. **What needs work:** No self-serve way to run the Alexa AI CLI or Local Inspector (FL-024, FR-004). No page states which protocolVersion Alexa+ sends (FL-026). No card size, `ui/*` messages, CSP or font guidance (FL-009, FR-002). Alexa+ in India is press-reported to list English, Hindi and Hinglish, not Telugu (FL-033). We never tested on real Alexa+.
4. **Onboarding:** About 2 hours reading the documentation (builder-reported, 2026-10-19).
5. **Build again:** Yes, we would build for MCP again (builder-reported, 2026-10-19).

## 4. AWS CLI and boto3 (Windows)

1. **Used for:** AWS CLI 2.37.4 for IAM Identity Center sign-in, plan and quota checks and a hello call; boto3 1.43.103 for the live Bedrock client, and `botocore.stub.Stubber` in the tests (`docs/VERSIONS.md`).
2. **What worked well:** The CLI signed in with no access keys. We read the Converse `toolChoice` and image formats in the installed botocore service model before any paid call.
3. **What needs work:** On Windows the CLI crashed with a `charmap` error while writing a reply with an emoji and left a truncated file (FL-019). `aws billing get-credits` answered "IAM user access not activated" to an Identity Center role (FL-015). A real boto3 client with an `aws login` profile needed `botocore[crt]` (builder-reported; exact error not recorded; FL-032).
4. **Onboarding:** About 60 minutes from install to a working `aws sts get-caller-identity` (builder-reported, 2026-10-19).
5. **Build again:** No verdict recorded.

## 5. MCP Python SDK (`mcp` 2.2.0)

1. **Used for:** The server: 14 tools over Streamable HTTP with sessions, and the MCP Apps server support (`src/clucktalk/server/app.py`, `docs/VERSIONS.md`).
2. **What worked well:** Our 29 protocol tests pass against the server (`tests/contract/test_protocol_conformance.py`), and it answers `initialize` for four protocol versions (`docs/RESULTS.md`, section 4).
3. **What needs work:** Two in-flight requests with the same id leave one unanswered with no error (FL-011). Default tool errors name the tool and the fields (FL-002, FR-001). Middleware results leak `resultType` onto the 2025-11-25 wire (FL-001).
4. **Onboarding:** Not easy from the documentation alone; we worked it out by brainstorming with Claude Code, about 2 hours (builder-reported, 2026-10-19).
5. **Build again:** No verdict recorded.

## 6. MCP Apps (ext-apps) and its reference host

1. **Used for:** Four HTML cards (status, health check, sale plan, briefing) written against the documented postMessage protocol with no JS SDK. We built the ext-apps `basic-host` (commit 82221c0) to test them (`docs/evidence/2026-10-01_basic_host/README.md`).
2. **What worked well:** The spec says a view needs no SDK, so the cards have no Node build and no npm dependency (`docs/VERSIONS.md`).
3. **What needs work:** The spec example sends `clientInfo` but the schema needs `appInfo` (FL-006). The default CSP has no `font-src`, which blocks even an inlined Telugu font (FL-007, FR-003). The basic-host build needs bun and a built repo root (FL-021).
4. **Onboarding:** About 20 minutes to build the basic-host (FL-021, time cost).
5. **Build again:** Yes (builder-reported, 2026-10-19).

## 7. Agent Skill

1. **Used for:** We packaged our tool-routing and safety rules as a skill in `skills/clucktalk/`.
2. **What worked well:** Tests keep the skill in step with the server (`tests/unit/test_skill.py`).
3. **What needs work:** We never loaded the skill in any agent, so we cannot say whether an agent picks it up. Install folders differ by agent (README, "Agent Skill").
4. **Onboarding:** About 8 hours to the first working `SKILL.md` (builder-reported, 2026-10-19).
5. **Build again:** No verdict recorded.

## 8. GitHub Actions

1. **Used for:** `python tasks.py setup` and `check` on ubuntu and windows with Python 3.12 and 3.13 (`.github/workflows/ci.yml`).
2. **What worked well:** CI caught two problems the local Windows run missed: a timer lower-bound failure and a CRLF card-bundle mismatch (FL-023, FL-025).
3. **What needs work:** The macOS job is manual-only because it uses about 50 quota minutes per run. We used `[skip ci]` on 23 of 186 commits (2026-10-07 to 2026-10-13) because our free CI minutes ran out (builder-reported), so those commits were not CI-checked. The repository's visibility history is not recorded in git, so the reason is not checkable from the repo. CI ran again from 2026-10-13; the last run, on `1f0a12c`, passed.
4. **Onboarding:** Time not recorded.
5. **Build again:** No verdict recorded.

## 9. Claude Code

1. **Used for:** Writing and checking the code, and independent review passes by fresh sessions that read the code cold (`docs/INDEPENDENT_REVIEW.md`).
2. **What worked well:** Ten recorded review rounds found real defects, each fixed with a regression test.
3. **What needs work:** The shell tool changed backslash sequences, so a `\b` reached a source file as a backspace character (FL-022). The reviewers are AI agents, not a human audit (`SECURITY.md`).
4. **Onboarding:** It took a long time before it was productive on this repo; we did not time it (builder-reported, 2026-10-19).
5. **Build again:** Yes (builder-reported, 2026-10-19).

## 10. Caddy, Let's Encrypt and sslip.io (optional; not an Amazon tool)

1. **Used for:** HTTPS for the farmer page on the Lightsail server, on a `<ip-with-dashes>.sslip.io` name, so no domain is needed (`deploy/cloud/Caddyfile.cloud.template`).
2. **What worked well:** The certificate was issued and is valid to 2027-01-10 (audit of 2026-10-19); Caddy came back after a reboot (`docs/CLOUD_PILOT.md`).
3. **What needs work:** No problem or surprise (builder-reported, 2026-10-19). The pilot depends on a free third-party name service.
4. **Onboarding:** Time not recorded.
5. **Build again:** No verdict recorded.
