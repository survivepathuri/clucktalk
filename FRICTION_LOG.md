# CluckTalk Friction Log

Developer friction with the hackathon's tools and services (Alexa+, MCP, AWS, SDKs), recorded **as it happens** (CLAUDE.md Rule 2).
Only real, reproducible experiences. Never batched, never invented.

**Severity**: Critical (blocks work) · High (major workaround) · Medium (slows work) · Low (annoyance / doc nit)

---

## Entry template

```
### FL-NNN: <one-line summary>
Date:
Tool / service:
Task attempted:
Steps taken:
Expected vs actual:
Severity: Critical / High / Medium / Low
Workaround:
Actionable suggestion:
```

---

## Entries

### FL-001: Middleware results skip per-version shaping, so `resultType` leaks onto the 2025-11-25 wire
Date: 2026-09-27
Tool / service: MCP Python SDK `mcp` 2.2.0 (server `ServerMiddleware`)
Task attempted: Return a customer-safe `CallToolResult` from a server middleware on `tools/call` for a client that negotiated protocol 2025-11-25.
Steps taken: Middleware returned a `mcp_types.CallToolResult` model; called it with curl after an `initialize` at 2025-11-25.
Expected vs actual: Expected the same wire shape as a normal tool result (no `resultType`; the SDK strips it for handler results on legacy connections). Actual: the response contained `"resultType":"complete"`, a 2026-07-28 field. `mcp/server/runner.py` says a short-circuiting middleware "is trusted to return its own well-formed result" and never reshapes it.
Severity: Medium
Workaround: Dump the model ourselves with `exclude={"result_type"}` before returning it from the middleware; contract test `test_no_2026_fields_on_the_2025_11_25_wire` guards it.
Actionable suggestion: Run middleware return values through the same per-version serializer as handler results (or expose a public `serialize_for(version, method, result)` helper), and state in the `ServerMiddleware` docstring that returned models are not version-shaped.

### FL-002: Default tool error text includes the tool name and validation details
Date: 2026-09-27
Tool / service: MCP Python SDK `mcp` 2.2.0 (`MCPServer` tool errors) vs Amazon Alexa+ MCP tool design guidance
Task attempted: Meet the Alexa+ guidance that tool errors are customer-safe (no codes, tool names, or JSON spoken).
Steps taken: Read `mcp/server/mcpserver/tools/base.py` and `server.py` `_handle_call_tool`.
Expected vs actual: Expected a hook for the user-facing error text. Actual: an unexpected exception becomes `"Error executing tool <name>"`, and argument-validation failures return pydantic text with field names, as `isError` content that a voice host may read aloud. No option changes this.
Severity: Medium
Workaround: A `tools/call` middleware validates arguments against the advertised `inputSchema` itself and replaces any non-contract error with a bilingual safe message (original text logged server-side only). 8 of 8 mutation checks confirm the contract tests catch regressions.
Actionable suggestion: Add an `MCPServer(tool_error_formatter=...)` hook (or a documented `on_tool_error` callback) so voice/consumer hosts can supply safe wording without re-validating arguments in middleware.

### FL-003: Localhost default Origin allow-list accepts every localhost port
Date: 2026-09-27
Tool / service: MCP Python SDK `mcp` 2.2.0 (`streamable_http_app` transport security defaults)
Task attempted: Validate `Origin` on the local Streamable HTTP server (spec: invalid Origin → 403).
Steps taken: Read `mcp/server/lowlevel/server.py` `streamable_http_app`.
Expected vs actual: Expected the default to allow only the server's own origin. Actual: for a localhost host the SDK auto-allows `http://127.0.0.1:*`, `http://localhost:*`, `http://[::1]:*`, so any page served from any local port (another dev server, a compromised local tool) passes the Origin check.
Severity: Low
Workaround: Pass explicit `TransportSecuritySettings` with our own host:port allow-list; contract test `test_other_localhost_port_origin_is_403` guards it.
Actionable suggestion: Default the localhost allow-list to the bound port, or document the wildcard prominently next to `TransportSecuritySettings`.

