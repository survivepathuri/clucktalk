# Product feedback

One section per tool, API, SDK or service that this project actually used, with the five questions the hackathon asks. The list was taken from `requirements.txt`, `requirements-dev.txt`, `.github/workflows/ci.yml`, the imports in `src/`, `scripts/` and `tasks.py`, and the dated records in `docs/`. The paste-ready copy is `docs/PRODUCT_FEEDBACK_DEVPOST.md`.

Rules for this file: every sentence comes from the repository's own records (`FRICTION_LOG.md`, `docs/DEV_NOTES.md`, `docs/AWS_SETUP.md`, `docs/VERSIONS.md`, `docs/SOURCES.md`, `FEATURE_REQUESTS.md`, git history) or from facts the builder reported on 7 October 2026, which are marked **builder-reported**. Where an answer is the builder's own verdict, or a duration that was not recorded, the field holds a placeholder in square brackets that starts with "BUILDER TO CONFIRM" and asks the question; nothing is guessed. Every placeholder is collected in "QUESTIONS FOR THE BUILDER" at the end of `docs/PRODUCT_FEEDBACK_DEVPOST.md`. FL numbers point to `FRICTION_LOG.md` (or `docs/DEV_NOTES.md` for our own tooling); FR numbers point to `FEATURE_REQUESTS.md`.

The five questions:
1. Which tool, API or SDK, and what did we use it for?
2. What worked well?
3. What needs work?
4. Onboarding: from zero to hello world, how was it?
5. Would we build with it again? Yes or no, and why.

---

## AWS services: what was live and what was mocked

This matches `submission.md` ("How we built it") and `docs/AWS_SETUP.md` sections 5.2 and 5.3.

- **Live:** Amazon Bedrock Runtime `converse` with Amazon Nova 2 Lite (`us.amazon.nova-2-lite-v1:0`) in us-east-1, a handful of one-off calls from the AWS CLI and boto3: a hello call (run twice, because the AWS CLI truncated the first capture, FL-019), then two forced-tool-choice spike calls on text and a tiny synthetic image (the second one misread a colour, FL-020). Their cost in `docs/AWS_SETUP.md` is under two tenths of a cent at third-party prices that were not confirmed on AWS's own price page. Also used: AWS Service Quotas and AWS Support cases, because the new account's Bedrock inference quotas were all 0 (FL-014), and an IAM Identity Center role for the CLI (FL-015).
- **Mocked:** every AI answer in the demo, in the golden evals and in the tests (`MOCK_BEDROCK=true`, shown by a "Demo data" badge). The server's live-AI path (the triage and briefing agents on a live model) was **not** verified end to end. Nothing was deployed to AWS; no Lambda, no Polly, no Knowledge Base. OpenSearch Serverless is never used, and a script checks that (`scripts/check_no_aoss.py`).
- **Read or attempted, not used (builder-reported, 7 October 2026):** AWS Lightsail and AWS App Runner documentation were read while choosing hosting; the hackathon's AWS credit request was submitted and is pending. None of these runs any part of CluckTalk. The farmer pilot is hosted on the builder's own PC through a free Tailscale Funnel instead.

---

## 1. Amazon Bedrock and Amazon Nova 2 Lite

