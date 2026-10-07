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
