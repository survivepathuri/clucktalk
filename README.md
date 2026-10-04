# CluckTalk (కోడి మిత్ర)

The voice farm manager for India's **broiler** poultry farmers. A self-hosted MCP server (implements MCP 2025-11-25 over
Streamable HTTP) plus an Agent Skill, built for the Alexa+ add-on program.

> **Status**: in development. Nothing below is claimed working unless it has evidence in `docs/evidence/` or a
> passing check in `python tasks.py check` / `python tasks.py eval-fast`. See `docs/DESIGN.md` for the full design
> and what is built vs planned, and `docs/EVALS.md` for the current golden-suite score.

## Try it now

Windows (cmd; on Linux or macOS use `python3`). Python 3.12 or 3.13, no Docker, no AWS account:

```
python tasks.py setup        :: creates .venv and installs the pinned dependencies
python tasks.py verify       :: one table of what a judge can check, in about 30 seconds (not the full test suites)
python tasks.py readiness    :: our own self-check of the locally checkable Alexa+ requirements (not an Amazon verdict)
python tasks.py serve        :: the MCP server on http://127.0.0.1:8765/mcp with fictional demo data (leave it running)
```

With `serve` running, in a second window, the MCP Inspector command line (`@modelcontextprotocol/inspector` 2.8.0, which
needs Node.js; our evidence in `docs/evidence/2026-09-27_farm_status_and_feed.md` used its installed `mcp-inspector --cli`,
and the `npx` form below is the same package but was not run in exactly this form):

```
npx @modelcontextprotocol/inspector@2.8.0 --cli http://127.0.0.1:8765/mcp --method tools/list
npx @modelcontextprotocol/inspector@2.8.0 --cli http://127.0.0.1:8765/mcp --method tools/call --tool-name get_farm_status --tool-arg "house=shed 2"
```

To see how a follow-up looks three days after a health check (the demo clock shifts follow-up and briefing dates only,
see "Demo clock" below):

```
python tasks.py demo-three-days
python tasks.py serve --demo-days-later 3
```

The local demo with the Alexa+ Simulator in a browser is `python tasks.py run` (see Quick start). Everything here runs on
seeded, clearly fictional data in mock mode.

## Known limitations

- **Nothing here has run on an Alexa+ device**, through Alexa's own speech, or through Amazon's review. The Local
  Inspector itself was not run (its guide is behind a Developer Console login, FL-024); `inspector-replay` is our replay of
  the documented flow.
- **Alexa composes its own speech** from a tool's result and description, so what it says can differ from our sentences.
  The card shows our sentence.
- **Not built:** OAuth 2.1 with PKCE, Protected Resource Metadata, a remote HTTPS URL, security and data policies. The
  server is for local use; off localhost it needs a bearer token, which is not Amazon's account linking.
- **Prices, sensors, the supplier, SMS and payments are simulated** and labelled Simulated. The demo farm is fictional.
- **The Telugu wording is not yet reviewed by a native speaker** (`docs/TELUGU_REVIEW.md` lists what is pending), and no
  Telugu voice has been tested through Alexa+.
