# ruff: noqa: E501  (long document text)
"""Generate docs/RESULTS.md from this machine and these files (Step 54): ``python tasks.py results``.

Nothing in the output is typed by hand. The numbers come from: ``pytest --collect-only`` (test counts, collected and not
run), the table that ``python tasks.py eval-fast`` wrote to docs/EVALS.md (run it first), ``tests/contract/
test_protocol_conformance.py`` (run now), ``scripts/inspector_replay.py`` (run now), ``scripts/readiness.py`` (run now),
and two data files that copy what the builder's progress log records (``data/results/mutation_results.json`` and
``data/results/review_rounds.json``). A full ``check`` is not run here: give ``--check-log FILE`` (the saved output of
``python tasks.py check``) to include its summary; otherwise the file says it is not recorded.

Usage (Windows):  python tasks.py results [--check-log FILE]
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "RESULTS.md"
EVALS_MD = ROOT / "docs" / "EVALS.md"
MUTATIONS = ROOT / "data" / "results" / "mutation_results.json"
REVIEWS = ROOT / "data" / "results" / "review_rounds.json"
SUITES = ("harness", "unit", "contract")
CONFORMANCE = "tests/contract/test_protocol_conformance.py"
LOCALHOST_NOTE = "server time on localhost, mock mode, not Amazon's 500 ms round trip"
NOT_RECORDED = "not recorded"


def _run(args: list[str], timeout: int = 900) -> str:
    done = subprocess.run(
        [sys.executable, "-B", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=timeout
    )
    return done.stdout + done.stderr


def git_state() -> tuple[str, str]:
    """(short commit hash, 'clean' or 'modified')."""
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    status = subprocess.run(["git", "status", "--short"], cwd=ROOT, capture_output=True, text=True)
    return head.stdout.strip() or NOT_RECORDED, "clean" if not status.stdout.strip() else "modified (uncommitted files)"


def git_history() -> list[tuple[str, int]]:
    """(date, commits that day) from ``git log``, oldest day first. Empty when git cannot say."""
    done = subprocess.run(["git", "log", "--format=%ad", "--date=short"], cwd=ROOT, capture_output=True, text=True)
    days: dict[str, int] = {}
    for line in done.stdout.split():
        days[line] = days.get(line, 0) + 1
    return sorted(days.items())


def collected(output: str) -> int | None:
    m = re.search(r"(\d+) tests? collected", output)
    return int(m.group(1)) if m else None


def parse_evals(text: str) -> dict[str, object]:
    """Run time, cases, passes and the failing case names from the table eval-fast wrote."""
    rows = re.findall(r"^\| ([\w-]+) \| (PASS|FAIL) \|", text, re.M)
    run = re.search(r"^Run (\S+),", text, re.M)
    score = re.search(r"\*\*Score: (\d+)/(\d+)\*\*", text)
    passed = sum(1 for _n, r in rows if r == "PASS")
    return {
        "run": run.group(1) if run else NOT_RECORDED,
        "cases": len(rows),
        "passed": passed,
        "failed": [n for n, r in rows if r == "FAIL"],
        "score_line": f"{score.group(1)}/{score.group(2)}" if score else NOT_RECORDED,
    }


def parse_pytest_line(output: str) -> str:
    lines = [ln.strip() for ln in output.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else NOT_RECORDED


def parse_replay(output: str) -> tuple[list[tuple[str, float, float]], int | None]:
    """((step, p50, p95) in order, rounds) from the replay's JSON summary line and its table heading."""
    m = re.search(r'^\{"replay_summary": (.*)\}$', output, re.M)
    steps: list[tuple[str, float, float]] = []
    if m:
        data = json.loads(m.group(1))
        steps = [(name, v["p50"], v["p95"]) for name, v in data.items()]
    r = re.search(r"over (\d+) rounds", output)
    return steps, int(r.group(1)) if r else None


def parse_check_log(text: str) -> list[str]:
    """The lines of the closing summary of ``tasks.py check`` ('PASS  lint (ruff)' ... 'check: PASSED')."""
    out = []
    started = False
    for line in text.splitlines():
        if line.startswith("== check summary =="):
            started = True
            continue
        if started and line.strip():
            out.append(line.strip())
    return out