### FL-004: Unclear whether `outputSchema` applies to `isError` results; SDK and Inspector disagree
Date: 2026-09-27
Tool / service: MCP spec 2025-11-25 (Tools, Output Schema), MCP Python SDK 2.2.0 client, MCP Inspector 2.8.0 CLI
Task attempted: Return a bilingual structured error (`isError: true` + `structuredContent.error`) from tools that declare an `outputSchema`.
Steps taken: Called `get_farm_status` with an unknown shed via the Python SDK client, then via `mcp-inspector --cli ... --method tools/call`.
Expected vs actual: Expected consistent client behavior. Actual: the Python SDK client skips output validation when `isError` is true (`mcp/client/session.py`), but Inspector 2.8.0 validated the error's `structuredContent` against the success schema and rejected it ("data must have required property 'text_en' ..."). The spec says "Servers MUST provide structured results that conform to this schema" with no statement about error results; its error example has only `content`.
Severity: Medium
Workaround: Errors now carry no `structuredContent`; bilingual details go in `_meta["clucktalk/error"]`, spoken text stays in `content`. Contract test asserts error results have no `structuredContent`.
Actionable suggestion: State in the Tools spec whether `outputSchema` constrains `isError` results, and align the SDK client and Inspector with that rule (or allow an `errorSchema`).

### FL-005: Inspector CLI crashes on Windows when a call ends in an error
Date: 2026-09-27
Tool / service: MCP Inspector `@modelcontextprotocol/inspector` 2.8.0 CLI, Node v24.15.0, Windows 11 Pro
Task attempted: Capture evidence of error results (`tools/call` returning `isError: true`, and an unknown tool name).
Steps taken: `node <inspector>/clients/launcher/build/index.js --cli http://127.0.0.1:8765/mcp --method tools/call --tool-name get_farm_status --tool-arg "house=shed 9"` (3 runs), plus `--tool-name nope`.
Expected vs actual: Expected the documented JSON error on stderr and a normal non-zero exit code. Actual: the JSON error is printed, then `Assertion failed: !(handle->flags & UV_HANDLE_CLOSING), file src\win\async.c, line 76`, and the process dies (exit 127 in Git Bash, 3221226505 = 0xC0000409 from Python). Reproduced 3/3; also on `tool_not_found`, so independent of the server. Successful calls exit 0.
Severity: Low
Workaround: Read the JSON printed before the crash; do not rely on the exit code for error cases on Windows.
Actionable suggestion: Close pending async handles before `process.exit` on the CLI error path (a double close of a libuv async handle), and add a Windows CI smoke test for error exits.

### FL-006: MCP Apps spec example sends `clientInfo` in `ui/initialize`, but the schema requires `appInfo`
Date: 2026-09-27
Tool / service: MCP Apps extension spec 2026-01-26 (`specification/2026-01-26/apps.mdx`) vs `src/spec.types.ts` in modelcontextprotocol/ext-apps (main)
Task attempted: Write the farm-status card against the documented postMessage protocol without the JS SDK (the spec says "you don't need an SDK").
Steps taken: Followed the "Transport Layer" example, then cross-checked the field names in `spec.types.ts`.
Expected vs actual: Expected the example to match the schema. Actual: the example calls `sendRequest("initialize", {capabilities: {}, clientInfo: {...}, protocolVersion: "2026-01-26"})`, while `McpUiInitializeRequest` is method `ui/initialize` with required params `appInfo`, `appCapabilities`, `protocolVersion`. A host that validates against the schema would reject a view written from the example.
Severity: Low
Workaround: The card sends `ui/initialize` with `appInfo` + `appCapabilities` + `protocolVersion`, as in the types file; the Simulator's developer panel logs what the card sent.
Actionable suggestion: Update the spec's hand-rolled example to `ui/initialize` with `appInfo` / `appCapabilities`, and add a schema check of spec examples to CI.

### FL-007: MCP Apps default CSP has no `font-src`, so even an inlined (data:) font is blocked; the reference host allows it
Date: 2026-09-27
Tool / service: MCP Apps extension spec 2026-01-26 ("Host Behavior", restrictive default CSP) vs ext-apps `examples/basic-host/serve.ts`
Task attempted: Bundle Noto Sans Telugu in the card so Telugu renders identically on every device (Indic system fonts vary).
Steps taken: Read the spec's mandatory default CSP and the reference host's CSP builder.
Expected vs actual: Expected a documented way for a card to ship its own font. Actual: the spec default is `default-src 'none'` with no `font-src`, so fonts fall back to `'none'` (data: URIs included), and `resourceDomains` only accepts origins. The reference host instead sends `font-src 'self' data: blob:`. A card that bundles a font works on the reference host and may silently lose it on a strict host.
Severity: Medium
Workaround: The card inlines the font as data: URIs, falls back to system Telugu fonts (Nirmala UI, Gautami) in CSS, and reports a `notifications/message` warning when its bundled font did not load. The Simulator follows the reference host (`font-src 'self' data:`) and says so in `docs/DESIGN.md` §15.
Actionable suggestion: Add `font-src 'self' data:` to the spec's default CSP (fonts cannot exfiltrate data), or a declared `fontDomains`/"inline fonts" flag in `McpUiResourceCsp`, and state whether hosts should provide Indic fonts through `hostContext.styles.css.fonts`.

