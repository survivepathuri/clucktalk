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
