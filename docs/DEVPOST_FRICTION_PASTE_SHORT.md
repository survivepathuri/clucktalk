# Friction log: submission copy (short)

Alexa+, MCP, MCP Apps and AWS friction from building CluckTalk, a Telugu-first MCP assistant for Indian broiler farmers. Amazon-owned entries first (Entries 1 to 5 are the ones Amazon's teams most need), then MCP and MCP Apps entries that matter to Alexa+ developers, then the least Amazon-related. Severity is one word, rated for the owner of the criticised tool. The FL number is the stable id used in `FRICTION_LOG.md`; the full version is `DEVPOST_FRICTION_PASTE.md`.


## Entry 1 (FL-014): New-account Bedrock access has three hidden gates
**Tag:** [AWS/Bedrock/Nova] · **Origin:** Amazon · **Severity:** High
**Task:** Make the first live Bedrock call on a new account.
**Steps:** Checked availability and quotas with the CLI, opened two Support cases, then called Nova 2 Lite.
**Expected vs actual:** Models showed AVAILABLE and AUTHORIZED, but every inference quota was 0, Support's reply gave no numbers, and the call failed with an "account is being verified" error that no read-only check shows.
**Workaround:** Compare quotas per model, wait out verification, keep demo mode.
**Suggestion:** Bedrock team: return quota and verification status in GetFoundationModelAvailability; Support replies should state the new quotas.
**Reproduce:** Commands in docs/AWS_SETUP.md §5; new account only.


## Entry 2 (FL-024): Alexa AI CLI / Local Inspector has no self-serve path
**Tag:** [Alexa+/MCP] · **Origin:** Amazon · **Severity:** High
**Task:** Set up the Alexa AI CLI / Local Inspector as a hackathon participant.
**Steps:** Read the hackathon Resources page and the Alexa+ setup page.
**Expected vs actual:** Expected a self-serve path. The setup asks for an AWS account provided by an Alexa Solutions Architect, lists macOS and Ubuntu only, and keeps the Local Inspector guide behind a Developer Console login.
**Workaround:** MCP Inspector, ext-apps basic-host and our own Simulator.
**Suggestion:** Alexa+ docs team and organizers: name a participant access path or publish the Local Inspector guide, and state Windows support.
**Reproduce:** Documentation-based, no command.


## Entry 3 (FL-009): Alexa+ docs give no MCP Apps container size, messages, CSP or fonts
**Tag:** [Alexa+/MCP] · **Origin:** Amazon · **Severity:** Medium
**Task:** Size the farm-status card for Echo Show and phone.
**Steps:** Read four Alexa+ pages, searched developer.amazon.com, fell back to APL device docs.
**Expected vs actual:** Expected an MCP Apps rendering profile. The docs state support but give no container size, supported ui/* messages, CSP or font availability.
**Workaround:** Responsive card tested at four sizes; tap-to-call is optional.
**Suggestion:** Alexa+ docs team: publish an "MCP Apps on Alexa+" page with size per device class, supported ui/* requests, CSP, Indic font policy, and whether card-initiated tools/call is allowed.
**Reproduce:** Documentation-based, no command.


## Entry 4 (FL-017): Alexa+ docs: proactive notifications and household identity for MCP add-ons
**Tag:** [Alexa+/MCP] · **Origin:** Amazon · **Severity:** Medium
**Task:** Plan an owner-and-worker flow with alerts to the owner.
**Steps:** Read the ProactiveNotificationSource page, MCP Toolkit overview and account-linking page.
**Expected vs actual:** Expected an MCP way to push a notification, or how a request identifies a household member. Proactive notifications are documented only for smart-home add-ons; household members are not mentioned.
**Workaround:** Pull-only alerts; one linked account per person.
**Suggestion:** Alexa+ docs team: add clear answers on MCP proactive notifications and identity fields to the Overview and Account Linking pages.
**Reproduce:** Documentation-based, no command.


## Entry 5 (FL-013): AWS India account: plan not shown, credit rules scattered
**Tag:** [AWS account/credits] · **Origin:** Amazon · **Severity:** Medium
**Task:** Confirm the plan, and Claude-on-Bedrock and credit rules, for a new AWS India account.
**Steps:** Checked four Billing pages; read the AWS India differences and Anthropic articles.
**Expected vs actual:** Expected the console to show the plan as the docs say; it shows none, and no page says whether credits cover Marketplace-billed Bedrock models.
**Workaround:** aws freetier get-account-plan-state; Pay by Invoice; Nova as fallback.
**Suggestion:** Billing and AWS India docs teams: show the plan on Billing home (or say why not); answer the credits question.
**Reproduce:** Documentation-based, no command.


## Entry 6 (FL-012): New-account CLI setup silently depends on the account plan
**Tag:** [AWS account/credits] · **Origin:** Amazon · **Severity:** Medium
**Task:** Plan a least-privilege CLI identity and Bedrock use on a new account.
**Steps:** Read the CLI, Identity Center, Billing plan and Bedrock model-access pages.
**Expected vs actual:** Expected one page for a new Free-plan account. The recommended setup upgrades the plan through AWS Organizations, which no setup page says; no page says if Anthropic models work on Free.
**Workaround:** Check the plan first, choose Paid knowingly, verify with a real call.
**Suggestion:** CLI, Identity Center and Billing teams: add a "new account" note and a table of Bedrock providers usable on Free.
**Reproduce:** Documentation-based, no command.


## Entry 7 (FL-019): AWS CLI on Windows truncates a redirected Converse reply
**Tag:** [AWS/Bedrock/Nova] · **Origin:** Amazon · **Severity:** Medium
**Task:** Save a Bedrock Converse reply to a file on Windows.
**Steps:** Ran converse with --output json redirected to result.json.
**Expected vs actual:** The call succeeded, but the CLI crashed on an emoji (charmap codec error) and left a 149-byte truncated file.
**Workaround:** PYTHONIOENCODING=utf-8 PYTHONUTF8=1.
**Suggestion:** AWS CLI team: default to UTF-8 for redirected output on Windows; write a temp file and rename on success.
**Reproduce:** The Steps command on Windows; needs a reply with an emoji.


## Entry 8 (FL-015): Billing CLI error does not name the setting
**Tag:** [AWS account/credits] · **Origin:** Amazon · **Severity:** Low
**Task:** Read credits with a least-privilege SSO role.
**Steps:** Ran aws billing get-credits with a role that allows billing:GetCredits.
**Expected vs actual:** Expected credits, or an error naming the setting. Got "IAM user access not activated" for a non-IAM-user caller.
**Workaround:** Read credits in the console as root.
**Suggestion:** AWS Billing team: name "IAM user and role access to Billing information" and where the root user enables it, in the error text.
**Reproduce:** aws billing get-credits --account-id <id> --start-date <epoch> --profile <sso profile>.


## Entry 9 (FL-020): Nova 2 Lite image read: blue half called white
**Tag:** [AWS/Bedrock/Nova] · **Origin:** Amazon · **Severity:** Low
**Task:** Check that Nova 2 Lite takes an image with a forced tool call.
**Steps:** Two paid calls: text only, then a 64x64 two-colour PNG.
**Expected vs actual:** Forced tool use worked with the image, but the blue half was read as white (one sample, an observation).
**Workaround:** Photo findings may only add signs; real photos tested before any claim.
**Suggestion:** Bedrock docs team: state the recommended image resolution for Nova 2 Lite and which models support toolChoice "tool".
**Reproduce:** Documentation-based, no command (parameters in docs/AWS_SETUP.md §5.3).


## Entry 10 (FL-026): Alexa+ docs state no MCP protocolVersion
**Tag:** [Alexa+/MCP] · **Origin:** Amazon · **Severity:** Low
**Task:** Connect an MCP server to Alexa+ and choose which protocolVersion to implement.
**Steps:** Read the QuickStart (MCP requirements) and the Local Inspector (Initialize the MCP session).
**Expected vs actual:** Expected the version Alexa+ sends or requires. The QuickStart names 2025-11-25 only as the version that deprecated HTTP+SSE and states no minimum; the Local Inspector example sends 2025-06-18.
**Workaround:** We implement 2025-11-25 and echo older versions.
**Suggestion:** Alexa+ MCP Toolkit docs team: state the minimum and negotiated protocolVersion, say whether to refuse older ones, and align the Inspector example.
**Reproduce:** Documentation-based, no command (our own server: probe-protocol-version, inspector-replay).


## Entry 11 (FL-027): App Runner takes no new customers since 30 April 2026
**Tag:** [AWS App Runner docs] · **Origin:** Amazon · **Severity:** Low
**Task:** Choose hosting for the farmer pilot (builder-reported, 7 October 2026).
**Steps:** Read the "AWS App Runner availability change" page.
**Expected vs actual:** Expected App Runner to be open to a new customer. The page says it stopped accepting new customers on 30 April 2026 and recommends ECS Express Mode.
**Workaround:** App Runner not used; the pilot is hosted on the builder's PC through a free Tailscale Funnel.
**Suggestion:** App Runner docs team: is the change shown on every getting-started page, with the ECS Express Mode link?
**Reproduce:** Documentation-based, no command.


## Entry 12 (FL-033): Alexa+ in India: Telugu is not a listed language
**Tag:** [Alexa+/MCP] · **Origin:** Amazon · **Severity:** Medium
**Task:** Find out whether a Telugu-first add-on can be tested by voice on Alexa+.
**Steps:** Read launch coverage (Medianama, Business Standard, September 2026). Press-reported, not verified with Amazon.
**Expected vs actual:** Expected a published list of supported add-on languages. As reported, Alexa+ in India supports English, Hindi and Hinglish; Telugu is not listed and no timeline for more languages was given.
**Workaround:** Written Telugu, a Simulator and the MCP Inspector; no voice test on the platform.
**Suggestion:** Alexa+ teams: publish the supported-locale list for add-ons and a roadmap for regional languages.
**Reproduce:** Documentation-based (press coverage), no command.


## Entry 13 (FL-007): MCP Apps default CSP blocks even inlined fonts
**Tag:** [MCP Apps] · **Origin:** MCP Apps SDK · **Severity:** Medium
**Task:** Bundle a Telugu font in a card under the MCP Apps default CSP.
**Steps:** Read the spec CSP and the reference host; built a strict-CSP mode; probed in Chrome.
**Expected vs actual:** The default CSP has no font-src, so data: fonts are blocked; the reference host allows them; the spec is silent on fall-through (Chrome falls through).
**Workaround:** Inline font, system-font fallback, and a warning message.
**Suggestion:** ext-apps spec maintainers: add font-src 'self' data: or a fonts field. Question to the Alexa+ team: does its renderer apply the default CSP literally?
**Reproduce:** font_probe.py in docs/evidence/2026-09-28_strict_csp/.


## Entry 14 (FL-002): Default tool errors name the tool and validation fields
**Tag:** [Alexa+/MCP] · **Origin:** third-party MCP SDK · **Severity:** Medium
**Task:** Return customer-safe tool errors for a voice host.
**Steps:** Read the SDK's tool error handling.
**Expected vs actual:** Expected a hook. Errors carry "Error executing tool <name>" or pydantic field text that a voice host may read aloud.
**Workaround:** A middleware validates arguments and replaces errors.
**Suggestion:** MCP Python SDK maintainers: add MCPServer(tool_error_formatter=...).
**Reproduce:** Documentation-based, no command.


## Entry 15 (FL-004): Does outputSchema apply to isError results?
**Tag:** [Alexa+/MCP] · **Origin:** third-party MCP SDK · **Severity:** Medium
**Task:** Return a structured error from a tool with an outputSchema.
**Steps:** Called an unknown shed through the Python SDK client and the Inspector CLI.
**Expected vs actual:** The SDK client skips validation on isError; Inspector 2.8.0 rejected the error against the success schema; the spec is silent.
**Workaround:** Error results carry no structuredContent.
**Suggestion:** MCP spec, SDK and Inspector maintainers: state whether outputSchema constrains isError results and align both clients.
**Reproduce:** Documentation-based, no command.


## Entry 16 (FL-001): Middleware results leak resultType onto the 2025-11-25 wire
**Tag:** [Alexa+/MCP] · **Origin:** third-party MCP SDK · **Severity:** Medium
**Task:** Return a safe result from a server middleware.
**Steps:** Returned a CallToolResult at protocol 2025-11-25 and called it with curl.
**Expected vs actual:** Expected the normal wire shape. The response carried resultType, a 2026-07-28 field, because middleware results are never reshaped.
**Workaround:** Dump the model without result_type; a contract test guards it.
**Suggestion:** MCP Python SDK maintainers: run middleware results through the per-version serializer, or document it.
**Reproduce:** pytest tests\contract\test_tools.py::test_no_2026_fields_on_the_2025_11_25_wire


## Entry 17 (FL-008): SDK drops the server's extensions capability on 2025-11-25
**Tag:** [MCP Apps] · **Origin:** third-party MCP SDK · **Severity:** Low
**Task:** Serve the card through the SDK's Apps extension on 2025-11-25.
**Steps:** Probed initialize, tools/list and resources over HTTP.
**Expected vs actual:** Expected capabilities.extensions in initialize. The 2025-11-25 model has no such field, though tool meta and resources work.
**Workaround:** None needed; hosts find cards through tool _meta.
**Suggestion:** MCP Python SDK maintainers: document which versions carry extensions, or pass it through experimental.
**Reproduce:** Documentation-based, no command (probe not saved).


## Entry 18 (FL-003): Localhost Origin allow-list accepts every port
**Tag:** [Alexa+/MCP] · **Origin:** third-party MCP SDK · **Severity:** Low
**Task:** Validate Origin on the local server.
**Steps:** Read streamable_http_app.
**Expected vs actual:** Expected only the server's own origin. The default allows any localhost port.
**Workaround:** Explicit allow-list plus a contract test.
**Suggestion:** MCP Python SDK maintainers: default to the bound port, or document the wildcard.
**Reproduce:** pytest tests\contract\test_transport.py::test_other_localhost_port_origin_is_403


## Entry 19 (FL-006): MCP Apps spec example disagrees with its schema
**Tag:** [MCP Apps] · **Origin:** MCP Apps SDK · **Severity:** Low
**Task:** Write a card against the documented postMessage protocol.
**Steps:** Followed the spec example and checked spec.types.ts.
**Expected vs actual:** The example sends initialize with clientInfo; the schema wants ui/initialize with appInfo.
**Workaround:** Followed the types file.
**Suggestion:** ext-apps spec maintainers: fix the example and check spec examples against the schema in CI.
**Reproduce:** Documentation-based, no command.


## Entry 20 (FL-011): Duplicate in-flight JSON-RPC id hangs silently
**Tag:** [Alexa+/MCP] · **Origin:** third-party MCP SDK · **Severity:** Medium
**Task:** Test that a repeated confirmation applies once.
**Steps:** Sent 5 concurrent tools/call requests with the same JSON-RPC id.
**Expected vs actual:** Expected answers or a duplicate-id error. Only 1 to 2 of 5 got a response; one request can stay unanswered for at least 40 seconds, or on some runs gets a 500.
**Workaround:** Distinct ids in the test client.
**Suggestion:** MCP Python SDK maintainers: reject an in-flight duplicate id with -32600 and log it.
**Reproduce:** `.venv\Scripts\python -m pytest -q tests\contract\test_concurrency.py::test_two_overlapping_requests_with_the_same_id_leave_one_unanswered_pinned_finding`


## Entry 21 (FL-021): basic-host cannot be built from its README
**Tag:** [MCP Apps] · **Origin:** MCP Apps SDK · **Severity:** Low
**Task:** Build the reference basic-host to test our cards.
**Steps:** Ran npm ci --ignore-scripts, then npm run build in examples/basic-host.
**Expected vs actual:** The README says npm install and start; the build failed because the repo root must be built first and bun is needed.
**Workaround:** Run bun's install script, build the root, then the host (about 20 minutes).
**Suggestion:** ext-apps maintainers: update the basic-host README or ship a prebuilt host.
**Reproduce:** Commands in docs/evidence/2026-10-01_basic_host/README.md.

## Entry 22 (FL-031): Nova 2 Lite calls all throttled; every Nova 2 Lite quota is 0
**Tag:** [AWS/Bedrock/Nova] · **Origin:** Amazon · **Severity:** Medium
**Task:** Run Nova 2 Lite once through CluckTalk's own server code path.
**Steps:** aws login, 4 Converse calls, then list-service-quotas for bedrock.
**Expected vs actual:** Expected a reply as on 2026-09-29; all 4 calls returned ThrottlingException. The account's Nova 2 Lite requests-per-minute and tokens-per-day quotas are 0 (AWS defaults: 2,000 per minute, 5,760,000,000 per day).
**Workaround:** None applied; a quota increase is the owner's decision.
**Suggestion:** Bedrock / Service Quotas team: say "quota is 0" in the ThrottlingException text.
**Reproduce:** aws service-quotas list-service-quotas --service-code bedrock --region us-east-1.

## Entry 23 (FL-032): `aws login` profile needs botocore[crt] for a real boto3 client
**Tag:** [AWS/Bedrock/Nova] · **Origin:** Amazon · **Severity:** Medium
**Task:** Use an `aws login` profile with a real boto3 client (Bedrock path, tests).
**Date:** 2026-10-17, seen during the Nova server-path attempt and during tasks.py check (builder's machine).
**Expected vs actual:** Expected the client to build. Builder-reported: botocore requires botocore[crt] (awscrt) for a real client with an `aws login` profile, and a unit test failed on the builder's machine.
**Workaround:** Temporary environment credentials for the server process only.
**Suggestion:** AWS CLI / botocore maintainers: document the extra on the `aws login` page and name it in the error.
**Reproduce:** Detail not recorded.
