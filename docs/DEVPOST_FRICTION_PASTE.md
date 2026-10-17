# Friction log: submission copy (full)

Every Alexa+, MCP, MCP Apps and AWS friction we hit while building CluckTalk, a Telugu-first MCP assistant for Indian broiler farmers. Entries are numbered in reading order: Amazon-owned entries first (Entries 1 to 5 are the ones we think Amazon's teams most need), then MCP and MCP Apps entries that matter to Alexa+ developers, then the ones least tied to Amazon. The FL number is the stable id used in `FRICTION_LOG.md`. **Origin** says whose product the friction is about: **Amazon** (Alexa+ docs, AWS and Bedrock), **MCP Apps SDK** (the MCP Apps spec and its reference host) or **third-party MCP SDK** (the Python `mcp` SDK, the MCP spec and the MCP Inspector). Our own tooling notes are not included. Severity is one word, rated from the owner's point of view: Critical (blocks work) · High (major workaround) · Medium (slows work) · Low (annoyance / doc nit).


## Entry 1 (FL-014): New account: Bedrock reports models "AVAILABLE" but every inference quota is 0; after quota cases, a Marketplace agreement and an "account verification" gate still blocked the first call

**Origin:** Amazon · **Tag:** [AWS/Bedrock/Nova] · **Severity:** High · **Date:** 2026-09-28

**Impact:** Blocks every live Bedrock call; the quota fix goes through quota requests and AWS Support with unknown lead time.

Merged from FL-016 and FL-018 (2026-10-01 audit). One story in three stages.

**Tool / service:** Amazon Bedrock (us-east-1), Service Quotas, Bedrock Runtime `converse`, AWS Support (Service Quota increase cases), AWS CLI 2.37.4; new Paid-plan AWS India account (the builder's older AWS account; access to it was later lost, see FL-031)

**Task attempted:** (1) Read-only check that the host model candidates can be called before the first (paid) request. (2) Get Bedrock inference quotas for Claude Haiku 4.5, Sonnet 5 and Nova 2 Lite above 0 in us-east-1. (3) One real (paid) Converse call to Amazon Nova 2 Lite, the one model confirmed both quota-ready and agreement-ready, to prove live Bedrock access end to end, with the account owner's explicit go-ahead.

**Steps taken:** (1) `aws bedrock get-foundation-model-availability` for Nova Lite, Nova 2 Lite, Claude Sonnet 5, Claude Haiku 4.5; then `aws service-quotas list-service-quotas` vs `list-aws-default-service-quotas` for service code `bedrock`. (2) Two Support cases (opened about 28 Sep) replied 28-29 Sep: "Your Amazon Bedrock access has been enabled in the US East (N. Virginia) Region. You can begin using supported models immediately. Your account has been granted access to reduced quotas. Some higher-tier foundation models may not be available at this access level." Re-checked the same day with the CLI. (3) `aws bedrock-runtime converse --model-id us.amazon.nova-2-lite-v1:0 --messages '[{"role":"user","content":[{"text":"Say hello to a poultry farmer in one short sentence."}]}]' --inference-config '{"maxTokens":50}' --region us-east-1 --profile clucktalk`. One attempt, no retry loop.

**Expected vs actual:** (1) Expected a model that reports `agreementAvailability: AVAILABLE`, `authorizationStatus: AUTHORIZED`, `entitlementAvailability: AVAILABLE` (Nova Lite, Nova 2 Lite) to be callable. Actual: the account's applied value is 0 for every on-demand, cross-region and global cross-region requests-per-minute and tokens-per-minute quota of all four models, while the AWS defaults are large (e.g. Claude Sonnet 5 cross-region tokens per minute: default 6,000,000, account 0; Nova Lite on-demand requests per minute: default 2,000, account 0, not adjustable). Nothing in the model availability response or the model access docs mentions it; only a quota-by-quota comparison shows it. (2) Expected either the new quota numbers or a list of which models are now enabled. Actual: the reply confirms access is "enabled" and quotas are "reduced" but states no numbers and no model list, so it cannot be used on its own to know which models are callable; only a fresh `list-service-quotas` call (or a real Converse call) can confirm that. Re-check: Nova 2 Lite got a real nonzero quota (20 req/min, reduced from the default 2,000; 8M tokens/min, the same as the default) and already has its Marketplace agreement: callable, not yet call-tested. Haiku 4.5 also got a real nonzero quota (10 req/min, 5M tokens/min) but its Marketplace agreement is still `NOT_AVAILABLE`: the quota fix did not unblock it. Sonnet 5 cross-region tokens/min is still 0 (default 6,000,000) and its agreement is also `NOT_AVAILABLE`, the "higher-tier" model the reply warned about. (3) Expected a response (the model's quota was nonzero and its Marketplace agreement `AVAILABLE`). Actual: `AccessDeniedException`: "Your account is currently being verified. Verification normally takes less than 2 hours. Until your account is verified, you may not have access to this operation. If you are still receiving this message after more than 2 hours, please let us know by writing to AWS verification support (the address is in the error text)." This is a third gate never mentioned by `get-foundation-model-availability`, `list-service-quotas`, or the two Support replies; none of them surfaces "account verification" as a state, so a read-only check can look fully green and a live call can still fail.

**Workaround:** Request increases for the adjustable quotas and open a Support case for the non-adjustable zeros; re-run the quota comparison after each reply, per model, and also check `get-foundation-model-availability`'s `agreementAvailability` (a fixed quota does not imply a usable Marketplace agreement); for the verification gate, wait and re-check (Amazon's own estimate: under 2 hours; write to AWS verification support if it persists past that). Keep demo mode (no AWS) as the working path meanwhile.

**Actionable suggestion:** Owners: Amazon Bedrock service team (`GetFoundationModelAvailability` and the model access console page); AWS Support (Bedrock quota-increase cases). Return a quota status in `GetFoundationModelAvailability` (for example `inferenceQuotaAvailability: ZERO`) and show 'your account's quota for this model is 0' on the model catalog page. Add a `verificationStatus` next to agreement, authorization, entitlement and Region, so a new account does not have to hit `AccessDeniedException` on a real call to find out. Support replies should state the new applied quota per model and whether the Marketplace agreement is still needed separately. Question to document: what is the expected path from reduced quotas to normal limits for a new account?

**Time cost:** Waiting time recorded: two Support cases opened about 28 Sep, replies 28 to 29 Sep; the account-verification gate had cleared at the retry on 29 Sep after 1:30 PM IST (Amazon's own estimate: under 2 hours). Hands-on time: about 30 minutes (the builder's statement).

**Reproduce:** Commands are in `docs/AWS_SETUP.md` §5 and §5.1: `aws bedrock get-foundation-model-availability`; `aws service-quotas list-service-quotas` against `list-aws-default-service-quotas` for service code `bedrock`; the Converse call is in this entry's Steps. They reproduce only on a new account in the same state.

**Evidence in the repo:** `docs/AWS_SETUP.md` §5, §5.1 and the verification retry notes; `docs/VERSIONS.md`.

**Why this matters to Alexa+ developers:** A new account can look ready (models AVAILABLE, agreements available) and still be refused on the first real call, by quotas set to 0 and by an account-verification gate that no read-only check shows.


