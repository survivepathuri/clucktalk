# Product feedback

One section per tool, API, SDK or service that this project actually used, with the five questions the hackathon asks. The list was taken from `requirements.txt`, `requirements-dev.txt`, `.github/workflows/ci.yml`, the imports in `src/`, `scripts/` and `tasks.py`, and the dated records in `docs/`. The paste-ready copy is `docs/PRODUCT_FEEDBACK_DEVPOST.md` (ten blocks, each under 110 words).

Rules for this file: every sentence comes from the repository's own records (`FRICTION_LOG.md`, `docs/DEV_NOTES.md`, `docs/AWS_SETUP.md`, `docs/VERSIONS.md`, `docs/SOURCES.md`, `FEATURE_REQUESTS.md`, git history) or from facts the builder reported on 7 October 2026, which are marked **builder-reported**. The Onboarding and Build again fields hold the builder's own approved verdicts, the same as in the ten blocks of `docs/PRODUCT_FEEDBACK_DEVPOST.md`; a verdict is an opinion and is not checked against a file. The first ten sections below are those ten blocks with their evidence; the tools that are not in the paste-ready copy are kept under "Also used" at the end. FL numbers point to `FRICTION_LOG.md` (or `docs/DEV_NOTES.md` for my own tooling); FR numbers point to `FEATURE_REQUESTS.md`.

The five questions:
1. Which tool, API or SDK, and what did I use it for?
2. What worked well?
3. What needs work?
4. Onboarding: from zero to hello world, how was it?
5. Would I build with it again? Yes or no, and why.

---

## AWS services: what was live and what was mocked

This matches `submission.md` ("How we built it") and `docs/AWS_SETUP.md` sections 5.2 and 5.3.

- **Live:** Amazon Bedrock Runtime `converse` with Amazon Nova 2 Lite (`us.amazon.nova-2-lite-v1:0`) in us-east-1, a handful of one-off calls from the AWS CLI and boto3: a hello call (run twice, because the AWS CLI truncated the first capture, FL-019), then two forced-tool-choice spike calls on text and a tiny synthetic image (the second one misread a colour, FL-020). Their cost in `docs/AWS_SETUP.md` is under two tenths of a cent at third-party prices that were not confirmed on AWS's own price page. Also used: AWS Service Quotas and AWS Support cases, because the new account's Bedrock inference quotas were all 0 (FL-014), and an IAM Identity Center role for the CLI (FL-015).
- **Mocked:** every AI answer in the demo, in the golden evals and in the tests (`MOCK_BEDROCK=true`, shown by a "Demo data" badge). The server's live-AI path (the triage and briefing agents on a live model) was **not** verified end to end. Only the Lightsail cloud pilot was deployed to AWS (since 13 October 2026, with the sample farm file and the rule-based test model, no Bedrock calls); no Lambda, no Polly, no Knowledge Base. OpenSearch Serverless is never used, and a script checks that (`scripts/check_no_aoss.py`). This sentence is the one in `submission.md` (next bullet: the Lightsail pilot).
- **Live since 13 October 2026, Amazon Lightsail (cloud pilot):** one Lightsail instance in Mumbai (ap-south-1) with a static IP and the Lightsail firewall runs the pilot page and the MCP server with the sample farm file; the AI there is the rule-based test model (`MOCK_BEDROCK=true`, no Bedrock calls). Section 3 has the details. No farmer has used it yet (`docs/CLOUD_PILOT.md`). The PC pilot with a free Tailscale Funnel (section 9) stays as the fallback.
- **Read, not used (builder-reported, 7 October 2026):** the AWS App Runner documentation (FL-027).
- **AWS Builder summary:** Bedrock Runtime (Nova 2 Lite, a handful of calls), Service Quotas and AWS Support cases (quotas were 0, FL-014), IAM Identity Center for CLI sign-in (FL-012, FL-015), the Billing console and the Free Tier plan API (FL-013), and Lightsail for the pilot host. Monthly cost model, builder-reported: one Lightsail plan of about $7 a month, paid from the hackathon credit per the Devpost mail; the credit amount of the account is not stated here. Bedrock cost so far: under two tenths of a cent (`docs/AWS_SETUP.md` section 5.2). Not used: Lambda, Polly, Knowledge Bases, AgentCore, S3 Vectors, OpenSearch Serverless.

