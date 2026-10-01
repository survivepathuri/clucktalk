# Friction log: submission copy (short)

Alexa+, MCP, MCP Apps and AWS friction from building CluckTalk, a voice farm manager for Indian poultry farmers. Highest severity first. Origin: Amazon (Alexa+ docs, AWS, Bedrock), MCP Apps SDK (the MCP Apps spec and reference host) or third-party MCP SDK (Python `mcp` SDK, MCP spec, MCP Inspector). The full version is `DEVPOST_FRICTION_PASTE.md`.


## FL-014: New-account Bedrock access has three hidden gates
**Origin:** Amazon · **Severity:** High
**What happened:** Bedrock reported our models AVAILABLE and AUTHORIZED, but every inference quota was 0 (Nova Lite on-demand requests per minute: default 2,000, account 0). Support then enabled "reduced quotas" without numbers; Haiku 4.5 still lacked a Marketplace agreement, and the first Nova 2 Lite call was denied: "Your account is currently being verified."
**Workaround:** Compare quotas per model with the CLI, check agreementAvailability, wait out verification; demo mode stayed the working path.
**Suggestion:** Show quota and verification status in GetFoundationModelAvailability.
**Why this matters to Alexa+ developers:** A new account can look ready and still be refused on the first real call; no read-only check shows the verification gate.


## FL-024: Alexa AI CLI / Local Inspector has no self-serve path (documentation-based, blocked at the prerequisite, no install was attempted)
**Origin:** Amazon · **Severity:** High for participants
**What happened:** The hackathon Resources page does not mention the CLI. The Alexa+ setup page says to use the AWS account provided to an Alexa Solutions Architect, assume a role in an Amazon-owned account and install from a private registry. Prerequisites list macOS or Ubuntu only (we use Windows 11); the Local Inspector guide sits behind a Developer Console login.
**Workaround:** Used the MCP Inspector, the ext-apps basic-host and our own Simulator.
**Suggestion:** Give participants an access path or publish the Local Inspector, and state Windows support.
**Why this matters to Alexa+ developers:** Participants have no documented self-serve path to the official validation tool.


## FL-001: Middleware results leak resultType onto the 2025-11-25 wire
**Origin:** third-party MCP SDK · **Severity:** Medium
**What happened:** A server middleware returned a CallToolResult for a 2025-11-25 client. The response contained "resultType":"complete", a 2026-07-28 field, because the SDK never reshapes a middleware result (mcp 2.2.0).
**Workaround:** Dump the model ourselves with exclude={"result_type"}; a contract test guards it.
**Suggestion:** Run middleware results through the per-version serializer, or document that they are not version-shaped.
**Why this matters to Alexa+ developers:** A customer-safe error returned from middleware carries a 2026-07-28 field unless the server strips it.


## FL-002: Default tool error text includes the tool name and validation details
**Origin:** third-party MCP SDK · **Severity:** Medium
**What happened:** Alexa+ guidance says tool errors are customer-safe. In mcp 2.2.0 an unexpected exception becomes "Error executing tool <name>" and argument-validation failures return pydantic text with field names, as isError content a voice host may read aloud. No option changes this.
**Workaround:** A tools/call middleware validates arguments itself and replaces non-contract errors with a bilingual safe message.
**Suggestion:** Add a tool_error_formatter hook to MCPServer.
**Why this matters to Alexa+ developers:** The SDK default puts the tool name and validation details in error text that a voice host may read aloud.


## FL-004: Unclear whether outputSchema applies to isError results
**Origin:** third-party MCP SDK · **Severity:** Medium
**What happened:** The Python SDK client skips output validation when isError is true, but Inspector 2.8.0 validated the error's structuredContent against the success schema and rejected it. The spec says servers MUST provide conforming structured results and is silent about errors.
**Workaround:** Errors carry no structuredContent; bilingual details go in _meta.
**Suggestion:** State in the Tools spec whether outputSchema constrains isError results.
**Why this matters to Alexa+ developers:** The SDK client and the Inspector disagree, so a structured error can be rejected by one and accepted by the other.