1. **Used for:** the live AI mode of the health-triage and briefing agents (`src/clucktalk/agents/bedrock.py`, boto3 `converse`), which is off by default. In practice: one hello call and a two-call spike on forced tool choice and image input, all with Nova 2 Lite in us-east-1 (`docs/AWS_SETUP.md` sections 5.2 and 5.3). Bedrock was also used read-only to check model availability, inference profiles and quotas (`docs/AWS_SETUP.md` section 5).
2. **What worked well:** once the account gates cleared, the first Nova 2 Lite call answered in `latencyMs` 450 with 57 input and 14 output tokens (`docs/AWS_SETUP.md` section 5.2). A forced `toolChoice` worked with text and with an image: a well-formed `toolUse` both times (FL-020). Amazon's own models such as Nova are not sold through AWS Marketplace, so Nova stayed callable on the AWS India account while the Anthropic models were blocked by their Marketplace agreement (`docs/AWS_SETUP.md`, "Accounts sold by AWS India").
3. **What needs work:**
   - A new account showed Nova 2 Lite and the Claude models as `AVAILABLE` and `AUTHORIZED` while every inference quota was 0; nothing in `get-foundation-model-availability` said so, and only a quota-by-quota comparison showed it (FL-014, FR-006).
   - The AWS Support reply said quotas were "reduced" but gave no numbers and no model list, so a fresh `list-service-quotas` call was the only way to know what was callable (FL-014).
   - The first real call then failed with `AccessDeniedException`, "Your account is currently being verified", a third gate that no read-only check reports (FL-014).
   - After the quota fix, Claude Haiku 4.5 and Claude Sonnet 5 were still blocked: the Anthropic Marketplace agreement stayed `NOT_AVAILABLE`, and Sonnet 5's cross-region tokens-per-minute quota stayed 0 against a default of 6,000,000 (`docs/AWS_SETUP.md` section 5.1).
   - On an AWS India (AISPL) account, a card as the default payment method can make the Marketplace subscription fail ("your Marketplace subscription can fail and model access isn't turned on"); this is only in the Bedrock-Anthropic article, and no page says whether promotional credits cover Marketplace-billed Bedrock models (FL-013, FR-007).
   - Nova 2 Lite read the blue half of a 64x64 synthetic image as "white" (one sample, an observation, not a benchmark), and the Converse reference documents `toolChoice` only as "if supported by model" (FL-020).
   - The official Bedrock price table could not be read by a plain fetch, so the cost was worked out from third-party prices (`docs/AWS_SETUP.md` section 5.2).
4. **Onboarding:** recorded timeline: quotas found at 0 on 28 September; two Support cases opened about 28 September and answered 28 to 29 September; the first call was refused by account verification on 29 September and succeeded on the retry about two hours later (FL-014, `docs/AWS_SETUP.md` section 5.2). Hands-on time was not recorded. Verdict: [BUILDER TO CONFIRM: How did onboarding to Bedrock and Nova 2 Lite feel?]
5. **Build again:** [BUILDER TO CONFIRM: Build with Bedrock and Nova 2 Lite again? Yes or no, and why?]

## 2. AWS CLI v2 and boto3 on Windows

1. **Used for:** the AWS CLI 2.37.4 on Windows 11 for the key-free sign-in through IAM Identity Center (`aws configure sso`, `aws sso login`), the account checks (`aws sts get-caller-identity`, `aws freetier get-account-plan-state`), the Bedrock availability and quota checks, and the hello call. boto3 1.43.103 for the two spike calls and for the server's live path; `botocore.stub.Stubber` in the tests (`docs/AWS_SETUP.md` sections 3 to 5, `docs/VERSIONS.md`).
2. **What worked well:** the CLI signed in through IAM Identity Center with no access keys; the profile stores only session and role names (`docs/AWS_SETUP.md` section 4). `aws freetier get-account-plan-state` showed the account plan (`PAID`, `ACTIVE`) when the console did not (FL-013). The Converse `toolChoice` values and `ImageBlock` formats could be read in the installed botocore service model before any paid call (`docs/VERSIONS.md`).
3. **What needs work:**
   - On Windows, a Converse reply that contained an emoji crashed the CLI's output with a `'charmap' codec` error and left a silently truncated 149-byte file; `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` fixed it (FL-019).
   - `aws billing get-credits` with an IAM Identity Center role answered "IAM user access not activated"; the caller is not an IAM user, and the message does not name the account setting that must be turned on (FL-015).
   - The recommended CLI identity (an IAM Identity Center organization instance) creates an AWS Organization, which upgrades a Free-plan account to Paid; no setup page says so (FL-012).
   - `billing:GetSellerOfRecord` has no CLI command in 2.37.4 (`docs/AWS_SETUP.md` sections 5 and 5.3).