---

---

## 1. Amazon Bedrock and Amazon Nova 2 Lite

1. **Used for:** the live AI mode of the health-triage and briefing agents (`src/clucktalk/agents/bedrock.py`, boto3 `converse`), which is off by default. In practice: a handful of one-off calls (a hello call, run twice because of FL-019, then a two-call spike on forced tool choice and image input), all with Nova 2 Lite in us-east-1 (`docs/AWS_SETUP.md` sections 5.2 and 5.3). Bedrock was also used read-only to check model availability, inference profiles and quotas (`docs/AWS_SETUP.md` section 5).
2. **What worked well:** once the account gates cleared, the first Nova 2 Lite call answered in `latencyMs` 450 with 57 input and 14 output tokens (`docs/AWS_SETUP.md` section 5.2). A forced `toolChoice` worked with text and with an image: a well-formed `toolUse` both times (FL-020). Amazon's own models such as Nova are not sold through AWS Marketplace, so Nova stayed callable on the AWS India account while the Anthropic models were blocked by their Marketplace agreement (`docs/AWS_SETUP.md`, "Accounts sold by AWS India").
3. **What needs work:**
   - A new account showed Nova 2 Lite and the Claude models as `AVAILABLE` and `AUTHORIZED` while every inference quota was 0; nothing in `get-foundation-model-availability` said so, and only a quota-by-quota comparison showed it (FL-014, FR-006).
   - The AWS Support reply said quotas were "reduced" but gave no numbers and no model list, so a fresh `list-service-quotas` call was the only way to know what was callable (FL-014).
   - The first real call then failed with `AccessDeniedException`, "Your account is currently being verified", a third gate that no read-only check reports (FL-014).
   - After the quota fix, Claude Haiku 4.5 and Claude Sonnet 5 were still blocked: the Anthropic Marketplace agreement stayed `NOT_AVAILABLE`, and Sonnet 5's cross-region tokens-per-minute quota stayed 0 against a default of 6,000,000 (`docs/AWS_SETUP.md` section 5.1).
   - On an AWS India (AISPL) account, a card as the default payment method can make the Marketplace subscription fail ("your Marketplace subscription can fail and model access isn't turned on"); this is only in the Bedrock-Anthropic article, and no page says whether promotional credits cover Marketplace-billed Bedrock models (FL-013, FR-007).
   - Nova 2 Lite read the blue half of a 64x64 synthetic image as "white" (one sample, an observation, not a benchmark), and the Converse reference documents `toolChoice` only as "if supported by model" (FL-020).
   - The live triage path and the briefing path on a live model were not run end to end; mock mode is the default.
   - The official Bedrock price table could not be read by a plain fetch, so the cost was worked out from third-party prices (`docs/AWS_SETUP.md` section 5.2).
4. **Onboarding:** **1 day** from the first recorded attempt (the read-only availability and quota check, 28 September) to the first successful call (29 September), after two quota cases. These are calendar dates from `docs/AWS_SETUP.md` sections 5 and 5.2 and FL-014 (the call was refused by account verification on 29 September and succeeded on the retry after 1:30 PM IST); hands-on time was not recorded.
5. **Build again:** yes for Nova 2 Lite, if quotas and model access were visible up front.

## 2. AWS CLI v2 and boto3 on Windows

1. **Used for:** the AWS CLI 2.37.4 on Windows 11 for the key-free sign-in through IAM Identity Center (`aws configure sso`, `aws sso login`), the account checks (`aws sts get-caller-identity`, `aws freetier get-account-plan-state`), the Bedrock availability and quota checks, and the hello call. boto3 1.43.103 for the two spike calls and for the server's live path; `botocore.stub.Stubber` in the tests (`docs/AWS_SETUP.md` sections 3 to 5, `docs/VERSIONS.md`).
2. **What worked well:** the CLI signed in through IAM Identity Center with no access keys; the profile stores only session and role names (`docs/AWS_SETUP.md` section 4). `aws freetier get-account-plan-state` showed the account plan (`PAID`, `ACTIVE`) when the console did not (FL-013). The Converse `toolChoice` values and `ImageBlock` formats could be read in the installed botocore service model before any paid call (`docs/VERSIONS.md`).
3. **What needs work:**
   - On Windows, a Converse reply that contained an emoji crashed the CLI's output with a `'charmap' codec` error and left a silently truncated 149-byte file; `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` fixed it (FL-019).
   - `aws billing get-credits` with an IAM Identity Center role answered "IAM user access not activated"; the caller is not an IAM user, and the message does not name the account setting that must be turned on (FL-015).
   - The recommended CLI identity (an IAM Identity Center organization instance) creates an AWS Organization, which upgrades a Free-plan account to Paid; no setup page says so (FL-012).
   - `billing:GetSellerOfRecord` has no CLI command in 2.37.4 (`docs/AWS_SETUP.md` sections 5 and 5.3).