## FL-007: MCP Apps default CSP has no font-src; fall-through of a blocked font source is undocumented
**Origin:** MCP Apps SDK · **Severity:** Medium
**What happened:** The spec default has no font-src, so even an inlined data: font is blocked; the reference host allows it. No doc says whether a CSP-blocked @font-face source falls through; a Chrome 153 test showed it does. Other engines and the Alexa+ renderer are untested.
**Workaround:** Inline the font, list an https copy second, fall back to system fonts, log a warning.
**Suggestion:** Add font-src 'self' data: to the default CSP and document how to ship non-Latin fonts.
**Why this matters to Alexa+ developers:** A bundled Telugu font may silently be lost on a strict host; Alexa+ font availability is not published.


## FL-009: Alexa+ docs give no MCP Apps card size, ui/* methods, CSP or fonts
**Origin:** Amazon · **Severity:** Medium
**What happened:** The Alexa+ pages state MCP Apps support and the under 500 ms latency requirement, but give no container size, display modes, supported MCP Apps messages, CSP or font availability (Telugu included). Device sizes had to come from APL docs, which describe skills, not add-on cards.
**Workaround:** A responsive card, checked at 1024x600, 960x600, 960x480 and a 390x844 phone in our Simulator.
**Suggestion:** Publish an "MCP Apps on Alexa+" page with container sizes, supported requests, CSP and font policy.
**Why this matters to Alexa+ developers:** Card sizes and fonts cannot be designed from the Alexa+ docs.


## FL-012: New-account setup: the recommended CLI identity depends on the account plan
**Origin:** Amazon · **Severity:** Medium
**What happened:** The CLI guide recommends IAM Identity Center; only an organization instance gives single sign-on, and the Billing page says Free plans upgrade to a paid plan if you join AWS Organizations. No setup page says so, and no page states whether Anthropic models on Bedrock work on a Free plan.
**Workaround:** Check the plan first, choose the Paid plan knowingly with budget alerts, verify Bedrock with a real call.
**Suggestion:** Add a new-account note to the getting-started pages and a Free-plan table for Bedrock providers.
**Why this matters to Alexa+ developers:** Following the recommended CLI setup can change a new account's plan.


## FL-013: AWS India (AISPL) account: plan not shown in the console; credit rules missing
**Origin:** Amazon · **Severity:** Medium
**What happened:** The Billing docs say the console home shows the plan, but none of the pages we checked did; credits showed ($120 active). The Marketplace card problem is only in the Bedrock-Anthropic article. No page says whether promotional credits apply to Marketplace-billed Bedrock models.
**Workaround:** Check the plan with aws freetier get-account-plan-state, set Pay by Invoice early, keep Amazon Nova as a fallback.
**Suggestion:** Show the plan on the Billing home for every account; document credits versus Marketplace-billed models.
**Why this matters to Alexa+ developers:** A new AWS India account cannot confirm its plan or credit rules from the docs.


## FL-017: Alexa+ docs do not say whether MCP add-ons can send proactive notifications or identify household members
**Origin:** Amazon · **Severity:** Medium
**What happened:** Alexa.ProactiveNotificationSource is documented only for Smart Home add-ons; neither it nor the MCP Toolkit overview says whether an MCP add-on can trigger it. The account-linking page says only that Alexa includes the access token in every request; it does not say whether any field tells household members apart.
**Workaround:** Pull-based alerts only; worker attribution through separately linked accounts.
**Suggestion:** Publish whether MCP add-ons can use proactive notifications and which identity fields exist.
**Why this matters to Alexa+ developers:** Features that depend on push or per-person identity cannot be designed from the docs.


## FL-019: AWS CLI on Windows truncates a Bedrock response file when the reply has an emoji
**Origin:** Amazon · **Severity:** Medium
**What happened:** Redirecting aws bedrock-runtime converse output to a file failed with 'charmap' codec can't encode character '\U0001f414'. The call succeeded, but the file was left truncated at 149 bytes with no marker, and the usage counts were lost.
**Workaround:** Re-ran with PYTHONIOENCODING=utf-8 PYTHONUTF8=1.
**Suggestion:** Default to UTF-8 for redirected output on Windows and avoid leaving partial files.
**Why this matters to Alexa+ developers:** On Windows a Bedrock response can be silently truncated when the model's reply contains an emoji.