## Entry 2 (FL-024): Alexa AI CLI / Local Inspector: no self-serve path for hackathon participants (documentation-based, blocked at the prerequisite, no install was attempted)

**Origin:** Amazon · **Tag:** [Alexa+/MCP] · **Severity:** High · **Date:** 2026-10-01

**Impact:** The official validation path is closed to participants.

**Tool / service:** Alexa+ developer documentation (hackathon Resources page; Alexa+ "Set Up Your Development Environment" page); Alexa AI CLI and Local Inspector

**Task attempted:** Set up the Alexa AI CLI / Local Inspector as a hackathon participant.

**Steps taken:** Read the hackathon Resources page (it does not mention the CLI), then the Alexa+ "Set Up Your Development Environment" page.

**Expected vs actual:** Expected a self-serve path for participants. Actual: step 1 says to use the AWS account that was provided to an Alexa Solutions Architect, to assume a role in an Amazon-owned account and install from a private registry; the prerequisites list macOS or Ubuntu only (we use Windows 11); the Local Inspector install guide sits behind a Developer Console login.

**Workaround:** Used the MCP Inspector, the ext-apps basic-host and our own Simulator.

**Actionable suggestion:** Owners: Alexa+ developer documentation team; the hackathon organizers (Resources page). Add a participant section to the hackathon Resources page that names a self-serve way to run the official validation, or publish the Alexa AI CLI / Local Inspector install guide outside the Developer Console login. Questions to answer there: can a participant without an AWS account provided by an Alexa Solutions Architect use the Alexa AI CLI at all, and does the Local Inspector support Windows 11 (the prerequisites list macOS and Ubuntu only)?

**Time cost:** not recorded

**Reproduce:** documentation-based, no command (blocked at the prerequisite; no install was attempted).

**Why this matters to Alexa+ developers:** Participants have no documented self-serve path to the official validation tool (Alexa AI CLI / Local Inspector).


## Entry 3 (FL-009): Alexa+ docs say MCP Apps render "in the conversation view" but give no container size, supported `ui/*` methods, CSP or fonts

**Origin:** Amazon · **Tag:** [Alexa+/MCP] · **Severity:** Medium · **Date:** 2026-09-27

**Impact:** Card sizes had to be taken from the Alexa Presentation Language (skills) documentation, which does not describe add-on cards.

**Tool / service:** Amazon Alexa+ developer docs (MCP Toolkit overview, Choose an integration approach, Functional Requirements, CX testing guide)

**Task attempted:** Size the farm-status card for Echo Show and phone from official Amazon docs rather than guesses.

**Steps taken:** Read the four Alexa+ pages above; searched developer.amazon.com; fell back to the Alexa Presentation Language (APL) docs for device viewports.

**Expected vs actual:** Expected an Alexa+ MCP Apps rendering profile. Actual: Alexa+ pages state MCP Apps support and the < 500 ms latency requirement, and the CX guide asks for arm's-length legibility on Echo Show (primary), mobile, web and voice-only devices, but none gives the card container's width/height, display modes, the subset of MCP Apps messages Alexa+ supports (e.g. `tools/call` from a card), CSP, or font availability (Telugu included). Device sizes had to come from APL docs (1024x600 px original Echo Show; 1280x800 px at 213 dpi; `hubLandscapeSmall` 960-1279 x 100-599 dp), which describe skills, not add-on cards.

**Workaround:** The card is responsive and was checked at 1024x600, 960x600, 960x480 and a 390x844 phone in the Simulator; tap-to-call is optional (voice gives the same answer).

**Actionable suggestion:** Owner: Alexa+ developer documentation team (MCP Toolkit pages). Publish an 'MCP Apps on Alexa+' page that lists, per device class (Echo Show, phone, web), the card container's width, height and display modes, the supported `ui/*` requests and notifications, the CSP, and the font policy including Indic scripts. Question to answer on that page: is a card-initiated `tools/call` allowed?

**Time cost:** not recorded

**Reproduce:** documentation-based, no command.

**Evidence in the repo:** `docs/evidence/2026-09-27_card_and_simulator.md`; `docs/DESIGN.md` §14; `docs/SOURCES.md`.