4. **Onboarding:** the CLI installs for the current user without admin rights from `AWSCLIV2-User.msi`, and sign-in used IAM Identity Center, so no access keys; at the end of `aws configure sso` CLI 2.37.4 also asked whether to configure AWS skills and the AWS MCP server for coding agents (answered no) (`docs/AWS_SETUP.md` section 4).
5. **Build again:** yes.

## 3. AWS console, accounts, credits and hosting options (Lightsail, App Runner, Free Tier credits)

**Lightsail has run the cloud pilot since 13 October 2026.** App Runner was only read about. Nothing else in CluckTalk runs on AWS except the optional Bedrock calls in section 1.

1. **Used for:** the Billing console, to check the account plan and credits (FL-013); and Amazon Lightsail as the host of the cloud pilot (`docs/CLOUD_PILOT.md`, `deploy/cloud/RUNBOOK.md`): one Ubuntu 24.04.4 instance in Mumbai (ap-south-1), a static IP, the Lightsail firewall (22, 80, 443), and a plan of about $7 a month paid from the hackathon credit per the Devpost mail (builder-reported, 13 October; no amounts of the account are stated here). On the instance, not AWS products: Caddy for HTTPS with a Let's Encrypt certificate on a `<ip-with-dashes>.sslip.io` name, and a systemd timer for a daily backup (newest 7 kept on the same disk). Snapshots: the runbook lists one as optional; none is recorded as taken. Automatic snapshots are enabled (builder-reported, 2026-10-13, confirmed by the builder in the console). The plan is about $7 a month with 1 GB (builder-reported, 2026-10-13).
2. **What worked well:** recorded: `deploy.ps1` ran twice and `verify.ps1 -Reboot` ran twice on the real server, all PASS apart from one intended WARN for the sample farm file; the app, Caddy and the backup timer came back after a reboot (`docs/CLOUD_PILOT.md`, "What was tested"). Builder-reported: the Lightsail documentation says that Lightsail is available in the Mumbai Region and that its short free trials were replaced by the AWS Free Tier credits. Recorded: the Billing console showed the account's credits ($120 active, FL-013).
3. **What needs work:**
   - **Lightsail, port 443:** a new instance does not open HTTPS; it had to be added in the console firewall (`deploy/cloud/RUNBOOK.md`, section 0).
   - **Lightsail, names (builder-reported, 13 October):** an instance name cannot be changed after creation, and a static IP gets a default name unless you set one (the default name is `staticip-1`, which says nothing about its purpose; builder-reported, 2026-10-13). The runbook therefore says to name everything `clucktalk-` at creation.
   - **Lightsail, key download:** the key from the console is a one-time download. Its file permissions were refused by Windows OpenSSH (FL-028); its text was pasted into an assistant session, so it was replaced by a new key pair (FL-030, which suggests an option to install your own public key at creation).
   - **Lightsail, my own mistake:** `ufw limit 22/tcp` locked my deploy scripts out of SSH after a few quick connections (FL-029). Not an AWS defect.
   - **Lightsail, size:** the plan has about 900 MB of memory, and about 460 MB was free after the app started. Disk: 38 GB in total, about 2.5 GB used (7%), from `sudo clucktalk-status` on 2026-10-13 (builder-reported, 2026-10-13; the memory figures above were recorded earlier). Memory under real load: not tested.
   - **Lightsail (builder-reported):** the documentation says the Mumbai plans include half the data transfer.
   - **App Runner (builder-reported, FL-027):** the AWS documentation page "AWS App Runner availability change" states that App Runner stopped accepting new customers on 30 April 2026 and recommends ECS Express Mode. The page's URL was not recorded.
   - **Credits (builder-reported):** the hackathon's $150 AWS credit request is a Google Form on the Devpost Resources page; it was submitted on 7 October 2026. The 13 October Lightsail plan is paid from that credit per the Devpost mail (builder-reported). Recorded earlier: no AWS page states whether promotional credits cover Marketplace-billed Bedrock models (FL-013).
   - **Account plan (recorded):** on the AWS India account the Billing console showed no Free or Paid plan, although the Billing docs say the console home shows it (FL-013, FR-007).
