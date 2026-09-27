# CLAUDE.md: CluckTalk build rules

CluckTalk (Telugu subtitle "కోడి మిత్ర") is an Alexa+ add-on for Indian poultry farmers: a self-hosted MCP server (spec 2025-11-25, Streamable HTTP) plus an Agent Skill.
These are the project's non-negotiable engineering rules. A maintainer's local `CLAUDE.local.md` (gitignored) may add the product spec, progress log, and phase plan. If rules disagree, stop and ask.

## Session protocol (Rule 10)
**Start**: read this file, the progress log, the current phase plan, and the last 10 entries of `FRICTION_LOG.md`.
**End**: update the progress log (done / evidence / next / risks / open questions). Then print `Friction log: N entries total (+M today)`.

## Windows commands (cmd first; Docker not required)
```
python tasks.py setup       :: create .venv + install pinned deps
python tasks.py check       :: lint + format + tests + AOSS check + secret scan  (run after EVERY change)
python tasks.py eval-fast   :: golden evals in mock mode, no AWS (after changing a tool/schema/prompt)
python tasks.py serve       :: MCP server only, demo data, http://127.0.0.1:8765/mcp
python tasks.py run         :: local demo: Simulator + MCP server, mock mode
.venv\Scripts\python -m ruff format .      :: auto-format
.venv\Scripts\python scripts\telugu_review.py  :: regenerate docs\TELUGU_REVIEW.md after changing any Telugu or English wording
.venv\Scripts\python -m pytest -q tests\unit   :: run one test folder
```
- Local development and the reviewer path use a **Python venv only**. Docker/`docker-compose` is optional and must never be required.
- Target: at most 5 commands from `git clone` to the first card.
- Project Python is **3.13** (`tasks.py setup` finds it via `py -3.13`). Python 3.14 may be the system default, but `bedrock-agentcore` doesn't list 3.14 support.
- Mock-first: every AWS verification waits for the "AWS setup" task.

## Guiding principles
- Every user-visible detail matters: README, UI, error messages, eval table, architecture diagram.
- **Honesty first.** Never claim a feature works unless it has been verified. Never invent numbers or fake results.
- When unsure, choose the option that (1) keeps the current phase on schedule, (2) is more verifiable, (3) is closer to Amazon's published Alexa+ guidance.

---

## ⚠️ 12 CRITICAL BUILD RULES (non-negotiable)

### RULE 1: NEVER use Amazon OpenSearch Serverless
- Never create, provision, or reference OpenSearch Serverless (AOSS): not in CDK, scripts, Knowledge Base config, or defaults. It bills always-on capacity.
- For live mode, use a pay-per-use vector store (e.g., Amazon S3 Vectors; verify support and pricing first). For mock mode, use a local in-process index.
- `scripts/check_no_aoss.py` scans `cdk synth` output (`cdk.out/`) and infra/source files. It runs in `check` and before every deploy.

### RULE 2: Friction log from Day 1
- Keep `FRICTION_LOG.md` and `FEATURE_REQUESTS.md` current.
- Append an entry **immediately** on any SDK/API error, confusing message, doc gap, workaround, slow setup, or platform limitation. Never batch; never invent.
- Fields: date, tool/service, task, steps, expected vs actual, severity, workaround, actionable suggestion.
- End every session with: `Friction log: N entries total (+M today)`.

### RULE 3: Nothing is "done" without passing the harness
- After any change, run `python tasks.py check`. After changing a tool, schema, or prompt, also run `python tasks.py eval-fast` and report the score delta.
- Never weaken, skip, or delete a test or eval to make it pass. If an expectation looks wrong, stop and ask.

### RULE 4: Latency budget
- Every MCP tool returns in **< 500 ms (p95)** from precomputed state. No synchronous LLM calls inside tools. Slow work goes to an async slow path.

### RULE 5: Verify before claiming done (evidence required)
- "Done" requires evidence: command output, test output, a real MCP call transcript, or a screenshot path. Paste the evidence summary in the reply and in the progress log.
- Run the actual user flow end-to-end (Simulator → MCP → card), not only unit tests.

### RULE 6: Fail loud, never fake
- Priority: works correctly > visible fallback with warning > clear error > **never** silent degradation.
- Never insert sample/mock data as a silent fallback when a real call fails. Mock mode exists only when `MOCK_BEDROCK=true` is set explicitly, and the UI then shows a visible "Demo data" badge.
- No bare `try/except: pass`. Log every caught exception with context and surface it as a structured error. (Enforced by ruff rules E722, BLE001, S110.)

### RULE 7: No hallucinated APIs or packages
- Before using any package, confirm it exists and pin its exact version. Before using any SDK method, check the official docs or the installed package source (`.venv\Lib\site-packages\...`). If a doc and existing code disagree, **stop and report**. Do not silently "fix" either one.
- Record every confirmed version in `docs/VERSIONS.md`.

### RULE 8: Scope discipline
- Build only what the current phase plan lists. Never start P1 before all P0 evals pass.
- Answer questions as questions; do not treat "why did you do X?" as "change X".
- For any change touching more than ~5 files or the architecture, present a plan and wait for approval.
- Don't revert verified work because an unrelated test fails. Investigate first.

### RULE 9: Secrets and safety of the repo
- Never commit credentials, `.env`, AWS keys, or tokens. Commit `.env.example` only. `scripts/scan_secrets.py` runs in `check`.
- Never commit `CLAUDE.local.md` or anything under `private/`; both are gitignored and stay local.
- Commit author email is `Survivepathuri@gmail.com` (maintainer's explicit choice). No other personal data (emails, phone numbers, addresses, names) in files or commit messages.
- No real personal data of farmers in the repo. Use seeded demo data only, clearly fictional.

### RULE 10: Session memory (beat cold-start amnesia)
- At session start: read `CLAUDE.md`, the progress log, the current phase plan, and the last 10 friction-log entries.
- At session end: update the progress log (done / evidence / next / risks / open questions).
- If context gets long, summarize into the progress log and start a fresh session rather than continuing degraded.

### RULE 11: Independent review for every P0 feature
- After finishing a P0 feature, run a separate review pass (fresh subagent/session). It reads the code cold against `docs/DESIGN.md` (§5 tool contract rules, §6 behavior requirements, §7 safety rules, §12 pitfalls). Fix its findings before moving on.

### RULE 12: Cross-platform
- User is on Windows (cmd). All scripts are Python (`tasks.py`), with no bash/make dependency. Build paths with `pathlib`. Document Windows commands first.

---

## Project facts to keep straight
- Name lives in **one config constant** (rename = one-line change).
- MCP: protocol **2025-11-25** via the `initialize` handshake. The `mcp` SDK version is pinned in `docs/VERSIONS.md`. A newer stateless protocol, 2026-07-28, exists; do not switch without approval.
- Every tool returns `text_en` + `text_te` + `structuredContent`, plus `_meta.ui.resourceUri` when a card exists.
- Simulated data (market rates, sensors, supplier, SMS, payments) is always labeled "Simulated".
