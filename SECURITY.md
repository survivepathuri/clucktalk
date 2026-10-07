# Security

CluckTalk is a hackathon prototype. This page says in plain words what it tries to protect, how, what independent reviews found, and what is **not** protected. It is a description of this repository, not a promise about any deployment.

## What it protects

- **A farmer's records.** The deaths, feed and health checks he tells it, stored in a SQLite file on the machine that runs the server.
- **The private link.** In the pilot, one link with a token that lets one farmer open the page. Whoever has the link can use the page.
- **The farmer's safety advice.** The levels, the minimum urgency of a health check and the "contact your vet" advice must not be lowered by bad input, a model, or a stored value that cannot be read.

## Threat model

| Who or what | What could go wrong | What the code does about it | Evidence |
|---|---|---|---|
| A web page in the farmer's or the builder's browser that calls the local server | It reads or changes records through the loopback port (DNS rebinding, a foreign `Origin`) | The server binds to 127.0.0.1; it checks the `Origin` and `Host` headers against an exact allow-list and never accepts `*`; the Simulator accepts API calls only from its own origin | `docs/DESIGN.md` section 4; `tests/contract/test_transport.py`, `tests/contract/test_cors.py` |
| Someone who finds the pilot link | Uses the page and sees the farmer's records | Every page and API call needs the token; wrong tokens are rate limited too; a per-token rate limit, a session cap and an 8 KB body cap; a kill-switch file pauses everything; the token sits after `#` in the link so the browser does not send it in the address, and the page removes it from the address bar | `docs/DESIGN.md` section 19; `tests/contract/test_pilot_hardening.py`, `tests/contract/test_pilot_routes.py` |
| Someone who reaches the MCP port directly | Calls tools without the page | In pilot mode the MCP server refuses to start without a strong token of its own, different from the farmer's. The MCP port is on the loopback only and the tunnel does not forward it | `tests/unit/test_pilot_config.py`, `tests/contract/test_pilot_mode.py`; `docs/PILOT_RUNBOOK_WINDOWS.md` |
| Malformed, huge or odd requests | A crash, a stack trace or a path in an error, a state change on an error, a hung server | Errors are short fixed messages; bodies of 10 MB or more get 413; a fuzz suite checks that no input gives a 500, a leak or a state change | `tests/contract/test_fuzz_inputs.py`, `tests/contract/test_protocol_errors.py`, `tests/contract/test_concurrency.py` |
| The farmer's own words (or a photo) containing instructions | Prompt injection into the model's decision | The model sees the farmer's words as data and answers only from closed lists (an urgency, categories, checks); code sets a floor the model cannot lower; the farmer's words are passed on as data | golden case `triage-prompt-injection-is-data`; `tests/unit/test_agents.py`; `tests/contract/test_health_tools.py` |
| The model itself | A wrong or invented answer, a medicine or a dose, a lowered urgency | The model's reply must match a strict schema or it is rejected; it can raise an urgency and never lower it; no tool gives a medicine or a dose; a model failure is shown, never replaced by sample data | golden cases `triage-floor-holds-against-model` and `triage-model-failure-fails-loud`; `docs/SAFETY_MATRIX.md` |
| A shed name or number that reads as another shed | A change saved on the wrong house | The shed-name reader never maps a name to a different shed and refuses a name with two different numbers; every write is read back and needs an explicit yes | `tests/unit/test_houses.py`, `tests/contract/test_fuzz_inputs.py` |
| A secret in the repository | A key or token published | `scripts/scan_secrets.py` runs in every `check`; real tokens, the farm file and the state file live outside the repository; the builder's local notes are kept out of the repository | `tests/harness/test_scan_secrets.py`; `tests/harness/test_windows_launcher.py` |
| A cost attack on live AI | Many requests run up an AWS bill | Live AI is off by default; a daily call budget and a throttle exist; no tool calls a model synchronously | `tests/unit/test_agents.py`; `docs/DESIGN.md` section 18 |

## What the independent reviews found

Fresh agents read the code cold in ten rounds (`docs/INDEPENDENT_REVIEW.md`, with the table in `docs/RESULTS.md`). The findings that matter for security and data integrity, and how each was fixed:

- **Data integrity (Critical, record book).** A backdated correction was not checked against later days, so total deaths could exceed the birds placed while the answer said "saved". Fixed with a bound across all days and a regression test.
- **Leak of numbers (High, `plan_sale`).** In contract mode the market price leaked into structured content although nothing spoke it. Fixed at the tool layer with a regression test.
- **Lowered urgency (High, triage).** Words that matched no known sign were called routine, even when they described a red flag. They now count as urgent and are never lowered.
- **Protocol errors that echo input (our own fuzz round, F1 and F2).** A body that was not a JSON-RPC request got the SDK's validation text and a link; an unknown method was echoed back (1 MB in, 1 MB out). Both now get short fixed messages from `ProtocolErrorGate` in `src/clucktalk/server/app.py`, and so does a body that is not JSON.
- **Pilot access (round 10).** The fixes: the MCP server refuses to start in pilot mode without its own strong token; when the session table is full the least recently used session is dropped (before, a new session could be refused with a 503); the card routes and the English demo page are not served on a pilot host; and every pilot answer carries a Content-Security-Policy, `Referrer-Policy: no-referrer` and `nosniff`.

Reported and left as they are, because they are SDK behaviors (pinned by tests, so an upgrade that changes them fails a test): an odd JSON-RPC id gets an empty 202; two overlapping requests with the same id leave one unanswered; the session limits are the SDK's defaults. See the README, "Known SDK behaviors".

## What is not protected

- **The pilot runs on a personal Windows PC** (planned, not started). Anyone with administrator access to it, anyone who takes the backup USB drive, and malware on it can read the farmer's records. The runbook recommends disk encryption; it does not check it. There is no hardened server, no firewall review and no intrusion monitoring.
- **No account system and no OAuth.** Access is one bearer token in a link. The server does not implement OAuth 2.1 with PKCE, Protected Resource Metadata or account linking, which Alexa+ add-ons need. A lost phone or a shared link means making a new token by hand.
- **The tunnel is a third party.** A free Tailscale Funnel relays the connection; what it can see was not examined here.
- **Alexa+ add-on security and data policies were not published to us**, so none were checked. We do not know what Amazon will require, and we make no claim about meeting it (`docs/ALEXA_READINESS.md`).
- **No human security audit and no penetration test.** The reviews were done by AI agents, and the fuzz, property and mutation tests are the builder's own.
- **No privacy or data-law review** (for example, how long to keep records, or consent wording beyond the one-screen notice in the pilot).
- **Backups and the state file are not encrypted by this project.**
- **Telugu wording is draft**, so a notice could be misread until a native speaker approves it.

## Reporting an issue

[SECURITY CONTACT: to be added before the repository is made public]

Until a contact is added, open an issue in the repository and leave out any real farm data, token or address. Please do not post a working exploit in public; describe the problem and the steps to see it.