4. **Onboarding:** a new AWS account plus redeeming the hackathon credit took about 1 hour (builder-reported, 2026-10-13); earlier sign-in problems on 7 October, on a previous account, were a separate issue (time not measured) (builder-reported). Lightsail, from creating the instance to the first deploy: the time was not recorded; the blockers were port 443 and the key file permissions above (FL-028).
5. **Build again:** yes (AWS, Lightsail) (builder-reported, 2026-10-13). The price is fixed and predictable (about $7 a month, covered by the hackathon credit); one server, a static IP and a firewall were enough to put a one-farmer pilot online in Mumbai; automatic snapshots were easy to enable. It needs work on: port 443 closed by default, an instance name that cannot be changed after creation, and a default static IP name that means nothing.

## 4. Alexa+ MCP documentation (QuickStart, Local Inspector and related pages)

1. **Used for:** the product target. CluckTalk is a self-hosted MCP server built to Amazon's published Alexa+ guidance. Pages read: the Alexa+ MCP QuickStart (last updated Jul 10, 2026), the Alexa+ Add-on Local Inspector page (last updated Aug 3, 2026), the MCP Toolkit overview, Choose an integration approach, Functional Requirements, the CX testing guide, MCP Toolkit Account Linking, `Alexa.ProactiveNotificationSource`, and "Set Up Your Development Environment" (`docs/SOURCES.md`, FL-009, FL-017, FL-024, FL-026). The Amazon Devices Builder Tools and the Local Inspector were **not** used (builder-reported; the Inspector install needs a Developer Console login, FL-024). The Alexa AI CLI was not used for the same reason (FL-024). The Alexa Web Simulator was not used; the reason is not recorded, and no add-on was ever deployed to Alexa+ (`docs/ALEXA_READINESS.md`).
2. **What worked well:** the QuickStart gave the transport (Streamable HTTP), the authentication checklist (OAuth 2.1 with PKCE, Protected Resource Metadata), the 500 ms round-trip requirement, the `addon.json` schema reference and the fact that tool information refreshes only when the add-on is deployed; the Local Inspector page documented an initialize flow that `python tasks.py inspector-replay` replays against my server (`docs/SOURCES.md`).
3. **What needs work:**
   - The Local Inspector and the Alexa AI CLI have no self-serve path for participants: the setup page asks for an AWS account provided to an Alexa Solutions Architect, lists macOS and Ubuntu only, and keeps the Local Inspector install guide behind a Developer Console login (FL-024, FR-004).
   - **Access (builder-reported, Amazon docs as read on 13 October 2026):** the Alexa+ MCP Toolkit is documented as partner-only and US-only, so CluckTalk was never tested on a real Alexa+ device or with Alexa+ itself. The Simulator and `inspector-replay` are my own stand-ins.
   - **Authentication and endpoint:** the QuickStart's checklist asks for OAuth 2.1 with PKCE, Protected Resource Metadata and a public HTTPS endpoint. I built no OAuth: the MCP server listens on `127.0.0.1` and, off localhost, uses a bearer token, which is not Amazon's account linking (`docs/ALEXA_READINESS.md`, README). The cloud pilot's HTTPS endpoint serves only the farmer page; the MCP server is not public (`docs/CLOUD_PILOT.md`).
   - No page states which MCP protocolVersion Alexa+ sends or requires; the QuickStart names 2025-11-25 only as the version that deprecated HTTP+SSE, and the Local Inspector example sends 2025-06-18 (FL-026).
   - The `addon.json` example lists only `US` in `distributionCountries`, and no page says whether `IN` is allowed for MCP add-ons (FR-008).
   - MCP Apps on Alexa+: no card container size, supported `ui/*` messages, CSP or font policy (Telugu included) (FL-009, FR-002).
   - No statement on whether an MCP add-on can send proactive notifications, or whether a request identifies which household member spoke (FL-017, FR-005).
