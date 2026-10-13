# CluckTalk (కోడి మిత్ర)

The voice farm manager for India's **broiler** poultry farmers. A self-hosted MCP server (implements MCP 2025-11-25 over
Streamable HTTP) plus an Agent Skill, built for the Alexa+ add-on program.

> **Status**: in development. Nothing below is claimed working unless it has evidence in `docs/evidence/` or a
> passing check in `python tasks.py check` / `python tasks.py eval-fast`. See `docs/DESIGN.md` for the full design
> and what is built vs planned, and `docs/EVALS.md` for the current golden-suite score.

## Try it now

**Python 3.12 or 3.13 is required** (3.11 runs with an "untested" warning; older versions stop). Check with `python --version` on Windows and `python3 --version` on macOS and Linux. No Docker, no AWS account, and no virtual-environment activation: `tasks.py` creates and uses its own `.venv`. Install lines for Python are in `docs/JUDGES.md` and under "Quick start" below.

Windows cmd:

```
python tasks.py setup
python tasks.py verify
python tasks.py readiness
python tasks.py serve
```

Windows PowerShell:

```
python tasks.py setup
python tasks.py verify
python tasks.py readiness
python tasks.py serve
```

macOS or Linux (bash or zsh):

```
python3 tasks.py setup
python3 tasks.py verify
python3 tasks.py readiness
python3 tasks.py serve
```

What each one does: `setup` creates `.venv` and installs the pinned dependencies. `verify` prints one table of what a judge can check in about 30 seconds (not the full test suites); it starts its own temporary server, so it needs neither Node.js nor a running server. `readiness` is our own self-check of the locally checkable Alexa+ requirements (not an Amazon verdict). `serve` starts the MCP server on http://127.0.0.1:8765/mcp with fictional demo data; leave it running. If port 8765 is busy, `serve` says so and starts nothing; see "Ports and browser" in `docs/JUDGES.md`.

With `serve` running, in a second window, the MCP Inspector command line needs Node.js (`@modelcontextprotocol/inspector` 2.8.0; our evidence in `docs/evidence/2026-09-27_farm_status_and_feed.md` used its installed `mcp-inspector --cli`, and the `npx` form below is the same package but was not run in exactly this form). Without Node.js, `python tasks.py inspector-replay` (`python3` on macOS and Linux) replays Amazon's documented Local Inspector flow against a temporary copy of the server and needs neither Node.js nor `serve`.

```
npx @modelcontextprotocol/inspector@2.8.0 --cli http://127.0.0.1:8765/mcp --method tools/list
npx @modelcontextprotocol/inspector@2.8.0 --cli http://127.0.0.1:8765/mcp --method tools/call --tool-name get_farm_status --tool-arg "house=shed 2"
```

To see skipped tests (for example when Node.js is missing) run `pytest -rs`: `.venv\Scripts\python -m pytest -rs tests\harness` on Windows, `.venv/bin/python -m pytest -rs tests/harness` on macOS and Linux.

Tested on:

