# Developer notes: friction with our own tooling

Entries from `FRICTION_LOG.md` that are about our own tooling (Claude Code, Windows, npm, CI) and not about Alexa+, MCP Apps, AWS or Bedrock. They keep their FL numbers, so references elsewhere stay valid. Same six official fields. Moved here in the 2026-10-01 audit; the wording is unchanged except where noted.

## FL-005: Inspector CLI crashes on Windows when a call ends in an error
Date: 2026-09-27
Tool / service: MCP Inspector `@modelcontextprotocol/inspector` 2.8.0 CLI, Node v24.15.0, Windows 11 Pro
Tag: [Dev]
Task attempted: Capture evidence of error results (`tools/call` returning `isError: true`, and an unknown tool name).
Steps taken: `node <inspector>/clients/launcher/build/index.js --cli http://127.0.0.1:8765/mcp --method tools/call --tool-name get_farm_status --tool-arg "house=shed 9"` (3 runs), plus `--tool-name nope`.
Expected vs actual: Expected the documented JSON error on stderr and a normal non-zero exit code. Actual: the JSON error is printed, then `Assertion failed: !(handle->flags & UV_HANDLE_CLOSING), file src\win\async.c, line 76`, and the process dies (exit 127 in Git Bash, 3221226505 = 0xC0000409 from Python). Reproduced 3/3; also on `tool_not_found`, so independent of the server. Successful calls exit 0.
Severity: Low
Workaround: Read the JSON printed before the crash; do not rely on the exit code for error cases on Windows.
Actionable suggestion: Close pending async handles before `process.exit` on the CLI error path (a double close of a libuv async handle), and add a Windows CI smoke test for error exits.
Evidence: `docs/evidence/2026-09-27_farm_status_and_feed.md`.

## FL-022: Claude Code's shell tool changes backslash sequences in a command (`\b` in a Python heredoc reached the file as a backspace character)
Merged with its recurrence note (build session 4, 2026-10-01).
Date: 2026-10-01
Tool / service: Claude Code (Bash tool, Git Bash on Windows 11) while editing source files with a Python heredoc script
Tag: [Dev]
Task attempted: Add regular expressions that use word boundaries (`\b`) to `src/clucktalk/simulator/intents.py` by running a `python - <<'EOF'` script that wrote the file.
Steps taken: Wrote the pattern with a doubled backslash inside a non-raw Python string in the quoted heredoc, ran it, then ran ruff. Recurrence in build session 4: two more Python heredocs, and one quoted heredoc whose text held an apostrophe.
Expected vs actual: Expected `\b` (backslash, b) in the file. Actual: the file held the invisible backspace character (0x08) ten times; the patterns looked right in the editor and in terminal output, and only ruff's line-length complaint and a failing intent test showed something was off. A second fix attempt written the same way produced the same ten characters. Recurrence: a `\r\n` pair became real line breaks and broke the script's syntax, and the apostrophe case failed with `unexpected EOF while looking for matching`.
Severity: Low (cost about 15 minutes the first time and about 10 minutes on the recurrence; no wrong code was committed)
Workaround: Do not type backslashes in shell commands that write code. Use the Write or Edit tools for any text with backslashes, or build the character in code (`chr(92) + "b"`). Check with `grep -P "\x08"` afterwards.
Actionable suggestion: Document how the Bash tool treats backslashes in quoted heredocs, or pass the command text to the shell unchanged.
Evidence: none beyond the entry.

## FL-023: Windows timer granularity made a lower-bound timing test fail in CI (a 300 ms sleep measured 290.6 ms)
Date: 2026-10-01
Tool / service: GitHub Actions windows-latest, Python 3.12 (server sleep measured with time.perf_counter)
Tag: [Dev]
Task attempted: Run `python tasks.py check` on the CI matrix after pushing the follow-up session 3 commit.
Steps taken: The Simulator applied a 300 ms simulated delay; `tests/contract/test_simulator.py::test_simulated_delay_is_applied_and_reported` asserted the measured backend time was at least 300 ms.
Expected vs actual: Expected at least 300 ms. Actual: 290.6 ms on windows / 3.12 only; the other three jobs and the local Windows run passed. The measurement already used perf_counter, so the sleep itself returned early (coarse Windows timer).
Severity: Low (one red CI job; no product bug)
Workaround: Lower-bound tolerance of 50 ms in the test, with a comment. Upper-bound latency checks were not changed.
Actionable suggestion: Never assert an exact lower bound on a measured sleep; allow a tolerance of one or two timer ticks.
Evidence: `tests/contract/test_simulator.py::test_simulated_delay_is_applied_and_reported`.