4. **Onboarding:** the pages read quickly; testing against Alexa+ itself was not possible (FL-024; access is partner-only and US-only, builder-reported).
5. **Build again:** yes for the MCP approach, with a caveat (builder-reported, 2026-10-13). Reasons: the MCP standard is clear and I built a normal, spec-conformant server with it; the documentation is detailed on OAuth and the public endpoint. But access is partner-only and the MCP Toolkit is US-only, so a solo developer in India cannot follow it end to end; I never ran on real Alexa+ and cannot judge the platform itself. I would build with it again if access opens to individual developers.

## 5. MCP Python SDK (`mcp` 2.2.0 and `mcp-types` 2.2.0)

1. **Used for:** the MCP server (`src/clucktalk/server/app.py`: `MCPServer`, `streamable_http_app`, `TransportSecuritySettings`, `mcp.server.apps.Apps`), tool results and middleware, and the protocol-version constants (`docs/VERSIONS.md`).
2. **What worked well:** the 29 protocol tests in `tests/contract/test_protocol_conformance.py` pass against my server of 14 tools; SDK 2.2.0 ships MCP Apps server support in-core (`_meta.ui.resourceUri`, the `text/html;profile=mcp-app` resource) (`docs/VERSIONS.md`); tool meta, resources and the client's Apps capability work on 2025-11-25 (FL-008); the server answers `initialize` for 2025-11-25, 2025-06-18, 2025-03-26 and 2024-11-05 (`docs/RESULTS.md` section 4).
3. **What needs work:** middleware results skip per-version shaping, so `resultType` leaks onto the 2025-11-25 wire (FL-001); default tool error text names the tool and validation fields, with no hook to change it (FL-002, FR-001), and my own fuzz round found protocol errors that echoed input until `ProtocolErrorGate` replaced them (F1 and F2, `SECURITY.md`); the localhost Origin allow-list accepts every local port (FL-003); the client and the MCP Inspector disagree on whether `outputSchema` applies to `isError` results (FL-004); the server's `extensions` capability is dropped on 2025-11-25 (FL-008); two in-flight requests with the same JSON-RPC id leave one unanswered for at least 40 seconds, with no error (FL-011).
4. **Onboarding:** straightforward from the documentation and examples; the server skeleton was built on the first day, 2026-09-27 (git history; `docs/evidence/2026-09-27_mcp_server_skeleton.md`).
5. **Build again:** yes.

## 6. MCP Apps (ext-apps, spec 2026-01-26) and its reference host (`basic-host`)

1. **Used for:** the four cards in `ui/cards/` (status, health check, sale plan, briefing), written against the documented postMessage protocol without the JS SDK; the ext-apps `basic-host` (commit 82221c0, v2.0.3) was built and started to test the cards (`docs/evidence/2026-10-01_basic_host/README.md`).
2. **What worked well:** the spec says a view needs no SDK, and the cards speak the protocol directly, so the card side has no Node build and no npm dependency (`docs/VERSIONS.md`); after the workaround in FL-021 the basic-host was built and started and its HTTP-level checks were done, although the four cards have not yet been looked at in a browser through it (`docs/evidence/2026-10-01_basic_host/README.md`).
3. **What needs work:** the spec's example sends `clientInfo` while the schema requires `appInfo` in `ui/initialize` (FL-006); the default CSP has no `font-src`, so even an inlined `data:` font is blocked, while the reference host allows it, and the spec does not say whether a CSP-blocked font source falls through (FL-007, FR-003); the Alexa+ documentation gives no card container size (FL-009); the basic-host cannot be built from its README, because the repo root must be built first and bun is needed (FL-021).
4. **Onboarding:** the examples helped; Windows setup took extra steps: building the basic-host took about 20 minutes (FL-021).
5. **Build again:** yes.

## 7. Claude Code and the Claude models (building and the independent reviews)