## FL-003: Localhost default Origin allow-list accepts every localhost port
**Origin:** third-party MCP SDK · **Severity:** Low
**What happened:** For a localhost host, mcp 2.2.0 auto-allows http://127.0.0.1:*, http://localhost:* and http://[::1]:*, so a page from any local port passes the Origin check.
**Workaround:** Pass explicit TransportSecuritySettings with our own host:port; a contract test guards it.
**Suggestion:** Default to the bound port or document the wildcard.
**Why this matters to Alexa+ developers:** On a local MCP server any local page passes the default Origin check.


## FL-006: MCP Apps spec example uses clientInfo; the schema requires appInfo
**Origin:** MCP Apps SDK · **Severity:** Low
**What happened:** The spec's hand-rolled example sends initialize with clientInfo, while McpUiInitializeRequest is ui/initialize with required appInfo, appCapabilities and protocolVersion.
**Workaround:** The card follows the types file.
**Suggestion:** Fix the example and check spec examples against the schema in CI.
**Why this matters to Alexa+ developers:** A card written from the spec example would be rejected by a validating host.


## FL-008: The SDK drops the server's capabilities.extensions on a 2025-11-25 connection
**Origin:** third-party MCP SDK · **Severity:** Low
**What happened:** mcp 2.2.0 reads the client's io.modelcontextprotocol/ui extension but the 2025-11-25 ServerCapabilities model has no extensions field, so the initialize result cannot declare the Apps extension. Tool _meta.ui.resourceUri and the card resource work.
**Workaround:** None needed for hosts that discover cards through the tool meta; contract tests pin the shape.
**Suggestion:** Document which protocol versions carry server extensions, or pass them under experimental.
**Why this matters to Alexa+ developers:** Hosts must discover cards through the tool's _meta.ui.resourceUri.


## FL-011: Two in-flight requests with the same JSON-RPC id: one is never answered
**Origin:** third-party MCP SDK · **Severity:** Low
**What happened:** Five concurrent tools/call POSTs on one session with the same id: only 1-2 got a response; the rest hung for 10 s with no server log line. The SDK stores each response stream by id without checking for an in-flight request. With distinct ids all five answered in 13-29 ms.
**Workaround:** Give every concurrent request its own id.
**Suggestion:** Reject a duplicate in-flight id with a JSON-RPC error.
**Why this matters to Alexa+ developers:** A retrying host that reuses an id can leave requests unanswered silently.


## FL-015: billing get-credits says "IAM user access not activated" to an Identity Center role
**Origin:** Amazon · **Severity:** Low
**What happened:** aws billing get-credits with a least-privilege SSO role returned AccessDeniedException ... IAM user access not activated. The caller is not an IAM user; the needed setting is "IAM user and role access to Billing information" (root only), which the message does not name.
**Workaround:** Read credits in the Billing console as root.
**Suggestion:** Name the setting and where to turn it on in the error.
**Why this matters to Alexa+ developers:** The error names the wrong cause for a role.


## FL-020: Nova 2 Lite: image input with forced tool call works, but one colour was misread
**Origin:** Amazon · **Severity:** Low
**What happened:** Before building photo triage we tested Nova 2 Lite with a forced toolChoice and a synthetic 64x64 image (left red, right blue). It returned a well-formed toolUse with right: white. One sample, so an observation, not a benchmark. botocore documents toolChoice only as "If supported by model".
**Workaround:** Photo findings may only add signs, never lower urgency.
**Suggestion:** Document recommended image resolution and which models support the tool choice.
**Why this matters to Alexa+ developers:** Image input and forced tool use work, but the docs do not say which models support them.


## FL-021: ext-apps basic-host cannot be built from its README
**Origin:** MCP Apps SDK · **Severity:** Low
**What happened:** npm ci --ignore-scripts then npm run build failed with Cannot find module '@modelcontextprotocol/ext-apps' (TS2307): the dependency is a workspace link to the repo root, which must be built first and needs bun, whose package refuses to run under --ignore-scripts. The README mentions none of this. Cost about 20 minutes.
**Workaround:** Run only bun's install.js, build the root, then the host.
**Suggestion:** State the root build and bun requirement, or ship a prebuilt host.
**Why this matters to Alexa+ developers:** It slows testing a card in the reference host.
