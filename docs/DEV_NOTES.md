# Developer notes: friction with our own tooling

Entries from `FRICTION_LOG.md` that are about our own tooling (Claude Code, Windows, npm, CI) and not about Alexa+, MCP Apps, AWS or Bedrock. They keep their FL numbers, so references elsewhere stay valid. Same fields as `FRICTION_LOG.md` (the six official fields, date, tag, `Time cost:`, `Reproduce:`). Moved here in the 2026-10-01 audit; the wording is unchanged except where noted. The severity is one word rated from the owner's point of view, with the cost to us on an `Impact:` line (2026-10-03).

## FL-005: Inspector CLI crashes on Windows when a call ends in an error
Date: 2026-09-27
Tool / service: MCP Inspector `@modelcontextprotocol/inspector` 2.8.0 CLI, Node v24.15.0, Windows 11 Pro
Tag: [Dev]
Task attempted: Capture evidence of error results (`tools/call` returning `isError: true`, and an unknown tool name).
Steps taken: `node <inspector>/clients/launcher/build/index.js --cli http://127.0.0.1:8765/mcp --method tools/call --tool-name get_farm_status --tool-arg "house=shed 9"` (3 runs), plus `--tool-name nope`.
Expected vs actual: Expected the documented JSON error on stderr and a normal non-zero exit code. Actual: the JSON error is printed, then `Assertion failed: !(handle->flags & UV_HANDLE_CLOSING), file src\win\async.c, line 76`, and the process dies (exit 127 in Git Bash, 3221226505 = 0xC0000409 from Python). Reproduced 3/3; also on `tool_not_found`, so independent of the server. Successful calls exit 0.
Severity: Low
Workaround: Read the JSON printed before the crash; do not rely on the exit code for error cases on Windows.
Actionable suggestion: Owner: MCP Inspector maintainers (CLI error path). Close pending async handles before `process.exit` (a double close of a libuv async handle), and add a Windows CI smoke test for error exits.
Time cost: not recorded
Reproduce: Run `python tasks.py serve`, then `node <inspector>\clients\launcher\build\index.js --cli http://127.0.0.1:8765/mcp --method tools/call --tool-name get_farm_status --tool-arg "house=shed 9"` (Inspector 2.8.0, Node 24.15.0, Windows 11). Reproduced 3 of 3 times.
Evidence: `docs/evidence/2026-09-27_farm_status_and_feed.md`.

## FL-022: Claude Code's shell tool changes backslash sequences in a command (`\b` in a Python heredoc reached the file as a backspace character)
Merged with its recurrence note (build session 4, 2026-10-01).
Date: 2026-10-01
Tool / service: Claude Code (Bash tool, Git Bash on Windows 11) while editing source files with a Python heredoc script
Tag: [Dev]
Task attempted: Add regular expressions that use word boundaries (`\b`) to `src/clucktalk/simulator/intents.py` by running a `python - <<'EOF'` script that wrote the file.
Steps taken: Wrote the pattern with a doubled backslash inside a non-raw Python string in the quoted heredoc, ran it, then ran ruff. Recurrence in build session 4: two more Python heredocs, and one quoted heredoc whose text held an apostrophe.
Expected vs actual: Expected `\b` (backslash, b) in the file. Actual: the file held the invisible backspace character (0x08) ten times; the patterns looked right in the editor and in terminal output, and only ruff's line-length complaint and a failing intent test showed something was off. A second fix attempt written the same way produced the same ten characters. Recurrence: a `\r\n` pair became real line breaks and broke the script's syntax, and the apostrophe case failed with `unexpected EOF while looking for matching`. Recurrence in Step 53 (2026-10-07): a long quoted heredoc holding PowerShell scripts failed with the same `unexpected EOF` (nothing was written), and a Python script typed in a heredoc with a Windows path in a normal string failed with a `unicodeescape` SyntaxError; the Write tool was used instead.
Severity: Medium
Impact: The corruption is silent: the file held invisible backspace characters and only a linter message and a failing test showed it. No wrong code was committed.
Workaround: Do not type backslashes in shell commands that write code. Use the Write or Edit tools for any text with backslashes, or build the character in code (`chr(92) + "b"`). Check with `grep -P "\x08"` afterwards.
Actionable suggestion: Owner: Anthropic Claude Code team (Bash tool). Pass the command text to the shell unchanged, or document how the Bash tool treats backslashes in quoted heredocs.
Time cost: About 15 minutes the first time and about 10 minutes on the recurrence, plus about 5 minutes in Step 53 and about 10 minutes in Step 54 (four Python heredocs: a newline escape inside a string became a real line break, and a word-boundary escape in a test file became a backspace character; each was found by ruff or a syntax error and rewritten with the Edit tool).
Reproduce: documentation-based, no command (detect the result afterwards with `grep -P "\x08" <file>`, from the Workaround).
Evidence: none beyond the entry.