1. **Used for:** writing and checking the code in this repository, and for the independent reviews: after each main feature a fresh agent read the code cold against `docs/DESIGN.md` (`docs/INDEPENDENT_REVIEW.md`). Which Claude model version each session used is not recorded.
2. **What worked well:** the project was built tests-first, with mutation checks that plant a fault the tests must catch (`docs/RESULTS.md`), in many small local commits. The ten recorded review rounds found real defects that were then fixed with regression tests, among them a Critical one in the voice record book (a backdated correction could push total deaths over the birds placed while saying it was saved) and a High one in triage (words that matched no known sign got the lowest urgency) (`docs/INDEPENDENT_REVIEW.md`). Round 10, on pilot mode, found same-day deaths that were added or replaced silently, pilot access (the MCP server now refuses to start in pilot mode without a strong token) and the session limit (a new session now drops the least recently used one); the fixes have tests.
3. **What needs work:** Windows line endings made a card bundle differ from the CI build, and the local check could not see it (FL-025, `docs/DEV_NOTES.md`); the shell tool changed backslash sequences in commands that wrote files: a `\b` reached a source file as an invisible backspace character, and the problem recurred in later sessions (FL-022, `docs/DEV_NOTES.md`). The reviewers are AI agents, not a human audit (`SECURITY.md`).
4. **Onboarding:** fast to start; it needed strict rules and tests to stay safe. Not recorded in this repository, so not claimed: usage limits and time spent waiting for CI.
5. **Build again:** yes, with those rules, tests and an independent review.

## 8. The Agent Skills format

1. **Used for:** `skills/clucktalk/`, a `SKILL.md` plus three reference files and an MIT license, which packages my tool-routing and safety rules and teaches a coding agent how to operate CluckTalk's 14 tools (README, "Agent Skill").
2. **What worked well:** one folder matches the skills layout that Kiro's and Cursor's documentation describe (web search on 2026-10-01); tests keep the skill in step with the server (`tests/unit/test_skill.py`).
3. **What needs work:** each agent uses a different install folder (`.claude/skills/`, `.kiro/skills/`, `.cursor/skills/`, `.github/skills/`), and the GitHub Copilot path was seen only on a third-party page; the skill was never loaded in any agent, so whether each one picks it is unverified (README, "Agent Skill").
4. **Onboarding:** short.
5. **Build again:** yes.

## 9. Tailscale Funnel (the free hosting tunnel for the farmer pilot)
1. **Used for:** a free HTTPS link from the builder's own Windows PC to one farmer's phone (builder-reported, 7 October 2026; `docs/PILOT_RUNBOOK_WINDOWS.md`). Only the page port is forwarded; the MCP port stays on the loopback (`docs/ARCHITECTURE.md`).
2. **What worked well:** builder-reported: it worked on the first try after HTTPS certificates and Funnel were enabled in the Tailscale admin console.
3. **What needs work:** recorded: what Tailscale's relay can see was not examined here (`SECURITY.md`), and availability depends on the PC and its internet (`docs/ARCHITECTURE.md`). The runbook's Tailscale commands are from memory of its documentation (`docs/PILOT_RUNBOOK_WINDOWS.md`).
4. **Onboarding:** short; builder-reported: first try, after the two admin-console settings above. Not in the repository's records, so not claimed: the free plan's bandwidth limit, what appears in public certificate logs, and whether the host name stays the same.
5. **Build again:** yes for pilots.

## 10. GitHub Actions (private repository)
1. **Used for:** `python tasks.py setup` and `python tasks.py check` on ubuntu and windows with Python 3.12 and 3.13 (`.github/workflows/ci.yml`).
2. **What worked well:** CI caught two problems that the local Windows run did not: a Windows timer lower-bound failure (FL-023) and a card bundle built from a CRLF template (FL-025) (`docs/DEV_NOTES.md`).
3. **What needs work:** the macOS job is manual-only because it uses about 50 quota minutes per run (`.github/workflows/ci.yml`); the repository is private until it is made public (`SECURITY.md`). Builder-reported: its free minutes ran out, and every commit from 7 October on (from `8850d2a`) ends with `[skip ci]`, so those commits were not CI-checked (git history). The reason Windows minutes cost more is not in the repository's records and is not claimed.
4. **Onboarding:** easy.
5. **Build again:** yes, with a public repository.

## Also used (not in the ten paste-ready blocks)

