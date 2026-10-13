# A one-page guide for judges

**Python 3.12 or 3.13 is required.** Check it first: `python --version` on Windows, `python3 --version` on macOS and Linux. Use `python` on Windows and `python3` on macOS and Linux in every command below. No virtual-environment activation is needed: `tasks.py` creates and uses its own `.venv`. Nothing else is needed: no Docker, no AWS account, no Node.js (Node.js is optional, see minute 2).

If you do not have Python 3.12 or 3.13 (these install lines are the ones in the README; they were not run here):

- Windows: the installer from python.org (tick "Add python.exe to PATH"), or `py install 3.13` if you have the Python install manager.
- macOS: `brew install python@3.13`
- Ubuntu: `sudo apt install python3 python3-venv` (Ubuntu 24.04 ships Python 3.12). On an older Ubuntu, use the deadsnakes PPA or `pyenv install 3.13`.

CluckTalk (కోడి మిత్ర) is a self-hosted **MCP server** (Streamable HTTP, spec 2025-11-25) for Alexa+, with a simulated Alexa+ web experience, for Indian broiler farmers. It tracks a shed's deaths, feed and health checks, and tells the farmer in English and Telugu what needs attention first. Nothing here has run on an Alexa+ device; the Simulator plays the client role.

## Run it: three commands

Windows cmd:

```
rem the three commands, one after the other
python tasks.py setup
python tasks.py verify
python tasks.py serve
```

Windows PowerShell:

```
# the three commands, one after the other
python tasks.py setup
python tasks.py verify
python tasks.py serve
```

macOS or Linux (bash or zsh):

```
# the three commands, one after the other
python3 tasks.py setup
python3 tasks.py verify
python3 tasks.py serve
```

`setup` creates `.venv` and installs the pinned dependencies. `verify` prints one table of what you can check, in about 30 seconds. `serve` starts the MCP server at http://127.0.0.1:8765/mcp with a fictional demo farm; leave it running.

`verify` starts its own temporary server, so it does not need `serve`. `serve` is needed only to call the tools yourself (minute 2). For the Simulator in a browser (Echo Show and Echo Dot modes, cards, a panel showing the exact MCP calls), run `python tasks.py run` instead of `serve`; it opens http://127.0.0.1:8766/. Everything runs on seeded, fictional data in mock mode and shows a "Demo data" badge.

## Ports and browser

If port 8765 (MCP server) or 8766 (Simulator) is busy, `run` and `serve` print one line that names the port and start nothing. If no browser opens, open the URL printed after "ready". To choose another port or stop the browser from opening, set the variables like this (one example per shell; the first is cmd, the second PowerShell, the third bash or zsh):

```
set CLUCKTALK_PORT=8775
$env:CLUCKTALK_PORT = "8775"
export CLUCKTALK_PORT=8775
```

The same syntax sets `CLUCKTALK_SIMULATOR_PORT` (default 8766) and `CLUCKTALK_NO_BROWSER=1`. For example, `set CLUCKTALK_NO_BROWSER=1` in cmd, `$env:CLUCKTALK_NO_BROWSER = "1"` in PowerShell, `export CLUCKTALK_NO_BROWSER=1` in bash or zsh.

## Five minutes, in this order

1. **Minute 1: run `verify`** and read the table. Then open `docs/RESULTS.md` (test counts, the golden evals, mutation checks, protocol conformance, latency, readiness, the independent reviews). The table and most of that page are generated from this machine's own runs; the mutation checks and the reviews are copied by hand from the builder's log, and the page says so.
2. **Minute 2: see the tool calls.** Run `python tasks.py inspector-replay` (`python3` on macOS and Linux). It needs no Node.js and no running `serve`: it replays the flow Amazon documents for its Local Inspector against a temporary copy of the server (our replay; the Local Inspector itself was not run). Second option, **needs Node.js**, with `serve` running in another window: `npx @modelcontextprotocol/inspector@2.8.0 --cli http://127.0.0.1:8765/mcp --method tools/list` lists the 14 tools. `verify` (minute 1) needs neither Node.js nor a running server. To see skipped tests, for example when Node.js is missing, run `pytest -rs`: `.venv\Scripts\python -m pytest -rs tests\harness` on Windows, `.venv/bin/python -m pytest -rs tests/harness` on macOS and Linux.
3. **Minute 3: ask the Simulator** "How is shed two doing?" Then say "5 birds died in shed 1". It reads the number back and saves nothing until you say yes.
4. **Minute 4: the safety rules.** `docs/SAFETY_MATRIX.md` has one row per rule: where it came from, where it is in the code, which tests pin it, a before and after example, and which thresholds are general guidance that may not fit a given farm.
5. **Minute 5: the limits.** The claims table in the README (section "What is verified, unverified and simulated") says for each claim whether it is verified, simulated, unverified or not built, with the file or command that shows it.

## Where things are

| What | Where |
|---|---|
| The 14 MCP tools | `src/clucktalk/server/tools/` (one file per feature; registered in `src/clucktalk/server/app.py`) |
| The Alexa+ Simulator (simulation source) | `src/clucktalk/simulator/` (the page is in `src/clucktalk/simulator/static/`) |
| Safety rules in code | `src/clucktalk/domain/` (`status.py`, `triage.py`, `follow_up.py`, `thresholds.py`) |
| Golden evals | `data/eval/golden_cases.json`, results in `docs/EVALS.md` |
| The architecture | `docs/ARCHITECTURE.md`; the full design is `docs/DESIGN.md` |
| What the pilot is | `docs/PILOT_RUNBOOK_WINDOWS.md` (no farmer has used it yet; usage numbers pending; the Lightsail cloud pilot with the sample farm has been deployed since 2026-10-13) |
| Friction with the platforms we used | `FRICTION_LOG.md`, `FEATURE_REQUESTS.md`, `docs/PRODUCT_FEEDBACK.md` |
| Security notes | `SECURITY.md` |
| The Agent Skill | `skills/clucktalk/` |

## Known limits, in plain words

- **Not on an Alexa+ device.** No Alexa+ device, Alexa speech or Amazon review was involved. Alexa composes its own speech, so what it says can differ from our sentences.
- **Not built:** OAuth 2.1 with PKCE, Protected Resource Metadata, a remote HTTPS URL for the Alexa+ add-on, security and data policies (`docs/ALEXA_READINESS.md`, `docs/PRODUCTION_PATH.md`).
- **Latency numbers** are server times on localhost in mock mode. Amazon's 500 ms is a round trip including the network, so we do not claim to meet it end to end.
- **Simulated:** prices, sensors, the supplier, SMS and payments, and the whole demo farm.
- **No veterinary or agronomic review.** The thresholds are general guidance or the builder's heuristics (`docs/SAFETY_MATRIX.md`). No tool gives a medicine or a dose.
- **Telugu:** 86 of 433 strings reviewed by the builder, a native Telugu speaker; 347 pending (including the pilot page); no independent review. No Telugu voice was tested through Alexa+ (`docs/TELUGU_REVIEW.md`).
- **In demo mode a shed with no alert is still described as doing well;** pilot mode says "no alert from the checks I can make".
- **Live AI** (Amazon Bedrock Nova 2 Lite) is off by default; the server's live path was not verified end to end here.
- **The farmer pilot** has a PC version (the builder's own PC through a free tunnel) and a Lightsail cloud version. No farmer has used the pilot yet, so usage numbers are pending (`docs/RESULTS.md`, section 9). The Lightsail cloud pilot with the sample farm has been deployed since 2026-10-13; results will be added after the pilot.