4. **Onboarding:** recorded: the CLI installs for the current user without admin rights from `AWSCLIV2-User.msi`, and at the end of `aws configure sso` CLI 2.37.4 also asked whether to configure AWS skills and the AWS MCP server for coding agents (answered no) (`docs/AWS_SETUP.md` section 4). Verdict: [BUILDER TO CONFIRM: How did installing the AWS CLI and signing in with IAM Identity Center feel?]
5. **Build again:** [BUILDER TO CONFIRM: Use the AWS CLI and boto3 again? Yes or no, and why?]

## 3. AWS Lightsail, AWS App Runner and the AWS Free Tier credits

These were **read or attempted, not used in production**. Nothing in CluckTalk runs on Lightsail or App Runner.

1. **Used for:** choosing where to host the farmer pilot (builder-reported, 7 October 2026). Earlier, the Billing console was used to check the account plan and credits (FL-013).
2. **What worked well:** builder-reported: the AWS Lightsail documentation says that Lightsail is available in the Mumbai Region and that its short free trials were replaced by the AWS Free Tier credits. Recorded: the Billing console showed the account's credits ($120 active, FL-013).
3. **What needs work:**
   - **App Runner (builder-reported, FL-027):** the AWS documentation page "AWS App Runner availability change" states that App Runner stopped accepting new customers on 30 April 2026 and recommends ECS Express Mode. The page's URL was not recorded.
   - **Lightsail (builder-reported):** the documentation says the Mumbai plans include half the data transfer.
   - **Credits (builder-reported):** the hackathon's $150 AWS credit request is a Google Form on the Devpost Resources page; it was submitted on 7 October 2026 and the answer is pending. Recorded earlier: no AWS page states whether promotional credits cover Marketplace-billed Bedrock models (FL-013).
   - **Account plan (recorded):** on the AWS India account the Billing console showed no Free or Paid plan, although the Billing docs say the console home shows it (FL-013, FR-007).
4. **Onboarding:** we lost [BUILDER TO CONFIRM: hours] hours signing in on 7 October because we had created several accounts ourselves; that was our mistake, not AWS's. Verdict: [BUILDER TO CONFIRM: How did choosing AWS hosting and requesting the credits feel?]
5. **Build again:** [BUILDER TO CONFIRM: Try AWS hosting (Lightsail or ECS Express Mode) again? Yes or no, and why?]

## 4. Alexa+ MCP documentation (QuickStart, Local Inspector and related pages)

1. **Used for:** the product target. CluckTalk is a self-hosted MCP server built to Amazon's published Alexa+ guidance. Pages read: the Alexa+ MCP QuickStart (last updated Jul 10, 2026), the Alexa+ Add-on Local Inspector page (last updated Aug 3, 2026), the MCP Toolkit overview, Choose an integration approach, Functional Requirements, the CX testing guide, MCP Toolkit Account Linking, `Alexa.ProactiveNotificationSource`, and "Set Up Your Development Environment" (`docs/SOURCES.md`, FL-009, FL-017, FL-024, FL-026). The Amazon Devices Builder Tools and the Local Inspector were **not** used (builder-reported; the Inspector install needs a Developer Console login, FL-024).
2. **What worked well:** the QuickStart gave the transport (Streamable HTTP), the authentication checklist (OAuth 2.1 with PKCE, Protected Resource Metadata), the 500 ms round-trip requirement, the `addon.json` schema reference and the fact that tool information refreshes only when the add-on is deployed; the Local Inspector page documented an initialize flow that `python tasks.py inspector-replay` replays against our server (`docs/SOURCES.md`).
3. **What needs work:**
   - The Local Inspector and the Alexa AI CLI have no self-serve path for participants: the setup page asks for an AWS account provided to an Alexa Solutions Architect, lists macOS and Ubuntu only, and keeps the Local Inspector install guide behind a Developer Console login (FL-024, FR-004).
   - No page states which MCP protocolVersion Alexa+ sends or requires; the QuickStart names 2025-11-25 only as the version that deprecated HTTP+SSE, and the Local Inspector example sends 2025-06-18 (FL-026).
   - The `addon.json` example lists only `US` in `distributionCountries`, and no page says whether `IN` is allowed for MCP add-ons (FR-008).
   - MCP Apps on Alexa+: no card container size, supported `ui/*` messages, CSP or font policy (Telugu included) (FL-009, FR-002).
   - No statement on whether an MCP add-on can send proactive notifications, or whether a request identifies which household member spoke (FL-017, FR-005).