### FL-008: On a 2025-11-25 connection, SDK 2.2.0 drops the server's `capabilities.extensions`, so the Apps extension is invisible in `initialize`
Date: 2026-09-27
Tool / service: MCP Python SDK `mcp` 2.2.0 (`mcp.server.apps.Apps`, `MCPServer(extensions=[...])`)
Task attempted: Serve the farm-status card through the SDK's MCP Apps extension on the 2025-11-25 wire.
Steps taken: Scratch probe over real HTTP: `initialize` (with and without the client's `io.modelcontextprotocol/ui` extension), `tools/list`, `resources/list`, `resources/read`, `tools/call` with `client_supports_apps(ctx)`.
Expected vs actual: Expected the server's `initialize` result to include `capabilities.extensions["io.modelcontextprotocol/ui"]`, which `_apply_extension` registers. Actual: the result has `experimental`, `prompts`, `resources`, `tools` only (the 2025-11-25 `ServerCapabilities` model has no `extensions` field). Everything else works: tool `_meta.ui.resourceUri`, the `text/html;profile=mcp-app` resource with `_meta.ui`, and `client_supports_apps` reading the client's capability. So the server reads the client's extension capability but cannot declare its own on this version.
Severity: Low
Workaround: None needed for hosts that discover cards via tool `_meta.ui.resourceUri` (the spec's mechanism). Contract tests pin the tool meta and resource shape.
Actionable suggestion: Document in `mcp.server.apps` which protocol versions carry the server's `extensions` capability, or pass it through under `experimental` on pre-2026 versions.

### FL-009: Alexa+ docs say MCP Apps render "in the conversation view" but give no container size, supported `ui/*` methods, CSP or fonts
Date: 2026-09-27
Tool / service: Amazon Alexa+ developer docs (MCP Toolkit overview, Choose an integration approach, Functional Requirements, CX testing guide)
Task attempted: Size the farm-status card for Echo Show and phone from official Amazon docs rather than guesses.
Steps taken: Read the four Alexa+ pages above; searched developer.amazon.com; fell back to the Alexa Presentation Language (APL) docs for device viewports.
Expected vs actual: Expected an Alexa+ MCP Apps rendering profile. Actual: Alexa+ pages state MCP Apps support and the < 500 ms latency requirement, and the CX guide asks for arm's-length legibility on Echo Show (primary), mobile, web and voice-only devices, but none gives the card container's width/height, display modes, the subset of MCP Apps messages Alexa+ supports (e.g. `tools/call` from a card), CSP, or font availability (Telugu included). Device sizes had to come from APL docs (1024x600 px original Echo Show; 1280x800 px at 213 dpi; `hubLandscapeSmall` 960-1279 x 100-599 dp), which describe skills, not add-on cards.
Severity: Medium
Workaround: The card is responsive and was checked at 1024x600, 960x600, 960x480 and a 390x844 phone in the Simulator; tap-to-call is optional (voice gives the same answer).
Actionable suggestion: Publish an "MCP Apps on Alexa+" page: container dimensions per device class, supported `ui/*` requests and notifications, CSP and font policy (Indic scripts), and whether card-initiated `tools/call` is allowed.

### FL-010: No doc says whether a CSP-blocked `@font-face` source falls through to the next one; had to test it
Date: 2026-09-28
Tool / service: MCP Apps extension spec 2026-01-26 (CSP, `resourceDomains`); MDN `@font-face` `src` and CSP `font-src` pages; Google Chrome 153.0.8010.53
Task attempted: Plan how the card keeps its bundled Telugu font on a host that applies the spec's default CSP literally (FL-007): inlined `data:` font first, a declared https copy second.
Steps taken: Read the spec (`resourceDomains` maps to `font-src`; hosts "MUST NOT allow undeclared domains") and MDN (`font-src` falls back to `default-src`; the browser uses "the first one it can successfully activate"). Neither says whether a source blocked by CSP counts as a failed source. Built a strict-CSP mode into the Simulator's sandbox proxy and a probe (docs/evidence/2026-09-28_strict_csp.md), ran it in headless Chrome.
Expected vs actual: Expected a documented answer. Actual: none found; the answer had to come from a test. Chrome 153 falls through: `font-src` violation for `data`, then the https entry loads; on a permissive CSP the https copy is never fetched. Other engines (WebKit, Firefox) and the Alexa+ renderer are untested.
Severity: Low
Workaround: Tested it; the card will list the inlined font first and the declared https copy second.
Actionable suggestion: MCP Apps spec: a short "Fonts" note in the CSP section (how a view should ship a custom or non-Latin font under the default CSP, and whether hosts should provide Indic fonts via `styles.css.fonts`). MDN: state in `@font-face` `src` that a source blocked by CSP is treated like a failed load.

### FL-011: Two in-flight requests with the same JSON-RPC id on one session: the SDK silently never answers one
Date: 2026-09-28
Tool / service: MCP Python SDK `mcp` 2.2.0, server Streamable HTTP transport (`json_response=True`), protocol 2025-11-25
Task attempted: Contract test that a repeated "yes" (the same `set_farm_mode` confirmation sent 5 times at once, as a retrying host might) is applied only once.
Steps taken: 5 concurrent `tools/call` POSTs on one `Mcp-Session-Id`, all with JSON-RPC `id: 2` (a test-client mistake). Repeated with a read-only tool, and with distinct ids.
Expected vs actual: Expected every POST to be answered, or a JSON-RPC error for the duplicate id. Actual: only 1-2 of the 5 POSTs got a response; the others hung until the client's 10 s timeout, with no server log line, for read-only tools too. With distinct ids all 5 answered in 13-29 ms. Cause in source: `mcp/server/streamable_http.py` stores each POST's response stream in `self._request_streams[request_id]` (line 645) without checking for an in-flight request with that id, so the later POST overwrites the earlier one's stream. The spec forbids reusing an id in a session, so the client was wrong, but the failure is a silent hang.
Severity: Low
Workaround: The test client now gives every concurrent request its own id. CluckTalk's confirmation flow still applied the change exactly once in the hanging run (1 applied, the answered repeats replayed).
Actionable suggestion: Reject a request whose id is already in flight on the session with a JSON-RPC error (-32600, "duplicate request id") instead of overwriting the pending stream, and log a warning.

### FL-012: New-account setup: the recommended CLI identity silently depends on the account plan; Bedrock-on-Free-plan is undocumented
Date: 2026-09-28
Tool / service: AWS Billing (Free vs Paid account plan), AWS IAM Identity Center, AWS CLI v2 guide, Amazon Bedrock model access
Task attempted: Plan a least-privilege, key-free CLI identity for a brand-new account and check that Bedrock (Anthropic models) is usable, from AWS docs only.
Steps taken: Read the AWS CLI guide (recommends IAM Identity Center), the Identity Center instance comparison, the Billing "Choosing a plan" page and the Bedrock "Request access to models" page.
Expected vs actual: Expected one page to say what a new Free-plan account must do. Actual: the CLI guide recommends Identity Center; the Identity Center page shows that only an organization instance (in an AWS Organizations management account) gives "single sign-on access to your AWS accounts"; the Billing page says Free plans "automatically upgrade to paid plan if you join AWS Organizations", and are "not eligible for other promotional credits". So following the recommended CLI setup changes the account plan, which no setup page mentions. Separately, the Bedrock model-access page requires AWS Marketplace permissions and a "valid payment method ... for AWS Marketplace purchases" for third-party models, and the Billing page says Free plans exclude "certain AWS Marketplace offers that can incur charges", but no page states whether Anthropic models on Bedrock work on a Free-plan account.
Severity: Medium
Workaround: Check the account plan first; decide on the Paid plan knowingly (budget alerts set), then use an Identity Center organization instance. Verify Bedrock access with a real call rather than from docs.
Actionable suggestion: Add a "new account" note to the CLI and Identity Center getting-started pages (enabling Organizations upgrades a Free-plan account), and a table in the Billing plan page listing which Bedrock model providers are usable on the Free plan.

### FL-013: AWS India (AISPL) account: plan not shown in the console; Claude-on-Bedrock and credit rules scattered or missing
Date: 2026-09-28
Tool / service: AWS Billing console (AWS India / AISPL account), AWS Knowledge Center, Amazon Bedrock (Anthropic via AWS Marketplace), AWS promotional credits
Task attempted: Confirm the account plan, and whether Claude on Bedrock and promotional credits work for a new AWS India account.
Steps taken: Owner checked Billing home, Free Tier, Credits and Account pages; I read the AWS India differences article, the "turn on Anthropic models" article, the credits docs, and searched docs.aws.amazon.com and re:Post.
Expected vs actual: Expected the console to show "Free plan" or "Paid plan" as the Billing docs describe ("You can monitor your credit balance and free account plan information in the AWS Billing and Cost Management console home"). Actual: none of those pages shows a plan or an "Upgrade plan" option; credits show ($120 active). The AWS India differences article lists INR billing and manual Marketplace payments but not the Marketplace/RBI card problem, which is only in the Bedrock-Anthropic article ("your Marketplace subscription can fail and model access isn't turned on"; pay manually "within one hour"). No page says whether promotional credits apply to Marketplace-billed Bedrock models or behave differently on AISPL accounts; re:Post has open community questions about exactly this.
Severity: Medium
Workaround: Check the plan with `aws freetier get-account-plan-state` after CLI login; set Pay by Invoice before the first Claude call; check each credit's "Applicable products"; keep Amazon Nova (not sold via Marketplace) as a fallback host model.
Actionable suggestion: Show the account plan on the Billing home for every account (or explain why it is absent for AISPL accounts); add the Marketplace/RBI note and a "credits vs Marketplace-billed Bedrock models" answer to the AWS India differences article.

### FL-014: New account: Bedrock reports models "AVAILABLE" but every inference quota is 0
Date: 2026-09-28
Tool / service: Amazon Bedrock (us-east-1), Service Quotas, AWS CLI 2.37.4; new Paid-plan AWS India account
Task attempted: Read-only check that the host model candidates can be called before the first (paid) request.
Steps taken: `aws bedrock get-foundation-model-availability` for Nova Lite, Nova 2 Lite, Claude Sonnet 5, Claude Haiku 4.5; then `aws service-quotas list-service-quotas` vs `list-aws-default-service-quotas` for service code `bedrock`.
Expected vs actual: Expected a model that reports `agreementAvailability: AVAILABLE`, `authorizationStatus: AUTHORIZED`, `entitlementAvailability: AVAILABLE` (Nova Lite, Nova 2 Lite) to be callable. Actual: the account's applied value is 0 for every on-demand, cross-region and global cross-region requests-per-minute and tokens-per-minute quota of all four models, while the AWS defaults are large (e.g. Claude Sonnet 5 cross-region tokens per minute: default 6,000,000, account 0; Nova Lite on-demand requests per minute: default 2,000, account 0, not adjustable). Nothing in the model availability response or the model access docs mentions it; only a quota-by-quota comparison shows it.
Severity: High (blocks every live Bedrock call; the fix goes through quota requests / AWS Support with unknown lead time)
Workaround: Request increases for the adjustable quotas and open a Support case for the non-adjustable zeros; keep demo mode (no AWS) as the working path meanwhile.
Actionable suggestion: Return a quota status in `GetFoundationModelAvailability` (or a field such as `inferenceQuotaAvailability: ZERO`), show "your account's quota for this model is 0" on the model catalog page, and document the new-account quota policy with the expected path to normal limits.

### FL-015: CLI billing call says "IAM user access not activated" to an IAM Identity Center role
Date: 2026-09-28
Tool / service: AWS CLI 2.37.4 `aws billing get-credits`, IAM Identity Center permission set with `billing:GetCredits`
Task attempted: Read the account's credits from the CLI with a least-privilege SSO role.
Steps taken: `aws billing get-credits --account-id <id> --start-date <epoch>` with profile `clucktalk` (role CluckTalkVerify, which allows `billing:GetCredits`).
Expected vs actual: Expected the credits, or an error naming the account setting to change. Actual: `AccessDeniedException ... IAM user access not activated`. The caller is not an IAM user; the needed switch is the account setting "IAM user and role access to Billing information" (root only), which the message does not name.
Severity: Low
Workaround: Read credits in the Billing console as root; activation is optional for this project.
Actionable suggestion: Name the setting and where to turn it on in the error ("IAM user and role access to Billing information is off for this account; the root user can activate it on the Account page").