These tools were used and have recorded evidence, but the builder's approved copy does not include them. They are kept so that nothing found is lost.

### The simulated Alexa+ path (my own Simulator)

1. **Used for:** playing the Alexa+ client role while no Alexa+ device could load the add-on: a local web app with Echo Show and Echo Dot modes, voice and text, cards, and a developer panel that shows the exact MCP wire (`src/clucktalk/simulator/`). It is my code, not Amazon's tool.
2. **What worked well:** the Simulator speaks the tool's own text, so the card sentence equals the spoken sentence and every number is the same on both (tested, `tests/crossmodal.py`, `tests/contract/test_card.py`); the golden evals run against a real MCP server over real HTTP (`docs/EVALS.md`).
3. **What needs work:** that equality holds in the Simulator only; on Alexa+ the assistant composes its own speech from the tool result and descriptions, so the words can differ (README, "Voice versus cards"). Its intent layer is rules, not a model (`src/clucktalk/simulator/intents.py`), so it is not a test of how Alexa+ picks a tool.
4. **Onboarding:** not applicable: it is part of this repository and starts with `python tasks.py run`.
5. **Build again:** no verdict is asked for; not in the ten paste-ready blocks.

### MCP Inspector 2.8.0 (CLI)

1. **Used for:** capturing evidence of tool calls and error results (`docs/evidence/`), as the stand-in for the Alexa+ Local Inspector I could not run (FL-024). Not a dependency of the code.
2. **What worked well:** `--method tools/list` and `--method tools/call` captured the evidence in `docs/evidence/2026-09-27_farm_status_and_feed.md`; successful calls exit 0 (FL-005).
3. **What needs work:** on Windows the CLI crashes with a libuv assertion when a call ends in an error, so the exit code cannot be used (FL-005); it validates an error result's `structuredContent` against the success schema, unlike the Python SDK client (FL-004).
4. **Onboarding:** no verdict is asked for; not in the ten paste-ready blocks.
5. **Build again:** no verdict is asked for; not in the ten paste-ready blocks.

### Hypothesis 6.168.3 (property and fuzz tests)
1. **Used for:** the property tests (`tests/unit/test_property_*.py`) and the fuzz tests (`tests/contract/test_fuzz_*.py`); a dev dependency only (`docs/VERSIONS.md`).
2. **What worked well:** the fuzz round found the protocol errors that echoed input back (F1 and F2, now short fixed messages), and the fuzz tests pin an SDK behaviour (F3) and my own shed-name reader (F4) (`SECURITY.md`; README, "Known SDK behaviors").
3. **What needs work:** nothing recorded.
4. **Onboarding:** no verdict is asked for; not in the ten paste-ready blocks.
5. **Build again:** no verdict is asked for; not in the ten paste-ready blocks.

### Other libraries used (no friction recorded)

1. **Used for:** Starlette 1.7.0 and uvicorn 0.54.0 (the ASGI app and its middleware), pydantic 2.13.5 (tool models), jsonschema 4.26.0 (argument validation), httpx2 2.13.1 (the Simulator's MCP client, the contract tests and scripts), SQLite 3.50.4 through Python's `sqlite3` (the farm state), Noto Sans Telugu 2.005 (Telugu on every card), ruff 0.16.9 and pytest 9.1.1 (`python tasks.py check`), and Node.js 24.15.0 for one optional card test (`docs/VERSIONS.md`, `NOTICE`).
2. **What worked well:** nothing beyond use is recorded; no friction-log entry names these, except Noto Sans Telugu under FL-007 (whether a strict host keeps an inlined font).
3. **What needs work:** nothing recorded.
4. **Onboarding:** no verdict is asked for; not in the ten paste-ready blocks.
5. **Build again:** no verdict is asked for; not in the ten paste-ready blocks.

## Mentioned but not used

Amazon Polly appears in comments as the planned voice of the live Simulator host and is not imported or called. `strands-agents` and `bedrock-agentcore` are listed in `docs/VERSIONS.md` as available, not as dependencies, and are not imported. The `@modelcontextprotocol/ext-apps` JS SDK is not used (`docs/VERSIONS.md`). The Amazon Devices Builder Tools, the Alexa AI CLI, the Alexa Web Simulator and the Alexa+ Local Inspector were not used (builder-reported; FL-024).
