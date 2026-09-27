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
