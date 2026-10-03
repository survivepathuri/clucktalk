# Product feedback (skeleton)

One section per tool, API or SDK that this repo actually imports or uses, and one for AWS services. The list was taken from `requirements.txt`, `requirements-dev.txt`, `.github/workflows/ci.yml`, the imports in `src/`, `scripts/` and `tasks.py`, and the dated evidence in `docs/`. It was not written from memory.

Rules for this file: an answer appears only when the repo backs it (a friction-log entry, a doc, a test). Everything else is `TODO` and stays `TODO` until someone has verified it. Friction facts live in `FRICTION_LOG.md` (FL numbers); this file points to them and does not repeat them.

The five questions for every section:
1. Which tools, APIs or SDKs did you use, and for what?
2. What worked well?
3. What needs work?
4. Onboarding: from zero to hello world, how was it?
5. Would you build with it again? Yes or no, and why.

Questions 2, 4 and 5 are opinions or measurements that nothing in the repo records yet, so they are `TODO` throughout.

---

## 1. Alexa+ (docs, MCP Toolkit, validation tools)

1. **Used for:** the product target. CluckTalk is a self-hosted MCP server (implements MCP 2025-11-25 over Streamable HTTP; the SDK also negotiates older versions, no minimum is enforced) built to Amazon's published Alexa+ guidance (`docs/SOURCES.md`, `docs/DESIGN.md`). The Alexa+ docs were read, not run: no real Alexa+ device or the official validation tools were used (FL-024).
2. What worked: TODO
3. **Needs work (from the friction log):** FL-009 (no MCP Apps card size, `ui/*` methods, CSP or fonts), FL-017 (no statement on proactive notifications or identifying household members for MCP add-ons), FL-024 (no self-serve path to the Alexa AI CLI / Local Inspector for participants; documentation-based, no install attempted). The rest: TODO
4. Onboarding, zero to hello world: TODO (FL-024 covers only the validation-tool prerequisite)
5. Build again, yes or no and why: TODO

## 2. `mcp` Python SDK 2.2.0 and `mcp-types` 2.2.0 (MCP server, Streamable HTTP, MCP Apps extension)

1. **Used for:** the MCP server (`src/clucktalk/server/app.py`: `MCPServer`, `streamable_http_app`, `TransportSecuritySettings`, `mcp.server.apps.Apps`), tool results and middleware (`server/errors.py`, `server/tools/*`), protocol-version constants (`mcp_types.version`). Pinned in `requirements.txt`.
2. What worked: TODO
3. **Needs work (from the friction log):** FL-001 (middleware results are not version-shaped), FL-002 (default error text has the tool name and validation details), FL-003 (localhost Origin allow-list accepts every local port), FL-004 (SDK client and Inspector disagree on `outputSchema` for `isError`), FL-008 (the Apps extension is not declared in `initialize` on 2025-11-25), FL-011 (a duplicate in-flight JSON-RPC id is silently never answered).
4. Onboarding, zero to hello world: TODO
5. Build again, yes or no and why: TODO

## 3. MCP Apps (spec 2026-01-26) and its reference host (`ext-apps` basic-host)

1. **Used for:** the four cards in `ui/cards/` (built into `src/clucktalk/server/cards/`), written against the documented postMessage protocol without the JS SDK. The ext-apps `basic-host` was built and started to test the cards (`docs/evidence/2026-10-01_basic_host/README.md`). It is not a dependency of the code.
2. What worked: TODO
3. **Needs work (from the friction log):** FL-006 (spec example sends `clientInfo`, schema requires `appInfo`), FL-007 (default CSP has no `font-src`; fall-through of a blocked font source undocumented), FL-021 (basic-host cannot be built from its README).
4. Onboarding, zero to hello world: TODO
5. Build again, yes or no and why: TODO

## 4. MCP Inspector 2.8.0 (CLI)

1. **Used for:** capturing evidence of tool calls and error results (`docs/evidence/`); the stand-in for the Alexa+ Local Inspector (FL-024). Not a dependency of the code.
2. What worked: TODO
3. **Needs work (from the friction log):** FL-004 (validates error `structuredContent` against the success schema); FL-005 (the CLI crashes on Windows when a call ends in an error; see `docs/DEV_NOTES.md`).
4. Onboarding, zero to hello world: TODO
5. Build again, yes or no and why: TODO

## 5. Starlette 1.7.0, uvicorn 0.54.0, pydantic 2.13.5, jsonschema 4.26.0, httpx2 2.13.1

1. **Used for:** the ASGI app and its middleware (starlette, uvicorn); tool input and output models (pydantic); validating tool arguments against the advertised `inputSchema` (`jsonschema`, `server/errors.py`); the Simulator's MCP client, the contract tests and `scripts/` HTTP calls (httpx2). All pinned in `requirements.txt`.
2. What worked: TODO
3. What needs work: TODO (no friction-log entry names these)
4. Onboarding, zero to hello world: TODO
5. Build again, yes or no and why: TODO

