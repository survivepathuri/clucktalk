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
| `mcp` (official MCP Python SDK) | **2.2.0** (latest; released 2026-09-07) | verified, pin at MCP server skeleton step | `pip index versions mcp`; PyPI JSON: `requires_python >=3.10`, classifiers include 3.14. Repo: github.com/modelcontextprotocol/python-sdk |
| `mcp-types` | 2.2.0 | verified (exact-pinned dependency of `mcp` 2.2.0) | PyPI `requires_dist`: `mcp-types==2.2.0` |
| `ruff` | 0.16.9 | pinned (`requirements-dev.txt`) | `pip index versions ruff`; installed in `.venv`, `ruff check` ran |
| `pytest` | 9.1.1 | pinned (`requirements-dev.txt`) | `pip index versions pytest`; installed in `.venv`; harness tests ran on 3.14.5 and again on 3.13.15 |
| `strands-agents` | 1.57.1 | verified | PyPI JSON: classifiers include 3.14 |
| `bedrock-agentcore` | 1.23.1 | verified | PyPI JSON: classifiers list 3.10–3.13 (no 3.14). Resolved by using Python 3.13 for the project |
| `boto3` | 1.43.103 | verified | PyPI JSON: classifiers include 3.14 |
| `pydantic` | 2.13.5 | verified | PyPI JSON: classifiers include 3.14 |
| `uvicorn` | 0.54.0 | verified | PyPI JSON: classifiers include 3.14 |

## npm packages

| Package | Version | Status | Evidence |
|---|---|---|---|
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

## Not yet verified: moved to the "AWS setup" task (no AWS account yet; user decision 2026-09-27)

Development continues mock-first. In the AWS setup task: verify which region supports **every** AgentCore feature we use (Runtime, Memory, Observability; P1: Gateway, Policy, Evaluations), then recommend one.

- AWS region with Bedrock, Guardrails, AgentCore Runtime/Memory/Observability, and S3 Vectors all available
- Bedrock model access enabled for the chosen host and multimodal models (model IDs)
- S3 Vectors as a Bedrock Knowledge Base vector store, plus its pricing (Rule 1 alternative to AOSS)