| Platform | Status |
|---|---|
| Windows 11 | local runs, Python 3.13.15 (the harness tests also ran on 3.14.5), `docs/VERSIONS.md` |
| Linux (ubuntu, CI) | last recorded green run: commit `023a90d`, 2026-10-04, Python 3.12 and 3.13; later commits: not recorded (pushed with `[skip ci]`, or not checked) |
| macOS | not yet run; a manual CI job exists (`workflow_dispatch`, `include_macos`), and its result will be recorded here |

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
- **Telugu:** 86 of 447 strings reviewed by the builder, a native Telugu speaker; 361 pending (including the pilot page); no independent review. `docs/TELUGU_REVIEW.md` lists each string. No Telugu voice has been tested through Alexa+.
- **In demo mode a shed with no alert is still described as doing well; pilot mode says: no alert from the checks I can make.**
- **The cards were tested at sizes of 10 inches and below only**; nothing was tested at 11 inches and above.
- **The sale-window hint** (`plan_sale`'s "best day to sell is within 3 days", simulated) shows on the daily briefing
  only. It never raises a shed's health status or its safety level.
- **`NOTICE` (third-party licenses)** was generated on Windows by `python tasks.py notices` from the installed package
  metadata. It is checked against the installed packages on every operating system the CI runs on (ubuntu and
  windows), by a test: a missing or changed package fails it, and only a package its platform marker excludes (pywin32 on Linux)
  may be listed there as not installed.
- **Latency is not measured end to end.**[^latency]
- **No agronomic or veterinary review.** Thresholds and the reference curve are cited in `docs/SOURCES.md`; they were not validated with a vet or a farmer, and no tool gives a medicine or a dose.
- **The pilot is hosted on the builder's own PC, published through a free Tailscale Funnel; availability depends on that PC and its internet.** No farmer has used the pilot yet, so usage numbers are pending. The Lightsail cloud pilot with the sample farm has been deployed since 2026-10-13 (`docs/CLOUD_PILOT.md`); results will be added after the pilot. Nothing about uptime, speed or reliability has been measured (`docs/PILOT_RUNBOOK_WINDOWS.md`).
- **Odd behaviours of the MCP SDK and of our shed-name reader** are listed under "Known SDK behaviors" below.

## What is verified, unverified and simulated

Each row names the file or test that shows it, so you can check it yourself. "Verified" means that evidence exists in
this repository, not that Alexa+ has seen it.

| Claim | Status | Evidence |
|---|---|---|
| The server implements MCP 2025-11-25 over Streamable HTTP (and negotiates three older versions, with no floor) | VERIFIED | `tests/contract/test_protocol_conformance.py`; the probe table in `python tasks.py verify` |
| The documented Local Inspector flow (JSON-only `Accept`, protocolVersion 2025-06-18) works against the server | VERIFIED (our replay, not Amazon's tool) | `python tasks.py inspector-replay`; `tests/harness/test_inspector_replay.py` |
| Every tool's server time is well under 500 ms at p95 on localhost, mock mode[^latency] | VERIFIED (localhost server time only) | `python tasks.py inspector-replay`; `python tasks.py readiness` |
| The locally checkable Alexa+ requirements we encoded are met (runtime checks against the server and document-structure checks, counted apart) | VERIFIED (our checklist, not an Amazon verdict) | `python tasks.py readiness`; `docs/ALEXA_READINESS.md` |
| The briefing, the farm status and its card agree on safety, level and vet advice | VERIFIED | `tests/contract/test_safety_agreement.py`; `tests/contract/test_status_card_follows_safety.py`; `tests/unit/test_property_follow_up_sequences.py` |
| Malformed, oversized and odd input never gives a 500, a leak or a state change | VERIFIED | `tests/contract/test_fuzz_inputs.py`; `tests/contract/test_protocol_errors.py` |
| Spoken numbers equal card numbers (in the Simulator) | VERIFIED | `tests/crossmodal.py`; `tests/contract/test_card.py`; `docs/evidence/2026-09-27_card_and_simulator.md` |
| `reset-demo` never destroys real data silently | VERIFIED | `tests/harness/test_reset_demo_safety.py` |
| The golden eval suite passes in mock mode | VERIFIED (mock mode, no AWS) | `python tasks.py eval-fast`; `docs/EVALS.md` |
| Weather reminders come only from the farmer's own rules file, never change a level, the safety field or the vet advice, and leave every answer byte-identical when the file is absent | VERIFIED | `tests/unit/test_property_weather_isolation.py`; `tests/contract/test_weather_display.py` |
| The weather lines in the demo (the forecast and the example rules) | SIMULATED | `tests/unit/test_weather_server.py`; `docs/weather_rules.example.json` |
| Weather from the live Open-Meteo service | UNVERIFIED (tested only with a fake transport, not run against the real service) | `tests/unit/test_weather_server.py`; `docs/SOURCES.md` |
| The Windows launcher files (`deploy/windows/`) list exactly the settings the code reads in pilot mode, hold no secret or hostname, and contain the refusals for a weak token and for data inside the repository | VERIFIED (text checks and the code's own settings loaders only; how the scripts behave on the pilot PC is not recorded in this repository) | `tests/harness/test_windows_launcher.py` |
| Each safety rule has a row with its source, code location, tests and a before and after example, and the files, functions and golden cases it names exist | VERIFIED (a test checks the references; the thresholds themselves were not validated by a vet or a farmer) | `docs/SAFETY_MATRIX.md`; `tests/harness/test_results_and_proof.py` |
| The results page (test counts, golden evals, protocol conformance, latency, readiness, build history) is generated from this machine's own runs | VERIFIED (local, mock mode, not an Amazon verdict) | `docs/RESULTS.md`; `python tasks.py results` |
| The saved outputs of the self-check commands carry their command, date and commit | VERIFIED (text files only) | `docs/proof/verify.txt`; `python tasks.py proof`; `tests/harness/test_proof_files.py` |
| The mutation counts and the independent-review rounds | UNVERIFIED (copied from the builder's own log; the mutation scripts are not in the repository, and the reviewers were AI agents, not a human audit) | `data/results/mutation_results.json`; `data/results/review_rounds.json`; `docs/INDEPENDENT_REVIEW.md` |
| The architecture diagrams and the judges' guide name exactly the tools the server lists | VERIFIED (a test compares the names; the diagrams are not rendered by a test) | `docs/ARCHITECTURE.md`; `docs/JUDGES.md`; `tests/harness/test_submission_docs.py` |
| The pilot page's access controls (a token on every call, exact host and origin, size and rate limits, a kill switch) work as the tests describe | VERIFIED (tests only; not checked on the shared pilot or on a phone) | `SECURITY.md`; `tests/contract/test_pilot_hardening.py` |
| A human security audit, a privacy and data-law review, OAuth 2.1, remote hosting | NOT BUILT (every item is listed as not done) | `docs/PRODUCTION_PATH.md` |
| The submission text is complete | UNVERIFIED (the demo video and the two mini-challenge URLs are pending; pilot numbers do not exist yet) | `submission.md` |
| The pilot runs on the builder's own PC through a Tailscale Funnel, and the farmer can use it | UNVERIFIED (no farmer has used the pilot yet, so usage numbers are pending; the Lightsail cloud pilot with the sample farm has been deployed since 2026-10-13; availability of the PC pilot depends on that PC and its internet) | none; `docs/PILOT_RUNBOOK_WINDOWS.md` |
| The server runs on an Alexa+ device, or passes Amazon's review | UNVERIFIED | none; see "Known limitations" |
| The Local Inspector itself accepts the server | UNVERIFIED | none; `FRICTION_LOG.md` FL-024 |
| Telugu wording is natural and correct | UNVERIFIED (86 of 447 strings reviewed by the builder, a native Telugu speaker; 361 pending (including the pilot page); no independent review.) | `docs/TELUGU_REVIEW.md` |
| Telugu voice works through Alexa+ | UNVERIFIED | none |
| The cards work at 11 inches and above | UNVERIFIED | `docs/DESIGN.md` (screen size classes) |
| Live AI (Amazon Bedrock) end to end | UNVERIFIED here | `docs/AWS_SETUP.md`; `FRICTION_LOG.md` FL-014 |
| Account linking, Protected Resource Metadata, a remote URL | NOT BUILT | `docs/ALEXA_READINESS.md` |
| Market prices, sensors, supplier, SMS, payments, the vet message sending | SIMULATED | `tests/contract/test_tool_descriptions_simulated.py`; `docs/DESIGN.md` section 9 |
| The demo farm and every farmer in it | SIMULATED (fictional) | `data/seed/demo_farm.json`; `tests/unit/test_seed.py` |

## Quick start (venv only; Docker is optional and never required)

Needs Python 3.12 or 3.13 (other versions from 3.11 run with a visible "untested" warning). Get it from
python.org, `brew install python@3.13` (macOS), `pyenv install 3.13`, or the deadsnakes PPA (Ubuntu).

Windows cmd:

```
git clone <this repo>
cd CluckTalk
python tasks.py setup
python tasks.py run
```

Windows PowerShell:

```
git clone <this repo>
cd CluckTalk
python tasks.py setup
python tasks.py run
```

macOS or Linux (bash or zsh):

```
git clone <this repo>
cd CluckTalk
python3 tasks.py setup
python3 tasks.py run
# optional: lint + tests + AOSS check + secret scan
python3 tasks.py check
```

`setup` creates `.venv` and installs the pinned dependencies. `run` starts the MCP server and the Alexa+ Simulator and opens http://127.0.0.1:8766/ in your browser; if no browser opens, open the URL printed after "ready". If port 8765 or 8766 is busy, `run` prints one line naming the port and starts nothing.

Ports and browser, one line per shell (cmd stays set for that window only; PowerShell and export for that session):

```
set CLUCKTALK_PORT=8775
$env:CLUCKTALK_PORT = "8775"
export CLUCKTALK_PORT=8775
```

The same syntax sets `CLUCKTALK_SIMULATOR_PORT` (the Simulator, default 8766) and `CLUCKTALK_NO_BROWSER=1` (do not open a browser). The first line is for cmd, the second for PowerShell, the third for bash and zsh.

Node.js is optional: the card tests that need a JavaScript engine and the pilot page tests are skipped, with a reason, when
`node` is not installed (`pytest -rs` lists them; the page logic is then not exercised). `verify` does not need Node.js. The secret scan
in `check` needs a git checkout; on a ZIP download it prints "SKIPPED" and the rest of `check` still runs.

Try asking (typed or, if your browser supports it, spoken): *"How is shed two doing?"*, *"When should I sell shed
one?"*, *"How much feed does shed two need this week?"*, *"Switch my farm to contract farming"*.

Everything runs on seeded, clearly fictional demo data (`MOCK_BEDROCK=true`, shown as a "Demo data" badge). Amazon
Bedrock (Nova 2 Lite) is the live engine for the triage and briefing agents. It is wired and tested with a botocore Stubber, and it was used in a few one-off live calls on 2026-09-29, but it has never been run end to end through the server. It is off by default: the demo and the pilot use a rule-based stand-in. Live mode needs an AWS account; see `docs/AWS_SETUP.md`.

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

`python tasks.py inspector-replay` replays the flow documented on Amazon's Local Inspector page against a temporary copy of the server (a temporary state file, mock mode, no AWS): `initialize` with protocolVersion 2025-06-18 and clientInfo `addon-local-inspector` using `Accept: application/json` only, the initialized notification, `tools/list`, `resources/read` for every `ui://` card and a `tools/call` for every tool. It prints a step table and the p50 and p95 per step over 20 rounds. **It is our replay of the documented flow, not Amazon's tool, and the Local Inspector itself was not run** (its guide is behind a Developer Console login, FL-024). On this machine the server answers the JSON-only request correctly at every step. What the p50 and p95 mean: see the latency note.[^latency]

[^latency]: **Latency note.** Our p50 and p95 are server times on localhost in mock mode, and Amazon's 500 ms requirement is a round trip that includes the network, so we do not claim to meet it end to end. There is no model call and the data is simulated; a remote host and a real model add to the times.

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

## Weather reminders

**What it is.** If you write your own outdoor-temperature rules in a small file, the daily briefing and the farm status
add one reminder line per rule that an hourly outdoor forecast matches. A rule says: "when the lowest or the highest
forecast temperature over the next N hours is below (or above) the number you set, show your own note". The number, the
hours ahead and the note are the farmer's, written into the file by the builder from what the farmer said; entering them
in the app is a roadmap item. The note is shown exactly as it is written. The repository ships only
`docs/weather_rules.example.json` with two example rules (below 20 and above 30, with placeholder notes): they are
examples, never defaults, and never used unless you point at the file. The example settings (the lowest or the highest value
over 12 hours) are example settings until the farmer answers the questions below. The reported rule (cover the curtains
below 20 degrees outside; spray a little water lightly above 30 degrees outside, with the curtains covered) was relayed by the
builder and not yet confirmed by the farmer.

**What it is not.** It gives no advice: the line states the forecast and shows your note, nothing more. It is not a
temperature inside the shed: a forecast is an outdoor value for one point (your farm's latitude and longitude, which you
write in the file). The farmer's target of 20 to 30 degrees on average inside the shed for the whole cycle is not stored or
compared with anything, and nothing in the code claims a shed-interior value. It is not real-time: the data is an hourly
forecast, and each line says when it was fetched. There is no push: a line appears only when you ask for the briefing or the
status. The rules are set in a config file now; entering them by voice is a roadmap item (it needs a new tool). The feature
never changes a shed's health status, safety level, reason codes, vet advice or any card level (a property test checks it),
and it adds no tool and no card.

**Default: off.** The feature is off unless the rules file exists. With no file, nothing is built, nothing is asked of any weather service, no network call
is possible, and every answer is byte-identical to what it was before (`tests/contract/test_weather_display.py` compares
against a recorded baseline). The farm status then has no `weather_reminders` key.

**Demo** (Windows cmd; simulated forecast, no network):

```
set CLUCKTALK_WEATHER_RULES_PATH=docs\weather_rules.example.json
python tasks.py serve
```

Then ask for the farm status or the briefing. The simulated forecast is a fixed daily curve from 16 to 33 degrees, so
the lines appear when it crosses the example numbers within the next 12 hours (that depends on the hour of day). They are
labelled Demo data and Simulated, and the farm status lists them in its separate `weather_reminders` field.

**Live forecast (opt-in).** `CLUCKTALK_WEATHER_LIVE=true` (and the rules file) turns on one adapter for
Open-Meteo: hourly `temperature_2m` only, no API key, a timeout of at most 3 seconds, a 30 minute cache that records when the
data was fetched, and a plain "no weather reminder" sentence when the forecast cannot be fetched. Open-Meteo's free service is
for non-commercial use only and asks for attribution under CC-BY 4.0; every weather line names its source (details and what
is not verified: `docs/SOURCES.md`). The adapter is tested only with a fake transport and has not been run against the real
service. If you ever use CluckTalk commercially, that needs Open-Meteo's paid plan.

**Questions the farmer must answer (we do not guess).** Does "below 20" mean the night minimum or the moment? How many hours
ahead? What time of day? Is 20 to 30 degrees inside the shed or outside? Is it a daily average or at all times? Does it change
with the age of the birds?

## Pilot (stage 1: a prototype for one farmer)

A separate mode (`CLUCKTALK_MODE=pilot`) lets one real farmer try CluckTalk on their phone in Telugu: their own houses
from a farm file, no demo data, no bird weights, a Telugu page that reads every change back and waits for a tap. It is a
prototype, **not Alexa+ and not a veterinary service** (see `docs/PILOT_RUNBOOK.md`). The PC version is hosted on the builder's own
Windows PC through a free tunnel (`docs/PILOT_RUNBOOK_WINDOWS.md`). No farmer has used the pilot yet, so usage numbers are
pending. The Lightsail cloud pilot with the sample farm has been deployed since 2026-10-13 (`docs/CLOUD_PILOT.md`); results will be added after the pilot.

**When the count belongs to a day.** The farmer counts the deaths of the last 24 hours once each morning, and that count is
the deaths of *today* (the Asia/Kolkata date). So a second number for the same house on the same day is most likely a
correction, not new deaths. CluckTalk never assumes: if the house already has deaths for that day it shows the old and the
new number and asks "add" (the new number is added, the total is shown) or "replace" (the new number replaces the old one,
which is named); a plain yes does not answer it, and nothing is saved until the farmer taps one of them. The first log of a day
works as it always did. No alert rule is changed by this.

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
| Claude Code | `.claude/skills/clucktalk/` | Install path not tested as a separate step (the project itself was built with Claude Code) |
| Kiro | `.kiro/skills/clucktalk/` | Matches Kiro's skills documentation as returned by a web search on 2026-10-01; never loaded in Kiro |
| Cursor | `.cursor/skills/clucktalk/` (also `.agents/skills/`; Cursor also reads `.claude/skills/`) | Matches Cursor's skills documentation as returned by a web search on 2026-10-01; never loaded in Cursor. A plain top-level `skills/` folder is unverified: we found no Cursor documentation for it |
| GitHub Copilot (VS Code) | `.github/skills/clucktalk/` | Unverified: seen only on a third-party page, not on GitHub's own documentation; never loaded in Copilot |

Windows (cmd): `xcopy /E /I skills\clucktalk .claude\skills\clucktalk`. Linux/macOS: `mkdir -p .claude/skills && cp -r skills/clucktalk .claude/skills/`.
Replace the folder name for another agent. Whether each agent loads the skill and picks it when a farmer's words match
is unverified for all four.

## Documentation

- `docs/DESIGN.md` — architecture, tool contract rules, safety rules, and what's built vs planned.
- `docs/JUDGES.md` — a one-page guide: what to look at in five minutes, the three commands, where things are, the limits.
- `docs/ARCHITECTURE.md` — the real system and the pilot deployment as two diagrams, each with what is real and what is simulated.
- `docs/SAFETY_MATRIX.md` — every safety rule: its source, code location, tests and a before and after example.
- `docs/RESULTS.md` — test counts, golden evals, mutation checks, conformance, latency, readiness and build history, generated by `python tasks.py results`.
- `docs/proof/` — the saved text output of four self-check commands, with their date and commit (`python tasks.py proof`).
- `docs/INDEPENDENT_REVIEW.md` — the review rounds, what they found and how each was fixed.
- `SECURITY.md` — the threat model in plain words, and what is not protected.
- `docs/PRODUCTION_PATH.md` — an honest list of what is missing before a farmer could depend on it (all not done).
- `submission.md` — the draft submission text, field by field, with pending items marked.
- `docs/SOURCES.md` — provenance for every number CluckTalk uses.
- `docs/VERSIONS.md` — pinned/verified tool and package versions.
- `docs/AWS_SETUP.md` — live-mode AWS setup (not needed for the demo).
- `skills/clucktalk/` — the Agent Skill for operating CluckTalk (see above).
- `FRICTION_LOG.md` / `FEATURE_REQUESTS.md` — developer friction with the platforms used, recorded as it happens.
- `docs/FRICTION_SUMMARY.md` — one page: the friction entries we would most like the Amazon teams to read.
- `docs/PRODUCT_FEEDBACK.md` — feedback on every tool, API and service used (the five hackathon questions); paste-ready copy: `docs/PRODUCT_FEEDBACK_DEVPOST.md`.
- `docs/TELUGU_REVIEW.md` — every Telugu string with its English pair and its review status.

## License

MIT. See `LICENSE`.