4. **Onboarding:** [BUILDER TO CONFIRM: How did getting started from the Alexa+ MCP QuickStart feel?]
5. **Build again:** [BUILDER TO CONFIRM: Build an Alexa+ add-on again? Yes or no, and why?]

## 5. The simulated Alexa+ path (our own Simulator)

1. **Used for:** playing the Alexa+ client role while no Alexa+ device could load the add-on: a local web app with Echo Show and Echo Dot modes, voice and text, cards, and a developer panel that shows the exact MCP wire (`src/clucktalk/simulator/`). It is our code, not Amazon's tool.
2. **What worked well:** the Simulator speaks the tool's own text, so the card sentence equals the spoken sentence and every number is the same on both (tested, `tests/crossmodal.py`, `tests/contract/test_card.py`); the golden evals run against a real MCP server over real HTTP (`docs/EVALS.md`).
3. **What needs work:** that equality holds in the Simulator only; on Alexa+ the assistant composes its own speech from the tool result and descriptions, so the words can differ (README, "Voice versus cards"). Its intent layer is rules, not a model (`src/clucktalk/simulator/intents.py`), so it is not a test of how Alexa+ picks a tool.
4. **Onboarding:** not applicable: it is part of this repository and starts with `python tasks.py run`.
5. **Build again:** [BUILDER TO CONFIRM: Build a simulated Alexa+ client again before having device access? Yes or no, and why?]

## 6. MCP Python SDK (`mcp` 2.2.0 and `mcp-types` 2.2.0)

1. **Used for:** the MCP server (`src/clucktalk/server/app.py`: `MCPServer`, `streamable_http_app`, `TransportSecuritySettings`, `mcp.server.apps.Apps`), tool results and middleware, and the protocol-version constants (`docs/VERSIONS.md`).
2. **What worked well:** SDK 2.2.0 ships MCP Apps server support in-core (`_meta.ui.resourceUri`, the `text/html;profile=mcp-app` resource) (`docs/VERSIONS.md`); tool meta, resources and the client's Apps capability work on 2025-11-25 (FL-008); the server answers `initialize` for 2025-11-25, 2025-06-18, 2025-03-26 and 2024-11-05 (`docs/RESULTS.md` section 4).
3. **What needs work:** middleware results skip per-version shaping, so `resultType` leaks onto the 2025-11-25 wire (FL-001); default tool error text names the tool and validation fields, with no hook to change it (FL-002, FR-001); the localhost Origin allow-list accepts every local port (FL-003); the client and the MCP Inspector disagree on whether `outputSchema` applies to `isError` results (FL-004); the server's `extensions` capability is dropped on 2025-11-25 (FL-008); two in-flight requests with the same JSON-RPC id leave one unanswered for at least 40 seconds, with no error (FL-011).
4. **Onboarding:** recorded: the server skeleton was built on the first day, 2026-09-27 (git history; `docs/evidence/2026-09-27_mcp_server_skeleton.md`). Verdict: [BUILDER TO CONFIRM: How did going from zero to a first tool call with the MCP Python SDK feel?]
5. **Build again:** [BUILDER TO CONFIRM: Build with the MCP Python SDK again? Yes or no, and why?]

## 7. MCP Apps (spec 2026-01-26) and its reference host (ext-apps `basic-host`)

