# Verified Versions (Rule 7)

Every version below was checked on the date shown, from the command or source named. Nothing here is from memory.
**Status**: `pinned` = in a requirements file · `verified` = confirmed to exist, not yet a dependency · `risk` = needs follow-up.

## Local toolchain (checked 2026-09-27, Windows 11 Pro 10.0.22621)

| Tool | Version | Evidence |
|---|---|---|
| **Python (project)** | **3.13.15** (64-bit). The `.venv` is built with it via `py -3.13` | `py install 3.13`, `py list`, `.venv\Scripts\python --version` → 3.13.15 (2026-09-27) |
| Python (system default) | 3.14.5, kept installed; `python` on PATH | `python --version`, `py list` |
| pip | 26.1.1 | `pip --version` |
| Node.js | v24.15.0 | `node --version` |
| npm | 11.12.1 | `npm --version` |
| git | 2.55.0.windows.3 | `git --version` |
| Docker | not installed; not required (Docker is optional, P1) | user decision 2026-09-27 |

## Python packages

| Package | Version | Status | Evidence / notes |
|---|---|---|---|
| `mcp` (official MCP Python SDK) | **2.2.0** (latest; released 2026-09-07) | **pinned** (`requirements.txt`, 2026-09-27) | `pip index versions mcp`; PyPI JSON: `requires_python >=3.10`, classifiers include 3.14. Repo: github.com/modelcontextprotocol/python-sdk |
| `mcp-types` | 2.2.0 | pinned (exact-pinned dependency of `mcp` 2.2.0) | PyPI `requires_dist`: `mcp-types==2.2.0` |
| `ruff` | 0.16.9 | pinned (`requirements-dev.txt`) | `pip index versions ruff`; installed in `.venv`, `ruff check` ran |
| `pytest` | 9.1.1 | pinned (`requirements-dev.txt`) | `pip index versions pytest`; installed in `.venv`; harness tests ran on 3.14.5 and again on 3.13.15 |
| `strands-agents` | 1.57.1 | verified | PyPI JSON: classifiers include 3.14 |
| `bedrock-agentcore` | 1.23.1 | verified | PyPI JSON: classifiers list 3.10–3.13 (no 3.14). Resolved by using Python 3.13 for the project |
| `boto3` | 1.43.103 | verified | PyPI JSON: classifiers include 3.14 |
| `pydantic` | 2.13.5 | pinned | PyPI JSON: classifiers include 3.14 |
| `uvicorn` | 0.54.0 | pinned | PyPI JSON: classifiers include 3.14 |

State store (2026-09-28): Python's built-in `sqlite3` module, no new package. The bundled SQLite library is **3.50.4** in the project's Python 3.13.15 (`.venv\Scripts\python -c "import sqlite3; print(sqlite3.sqlite_version)"`). Used: `connect(check_same_thread=False, isolation_level=None)`, `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK`, `Row` factory. Nothing newer than SQLite 3.x basics. Schema bumped to **v2** on 2026-09-29 (added `contract_terms`); an older `.local/clucktalk.sqlite3` fails loud at startup and `python tasks.py reset-demo` clears it.