- **The cards were tested at sizes of 10 inches and below only**; nothing was tested at 11 inches and above.
- **The sale-window hint** (`plan_sale`'s "best day to sell is within 3 days", simulated) shows on the daily briefing
  only. It never raises a shed's health status or its safety level.
- **`NOTICE` (third-party licenses)** was generated on Windows by `python tasks.py notices` from the installed package
  metadata. It is checked against the installed packages on every operating system the CI runs on (ubuntu and
  windows), by a test: a missing or changed package fails it, and only a package its platform marker excludes (pywin32 on Linux)
  may be listed there as not installed.
- **Latency numbers are localhost, mock mode, no model call.** A network, a remote host and a real model add to them.
- **No agronomic or veterinary review.** Thresholds and the reference curve are cited in `docs/SOURCES.md`; they were not validated with a vet or a farmer, and no tool gives a medicine or a dose.
- **Odd behaviours of the MCP SDK and of our shed-name reader** are listed under "Known SDK behaviors" below.

## What is verified, unverified and simulated

Each row names the file or test that shows it, so you can check it yourself. "Verified" means that evidence exists in
this repository, not that Alexa+ has seen it.

| Claim | Status | Evidence |
|---|---|---|
| The server implements MCP 2025-11-25 over Streamable HTTP (and negotiates three older versions, with no floor) | VERIFIED | `tests/contract/test_protocol_conformance.py`; the probe table in `python tasks.py verify` |
| The documented Local Inspector flow (JSON-only `Accept`, protocolVersion 2025-06-18) works against the server | VERIFIED (our replay, not Amazon's tool) | `python tasks.py inspector-replay`; `tests/harness/test_inspector_replay.py` |
| Every tool answers well under 500 ms at p95 on localhost, mock mode | VERIFIED (localhost only) | `python tasks.py inspector-replay`; `python tasks.py readiness` |
| The locally checkable Alexa+ requirements we encoded are met | VERIFIED (our checklist, not an Amazon verdict) | `python tasks.py readiness`; `docs/ALEXA_READINESS.md` |
| The briefing, the farm status and its card agree on safety, level and vet advice | VERIFIED | `tests/contract/test_safety_agreement.py`; `tests/contract/test_status_card_follows_safety.py`; `tests/unit/test_property_follow_up_sequences.py` |
| Malformed, oversized and odd input never gives a 500, a leak or a state change | VERIFIED | `tests/contract/test_fuzz_inputs.py`; `tests/contract/test_protocol_errors.py` |
| Spoken numbers equal card numbers (in the Simulator) | VERIFIED | `tests/crossmodal.py`; `tests/contract/test_card.py`; `docs/evidence/2026-09-27_card_and_simulator.md` |
| `reset-demo` never destroys real data silently | VERIFIED | `tests/harness/test_reset_demo_safety.py` |
| The golden eval suite passes in mock mode | VERIFIED (mock mode, no AWS) | `python tasks.py eval-fast`; `docs/EVALS.md` |
| The server runs on an Alexa+ device, or passes Amazon's review | UNVERIFIED | none; see "Known limitations" |
| The Local Inspector itself accepts the server | UNVERIFIED | none; `FRICTION_LOG.md` FL-024 |
| Telugu wording is natural and correct | UNVERIFIED | `docs/TELUGU_REVIEW.md` (pending native review) |
| Telugu voice works through Alexa+ | UNVERIFIED | none |
| The cards work at 11 inches and above | UNVERIFIED | `docs/DESIGN.md` (screen size classes) |
| Live AI (Amazon Bedrock) end to end | UNVERIFIED here | `docs/AWS_SETUP.md`; `FRICTION_LOG.md` FL-014 |
| Account linking, Protected Resource Metadata, a remote URL | NOT BUILT | `docs/ALEXA_READINESS.md` |
| Market prices, sensors, supplier, SMS, payments, the vet message sending | SIMULATED | `tests/contract/test_tool_descriptions_simulated.py`; `docs/DESIGN.md` section 9 |
| The demo farm and every farmer in it | SIMULATED (fictional) | `data/seed/demo_farm.json`; `tests/unit/test_seed.py` |

## Quick start (venv only; Docker is optional and never required)

Needs Python 3.12 or 3.13 (other versions from 3.11 run with a visible "untested" warning). Get it from
python.org, `brew install python@3.13` (macOS), `pyenv install 3.13`, or the deadsnakes PPA (Ubuntu).

Windows (cmd):

```
git clone <this repo>
cd CluckTalk
python tasks.py setup    :: creates .venv and installs pinned dependencies
python tasks.py run      :: starts the MCP server + the Alexa+ Simulator, opens http://127.0.0.1:8766/
```

Linux / macOS:

```
git clone <this repo>
cd CluckTalk
python3 tasks.py setup   # creates .venv and installs pinned dependencies
python3 tasks.py run     # starts the MCP server + the Alexa+ Simulator, opens http://127.0.0.1:8766/
python3 tasks.py check   # optional: lint + tests + AOSS check + secret scan
```

Set `CLUCKTALK_NO_BROWSER=1` to stop `run` from opening a browser. Node.js is optional: one card test
(`test_card_num_matches_the_server_formatter`) is skipped, with a reason, when `node` is not installed. The secret scan
in `check` needs a git checkout; on a ZIP download it prints "SKIPPED" and the rest of `check` still runs.

Try asking (typed or, if your browser supports it, spoken): *"How is shed two doing?"*, *"When should I sell shed
one?"*, *"How much feed does shed two need this week?"*, *"Switch my farm to contract farming"*.

Everything runs on seeded, clearly fictional demo data (`MOCK_BEDROCK=true`, shown as a "Demo data" badge). Live
mode (real Bedrock/Polly) needs an AWS account; see `docs/AWS_SETUP.md`.

## What it does today

- **Farm status** (`get_farm_status`) and **feed planning** (`plan_feed`) per shed, bilingual, with a card.
- **Sell-day plan** (`plan_sale`): the best day to sell a broiler shed, the break-even day, and why — or, for
  contract farmers, how each extra day changes FCR and the growing charge.
- **Farm profile** (`get_farm_profile`, `set_farm_mode`) and **contract terms** (`set_contract_terms`): switch
  between independent and contract farming, with an explicit read-back and "yes" before anything changes.
- **Daily briefing** (`get_daily_briefing`): the top things that need attention today, ranked, as a swipeable card. By
  voice it reads the top 3 and offers "more" (5 items at most). Health alerts always come first, decided by code; an
  AI model, only when live AI is switched on, may re-order the other items from a fixed list and can write no text.
  A death spike logged a few days ago still shows. A sale-window item is a simulated estimate and shows no rupees.
- **Voice record book** (`log_daily_record`, `get_record_book`): the farmer says deaths, feed, a weight sample or a
  treatment name; it is read back and saved only after an explicit "yes". No medicine advice and no doses.
- **Health triage** (`start_health_check`, `get_health_check`, `prepare_vet_handoff`): guidance, never a diagnosis.
  Code decides the urgency from the signs and the record book (a model can raise it, never lower it); a suspected
  reportable disease gets the report-and-isolate steps. The vet summary is a **simulated SMS** to a demo contact.
- **Follow-up** (`report_health_follow_up`): days after a flagged check the next briefing or farm status asks how the shed
  is now. "Same", "worse" and "not sure" always end with "To be safe, contact your vet or doctor." Nothing is pushed;
  CluckTalk only speaks when the farmer asks. A death spike logged after the check counts as "worse", including one
  logged on the check's own day after the check; one logged after a same-day vet handoff is not caught by the follow-up
  (the briefing's separate "N birds died yesterday" item still shows it).
- **What can you do?** (`get_help`).
- A local **Alexa+ Simulator** (Echo Show / Echo Dot device modes, voice and text, a developer panel showing the
  exact MCP wire).

## Voice versus cards, and what is not verified

In the Simulator the host speaks the tool's own text, so the card sentence equals the spoken sentence and every
number is the same on both (tested). **That equality holds in the Simulator only.** On Alexa+ the assistant composes
its own speech from the tool result and the tool descriptions, so the words it says can differ from ours; the card
still shows the tool's own sentence. We cannot script Alexa's wording, and no Alexa+ device has loaded CluckTalk.

The server implements MCP 2025-11-25 over Streamable HTTP; for compatibility the SDK also negotiates 2025-06-18, 2025-03-26 and 2024-11-05, and we do not enforce a minimum version. Known limits: it accepts a missing or different `MCP-Protocol-Version` header on an established session, a POST without an `Accept` header returns 406 (the SDK builds a transport for it and discards it at once; no session is left open, tested), and two simultaneous requests with the same JSON-RPC id in one session leave one unanswered. Sessions that clients never end stay open until the SDK's 30-minute idle timeout, at most 10,000 at once. To see what it answers for each version, run `python tasks.py probe-protocol-version` (temporary state file, no AWS; it reports what it saw and judges nothing).

`python tasks.py inspector-replay` replays the flow documented on Amazon's Local Inspector page against a temporary copy of the server (a temporary state file, mock mode, no AWS): `initialize` with protocolVersion 2025-06-18 and clientInfo `addon-local-inspector` using `Accept: application/json` only, the initialized notification, `tools/list`, `resources/read` for every `ui://` card and a `tools/call` for every tool. It prints a step table and the p50 and p95 per step over 20 rounds. **It is our replay of the documented flow, not Amazon's tool, and the Local Inspector itself was not run** (its guide is behind a Developer Console login, FL-024). On this machine the server answers the JSON-only request correctly at every step.

**The `safety` field.** `get_daily_briefing` and `get_farm_status` also return a structured `safety` object (`level`
OK / WATCH / ALERT / UNKNOWN, `reason_codes`, `vet_contact_advised`) that equals the card's level. The briefing and the farm status read it
from the same facts, so they agree on it for the same farm; a death spike logged on an earlier day this week is on the
shed's status card too (the same sentence the briefing uses). The limitation, in
plain words: Alexa+ composes its own speech from a tool's result and its description, so a safety step that lives only
in our sentence can be left out. The field exists so a host can surface the urgency itself. We do not claim Alexa+ uses
it, and it is not yet on the health-check and follow-up answers.

**Unknown shed names.** If a farmer names a shed that does not exist, the error repeats the name only after it is
cleaned and shortened (letters and digits, at most 24 characters; control characters, emoji and markup removed), then lists
the real sheds. An empty or emoji-only name is spoken as an empty name, because the project has no name-free sentence
for it yet.

## Known SDK behaviors

Things the MCP Python SDK (`mcp` 2.2.0) or our shed-name reader does that you might not expect. Each one has a test that pins it, so a change after an SDK upgrade shows up as a failing test.

- **An odd request id is accepted without an answer.** A JSON-RPC id that is an object, a list or a decimal number gets an empty `202`, as if the request were a notification, instead of an error. Nothing is changed or saved. (`test_..._finding_f3` in `tests/contract/test_fuzz_inputs.py`.)
- **The shed-name reader ignores symbols and non-Latin words.** It keeps only plain letters and digits, so `shed -1` and `🐔 1` both mean shed 1. It never maps a name to a different shed, and a name with two different numbers is refused. This is our own reader, not the SDK's. (`..._finding_f4`.)
- **Two overlapping requests with the same JSON-RPC id in one session leave one unanswered.** One request can stay unanswered for at least 40 seconds, or, on some runs, is answered at once with a 500 "Session terminated before the request completed" (the SDK's own message). The protocol requires unique ids, so this is a client mistake, but nothing tells the client. The session and the other requests keep working. This is friction entry FL-011. (`tests/contract/test_concurrency.py`.)
- **Session limits are the SDK defaults, which we do not change:** at most 10,000 sessions at once, and a session nobody ends is closed after 30 minutes without a request.

## Demo clock (for recordings only)

`python tasks.py serve --demo-days-later 3` (or `run`) makes "today" three days later, so a recording can show how a
follow-up asks about a shed days after a health check. Its **honest scope: it shifts follow-up and briefing dates only.**
Flock ages, the record-book entries and the sale plan do not move (the seeded farm is rebuilt for the shifted date, so
they look exactly as before), so a video must not present it as time passing for the flock. It is demo mode only (live
mode refuses it) and no tool can set it. It uses a **separate state file** next to the live one
(`.local/clucktalk_demo_clock.sqlite3`, marked as a demo-clock file) and never the live farm state; a demo-clock file
is refused without the clock, and `python tasks.py reset-demo` clears both files.

## See three days later in 3 commands

For a recording of how the follow-up asks about a shed days after a health check (mock mode, venv only, no AWS):

```
python tasks.py demo-three-days
python tasks.py serve --demo-days-later 3
python tasks.py reset-demo --yes
```

1. `demo-three-days` builds the separate demo-clock state file by making real MCP calls: a watch check on shed one and an
   urgent check on shed two on day 0, and the "worse" answer for shed two on day 1. It refuses live mode, never opens the
   live farm state, and refuses to overwrite an existing demo-clock file.
2. `serve --demo-days-later 3` serves that file with "today" three days later. Open it in the ext-apps basic-host
   (`SERVERS=["http://127.0.0.1:8765/mcp"]`, `CLUCKTALK_ALLOWED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080`;
   see `docs/evidence/2026-10-01_basic_host/README.md`) at `http://localhost:8080/` and call `get_daily_briefing` and
   `get_farm_status`.
3. `reset-demo --yes` clears both state files, so the story can start again.

**`reset-demo` never destroys real data silently.** Run on its own it only lists each state file with its size and record counts and changes nothing; it needs `--yes` to act. The demo-clock file (it holds only shifted demo dates) is deleted; any other state file is moved to a `backups` folder next to it (`.local/backups`) with a timestamp, never deleted, so a farm you entered by hand can be put back by moving the file back.

The honest scope is the one above: follow-up and briefing dates only; flock ages, record-book entries and the sale plan
do not move.

## Roadmap

- **Layer farming.** The domain layer already models egg-laying flocks (status, feed planning), but the current
  build, demo data and video target **broiler** farms only. Extending the voice/card experience to layer flocks
  the way broilers are covered today is future work.
- The full Contract Earnings Tracker (sensitivity/what-if), the vaccination planner and vaccine-day coach, and
  feed/order confirmation flows — see `docs/DESIGN.md` §13 for the design of each. (The voice record book and
  health triage are built; see above.)

## Agent Skill: operate CluckTalk from a coding agent

`skills/clucktalk/` is an Agent Skill (a `SKILL.md` plus three reference files and an MIT
license) that teaches an AI agent how to operate CluckTalk: which of the 14 tools to call for a farmer's words (shed /
kotam / house; haan / avunu / nahi / vaddu), the propose, read-back, yes protocol, the safety rules, voice-only versus
card behaviour, and the rule that spoken numbers equal card numbers. It does not claim that Alexa+ runs CluckTalk. Tests
keep it in step with the server (`tests/unit/test_skill.py`): it names exactly the tools the server lists, and every
example phrase routes through the Simulator's rules as the skill says.

Install by copying the folder `skills/clucktalk` into the agent's skills folder, in your project (or the user-level
folder of the same name):

| Agent | Project folder | What we checked |
|---|---|---|
| Claude Code | `.claude/skills/clucktalk/` | Unverified: not checked against the official docs in this change, and never loaded in Claude Code here |
| Kiro | `.kiro/skills/clucktalk/` | Matches Kiro's skills documentation as returned by a web search on 2026-10-01; never loaded in Kiro |
| Cursor | `.cursor/skills/clucktalk/` (also `.agents/skills/`; Cursor also reads `.claude/skills/`) | Matches Cursor's skills documentation as returned by a web search on 2026-10-01; never loaded in Cursor. A plain top-level `skills/` folder is unverified: we found no Cursor documentation for it |
| GitHub Copilot (VS Code) | `.github/skills/clucktalk/` | Unverified: seen only on a third-party page, not on GitHub's own documentation; never loaded in Copilot |

Windows (cmd): `xcopy /E /I skills\clucktalk .claude\skills\clucktalk`. Linux/macOS: `mkdir -p .claude/skills && cp -r skills/clucktalk .claude/skills/`.
Replace the folder name for another agent. Whether each agent loads the skill and picks it when a farmer's words match
is unverified for all four.

## Documentation

- `docs/DESIGN.md` — architecture, tool contract rules, safety rules, and what's built vs planned.
- `docs/SOURCES.md` — provenance for every number CluckTalk uses.
- `docs/VERSIONS.md` — pinned/verified tool and package versions.
- `docs/AWS_SETUP.md` — live-mode AWS setup (not needed for the demo).
- `skills/clucktalk/` — the Agent Skill for operating CluckTalk (see above).
- `FRICTION_LOG.md` / `FEATURE_REQUESTS.md` — developer friction with the platforms used, recorded as it happens.
- `docs/TELUGU_REVIEW.md` — every Telugu string with its English pair and native-speaker review status.

## License

MIT. See `LICENSE`.