1. **Used for:** the four cards in `ui/cards/`, written against the documented postMessage protocol without the JS SDK; the ext-apps `basic-host` (commit 82221c0, v2.0.3) was built and started to test the cards (`docs/evidence/2026-10-01_basic_host/README.md`).
2. **What worked well:** the spec says a view needs no SDK, and the cards speak the protocol directly, so the card side has no Node build and no npm dependency (`docs/VERSIONS.md`); after the workaround in FL-021 the basic-host was built and started and its HTTP-level checks were done, although the four cards have not yet been looked at in a browser through it (`docs/evidence/2026-10-01_basic_host/README.md`).
3. **What needs work:** the spec's example sends `clientInfo` while the schema requires `appInfo` in `ui/initialize` (FL-006); the default CSP has no `font-src`, so even an inlined `data:` font is blocked, while the reference host allows it, and the spec does not say whether a CSP-blocked font source falls through (FL-007, FR-003); the basic-host cannot be built from its README, because the repo root must be built first and bun is needed (FL-021).
4. **Onboarding:** recorded: building the basic-host took about 20 minutes (FL-021). Verdict: [BUILDER TO CONFIRM: How did building MCP Apps cards and running the reference host feel?]
5. **Build again:** [BUILDER TO CONFIRM: Build MCP Apps cards again? Yes or no, and why?]

## 8. MCP Inspector 2.8.0 (CLI)

1. **Used for:** capturing evidence of tool calls and error results (`docs/evidence/`), as the stand-in for the Alexa+ Local Inspector we could not run (FL-024). Not a dependency of the code.
2. **What worked well:** `--method tools/list` and `--method tools/call` captured the evidence in `docs/evidence/2026-09-27_farm_status_and_feed.md`; successful calls exit 0 (FL-005).
3. **What needs work:** on Windows the CLI crashes with a libuv assertion when a call ends in an error, so the exit code cannot be used (FL-005); it validates an error result's `structuredContent` against the success schema, unlike the Python SDK client (FL-004).
4. **Onboarding:** [BUILDER TO CONFIRM: How did getting the MCP Inspector CLI running feel?]
5. **Build again:** [BUILDER TO CONFIRM: Use the MCP Inspector CLI again? Yes or no, and why?]

## 9. Claude Code and the Claude models (building and the independent reviews)

1. **Used for:** writing and checking the code in this repository, and for the independent reviews: after each main feature a fresh agent read the code cold against `docs/DESIGN.md` (`docs/INDEPENDENT_REVIEW.md`). Which Claude model version each session used is not recorded.
2. **What worked well:** the ten recorded review rounds found real defects that were then fixed with regression tests, among them a Critical one in the voice record book (a backdated correction could push total deaths over the birds placed while saying it was saved) and a High one in triage (words that matched no known sign got the lowest urgency) (`docs/INDEPENDENT_REVIEW.md`).
3. **What needs work:** the shell tool changed backslash sequences in commands that wrote files: a `\b` reached a source file as an invisible backspace character, and the problem recurred in later sessions (FL-022, `docs/DEV_NOTES.md`). The reviewers are AI agents, not a human audit (`SECURITY.md`).
4. **Onboarding:** [BUILDER TO CONFIRM: How did starting this project with Claude Code feel?]
5. **Build again:** [BUILDER TO CONFIRM: Build with Claude Code again? Yes or no, and why?]

## 10. The Agent Skills format

1. **Used for:** `skills/clucktalk/`, a `SKILL.md` plus three reference files and an MIT license, which teaches a coding agent how to operate CluckTalk's 14 tools (README, "Agent Skill").
2. **What worked well:** one folder matches the skills layout that Kiro's and Cursor's documentation describe (web search on 2026-10-01); tests keep the skill in step with the server (`tests/unit/test_skill.py`).
3. **What needs work:** each agent uses a different install folder (`.claude/skills/`, `.kiro/skills/`, `.cursor/skills/`, `.github/skills/`), and the GitHub Copilot path was seen only on a third-party page; the skill was never loaded in any agent, so whether each one picks it is unverified (README, "Agent Skill").
4. **Onboarding:** [BUILDER TO CONFIRM: How did writing the Agent Skill feel?]
5. **Build again:** [BUILDER TO CONFIRM: Write an Agent Skill again? Yes or no, and why?]

## 11. Third-party tools that mattered