## 6. SQLite (Python standard library `sqlite3`)

1. **Used for:** the farm's saved state (`src/clucktalk/store/sqlite.py`): profile, proposals, records, health checks, vet handoffs, follow-up answers.
2. What worked: TODO
3. What needs work: TODO
4. Onboarding, zero to hello world: TODO
5. Build again, yes or no and why: TODO

## 7. Noto Sans Telugu 2.005 (font, SIL OFL 1.1)

1. **Used for:** Telugu text on every card, inlined as `data:` URIs by `scripts/build_cards.py` (`ui/fonts/`, `ui/fonts/README.md`).
2. What worked: TODO
3. **Needs work (from the friction log):** FL-007 (whether a strict host keeps an inlined font).
4. Onboarding, zero to hello world: TODO
5. Build again, yes or no and why: TODO

## 8. Python tooling: ruff 0.16.9, pytest 9.1.1; Node.js (optional card test)

1. **Used for:** lint and format (`ruff`), the harness, unit and contract tests (`pytest`), all run by `python tasks.py check`; Node.js only for the card number-format test, which is skipped when Node is missing.
2. What worked: TODO
3. What needs work: TODO
4. Onboarding, zero to hello world: TODO
5. Build again, yes or no and why: TODO

## 9. GitHub Actions (`.github/workflows/ci.yml`: `actions/checkout@v7`, `actions/setup-python@v7`)

1. **Used for:** running `python tasks.py setup` and `python tasks.py check` on ubuntu and windows with Python 3.12 and 3.13; a manual-only macOS job.
2. What worked: TODO
3. **Needs work (from the dev notes):** FL-023 (Windows timer granularity broke a lower-bound timing test; see `docs/DEV_NOTES.md`).
4. Onboarding, zero to hello world: TODO
5. Build again, yes or no and why: TODO

## 10. Claude Code (the coding assistant used to build this repo)

1. **Used for:** writing and checking the code in this repo. The shell tool is where FL-022 happened (see `docs/DEV_NOTES.md`).
2. What worked: TODO
3. **Needs work (from the dev notes):** FL-022 (backslash sequences changed in shell heredocs).
4. Onboarding, zero to hello world: TODO
5. Build again, yes or no and why: TODO

---

## AWS services

Live mode is off by default; the demo and every test run with `MOCK_BEDROCK=true` and make no AWS call. The live path is `src/clucktalk/agents/__init__.py` and `agents/bedrock.py` (boto3 1.43.103, botocore 1.43.104). Verified calls and checks are dated in `docs/AWS_SETUP.md`.

### Amazon Bedrock Runtime (`Converse`) with Amazon Nova 2 Lite (`us.amazon.nova-2-lite-v1:0`, us-east-1)

1. **Used for:** the live AI mode of the health-triage and briefing agents on the synthetic demo farm (`agents/bedrock.py`); one real Converse call and one 2-call spike on forced tool choice and image input (`docs/AWS_SETUP.md` §5.2, §5.3).
2. What worked: TODO (the repo records that the forced tool call worked with text and with image input, FL-020; nothing else is claimed here)
3. **Needs work (from the friction log):** FL-014 (models AVAILABLE but every quota 0, then an account-verification gate), FL-019 (the AWS CLI truncated a response file on Windows when the reply held an emoji), FL-020 (`toolChoice` support documented only as "if supported by model"; one colour misread).
4. Onboarding, zero to hello world: TODO
5. Build again, yes or no and why: TODO

### Amazon Bedrock model access, Service Quotas and AWS Support

1. **Used for:** reading model availability and quotas (`aws bedrock get-foundation-model-availability`, `aws service-quotas`) and two Support cases for quota increases (`docs/AWS_SETUP.md` §5, §5.1).
2. What worked: TODO
3. **Needs work:** FL-014.
4. Onboarding, zero to hello world: TODO
5. Build again, yes or no and why: TODO

### AWS account setup: Billing, credits, IAM Identity Center, AWS CLI v2 (AWS India account)

1. **Used for:** a key-free CLI identity through IAM Identity Center, the account plan and credit checks (`docs/AWS_SETUP.md` §2-§4).
2. What worked: TODO
3. **Needs work (from the friction log):** FL-012 (the recommended CLI identity depends on the account plan), FL-013 (plan not shown in the console for an AWS India account; credit rules missing), FL-015 (billing error names the wrong cause).
4. Onboarding, zero to hello world: TODO
5. Build again, yes or no and why: TODO

### Mentioned but not used

Amazon Polly appears in comments as the planned voice of the live Simulator host and is not imported or called. `strands-agents` and `bedrock-agentcore` are listed in `docs/VERSIONS.md` as "verified", not as dependencies, and are not imported. No AWS service beyond the three sections above is called by the code.