**See also:** FL-007 (the spec's default CSP and fonts).

**Why this matters to Alexa+ developers:** Alexa+ docs state MCP Apps support and the under 500 ms latency requirement but give no card size, supported ui/* methods, CSP or font policy, so card sizes had to come from APL device docs.


## Entry 4 (FL-017): Alexa+ docs don't say whether MCP add-ons can send proactive/push notifications, or how they'd distinguish which household member is calling a tool

**Origin:** Amazon · **Tag:** [Alexa+/MCP] · **Severity:** Medium · **Date:** 2026-09-29

**Impact:** Alerts were designed as pull-based only, and worker attribution around separately linked accounts, because push and per-person behaviour for MCP add-ons could not be verified.

**Tool / service:** Amazon Alexa+ developer docs: `Alexa.ProactiveNotificationSource` (device-apis), MCP Toolkit Overview, MCP Toolkit Account Linking (all under developer.amazon.com/docs/alexaplus)

**Task attempted:** Plan an "Owner-Worker mode" (owner assigns tasks by voice while away; a worker at the shed asks "my tasks today?" and marks them done; alerts should reach the owner) without guessing at undocumented behavior.

**Steps taken:** Read the Alexa+ `Alexa.ProactiveNotificationSource` page, the MCP Toolkit overview, and the MCP account-linking page.

**Expected vs actual:** Expected either an MCP-native way to push a notification to the owner, or documentation of how the OAuth 2.1 payload identifies which household member/device made a tool call. Actual: `Alexa.ProactiveNotificationSource` (push-based `Alexa.ChangeReport` announcements, opt-in required, no announcements 10pm–7am local) is documented only for traditional Smart Home add-ons; neither it nor the MCP Toolkit overview says whether an MCP-based add-on can trigger it. The account-linking page says only that "Alexa includes this access token in every request it sends to your add-on"; it does not say whether the token or any other field distinguishes one household member from another, or mentions Household Profiles/Voice ID at all.

**Workaround:** Design alerts as pull-based only (the owner hears them on the next "how is my farm?" / daily briefing, already the plan). Design worker attribution around each person having their own Alexa account/device linked separately (verified: account linking supports one identity per linked account) rather than in-household voice recognition, since the latter is unverified for MCP add-ons.

**Actionable suggestion:** Owner: Alexa+ developer documentation team (MCP Toolkit Overview, MCP Toolkit Account Linking, and the `Alexa.ProactiveNotificationSource` page). Add the answers to these questions to those pages: can an MCP-based add-on trigger proactive notifications, and if so how, given the opt-in and 10 pm to 7 am rules documented for smart-home add-ons? Does the OAuth access token, or any other field in a request, identify which household member or device made a tool call? Does Household Profiles or Voice ID apply to MCP add-ons at all?

**Time cost:** not recorded

**Reproduce:** documentation-based, no command.

**Evidence in the repo:** code comment in `src/clucktalk/server/tools/health.py` (no verified way to push a reminder).

**Why this matters to Alexa+ developers:** Alexa+ docs do not say whether an MCP add-on can send proactive notifications or tell household members apart, so features that depend on either cannot be designed from the docs.


## Entry 5 (FL-013): AWS India (AISPL) account: plan not shown in the console; Claude-on-Bedrock and credit rules scattered or missing

**Origin:** Amazon · **Tag:** [AWS account/credits] · **Severity:** Medium · **Date:** 2026-09-28

**Impact:** The account plan could not be confirmed in the console and was checked with a CLI command; manual payment had to be set before the first Claude call.

**Tool / service:** AWS Billing console (AWS India / AISPL account), AWS Knowledge Center, Amazon Bedrock (Anthropic via AWS Marketplace), AWS promotional credits

**Task attempted:** Confirm the account plan, and whether Claude on Bedrock and promotional credits work for a new AWS India account.

**Steps taken:** Owner checked Billing home, Free Tier, Credits and Account pages; I read the AWS India differences article, the "turn on Anthropic models" article, the credits docs, and searched docs.aws.amazon.com and re:Post.

**Expected vs actual:** Expected the console to show "Free plan" or "Paid plan" as the Billing docs describe ("You can monitor your credit balance and free account plan information in the AWS Billing and Cost Management console home"). Actual: none of those pages shows a plan or an "Upgrade plan" option; credits show ($120 active). The AWS India differences article lists INR billing and manual Marketplace payments but not the Marketplace/RBI card problem, which is only in the Bedrock-Anthropic article ("your Marketplace subscription can fail and model access isn't turned on"; pay manually "within one hour"). No page says whether promotional credits apply to Marketplace-billed Bedrock models or behave differently on AISPL accounts; re:Post has open community questions about exactly this.

**Workaround:** Check the plan with `aws freetier get-account-plan-state` after CLI login; set Pay by Invoice before the first Claude call; check each credit's "Applicable products"; keep Amazon Nova (not sold via Marketplace) as a fallback host model.

**Actionable suggestion:** Owners: AWS Billing and Cost Management console team; AWS India (AISPL) documentation team; Amazon Bedrock documentation team. Billing home: show the account plan for every account; if it is absent for AISPL accounts by design, say so on the 'Choosing a plan' page. India differences article: add the AWS Marketplace card and manual-payment note that today appears only in the Bedrock-Anthropic article. Questions to answer there: do promotional credits apply to Marketplace-billed Bedrock models, and does that differ on AISPL accounts?

**Time cost:** not recorded

**Reproduce:** documentation-based, no command (the plan check that worked is `aws freetier get-account-plan-state`, run after CLI login).

**See also:** FL-012 (the plan decides what the recommended CLI setup does to a new account).

**Why this matters to Alexa+ developers:** A new AWS India account cannot confirm its plan in the console, and no page says whether promotional credits apply to Marketplace-billed Bedrock models.


## Entry 6 (FL-012): New-account setup: the recommended CLI identity silently depends on the account plan; Bedrock-on-Free-plan is undocumented

**Origin:** Amazon · **Tag:** [AWS account/credits] · **Severity:** Medium · **Date:** 2026-09-28

**Impact:** Following the recommended CLI setup would change the account plan, so the plan had to be checked and decided before setup.

**Tool / service:** AWS Billing (Free vs Paid account plan), AWS IAM Identity Center, AWS CLI v2 guide, Amazon Bedrock model access

**Task attempted:** Plan a least-privilege, key-free CLI identity for a brand-new account and check that Bedrock (Anthropic models) is usable, from AWS docs only.

**Steps taken:** Read the AWS CLI guide (recommends IAM Identity Center), the Identity Center instance comparison, the Billing "Choosing a plan" page and the Bedrock "Request access to models" page.

**Expected vs actual:** Expected one page to say what a new Free-plan account must do. Actual: the CLI guide recommends Identity Center; the Identity Center page shows that only an organization instance (in an AWS Organizations management account) gives "single sign-on access to your AWS accounts"; the Billing page says Free plans "automatically upgrade to paid plan if you join AWS Organizations", and are "not eligible for other promotional credits". So following the recommended CLI setup changes the account plan, which no setup page mentions. Separately, the Bedrock model-access page requires AWS Marketplace permissions and a "valid payment method ... for AWS Marketplace purchases" for third-party models, and the Billing page says Free plans exclude "certain AWS Marketplace offers that can incur charges", but no page states whether Anthropic models on Bedrock work on a Free-plan account.

**Workaround:** Check the account plan first; decide on the Paid plan knowingly (budget alerts set), then use an Identity Center organization instance. Verify Bedrock access with a real call rather than from docs.

**Actionable suggestion:** Owners: AWS CLI User Guide, IAM Identity Center getting-started and AWS Billing 'Choosing a plan' page teams. Add a 'new account' note to the first two pages (enabling AWS Organizations upgrades a Free-plan account), and add a table to the plan page listing which Bedrock model providers are usable on the Free plan.

**Time cost:** not recorded

**Reproduce:** documentation-based, no command.

**See also:** FL-013 (the account plan is also not shown in the console for an AWS India account).

**Why this matters to Alexa+ developers:** Following the recommended AWS CLI setup can change a new account's plan, and no page says whether Anthropic models on Bedrock work on a Free plan.


## Entry 7 (FL-019): AWS CLI (Windows) crashes writing a Bedrock Converse response to a file if the model's text contains certain Unicode (an emoji), truncating the output with no clear signal

**Origin:** Amazon · **Tag:** [AWS/Bedrock/Nova] · **Severity:** Medium · **Date:** 2026-09-29

**Impact:** The usage counts of that call were lost and the identical call was run a second time to capture a clean reply.

**Tool / service:** AWS CLI 2.37.4 on Windows, `aws bedrock-runtime converse`, redirecting `--output json` to a file

**Task attempted:** The first real (paid) Converse call to Amazon Nova 2 Lite (`us.amazon.nova-2-lite-v1:0`, us-east-1), after Bedrock access was confirmed quota- and agreement-ready (FL-014) and the earlier "account verification" gate (FL-014) had cleared.

**Steps taken:** `aws bedrock-runtime converse --model-id us.amazon.nova-2-lite-v1:0 --messages '[{"role":"user","content":[{"text":"Say hello to a poultry farmer in one short sentence."}]}]' --inference-config '{"maxTokens":50}' --region us-east-1 --profile clucktalk --output json > result.json`, redirected on Windows (Git Bash).

**Expected vs actual:** Expected either a clean JSON file or a clear top-level error. Actual: the API call itself succeeded (confirmed by re-running with the fix below and by the exit code), but the CLI crashed while serializing the response to the redirected file: `[ERROR]: 'charmap' codec can't encode character '\U0001f414' in position 79: character maps to <undefined>`. Nova 2 Lite's reply apparently included a 🐔 emoji, and the CLI's default Windows output encoding (cp1252/"charmap") can't represent it. The file was left silently truncated mid-write (149 bytes, cut off inside the `"text":` value) with no indication in the truncated file itself that anything was wrong; only the stderr line revealed the cause. `usage`/token counts were lost for that call since the write never reached them.

**Workaround:** Re-ran the identical call with `PYTHONIOENCODING=utf-8 PYTHONUTF8=1` set (the CLI is Python-based): clean output, exit 0, full `usage` block.

**Actionable suggestion:** Owner: AWS CLI team (Windows output encoding; `aws bedrock-runtime converse` output). Default to UTF-8 for redirected output on Windows, or document `PYTHONIOENCODING` / `PYTHONUTF8` on the CLI's output/Windows page. Write the response to a temporary file and rename it on success, or fail before writing anything, so a failed serialization never leaves a truncated file.

**Time cost:** not recorded

**Reproduce:** The command in this entry's Steps (`aws bedrock-runtime converse ... --output json > result.json`) on Windows. It fails only when the model's reply contains a character that cp1252 cannot encode, so it depends on the model's wording.

**Evidence in the repo:** `docs/AWS_SETUP.md`; `docs/VERSIONS.md`.

**Why this matters to Alexa+ developers:** On Windows the AWS CLI can silently truncate a Bedrock response file when the model's reply contains an emoji.


## Entry 8 (FL-015): CLI billing call says "IAM user access not activated" to an IAM Identity Center role

**Origin:** Amazon · **Tag:** [AWS account/credits] · **Severity:** Low · **Date:** 2026-09-28

**Impact:** The credits could not be read from the CLI with the least-privilege role; they were read in the console as root instead.

**Tool / service:** AWS CLI 2.37.4 `aws billing get-credits`, IAM Identity Center permission set with `billing:GetCredits`

**Task attempted:** Read the account's credits from the CLI with a least-privilege SSO role.

**Steps taken:** `aws billing get-credits --account-id <id> --start-date <epoch>` with profile `clucktalk` (role CluckTalkVerify, which allows `billing:GetCredits`).

**Expected vs actual:** Expected the credits, or an error naming the account setting to change. Actual: `AccessDeniedException ... IAM user access not activated`. The caller is not an IAM user; the needed switch is the account setting "IAM user and role access to Billing information" (root only), which the message does not name.

**Workaround:** Read credits in the Billing console as root; activation is optional for this project.

**Actionable suggestion:** Owner: AWS Billing team (the `GetCredits` error message). Name the setting and where to turn it on in the error: 'IAM user and role access to Billing information is off for this account; the root user can activate it on the Account page'.

**Time cost:** not recorded

**Reproduce:** `aws billing get-credits --account-id <account id> --start-date <epoch seconds> --profile <IAM Identity Center profile>` with a permission set that allows `billing:GetCredits` (account-specific; the root user has not activated IAM access to Billing).

**Evidence in the repo:** `docs/AWS_SETUP.md`.

**Why this matters to Alexa+ developers:** The billing error names the wrong cause ('IAM user') for a caller that is an Identity Center role, and does not name the account setting to change.


## Entry 9 (FL-020): Nova 2 Lite accepts image input with a forced tool call, but misread a solid blue area as "white" on a tiny synthetic image

**Origin:** Amazon · **Tag:** [AWS/Bedrock/Nova] · **Severity:** Low · **Date:** 2026-09-29

**Impact:** For CluckTalk, photo triage was already designed as advisory below a deterministic safety floor, so little was lost.

**Tool / service:** Amazon Bedrock Runtime `Converse` (boto3 1.43.103), `us.amazon.nova-2-lite-v1:0`, us-east-1

**Task attempted:** Verify, before building photo triage, that Nova 2 Lite takes image input together with a forced `toolChoice` (botocore documents `toolChoice` only as "If supported by model").

**Steps taken:** Two one-off paid calls (a budgeted spike). Call 1, text only, `toolChoice: {"tool": {"name": "report_colours"}}`, enum-only schema: correct `toolUse` (`left: red, right: blue`), 997 input / 35 output tokens. Call 2: the same tool plus a synthetic 64x64 PNG generated locally (left half RGB 220,30,30; right half RGB 30,60,220), `temperature 0`.

**Expected vs actual:** Expected `left: red, right: blue`. Actual: a well-formed forced `toolUse` with `left: red, right: white` (1,231 input / 35 output tokens, 456 ms). Image input and forced tool use both work; the colour answer for a flat, saturated blue area was wrong. One sample at a very small resolution, so this is an observation, not a benchmark.

**Workaround:** Photo findings may only add signs, never lower urgency; the spike was stopped at this first wrong answer, as agreed. Photo triage (step 1B) will be tested on real, licensed photos at a realistic resolution before any claim is made.

**Actionable suggestion:** Owner: Amazon Bedrock documentation team (Nova 2 Lite image-understanding page; Converse API reference, `toolChoice`). State the minimum and recommended image resolution for image understanding, and list which models support the `tool` choice (it worked here, but the reference says only 'if supported by model').

**Time cost:** not recorded

**Reproduce:** documentation-based, no command (two paid one-off calls; parameters in `docs/AWS_SETUP.md` §5.3; not repeated without approval).

**Evidence in the repo:** `docs/AWS_SETUP.md`; `docs/DESIGN.md` §18; `src/clucktalk/agents/bedrock.py`.

**Why this matters to Alexa+ developers:** Nova 2 Lite took image input with a forced tool call, but misread a colour in one small test, and the Converse docs do not say which models support forced tool choice.


## Entry 10 (FL-026): Alexa+ docs do not state which MCP protocolVersion Alexa+ sends or requires, and the Local Inspector example uses a different one than the track asks for

**Origin:** Amazon · **Tag:** [Alexa+/MCP] · **Severity:** Low · **Date:** 2026-10-04

**Impact:** A builder cannot tell which version Alexa+ negotiates, or whether a server should refuse older versions.

**Tool / service:** Alexa+ developer documentation: Alexa+ MCP QuickStart (section "MCP requirements for Alexa+", last updated Jul 10, 2026) and Alexa+ Add-on Local Inspector (step "Initialize the MCP session", last updated Aug 3, 2026); our server on MCP Python SDK 2.2.0

**Task attempted:** Connect an MCP server to Alexa+ following the documentation and decide which MCP protocolVersion to implement.

**Steps taken:** Read the QuickStart page (section "MCP requirements for Alexa+") and the Local Inspector page (step "Initialize the MCP session"); both were read by the project owner. Compared them with what our own server answers.

**Expected vs actual:** Expected the docs to state which protocolVersion Alexa+ and the Local Inspector send or require. Actual: the QuickStart names the 2025-11-25 specification only as the version that deprecated the standalone HTTP+SSE transport and states no minimum protocolVersion; the Local Inspector example initialize request sends protocolVersion 2025-06-18 with clientInfo name addon-local-inspector. (The hackathon track rules, read separately, ask for 2025-11-25 or later.)

**Workaround:** Our server implements 2025-11-25 and answers older versions with the version the client asked for. `python tasks.py probe-protocol-version` prints OUR server's answers and `python tasks.py inspector-replay` replays the documented flow; neither shows Amazon's behavior.

**Actionable suggestion:** Owner: Alexa+ MCP Toolkit documentation team. State the minimum and the negotiated protocolVersion on the QuickStart page, say whether servers should accept or refuse older versions, and align the Local Inspector example with that statement.

**Time cost:** not recorded

**Reproduce:** documentation-based, no command (plus `python tasks.py probe-protocol-version` and `python tasks.py inspector-replay` for our own server only).

**Evidence in the repo:** `docs/SOURCES.md` (both pages); `tests/contract/test_protocol_conformance.py`; `scripts/probe_protocol_version.py`; `scripts/inspector_replay.py`.

**Why this matters to Alexa+ developers:** The docs give a builder no protocolVersion to implement or to refuse, and the Local Inspector example uses a different one than the hackathon track asks for, so a builder cannot tell which one to follow.


## Entry 11 (FL-027): AWS App Runner no longer accepts new customers (since 30 April 2026); the documentation recommends ECS Express Mode

**Origin:** Amazon · **Tag:** [AWS App Runner docs] · **Severity:** Low · **Date:** 2026-10-07

**Impact:** App Runner was not an option for this project.

**Tool / service:** AWS App Runner; the AWS documentation page "AWS App Runner availability change". Builder-reported; no command output exists in the repository.

**Task attempted:** Choose a hosting service for the farmer pilot.

**Steps taken:** Read the AWS documentation page "AWS App Runner availability change" while comparing hosting options.

**Expected vs actual:** Expected App Runner to be available to a new customer. Actual: the page states that App Runner stopped accepting new customers on 30 April 2026 and recommends ECS Express Mode.

**Workaround:** App Runner was not used. The farmer pilot is hosted on the builder's own PC through a free Tailscale Funnel (builder-reported).

**Actionable suggestion:** Owner: the AWS App Runner documentation team. Question: is the 30 April 2026 change shown at the top of every App Runner getting-started page, with the link to ECS Express Mode?

**Time cost:** not recorded

**Reproduce:** documentation-based, no command.

**Evidence in the repo:** none (builder-reported, 7 October 2026). Doc URL: not recorded.

**Why this matters to Alexa+ developers:** An Alexa+ add-on needs a reachable HTTPS endpoint (`docs/PRODUCTION_PATH.md`, item 3), and App Runner, one of the AWS hosting options a builder may look at first, no longer takes new customers.


## Entry 12 (FL-033): Alexa+ in India is press-reported to support English, Hindi and Hinglish; Telugu is not listed and no timeline for more languages was given, so a Telugu-first add-on cannot be tested by voice on the platform

**Origin:** Amazon · **Tag:** [Alexa+/MCP] · **Severity:** Medium · **Date:** 2026-10-18

**Impact:** A Telugu-first add-on cannot be tested by voice on the platform.

**Tool / service:** Alexa+ launch in India, as described in launch coverage (Medianama and Business Standard, September 2026). Press-reported, not verified with Amazon.

**Task attempted:** Find out whether a Telugu-first add-on can be tested by voice on Alexa+.

**Steps taken:** Read the launch coverage of Alexa+ in India. The article URLs are not recorded here.

**Expected vs actual:** Expected a published list of the languages and locales an add-on can use. Actual (as reported): Alexa+ in India supports English, Hindi and Hinglish; Telugu is not listed, and no timeline for more languages was given.

**Workaround:** CluckTalk uses written Telugu, the Simulator and the MCP Inspector instead. The Simulator's microphone is the browser's English speech recognition; there is no Telugu speech recognition and no spoken Telugu reply.

**Actionable suggestion:** Owner: the Alexa+ product and documentation teams. Publish the supported-locale list for add-ons and a roadmap for regional languages.

**Time cost:** not recorded

**Reproduce:** documentation-based (press coverage), no command.

**Evidence in the repo:** none (press-reported; not verified with Amazon).

**Why this matters to Alexa+ developers:** A builder for a regional language cannot tell from the documentation whether the add-on can be spoken to on Alexa+ at all.


## Entry 13 (FL-007): MCP Apps default CSP has no `font-src`, so even an inlined (data:) font is blocked; the reference host allows it; the spec does not say whether a CSP-blocked `@font-face` source falls through

**Origin:** MCP Apps SDK · **Tag:** [MCP Apps] · **Severity:** Medium · **Date:** 2026-09-27

Merged from FL-010 (2026-10-01 audit).

**Tool / service:** MCP Apps extension spec 2026-01-26 ("Host Behavior", restrictive default CSP, `resourceDomains`) vs ext-apps `examples/basic-host/serve.ts`; MDN `@font-face` `src` and CSP `font-src` pages; Google Chrome 153.0.8010.53

**Task attempted:** Bundle Noto Sans Telugu in the card so Telugu renders identically on every device (Indic system fonts vary), and plan how the card keeps its bundled font on a host that applies the spec's default CSP literally: inlined `data:` font first, a declared https copy second.

**Steps taken:** Read the spec's mandatory default CSP and the reference host's CSP builder. Read the spec (`resourceDomains` maps to `font-src`; hosts "MUST NOT allow undeclared domains") and MDN (`font-src` falls back to `default-src`; the browser uses "the first one it can successfully activate"); neither says whether a source blocked by CSP counts as a failed source. Built a strict-CSP mode into the Simulator's sandbox proxy and a probe, and ran it in headless Chrome.

**Expected vs actual:** Expected a documented way for a card to ship its own font, and a documented answer on fall-through. Actual: the spec default is `default-src 'none'` with no `font-src`, so fonts fall back to `'none'` (data: URIs included), and `resourceDomains` only accepts origins. The reference host instead sends `font-src 'self' data: blob:`. A card that bundles a font works on the reference host and may silently lose it on a strict host. No documentation answers the fall-through question; the answer had to come from a test. Chrome 153 falls through: `font-src` violation for `data`, then the https entry loads; on a permissive CSP the https copy is never fetched. Other engines (WebKit, Firefox) and the Alexa+ renderer are untested.

**Workaround:** The card inlines the font as data: URIs, falls back to system Telugu fonts (Nirmala UI, Gautami) in CSS, and reports a `notifications/message` warning when its bundled font did not load. The card lists the inlined font first and the declared https copy second. The Simulator follows the reference host (`font-src 'self' data:`) and says so in `docs/DESIGN.md` §15.

**Actionable suggestion:** Owners: MCP Apps (ext-apps) specification maintainers (CSP section) and MDN. In the spec's default CSP add `font-src 'self' data:` (fonts cannot exfiltrate data), or a declared `fontDomains` / inline-fonts field in `McpUiResourceCsp`, and add a short 'Fonts' note on how a view ships a custom or non-Latin font under the default CSP. MDN `@font-face` `src` page: state that a source blocked by CSP is treated like a failed load. Questions for the Alexa+ team: does the Alexa+ renderer apply the spec's default CSP literally, and does it provide Telugu and other Indic fonts through `hostContext.styles.css.fonts`?

**Time cost:** not recorded

**Reproduce:** Strict-CSP probe: `.venv\Scripts\python docs\evidence\2026-09-28_strict_csp\font_probe.py 8799`, then `chrome --headless=new --virtual-time-budget=8000 --dump-dom "http://127.0.0.1:8799/probe?case=<name>"` (needs network access to fonts.gstatic.com; the result is the JSON in `<pre id="out">`). In the Simulator: URL option `?csp=strict`.

**Evidence in the repo:** `docs/evidence/2026-09-28_strict_csp.md`; `docs/evidence/2026-09-27_card_and_simulator.md`; `docs/DESIGN.md` §14 and §15; `docs/evidence/2026-10-01_basic_host/README.md`.

**See also:** FL-009 (Alexa+ publishes no CSP or font policy for MCP Apps).

**Why this matters to Alexa+ developers:** A card that bundles a Telugu font works on the reference host but may silently lose it on a host that applies the spec's default CSP, and Alexa+ font availability is not published (FL-009).


## Entry 14 (FL-002): Default tool error text includes the tool name and validation details

**Origin:** third-party MCP SDK · **Tag:** [Alexa+/MCP] · **Severity:** Medium · **Date:** 2026-09-27

**Tool / service:** MCP Python SDK `mcp` 2.2.0 (`MCPServer` tool errors) vs Amazon Alexa+ MCP tool design guidance

**Task attempted:** Meet the Alexa+ guidance that tool errors are customer-safe (no codes, tool names, or JSON spoken).

**Steps taken:** Read `mcp/server/mcpserver/tools/base.py` and `server.py` `_handle_call_tool`.

**Expected vs actual:** Expected a hook for the user-facing error text. Actual: an unexpected exception becomes `"Error executing tool <name>"`, and argument-validation failures return pydantic text with field names, as `isError` content that a voice host may read aloud. No option changes this.

**Workaround:** A `tools/call` middleware validates arguments against the advertised `inputSchema` itself and replaces any non-contract error with a bilingual safe message (original text logged server-side only). 8 of 8 mutation checks confirm the contract tests catch regressions.

**Actionable suggestion:** Owner: MCP Python SDK maintainers (`MCPServer`; `_handle_call_tool` in `mcp/server/mcpserver/server.py`). Add an `MCPServer(tool_error_formatter=...)` hook (or a documented `on_tool_error` callback) that receives the tool name, the error kind and the exception and returns the `CallToolResult` to send, so voice and other consumer hosts can supply safe wording without re-validating arguments in middleware. Question for the Alexa+ team: is a tool error's `content` spoken as is, or does Alexa+ word its own answer?

**Time cost:** not recorded

**Reproduce:** documentation-based, no command (found by reading `mcp/server/mcpserver/tools/base.py` and `server.py`).

**Evidence in the repo:** `docs/VERSIONS.md`.

**Why this matters to Alexa+ developers:** Alexa+ guidance says tool errors must be customer-safe, but the SDK default puts the tool name and validation details in error text that a voice host may read aloud.


## Entry 15 (FL-004): Unclear whether `outputSchema` applies to `isError` results; SDK and Inspector disagree

**Origin:** third-party MCP SDK · **Tag:** [Alexa+/MCP] · **Severity:** Medium · **Date:** 2026-09-27

**Tool / service:** MCP spec 2025-11-25 (Tools, Output Schema), MCP Python SDK 2.2.0 client, MCP Inspector 2.8.0 CLI

**Task attempted:** Return a bilingual structured error (`isError: true` + `structuredContent.error`) from tools that declare an `outputSchema`.

**Steps taken:** Called `get_farm_status` with an unknown shed via the Python SDK client, then via `mcp-inspector --cli ... --method tools/call`.

**Expected vs actual:** Expected consistent client behavior. Actual: the Python SDK client skips output validation when `isError` is true (`mcp/client/session.py`), but Inspector 2.8.0 validated the error's `structuredContent` against the success schema and rejected it ("data must have required property 'text_en' ..."). The spec says "Servers MUST provide structured results that conform to this schema" with no statement about error results; its error example has only `content`.

**Workaround:** Errors now carry no `structuredContent`; bilingual details go in `_meta["clucktalk/error"]`, spoken text stays in `content`. Contract test asserts error results have no `structuredContent`.

**Actionable suggestion:** Owners: MCP specification maintainers (Tools page, Output Schema section), MCP Python SDK maintainers (`mcp/client/session.py`) and MCP Inspector maintainers. State in the Tools spec whether `outputSchema` constrains `isError` results (or add an optional `errorSchema`), then align the SDK client and the Inspector CLI with that rule.

**Time cost:** not recorded

**Reproduce:** documentation-based, no command (our server no longer returns `structuredContent` on error results, so the Inspector rejection cannot be shown on it).

**Evidence in the repo:** `docs/evidence/2026-09-27_mcp_server_skeleton.md`; `docs/evidence/2026-09-27_farm_status_and_feed.md`.

**Why this matters to Alexa+ developers:** The SDK client and the Inspector disagree on whether an error result must match the tool's output schema, so a structured error can be rejected by one and accepted by the other.


## Entry 16 (FL-001): Middleware results skip per-version shaping, so `resultType` leaks onto the 2025-11-25 wire

**Origin:** third-party MCP SDK · **Tag:** [Alexa+/MCP] · **Severity:** Medium · **Date:** 2026-09-27

**Tool / service:** MCP Python SDK `mcp` 2.2.0 (server `ServerMiddleware`)

**Task attempted:** Return a customer-safe `CallToolResult` from a server middleware on `tools/call` for a client that negotiated protocol 2025-11-25.

**Steps taken:** Middleware returned a `mcp_types.CallToolResult` model; called it with curl after an `initialize` at 2025-11-25.

**Expected vs actual:** Expected the same wire shape as a normal tool result (no `resultType`; the SDK strips it for handler results on legacy connections). Actual: the response contained `"resultType":"complete"`, a 2026-07-28 field. `mcp/server/runner.py` says a short-circuiting middleware "is trusted to return its own well-formed result" and never reshapes it.

**Workaround:** Dump the model ourselves with `exclude={"result_type"}` before returning it from the middleware; contract test `test_no_2026_fields_on_the_2025_11_25_wire` guards it.

**Actionable suggestion:** Owner: MCP Python SDK maintainers (`mcp/server/runner.py`, `ServerMiddleware`). Run middleware return values through the same per-version serializer as handler results (or expose a public `serialize_for(version, method, result)` helper), and state in the `ServerMiddleware` docstring that returned models are not version-shaped.

**Time cost:** not recorded

**Reproduce:** Test that pins the behaviour (our workaround): `.venv\Scripts\python -m pytest -q tests\contract\test_tools.py::test_no_2026_fields_on_the_2025_11_25_wire`. The SDK behaviour itself is in `mcp/server/runner.py`; no command shows it without removing the workaround.

**Evidence in the repo:** contract test `test_no_2026_fields_on_the_2025_11_25_wire`; `docs/VERSIONS.md`.

**Why this matters to Alexa+ developers:** A customer-safe error returned from server middleware carries a 2026-07-28 field onto the 2025-11-25 wire unless the server strips it itself.


## Entry 17 (FL-008): On a 2025-11-25 connection, SDK 2.2.0 drops the server's `capabilities.extensions`, so the Apps extension is invisible in `initialize`

**Origin:** third-party MCP SDK · **Tag:** [MCP Apps] · **Severity:** Low · **Date:** 2026-09-27

**Tool / service:** MCP Python SDK `mcp` 2.2.0 (`mcp.server.apps.Apps`, `MCPServer(extensions=[...])`)

**Task attempted:** Serve the farm-status card through the SDK's MCP Apps extension on the 2025-11-25 wire.

**Steps taken:** Scratch probe over real HTTP: `initialize` (with and without the client's `io.modelcontextprotocol/ui` extension), `tools/list`, `resources/list`, `resources/read`, `tools/call` with `client_supports_apps(ctx)`.

**Expected vs actual:** Expected the server's `initialize` result to include `capabilities.extensions["io.modelcontextprotocol/ui"]`, which `_apply_extension` registers. Actual: the result has `experimental`, `prompts`, `resources`, `tools` only (the 2025-11-25 `ServerCapabilities` model has no `extensions` field). Everything else works: tool `_meta.ui.resourceUri`, the `text/html;profile=mcp-app` resource with `_meta.ui`, and `client_supports_apps` reading the client's capability. So the server reads the client's extension capability but cannot declare its own on this version.

**Workaround:** None needed for hosts that discover cards via tool `_meta.ui.resourceUri` (the spec's mechanism). Contract tests pin the tool meta and resource shape.

**Actionable suggestion:** Owner: MCP Python SDK maintainers (`mcp.server.apps`). Document which protocol versions carry the server's `extensions` capability, or pass it through under `experimental` on pre-2026 versions.

**Time cost:** not recorded

**Reproduce:** documentation-based, no command (found with a scratch probe that was not saved).

**Evidence in the repo:** `docs/evidence/2026-09-27_card_and_simulator.md`; `docs/VERSIONS.md`.

**Why this matters to Alexa+ developers:** On a 2025-11-25 connection a server cannot declare the Apps extension in its initialize result; hosts must discover cards through the tool's _meta.ui.resourceUri.


## Entry 18 (FL-003): Localhost default Origin allow-list accepts every localhost port

**Origin:** third-party MCP SDK · **Tag:** [Alexa+/MCP] · **Severity:** Low · **Date:** 2026-09-27

**Tool / service:** MCP Python SDK `mcp` 2.2.0 (`streamable_http_app` transport security defaults)

**Task attempted:** Validate `Origin` on the local Streamable HTTP server (spec: invalid Origin → 403).

**Steps taken:** Read `mcp/server/lowlevel/server.py` `streamable_http_app`.

**Expected vs actual:** Expected the default to allow only the server's own origin. Actual: for a localhost host the SDK auto-allows `http://127.0.0.1:*`, `http://localhost:*`, `http://[::1]:*`, so any page served from any local port (another dev server, a compromised local tool) passes the Origin check.

**Workaround:** Pass explicit `TransportSecuritySettings` with our own host:port allow-list; contract test `test_other_localhost_port_origin_is_403` guards it.

**Actionable suggestion:** Owner: MCP Python SDK maintainers (`streamable_http_app`, `TransportSecuritySettings`). Default the localhost allow-list to the bound port, or document the wildcard prominently next to `TransportSecuritySettings`.

**Time cost:** not recorded

**Reproduce:** Test that pins the behaviour (our workaround): `.venv\Scripts\python -m pytest -q tests\contract\test_transport.py::test_other_localhost_port_origin_is_403`.

**Evidence in the repo:** contract test `test_other_localhost_port_origin_is_403`; `docs/VERSIONS.md`.

**Why this matters to Alexa+ developers:** On a local MCP server, a page served from any local port passes the SDK's default Origin check.


## Entry 19 (FL-006): MCP Apps spec example sends `clientInfo` in `ui/initialize`, but the schema requires `appInfo`

**Origin:** MCP Apps SDK · **Tag:** [MCP Apps] · **Severity:** Low · **Date:** 2026-09-27

**Tool / service:** MCP Apps extension spec 2026-01-26 (`specification/2026-01-26/apps.mdx`) vs `src/spec.types.ts` in modelcontextprotocol/ext-apps (main)

**Task attempted:** Write the farm-status card against the documented postMessage protocol without the JS SDK (the spec says "you don't need an SDK").

**Steps taken:** Followed the "Transport Layer" example, then cross-checked the field names in `spec.types.ts`.

**Expected vs actual:** Expected the example to match the schema. Actual: the example calls `sendRequest("initialize", {capabilities: {}, clientInfo: {...}, protocolVersion: "2026-01-26"})`, while `McpUiInitializeRequest` is method `ui/initialize` with required params `appInfo`, `appCapabilities`, `protocolVersion`. A host that validates against the schema would reject a view written from the example.

**Workaround:** The card sends `ui/initialize` with `appInfo` + `appCapabilities` + `protocolVersion`, as in the types file; the Simulator's developer panel logs what the card sent.

**Actionable suggestion:** Owner: MCP Apps (ext-apps) specification maintainers (`specification/2026-01-26/apps.mdx`, the 'Transport Layer' example). Change the example to `ui/initialize` with `appInfo`, `appCapabilities` and `protocolVersion`, and add a check of the spec's examples against `spec.types.ts` to the repo's CI.

**Time cost:** not recorded

**Reproduce:** documentation-based, no command.

**Why this matters to Alexa+ developers:** A card written from the spec's own example would be rejected by a host that validates against the schema.


## Entry 20 (FL-011): Two in-flight requests with the same JSON-RPC id on one session: the SDK silently never answers one

**Origin:** third-party MCP SDK · **Tag:** [Alexa+/MCP] · **Severity:** Medium · **Date:** 2026-09-28

**Impact:** One request can stay unanswered for at least 40 seconds (the longest we waited; the test itself waits 3 s) and holds its connection open. The session and every other request keep working, and the session can still be ended. CluckTalk's own confirmation flow was not affected. On one CI run (Windows, Python 3.13, 2026-10-03) the second request was answered at once with HTTP 500 "Session terminated before the request completed" instead: the first request's clean-up had closed the stream they share.

**Tool / service:** MCP Python SDK `mcp` 2.2.0, server Streamable HTTP transport (`json_response=True`), protocol 2025-11-25

**Task attempted:** Contract test that a repeated "yes" (the same `set_farm_mode` confirmation sent 5 times at once, as a retrying host might) is applied only once.

**Steps taken:** 5 concurrent `tools/call` POSTs on one `Mcp-Session-Id`, all with JSON-RPC `id: 2` (a test-client mistake). Repeated with a read-only tool, and with distinct ids.

**Expected vs actual:** Expected every POST to be answered, or a JSON-RPC error for the duplicate id. Actual: only 1-2 of the 5 POSTs got a response; the others hung until the client's 10 s timeout, with no server log line, for read-only tools too. (Step 48C: with two overlapping requests the second was still unanswered after 40 s.) With distinct ids all 5 answered in 13-29 ms. Cause in source: `mcp/server/streamable_http.py` stores each POST's response stream in `self._request_streams[request_id]` (line 645) without checking for an in-flight request with that id, so the later POST overwrites the earlier one's stream. The spec forbids reusing an id in a session, so the client was wrong, but the failure is a silent hang.

**Workaround:** The test client now gives every concurrent request its own id. CluckTalk's confirmation flow still applied the change exactly once in the hanging run (1 applied, the answered repeats replayed).

**Actionable suggestion:** Owner: MCP Python SDK maintainers (`mcp/server/streamable_http.py`, where the response stream is stored per request id). Reject a request whose id is already in flight on the session with a JSON-RPC error (-32600, 'duplicate request id') instead of overwriting the pending stream, and log a warning.

**Time cost:** not recorded

**Reproduce:** `tests\contract\test_concurrency.py::test_two_overlapping_requests_with_the_same_id_leave_one_unanswered_pinned_finding`; run it with `.venv\Scripts\python -m pytest -q tests\contract\test_concurrency.py::test_two_overlapping_requests_with_the_same_id_leave_one_unanswered_pinned_finding`. The cause is in `mcp/server/streamable_http.py`, line 645 in `mcp` 2.2.0.

**Evidence in the repo:** `tests/contract/test_concurrency.py`; `docs/evidence/2026-09-28_farm_profile.md`.

**Why this matters to Alexa+ developers:** A retrying host that reuses a JSON-RPC id on one session can leave requests unanswered with no server log line.


## Entry 21 (FL-021): ext-apps basic-host cannot be built with `npm ci --ignore-scripts`: it needs the unbuilt repo root, bun, and bun's postinstall

**Origin:** MCP Apps SDK · **Tag:** [MCP Apps] · **Severity:** Low · **Date:** 2026-10-01

**Impact:** A documentation gap.

**Tool / service:** `modelcontextprotocol/ext-apps` (commit 82221c0, v2.0.3) `examples/basic-host`, npm 11.12.1, Node 24.15.0, Windows 11

**Task attempted:** Build and start the reference MCP Apps host to test our four cards, installing with `--ignore-scripts` as a precaution.

**Steps taken:** Read `examples/basic-host/README.md` (says `npm install`, `npm run start`). Ran `npm ci --ignore-scripts` (first only for the `basic-host` workspace, then the whole repo), then `npm run build` in `examples/basic-host`.

**Expected vs actual:** Expected a working build from the README. Actual: `tsc` failed with `Cannot find module '@modelcontextprotocol/ext-apps'` (TS2307) plus cascading implicit-any errors, because that dependency is a workspace link to the repo root, which has no `dist/` until its own `npm run build` runs (normally from the root `prepare` script). That build needs `bun`; the `bun` npm package then refuses to run ("Bun's postinstall script was not run") under `--ignore-scripts`. The README does not mention bun, the root build, or that `npm run start` (`bun --watch serve.ts`) also needs bun.

**Workaround:** `npm ci --ignore-scripts`, then run only `node node_modules/bun/install.js`, then `npm run build` at the root, then `npm run build` in `examples/basic-host`, then `npm run serve`.

**Actionable suggestion:** Owner: ext-apps maintainers (`examples/basic-host/README.md` and its `package.json` scripts). State that the repo root must be built first and that bun is required, or ship a prebuilt host, and make `npm run start` work without a globally installed bun.

**Time cost:** About 20 minutes.

**Reproduce:** The commands in `docs/evidence/2026-10-01_basic_host/README.md` ('Commands'). The failing step is `npm ci --ignore-scripts`, then `npm run build` in `examples/basic-host` of ext-apps commit 82221c0.

**Evidence in the repo:** `docs/evidence/2026-10-01_basic_host/README.md`.

**Why this matters to Alexa+ developers:** The reference MCP Apps host cannot be built from its README alone, which slows testing a card in a real host.

## Entry 22 (FL-031): Nova 2 Lite calls through the server code path all returned ThrottlingException; every Nova 2 Lite requests-per-minute and tokens-per-day quota in the account is 0

**Origin:** Amazon · **Tag:** [AWS/Bedrock/Nova] · **Severity:** Medium · **Date:** 2026-10-17

**Impact:** No live Nova 2 Lite evidence could be produced on 2026-10-17; the earlier 2026-09-29 calls are the only recorded live calls.

**Tool / service:** Amazon Bedrock Runtime `Converse` (`us.amazon.nova-2-lite-v1:0`, us-east-1); Service Quotas (`bedrock`); `aws login`. Recorded on the builder's newer AWS account, opened later because access to the older account (FL-014) was lost. New accounts start with Nova 2 Lite quotas at 0.

**Task attempted:** Run Nova 2 Lite once through CluckTalk's own server code path (triage and briefing agents, synthetic demo farm, local process, live Bedrock for that process only).

**Steps taken:** `aws login --region us-east-1` (console sign-in by the owner, temporary credentials). Started the real server with MOCK_BEDROCK=false, 4 Converse calls (2 triage, 2 briefing), `maxTokens` clamped to 300, call cap 6. Then `aws service-quotas list-service-quotas` and `list-aws-default-service-quotas` for `bedrock`.

**Expected vs actual:** Expected a tool-call reply as on 2026-09-29 (docs/AWS_SETUP.md §5.2, §5.3). Actual: all 4 calls returned `ThrottlingException` (no usage returned); the server surfaced "no AI answer" for the check and "AI ordering didn't finish" for the briefing, as designed. Service Quotas for this account: Nova 2 Lite "Cross-region model inference requests per minute" 0, "tokens per minute" 0, "Global cross-region ... requests per minute" 0, "Model invocation max tokens per day" 0; the AWS defaults are 2,000 requests per minute and 5,760,000,000 tokens per day.

**Workaround:** None applied. A quota increase request is the owner's decision (Service Quotas console, Amazon Bedrock, us-east-1).

**Actionable suggestion:** Owner: Amazon Bedrock / Service Quotas team. Show a clear "quota is 0" message in the ThrottlingException text (it says only "Too many requests"), and say in the console why a new account's Nova quotas are 0 when the model is listed as available.

**Time cost:** about 15 minutes

**Reproduce:** `aws service-quotas list-service-quotas --service-code bedrock --region us-east-1 --query "Quotas[?contains(QuotaName,'Nova 2 Lite')]"`.

**Evidence in the repo:** the server log lines "Bedrock ThrottlingException for agent triage / briefing"; 4 Bedrock request ids were captured locally (not committed). See also FL-014. FL-014 and FL-031 were recorded on two different AWS accounts: the nonzero Nova 2 Lite quota of FL-014 (20 requests per minute) belonged to the older account and was not reverted.

**Why this matters to Alexa+ developers:** A new account can list a model as available and still answer every call with a ThrottlingException, with nothing in the error saying the quota is 0.

## Entry 23 (FL-032): With an `aws login` profile, building a real boto3 client needs `botocore[crt]` (awscrt); a unit test failed and the server needed temporary environment credentials

**Origin:** Amazon · **Tag:** [AWS/Bedrock/Nova] · **Severity:** Medium · **Date:** 2026-10-17 (seen during the Nova server-path attempt and during `tasks.py check` on the builder's machine)

**Impact:** A unit test failed on the builder's machine, and the live-path run had to use a different credential route. Time lost: Detail not recorded.

**Tool / service:** AWS CLI `aws login` credentials; boto3 1.43.103 / botocore 1.43.104 (the pinned versions in `docs/VERSIONS.md`; the versions on the day are not recorded).

**Task attempted:** Use the credentials of an `aws login` profile with a real boto3 client, for CluckTalk's live Bedrock path and its tests.

**Steps taken:** Detail not recorded.

**Expected vs actual:** Expected a boto3 client to build from the `aws login` profile like from any other profile. Actual (builder-reported): botocore requires `botocore[crt]` (the `awscrt` package) when a real client is built with an `aws login` profile, which made a unit test fail on the builder's machine. The exact error text is not recorded.

**Workaround:** Temporary environment credentials for the server process only. How they were obtained and set is not recorded. `botocore[crt]` is not in `requirements.txt` and was not added.

**Actionable suggestion:** Owner: AWS CLI and botocore (boto3) maintainers. State on the `aws login` documentation page that using the profile from boto3 requires `botocore[crt]`, and make the botocore error name that extra (the error text was not recorded, so whether it already does is not known).

**Time cost:** not recorded

**Reproduce:** Detail not recorded.

**Evidence in the repo:** none (builder-reported). See also FL-031.

**Why this matters to Alexa+ developers:** A developer who signs in with `aws login` and then builds a boto3 client for Bedrock can hit a missing-extra failure that the login page does not mention.