### Hypothesis 6.168.3 (property and fuzz tests)
1. **Used for:** the property tests (`tests/unit/test_property_*.py`) and the fuzz tests (`tests/contract/test_fuzz_*.py`); a dev dependency only (`docs/VERSIONS.md`).
2. **What worked well:** the fuzz round found the protocol errors that echoed input back (F1 and F2, now short fixed messages), and the fuzz tests pin an SDK behaviour (F3) and our own shed-name reader (F4) (`SECURITY.md`; README, "Known SDK behaviors").
3. **What needs work:** nothing recorded.
4. **Onboarding:** [BUILDER TO CONFIRM: How did adding Hypothesis tests feel?]
5. **Build again:** [BUILDER TO CONFIRM: Use Hypothesis again? Yes or no, and why?]

### Tailscale Funnel (the free hosting tunnel for the farmer pilot)
1. **Used for:** publishing the pilot page from the builder's own Windows PC (builder-reported, 7 October 2026; `docs/PILOT_RUNBOOK_WINDOWS.md`). Only the page port is forwarded; the MCP port stays on the loopback (`docs/ARCHITECTURE.md`).
2. **What worked well:** builder-reported: it worked on the first try after HTTPS certificates and Funnel were enabled in the Tailscale admin console.
3. **What needs work:** recorded: what Tailscale's relay can see was not examined here (`SECURITY.md`), and availability depends on the PC and its internet (`docs/ARCHITECTURE.md`). The runbook's Tailscale commands are from memory of its documentation (`docs/PILOT_RUNBOOK_WINDOWS.md`).
4. **Onboarding:** builder-reported: first try, after the two admin-console settings above.
5. **Build again:** [BUILDER TO CONFIRM: Use Tailscale Funnel again for a pilot like this? Yes or no, and why?]

### GitHub Actions
1. **Used for:** `python tasks.py setup` and `python tasks.py check` on ubuntu and windows with Python 3.12 and 3.13 (`.github/workflows/ci.yml`).
2. **What worked well:** CI caught two problems that the local Windows run did not: a Windows timer lower-bound failure (FL-023) and a card bundle built from a CRLF template (FL-025) (`docs/DEV_NOTES.md`).
3. **What needs work:** the macOS job is manual-only because it uses about 50 quota minutes per run (`.github/workflows/ci.yml`); the repository is private until it is made public (`SECURITY.md`).
4. **Onboarding:** [BUILDER TO CONFIRM: How did setting up GitHub Actions for this repository feel?]
5. **Build again:** [BUILDER TO CONFIRM: Use GitHub Actions again? Yes or no, and why?]

## 12. Other libraries used (no friction recorded)

1. **Used for:** Starlette 1.7.0 and uvicorn 0.54.0 (the ASGI app and its middleware), pydantic 2.13.5 (tool models), jsonschema 4.26.0 (argument validation), httpx2 2.13.1 (the Simulator's MCP client, the contract tests and scripts), SQLite 3.50.4 through Python's `sqlite3` (the farm state), Noto Sans Telugu 2.005 (Telugu on every card), ruff 0.16.9 and pytest 9.1.1 (`python tasks.py check`), and Node.js 24.15.0 for one optional card test (`docs/VERSIONS.md`, `NOTICE`).
2. **What worked well:** nothing beyond use is recorded; no friction-log entry names these, except Noto Sans Telugu under FL-007 (whether a strict host keeps an inlined font).
3. **What needs work:** nothing recorded.
4. **Onboarding:** [BUILDER TO CONFIRM: Anything to add about onboarding for the other libraries, or nothing to add?]
5. **Build again:** [BUILDER TO CONFIRM: Use the other libraries again? Yes or no, and why?]

## Mentioned but not used

Amazon Polly appears in comments as the planned voice of the live Simulator host and is not imported or called. `strands-agents` and `bedrock-agentcore` are listed in `docs/VERSIONS.md` as available, not as dependencies, and are not imported. The `@modelcontextprotocol/ext-apps` JS SDK is not used (`docs/VERSIONS.md`). The Amazon Devices Builder Tools and the Alexa+ Local Inspector were not used (builder-reported; FL-024).