Full app dependency set (transitive included) is pinned in `requirements.txt`; on 2026-09-27 it matched `pip freeze` of the venv exactly (dev tools excluded). Notable transitive packages: `starlette` 1.7.0 (imported directly for ASGI types), `jsonschema` 4.26.0 (imported directly for argument validation), `httpx2` 2.13.1 (the SDK's HTTP client; also used by the contract tests).

## npm packages

| Package | Version | Status | Evidence |
|---|---|---|---|
| `@modelcontextprotocol/inspector` | 2.8.0 | verified, used outside the repo for evidence | `npm view @modelcontextprotocol/inspector version`; CLI flags read from `mcp-inspector --cli --help` (`--method`, `--tool-name`, `--strict`, `--protocol-era`) |
| `@modelcontextprotocol/ext-apps` | 2.0.0 (npm metadata modified 2026-09-25) | verified | `npm view @modelcontextprotocol/ext-apps version` |

## MCP protocol version: what SDK 2.2.0 actually speaks

Read from the installed wheel source (`mcp_types/version.py`), not from docs:

```
KNOWN_PROTOCOL_VERSIONS     = 2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25, 2026-07-28
HANDSHAKE_PROTOCOL_VERSIONS = 2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25   (initialize handshake)
MODERN_PROTOCOL_VERSIONS    = 2026-07-28                                         (stateless per-request envelope)
```

- **2025-11-25**, the version the design targets (docs/DESIGN.md §2), is the SDK's newest *handshake* version (`LATEST_HANDSHAKE_VERSION`). It keeps the `initialize → tools/list → tools/call → resources/read` flow and `Mcp-Session-Id` sessions. ✅
- A newer protocol, **2026-07-28**, exists and is stateless (no `initialize`). Amazon's Alexa+ docs target 2025-11-25. **Decision: stay on 2025-11-25** unless Amazon's current Alexa+ docs say otherwise; a contract test will assert the negotiated version.
- SDK 2.2.0 ships MCP Apps server support in-core (`mcp.server.apps`: `Apps` extension, `_meta.ui.resourceUri`, `text/html;profile=mcp-app`). The source comment says the TypeScript SDK ships it as the separate `@modelcontextprotocol/ext-apps` package, which the card side uses.

## AWS setup task (started 2026-09-28): see docs/AWS_SETUP.md

Region check from AWS docs (2026-09-28, sources in docs/AWS_SETUP.md §1): us-east-1, us-west-2 and ap-south-1 all
have every AgentCore feature we use (Runtime, Memory, Gateway, Identity, Observability, Policy, Evaluations), S3
Vectors, Titan Text Embeddings V2 and Polly neural (en-IN Kajal). Claude Sonnet 5 / Opus 5.5 are in-Region only in
us-east-1 (Geo in us-west-2, Global only in ap-south-1). Recommended: **us-east-1**.

Verified in the account 2026-09-28 (AWS CLI **2.37.4**, profile `clucktalk`; full table in docs/AWS_SETUP.md §5):
plan PAID/ACTIVE; Claude models in us-east-1 are inference-profile only; profile IDs listed from the account
(`us.anthropic.claude-sonnet-5`, `us.anthropic.claude-haiku-4-5-20251001-v1:0`, `us.amazon.nova-2-lite-v1:0`, …);
Nova models accessible, Claude agreement not yet created; **all inference quotas for these models are 0** (blocker,
FRICTION_LOG FL-014); Polly Kajal neural available.

Re-checked 2026-09-29 after AWS Support's quota-case replies (docs/AWS_SETUP.md §5.1, FRICTION_LOG FL-016):
**Nova 2 Lite now has a real applied quota** (20 requests/min, 8M tokens/min cross-region; reduced from the
2,000/8M defaults) and its Marketplace agreement is `AVAILABLE` — the only one of the three ready for a live call,
not yet proven with one. **Haiku 4.5's quota is also fixed** (10 requests/min, 5M tokens/min), but its Anthropic
Marketplace agreement is still `NOT_AVAILABLE`, which now the blocker, not quota. **Sonnet 5 cross-region tokens/min
is still 0** (default 6,000,000) and its agreement is also `NOT_AVAILABLE` — matches Support's "some higher-tier
foundation models may not be available at this access level."

Still to verify: the Anthropic Marketplace agreement (console "Model access" page, account owner only); Guardrails
and Knowledge Bases on S3 Vectors in us-east-1, plus S3 Vectors pricing (Rule 1 alternative to AOSS).

**First live Converse call, 2026-09-29** (docs/AWS_SETUP.md §5.2): Nova 2 Lite (`us.amazon.nova-2-lite-v1:0`,
us-east-1) answered a real prompt — the account-verification gate (FL-018) had cleared. 57 input + 14 output
tokens, ≈$0.00005. A second, unrelated CLI bug found in the same step: the AWS CLI on Windows crashes writing a
response containing certain Unicode (an emoji) to a redirected file (FL-019; workaround: `PYTHONIOENCODING=utf-8`).
Haiku 4.5 and Sonnet 5 are still not callable (Marketplace agreement / quota gaps above).

## SDK behaviors verified in source (mcp 2.2.0, 2026-09-27)
Each one shaped the server design; the contract tests pin them.
- `MCPServer` (FastMCP was renamed in 2.x; `mcp.server.fastmcp` now raises on import).
- `streamable_http_app(host=localhost)` auto-enables DNS-rebinding protection but allows **any localhost port** as Origin; CluckTalk passes its own allow-list (FRICTION_LOG FL-003). Absent `Origin` is allowed (non-browser clients); a present, unlisted one gets 403; bad `Host` gets 421.
- The session manager routes any `MCP-Protocol-Version` header outside the handshake set (e.g. 2026-07-28) to the stateless path; CluckTalk's `ProtocolVersionGate` returns 400 for those. The SDK client's default `mode="auto"` probes `server/discover` first and falls back to `initialize` on that 400 (contract test).
- Tool errors: crash → `"Error executing tool <name>"`; bad arguments → pydantic text. CluckTalk's `SafeToolErrors` middleware replaces both (FL-002).
- Middleware return values are not version-shaped by the runner, so `resultType` must be stripped for 2025-11-25 (FL-001).
- `Annotated[CallToolResult, Model]` return type: publishes `Model` as `outputSchema`, validates `structuredContent` on success, lets the tool set `content`/`_meta` itself. The client validates `structuredContent` only when `isError` is false.

## MCP Apps (cards), checked 2026-09-27
| Item | Version | Status | Evidence |
|---|---|---|---|
| MCP Apps extension spec (`io.modelcontextprotocol/ui`) | **2026-01-26** (stable; a `draft` also exists) | used | `specification/2026-01-26/apps.mdx` and `src/spec.types.ts` (`LATEST_PROTOCOL_VERSION = "2026-01-26"`) read from github.com/modelcontextprotocol/ext-apps (main). The card sends `ui/initialize` with this `protocolVersion` |
| `mcp.server.apps` (in `mcp` 2.2.0) | 2.2.0 | used | `Apps.tool(resource_uri=...)`, `Apps.add_html_resource(...)`, `MCPServer(extensions=[apps])` read in the installed source; wire shape confirmed by a scratch probe and pinned by `tests/contract/test_card.py`. On 2025-11-25 the server's `capabilities.extensions` is not sent (FRICTION_LOG FL-008) |
| `@modelcontextprotocol/ext-apps` (JS SDK) | 2.0.0 | **not used** | The card speaks the documented postMessage protocol directly, so no Node build and no npm dependency |
| Noto Sans Telugu | **2.005** (Regular 400, Bold 700, OTF) | bundled (`ui/fonts/`) | Official release `NotoSansTelugu-v2.005` (2023-09-28, latest Sans release on 2026-09-27) from github.com/notofonts/telugu; SIL OFL 1.1; checksums in `ui/fonts/README.md` |

The Simulator adds no dependencies: it uses Starlette (routing, static files), uvicorn and httpx2, already pinned for the server.