def history_text(history: list[tuple[str, int]]) -> str:
    if not history:
        return f"Git history: {NOT_RECORDED} (git did not answer)."
    total = sum(n for _d, n in history)
    lines = [
        f"The first commit is dated {history[0][0]} and the latest {history[-1][0]}; {total} commits on {len(history)} days.",
        "",
        "| Date | Commits |",
        "|---|---|",
    ]
    lines += [f"| {d} | {n} |" for d, n in history]
    return "\n".join(lines)


def mutation_table(data: dict) -> str:
    rows = data["rows"]
    caught = sum(r["caught"] for r in rows)
    total = sum(r["total"] for r in rows)
    lines = ["| Step | Part | Caught / total | Note |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['step']} | {r['part']} | {r['caught']} / {r['total']} | {r['note'] or '-'} |")
    lines.append(
        f"| | **All listed parts** | **{caught} / {total}** | {total - caught} survivor(s), each named in its note |"
    )
    return "\n".join(lines)


def review_table(data: dict) -> str:
    lines = ["| Scope | Found | What was done |", "|---|---|---|"]
    for r in data["rounds"]:
        lines.append(f"| {r['scope']} | {r['found']} | {r['fixed']} |")
    return "\n".join(lines)


def render(
    *,
    today: str,
    commit: str,
    tree: str,
    counts: dict[str, int | None],
    evals: dict[str, object],
    conformance: str,
    probe_rows: list[str],
    replay: tuple[list[tuple[str, float, float]], int | None],
    readiness_line: str,
    check_summary: list[str],
    mutations: dict,
    reviews: dict,
    history: list[tuple[str, int]],
) -> str:
    steps, rounds = replay
    total_tests = sum(v for v in counts.values() if v)
    out: list[str] = []
    out += [
        "# Results",
        "",
        f"Generated by `python tasks.py results` on {today} at commit `{commit}` (working tree: {tree}). Nothing here is "
        "typed by hand: each section says where its numbers come from. This is a local run on the builder's Windows PC "
        "in mock mode (no AWS, no model call). It is **not an Amazon verdict**, and nothing here ran on an Alexa+ device.",
        "",
        "## 1. Tests (collected now, not typed)",
        "",
        "| Suite | Tests collected |",
        "|---|---|",
    ]
    for s in SUITES:
        out.append(f"| `tests/{s}` | {counts[s] if counts[s] is not None else NOT_RECORDED} |")
    out.append(f"| **Total** | **{total_tests}** |")
    out += [
        "",
        "Collected is not passed: `python tasks.py check` runs them. Its closing summary, if one was given to this "
        "script:",
        "",
    ]
    if check_summary:
        out += ["```", *check_summary, "```"]
    else:
        out.append(
            f"Last full `check` summary: {NOT_RECORDED} by this run (run `python tasks.py check` and give its saved "
            "output with `--check-log`)."
        )
    out += [
        "",
        "## 2. Golden evals (`python tasks.py eval-fast`, mock mode)",
        "",
        f"The table in `docs/EVALS.md` was written by the eval run of {evals['run']}: "
        f"**{evals['passed']} of {evals['cases']} cases passed** (score line `{evals['score_line']}`).",
        "",
    ]
    if evals["failed"]:
        out.append("Failing cases: " + ", ".join(f"`{n}`" for n in evals["failed"]) + ".")
    else:
        out.append("Failing cases: none in that table.")
    out += [
        "",
        "The cases run against a real MCP server over real HTTP with a test model in mock mode, so the score says "
        "nothing about live Bedrock answers. Re-run `python tasks.py eval-fast` before this command to refresh it.",
        "",
        "## 3. Mutation checks (planted faults the tests had to catch)",
        "",
        mutations["source"],
        "",
        mutation_table(mutations),
        "",
        "## 4. Protocol conformance",
        "",
        f"`{CONFORMANCE}` was run now: `{conformance}`.",
        "",
        "What the server answers to `initialize` for each protocol version (`python tasks.py probe-protocol-version`, "
        "same run):",
        "",
        "| Requested | HTTP status | Server answered with |",
        "|---|---|---|",
    ]
    out += [f"| {r} |" for r in probe_rows] or [f"| {NOT_RECORDED} | | |"]
    out += [
        "",
        f"## 5. Latency: {LOCALHOST_NOTE}",
        "",
        f"From `python tasks.py inspector-replay`, our replay of the flow documented on Amazon's Local Inspector page "
        f"({rounds if rounds else NOT_RECORDED} rounds, milliseconds). **These are {LOCALHOST_NOTE}.** There is no model "
        "call and the data is simulated; a remote host and a real model add to the times. The Local Inspector itself was "
        "not run (FL-024).",
        "",
        "| Step | p50 (ms) | p95 (ms) |",
        "|---|---|---|",
    ]
    out += [f"| {n} | {a} | {b} |" for n, a, b in steps] or [f"| {NOT_RECORDED} | | |"]
    out += [
        "",
        "## 6. Readiness",
        "",
        f"`python tasks.py readiness` (our own checklist, not Amazon's tool): **{readiness_line}** Details and the four "
        "requirements it cannot check: `docs/ALEXA_READINESS.md`.",
        "",
        "## 7. Independent reviews",
        "",
        reviews["source"],
        "",
        review_table(reviews),
        "",
        f"{len(reviews['rounds'])} rounds are recorded. Severity words are the reviewers'. A review finds what it was "
        "pointed at; it is not a proof that nothing else is wrong. More on the process: `docs/INDEPENDENT_REVIEW.md`.",
        "",
        "## 8. Build history (from `git log`)",
        "",
        history_text(history),
        "",
        "## 9. What this file does not show",
        "",
        "- Pilot numbers do not exist yet: [PILOT NUMBERS: to be filled on <date> from python tasks.py pilot-stats].",
        "- No live AWS or model result: the evals and the latency run in mock mode.",
        "- No Alexa+ device, no Telugu voice through Alexa+, no native-speaker review of the new Telugu wording "
        "(`docs/TELUGU_REVIEW.md`).",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    check_log = None
    if args[:1] == ["--check-log"] and len(args) == 2:
        check_log = Path(args[1])
    elif args:
        print("results: the only option is --check-log FILE.", file=sys.stderr)
        return 2
    counts = {
        s: collected(_run(["-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", f"tests/{s}"], 300))
        for s in SUITES
    }
    evals = parse_evals(EVALS_MD.read_text(encoding="utf-8"))
    conformance = parse_pytest_line(_run(["-m", "pytest", "-q", "-p", "no:cacheprovider", CONFORMANCE]))
    probe = _run(["scripts/probe_protocol_version.py"])
    probe_rows = [
        " | ".join(p.strip() for p in ln.split("|"))
        for ln in probe.splitlines()
        if re.match(r"^\d{4}-\d{2}-\d{2} \| \d+", ln)
    ]
    replay = parse_replay(_run(["scripts/inspector_replay.py"]))
    ready = _run(["scripts/readiness.py"])
    m = re.search(r"^(\d+ of \d+ locally checkable requirements met[^\n]*)$", ready, re.M)
    commit, tree = git_state()
    check_summary = parse_check_log(check_log.read_text(encoding="utf-8", errors="replace")) if check_log else []
    text = render(
        today=date.today().isoformat(),
        commit=commit,
        tree=tree,
        counts=counts,
        evals=evals,
        conformance=conformance,
        probe_rows=probe_rows,
        replay=replay,
        readiness_line=(m.group(1).rstrip(".") + "." if m else NOT_RECORDED),
        check_summary=check_summary,
        mutations=json.loads(MUTATIONS.read_text(encoding="utf-8")),
        reviews=json.loads(REVIEWS.read_text(encoding="utf-8")),
        history=git_history(),
    )
    OUT.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))
    print(f"results: wrote {OUT.relative_to(ROOT).as_posix()} ({len(text.splitlines())} lines) at commit {commit}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