## FL-023: Windows timer granularity made a lower-bound timing test fail in CI (a 300 ms sleep measured 290.6 ms)
Date: 2026-10-01
Tool / service: GitHub Actions windows-latest, Python 3.12 (server sleep measured with time.perf_counter)
Tag: [Dev]
Task attempted: Run `python tasks.py check` on the CI matrix after pushing the follow-up session 3 commit.
Steps taken: The Simulator applied a 300 ms simulated delay; `tests/contract/test_simulator.py::test_simulated_delay_is_applied_and_reported` asserted the measured backend time was at least 300 ms.
Expected vs actual: Expected at least 300 ms. Actual: 290.6 ms on windows / 3.12 only; the other three jobs and the local Windows run passed. The measurement already used perf_counter, so the sleep itself returned early (coarse Windows timer).
Severity: Low
Impact: One red CI job; no product bug.
Workaround: Lower-bound tolerance of 50 ms in the test, with a comment. Upper-bound latency checks were not changed.
Actionable suggestion: Owner: CluckTalk tests (ours). Never assert an exact lower bound on a measured sleep; allow a tolerance of one or two timer ticks.
Time cost: not recorded
Reproduce: `.venv\Scripts\python -m pytest -q tests\contract\test_simulator.py::test_simulated_delay_is_applied_and_reported`. The failure was seen on GitHub Actions windows-latest / Python 3.12 only; the test now has a 50 ms tolerance, so it passes locally.
Evidence: `tests/contract/test_simulator.py::test_simulated_delay_is_applied_and_reported`.

