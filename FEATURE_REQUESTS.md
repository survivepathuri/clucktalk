# CluckTalk Feature Requests

Concrete requests to Amazon (Alexa+, AWS) and the MCP ecosystem, each grounded in something we hit while building.
Link each to the friction-log entry that motivated it where one exists. No speculative wish-lists.

**Priority**: Critical · Important · Nice-to-have

---

## Entry template

```
### FR-NNN: <request>
Date:
Product / service:
Priority: Critical / Important / Nice-to-have
Problem it solves (who, when):
Related friction-log entry: FL-NNN or n/a
Proposed behavior:
```

---

## Requests

### FR-001: A hook for customer-safe tool error text in the MCP Python SDK
Date: 2026-09-27
Product / service: MCP Python SDK (`mcp` 2.x, `MCPServer`)
Priority: Important
Problem it solves (who, when): Voice add-on builders (e.g., Alexa+) must never have a tool name, field name, or exception text spoken to a customer. Today the SDK's default error results contain "Error executing tool <name>" or pydantic validation text, and changing that needs a custom middleware that re-validates arguments.
Related friction-log entry: FL-002
Proposed behavior: `MCPServer(tool_error_formatter=callable)` receiving (tool name, error kind: validation | tool_error | crash, exception) and returning the `CallToolResult` to send, with the SDK still logging the original server-side and applying per-version wire shaping (see FL-001).

### FR-002: An "MCP Apps on Alexa+" rendering profile
Date: 2026-09-27
Product / service: Amazon Alexa+ MCP Toolkit documentation
Priority: Important
Problem it solves (who, when): Add-on builders designing cards for Echo Show, Fire TV and the Alexa app must guess the card's container size, which MCP Apps messages work (card-initiated `tools/call`, display modes), the CSP, and whether Indic fonts are available. Guessing wrong means truncated data or a card that cannot load its font.
Related friction-log entry: FL-009 (also FL-007)
Proposed behavior: One page listing, per device class, the MCP App container dimensions and display modes, the supported `ui/*` requests and notifications, the CSP applied, font availability (including Telugu and other Indian scripts), and a downloadable host test harness or screenshots per device.

### FR-003: Let MCP App views bundle fonts under the default CSP
Date: 2026-09-27
Product / service: MCP Apps extension spec (`io.modelcontextprotocol/ui`)
Priority: Important
Problem it solves (who, when): Cards in scripts that system fonts cover unevenly (Telugu, Tamil, and more) need to ship a font. Under the spec's default CSP (no `font-src`), even an inlined data: font is blocked, while the reference host allows it, so behaviour differs by host.
Related friction-log entry: FL-007
Proposed behavior: Add `font-src 'self' data:` to the normative default CSP, or a declared `fontDomains` / `inlineFonts` field in `McpUiResourceCsp`, and document how hosts should expose their own Indic fonts via `hostContext.styles.css.fonts`.

### FR-004: A self-serve way for hackathon builders to run the official Alexa AI validation (Alexa AI CLI / Local Inspector)
Date: 2026-10-03
Product / service: Alexa+ developer tooling (Alexa AI CLI, Local Inspector) and the hackathon Resources page
Priority: Critical
Problem it solves (who, when): A hackathon participant who builds an Alexa+ add-on has no documented way to run the official validation tool. The setup page asks for an AWS account provided to an Alexa Solutions Architect and an Amazon-owned role, lists macOS and Ubuntu only, and keeps the Local Inspector install guide behind a Developer Console login. We validated with the generic MCP Inspector, the ext-apps basic-host and our own Simulator, none of which says how Alexa+ itself will treat the add-on, so the check that matters most is the one we could not run.
Related friction-log entry: FL-024
Proposed behavior: Publish the Alexa AI CLI and Local Inspector to participants (a public install guide, or a participant access path named on the hackathon Resources page), and state whether Windows 11 is supported.

### FR-005: Document whether MCP add-ons can send proactive notifications and how household members are told apart
Date: 2026-10-03
Product / service: Alexa+ MCP Toolkit documentation (Overview, Account Linking) and the `Alexa.ProactiveNotificationSource` page
Priority: Important
Problem it solves (who, when): Builders planning reminders or an owner-and-worker flow cannot tell from the docs whether an MCP-based add-on can push a notification at all, or whether the OAuth token or request identifies the household member who spoke. We designed alerts as pull-only and gave each person a separate linked account because neither point is documented. This is a documentation answer, not necessarily a new feature, and the product still works without it.
Related friction-log entry: FL-017
Proposed behavior: Add to the MCP Toolkit Overview and Account Linking pages a clear yes or no for proactive notifications from MCP add-ons (with the opt-in and quiet-hours rules if yes), and list which identity fields, if any, distinguish household members.

### FR-006: Make an "AVAILABLE" Bedrock model usable on a new account, or expose the quota and verification state
Date: 2026-10-03
Product / service: Amazon Bedrock (`GetFoundationModelAvailability`, model access console page), Service Quotas, AWS Support
Priority: Important
Problem it solves (who, when): A new account can show a model as AVAILABLE and AUTHORIZED while every inference quota is 0, then still be refused on the first real call by an agreement gate and an "account verification" step that no read-only check reports. The Support cases were opened about 28 Sep and the first live call worked on 29 Sep after a verification wait (demo mode stayed the working path meanwhile). It did not stop the project, so this is Important rather than Critical.
Related friction-log entry: FL-014
Proposed behavior: Return the applied inference quota and an account-verification status in `GetFoundationModelAvailability` and show them on the model catalog page; have quota-increase replies state the new applied quota per model.

### FR-007: Show the account plan on the Billing home for every account
Date: 2026-10-03
Product / service: AWS Billing and Cost Management console (AWS India / AISPL accounts)
Priority: Nice-to-have
Problem it solves (who, when): The Billing docs say the console home shows the plan (Free or Paid), but on our AWS India account it did not, so we had to find the plan with a CLI call after login. Choosing between plans decides what the recommended CLI setup does to a new account, so a new builder wants to see it. A workaround exists (`aws freetier get-account-plan-state`).
Related friction-log entry: FL-013 (also FL-012)
Proposed behavior: Show the account plan and an upgrade option on the Billing home for every account, or document why it is absent for AISPL accounts.
