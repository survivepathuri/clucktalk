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