## FL-025: A card bundle built on Windows from a CRLF template differed from the CI build, and the local check passed anyway
Date: 2026-10-01
Tool / service: scripts/build_cards.py, Git for Windows (core.autocrlf=true), GitHub Actions (all four jobs)
Tag: [Dev]
Task attempted: Push the Step 47A fixes and get the CI matrix green.
Steps taken: Edited two card templates with a script in Windows text mode (which wrote CRLF into the working copy), rebuilt the bundles and ran `python tasks.py check` (green), committed (Git normalised every blob to LF, as .gitattributes says) and pushed.
Expected vs actual: Expected the same green result on CI. Actual: all four jobs failed `tests/harness/test_build_cards.py::test_built_cards_are_up_to_date` ("Out of date: farm_status.html, sale_plan.html"). Root cause: the build did `out.replace("<!doctype html>
", ...)`, which silently matched nothing when the template had CRLF, so the committed bundles lacked their one "Built by" header line; CI builds from LF and adds it. The local check compared a CRLF build with a CRLF-built bundle, so it passed. The git blobs never contained a CR (a fresh clone's bundle hashes differed from the committed ones only by that line).
Severity: Medium
Impact: A red CI on every job; no product bug, but a push that looked verified was not.
Workaround: The build now reads the template as text with CRLF turned into LF, writes bytes (UTF-8, LF) and refuses to emit a CR or to drop the header; `.gitattributes` names the generated and compared files with `text eol=lf`; three harness tests (a CRLF template builds the same bytes, committed bundles equal the build and have no CR, the attributes exist). The CI comparison itself is still byte-exact.
Actionable suggestion: Owner: CluckTalk build scripts (ours, `scripts/build_cards.py`). A generated-file check must build from the same bytes on every OS; never rely on a string replace that contains a newline, and read templates in a way that does not depend on the checkout's line endings.
Time cost: not recorded
Reproduce: `.venv\Scripts\python -m pytest -q tests\harness\test_build_cards.py`. The original failure was on CI before the fix in `cdde7ff`; the tests now also build from a CRLF template.
Evidence: `scripts/build_cards.py`, `tests/harness/test_build_cards.py`, `.gitattributes`.

## FL-028: Windows OpenSSH refused a freshly downloaded Lightsail key ("UNPROTECTED PRIVATE KEY FILE") because the file inherited another local group's read access
Date: 2026-10-13
Tool / service: OpenSSH_for_Windows_9.5p1 (ssh.exe), Windows 11 Pro; the private key file was on the Desktop
Tag: [Dev]
Task attempted: First non-interactive SSH login to the new Lightsail server with the key downloaded from the console.
Steps taken: `ssh.exe -i <key.pem> -o IdentitiesOnly=yes -o BatchMode=yes ubuntu@<static IP> "echo ok"`; then `icacls <key.pem>`; then `icacls <key.pem> /inheritance:r /grant:r "$($env:USERNAME):(R)"` and the same ssh command again.
Expected vs actual: Expected the key to work as downloaded. Actual: exit 255, "WARNING: UNPROTECTED PRIVATE KEY FILE! ... Permissions ... are too open ... This private key will be ignored ... Permission denied (publickey)". `icacls` showed the file inherited read access for a second local group, a local sandbox group of another tool, besides SYSTEM, Administrators and the user. The message named the group, which made the fix clear.
Severity: Low
Impact: One failed login before the fix.
Workaround: `icacls <key.pem> /inheritance:r /grant:r "$($env:USERNAME):(R)"` on that one file only; the file was not moved or copied.
Actionable suggestion: Owner: our own runbook (`deploy/cloud/RUNBOOK.md`, section 0): add the one `icacls` line for the key; `deploy.ps1` and `verify.ps1` could test the ACL and print it. I did not check whether the Lightsail console's own SSH page mentions this on Windows.
Time cost: not recorded
Reproduce: `icacls <key.pem>` shows the inherited entries; any `ssh.exe -i <key.pem> ...` shows the error.
Evidence: the ssh output above, 2026-10-13 (exit code 255); the `icacls` output after the fix lists only the current user with read access.

## FL-029: `ufw limit 22/tcp` locked our own deploy and verify scripts out of SSH (connection timed out) after a few quick connections
Date: 2026-10-13
Tool / service: ufw on Ubuntu 24.04.4 (Lightsail, Mumbai); our `deploy/cloud/bootstrap.sh`, `deploy.ps1`, `verify.ps1`; Windows OpenSSH (no ControlMaster, so every command is a new connection)
Tag: [Dev]
Task attempted: Run `deploy.ps1` a second time (idempotency test) right after several ssh commands from the same PC.
Steps taken: `bootstrap.sh` had set `ufw limit 22/tcp` (meant to slow SSH guessing). A run of about six ssh/scp connections within 30 seconds (checks, then the second `deploy.ps1`) followed.
Expected vs actual: Expected the second run to connect. Actual: "ssh: connect to host <IP> port 22: Connection timed out" from our own PC. `ufw limit` denies an address that opens 6 or more connections in 30 seconds. It cleared by itself after about a minute.
Severity: Low
Impact: One failed deploy run and a short wait; with `verify.ps1` (about 8 connections) it could have happened mid-test.
Workaround: `bootstrap.sh` now runs `ufw delete limit 22/tcp` and `ufw allow 22/tcp`; SSH stays key-only and port 22 should be restricted to the owner's IP in the Lightsail firewall. The second `deploy.ps1` run applied the change (`ufw status` then shows ALLOW).
Actionable suggestion: Owner: our own scripts and `docs/CLOUD_PILOT.md`. Do not use `ufw limit` on a port that automation connects to many times in a row; use the provider firewall's source-IP restriction instead (written in the doc).
Time cost: not recorded
Reproduce: on a server with `ufw limit 22/tcp`, open 6 or more SSH connections within 30 seconds from one address, then connect once more.
Evidence: the ssh error above on 2026-10-13; `ufw status` before ("22/tcp LIMIT") and after ("22/tcp ALLOW") the second deploy.

## FL-030: A private SSH key's text was pasted into an assistant session, so the key had to be replaced (rotation steps that worked)
Date: 2026-10-13
Tool / service: Amazon Lightsail (key downloaded from the console), Windows OpenSSH 9.5p1, `ssh-keygen`, an AI assistant session (Claude Code)
Tag: [Dev]
Task attempted: Run the cloud pilot deployment with a key whose text had been included in a task description.
Steps taken: (1) generated an ed25519 pair with `ssh-keygen -t ed25519 -N ""` and restricted the private file to the user with `icacls`; (2) appended the new public line to `~/.ssh/authorized_keys` using the old key (first attempt appended nothing: the key line was passed as a remote shell argument and split at the spaces, so the "already present" check ran on an empty string; it was then sent as script text); (3) logged in with the new key alone (`-o IdentitiesOnly=yes -i`); (4) found the old key's line by comparing the public key derived with `ssh-keygen -y -f` (public output only) and removed exactly one matching line; (5) checked that the old key is refused and the new one works; (6) counted key lines in every file sshd reads, comments only.
Expected vs actual: Expected the console's key to be the only way in until replaced. Actual: the rotation worked; afterwards `authorized_keys` held exactly 1 line (the new key), root had none, and no other key had been injected. The old private key file stays on the PC until its owner deletes it. I did not check how Lightsail's browser-based SSH authenticates.
Severity: Low
Impact: About one working session of rotation work; the exposure window was the time the text sat in a session transcript, which cannot be deleted from here.
Workaround: Rotation as above (RUNBOOK section 11). The scripts now default to `~\.ssh\clucktalk-pilot-ed25519`, so a key path is never needed in a task description.
Actionable suggestion: Owner: our runbook and any task template. Give a key by path only; never paste key text. For the platform: Lightsail's key download is a one-time secret that is easy to leak into chats and tickets; a console option to install your own public key at creation would avoid the download.
Time cost: not recorded
Reproduce: follow RUNBOOK section 11 on any instance; check with `grep -c "^ssh-"` on the `authorized_keys` files.
Evidence: login with the old key after the change printed "Permission denied (publickey)"; the new key logged in; `verify.ps1` passed with the new key (2026-10-13).

## FL-034: On the public demo the cards did not render: the card sandbox origin was built as `https://localhost:` (empty port)
Date: 2026-10-21 (fixed in commit a04e8e5)
Tool / service: CluckTalk Simulator (`src/clucktalk/simulator/static/app.js`, `sandbox.js`, `simulator/app.py`) served over https on the public demo host; the MCP Apps rule that the card proxy ("sandbox") and the host page must have different origins
Tag: [Dev]
Task attempted: Show the cards in the Simulator on the public demo host (https, port 443) for judges.
Steps taken: Opened the public demo and asked for a card answer. The exact click path was not recorded.
Expected vs actual: Expected the card to render as it does locally. Actual (found on the public demo, per the test docstring in `tests/harness/test_windows_launcher.py`): the page chose the card proxy's origin by swapping `127.0.0.1` and `localhost` on the same port (the local way to get a second origin). Behind https on port 443 `location.port` is empty, so the result was `https://localhost:` and no card rendered.
Severity: Medium
Impact: Cards did not render on the public demo until the fix; a local run and the pilot were not affected.
Workaround: Fixed in code (status: FIXED; CI green on a04e8e5, run 39497290345). A public host now sets `CLUCKTALK_SANDBOX_ORIGIN=https://sandbox.<public host>`. The page uses it as the proxy origin; on that name the server answers only `/sandbox` and `/static/` (anything else is 404); the proxy's `frame-ancestors` names the page origin; `sandbox.js` takes the embedding page's origin from its own host name, because that page may send no referrer. Unset, nothing changes (the loopback swap). The DNS and web-server side of the `sandbox.` name is outside this repository and is not recorded here.
Actionable suggestion: Owner: CluckTalk (ours). A host page that must put the sandbox on a different origin needs a second host name when it is served on the default https port; say so wherever the second-origin rule is explained. Our own test now pins the origin choice.
Time cost: not recorded
Reproduce: `tests/harness/test_windows_launcher.py::test_card_sandbox_origin_is_the_loopback_swap_unless_a_sibling_host_is_set` pins the new rule. The original failure was seen on the public demo only and is not reproduced locally.
Evidence: commit a04e8e5; CI run 39497290345 (success, all four jobs). That cards render on the public demo after the fix is owner-reported (handoff), not re-checked in this entry.

## FL-035: The briefing card's date text was not excluded from the cross-modal number check, which could report a false mismatch
Date: 2026-10-21 (fixed in commit 764fa80)
Tool / service: CluckTalk briefing card (`src/clucktalk/server/cards/briefing.html`, `ui/cards/briefing.html`) and the Simulator's cross-modal check (`crossModal` in `src/clucktalk/simulator/static/app.js`)
Tag: [Dev]
Task attempted: Keep "spoken numbers equal card numbers" checked in the Simulator for every card.
Steps taken: Detail not recorded (the failing check output was not saved).
Expected vs actual: Expected the check to compare only the numbers of the answer. Actual: the farm-status card already marked its display-only date spans with `data-xm-skip` (the card removes those nodes before the check reads its text); the briefing card's date span had no such mark, so its digits were part of the checked text. The commit message calls this a false cross-modal failure.
Severity: Low
Impact: A false failure on a display-only date, not a wrong number on the card.
Workaround: Fixed (status: FIXED; CI green on 764fa80, run 39486708012 on its second attempt, see FL-036): `data-xm-skip` added to the briefing date span in both card copies.
Actionable suggestion: Owner: CluckTalk (ours). Give every card the same list of display-only elements, and test the check on each card that shows a date.
Time cost: not recorded
Reproduce: Detail not recorded.
Evidence: commit 764fa80 (two lines, one per card copy).

## FL-036: One Windows 3.12 CI job failed on a contract test about overlapping request ids; a single re-run passed and the cause was not investigated
Date: 2026-10-20 (GitHub Actions log time, UTC)
Tool / service: GitHub Actions windows-latest, Python 3.12; `tests/contract/test_concurrency.py::test_two_overlapping_requests_with_the_same_id_leave_one_unanswered_pinned_finding`
Tag: [Dev]
Task attempted: Run `python tasks.py check` on the CI matrix for commit 764fa80.
Steps taken: Pushed 764fa80; the windows / 3.12 job failed; the run was re-run once (attempt 2) and all jobs passed.
Expected vs actual: Expected one of the two pinned outcomes (`["200", "unanswered"]` or `["200", "500"]`, see FL-011). Actual in attempt 1: `["200", "200"]` (both requests answered); 1 failed, 1204 passed in 358.62 s. The other three jobs passed in the same attempt.
Severity: Low
Impact: One red CI job and one re-run; no product change.
Workaround: A single re-run (status: OPEN). Not investigated: it is not known whether the SDK's behaviour or the test's timing produced the third outcome, and the test was not changed.
Actionable suggestion: Owner: CluckTalk tests (ours). If it recurs, record the outcomes of each run and decide whether `["200", "200"]` is a third valid outcome of the SDK finding in FL-011 or a timing artefact; do not loosen the test before that.
Time cost: not recorded
Reproduce: not reproduced; see the failed log of run 39486708012, attempt 1 (`gh run view 39486708012 --attempt 1 --log-failed`).
Evidence: run 39486708012: attempt 1 failure, attempt 2 success.

## FL-037: `CLUCKTALK_SANDBOX_ORIGIN` is a new deployment setting, so it refuses any value except the sibling name of the public origin
Date: 2026-10-21 (added with the fix in commit a04e8e5)
Tool / service: CluckTalk Simulator settings (`sandbox_origin_from_env` in `src/clucktalk/simulator/app.py`)
Tag: [Dev]
Task attempted: Let the public demo host name its card proxy origin without letting a wrong value change which page may embed the proxy.
Steps taken: The setting is read at start-up; the code compares it with `CLUCKTALK_PUBLIC_ORIGIN`.
Expected vs actual: Expected a plain environment variable to be enough. Actual (a design finding, not an outage): the value decides which page the proxy's `frame-ancestors` allows, so the code raises a configuration error unless the value is exactly `https://sandbox.<host of CLUCKTALK_PUBLIC_ORIGIN>`. A test pins four wrong cases: no public origin, a different host, `http`, and the page's own origin. The Windows pilot launcher does not list it ("the farmer's phone page shows no cards; only the judges' demo host sets it").
Severity: Low
Impact: A wrong value stops the Simulator at start-up with a message instead of serving a proxy that the wrong page could embed.
Workaround: None needed (status: FIXED by the guard; unset means no change).
Actionable suggestion: Owner: CluckTalk (ours). Keep the setting out of the pilot launcher's list, and keep the four refusals in the test.
Time cost: not recorded
Reproduce: `tests/harness/test_windows_launcher.py::test_card_sandbox_origin_is_the_loopback_swap_unless_a_sibling_host_is_set`.
Evidence: commit a04e8e5.
