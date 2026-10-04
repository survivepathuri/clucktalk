# ruff: noqa: E501  (table texts)
"""Everything a judge can check in one command, fast, on this machine.

It does NOT rerun the full test suites (``python tasks.py check`` does that, in about 25 minutes). It runs a FAST SUBSET
(listed below), counts the tests it collects in each folder (collected, not run), scans the text for claims the project
must not make, and runs the protocol probe, the replay latency summary, the readiness self-check and the secret scan.
Exit code: 0 when no row is FAIL, 1 otherwise.

Usage (Windows):  python tasks.py verify
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import inspector_replay as replay  # noqa: E402
import readiness  # noqa: E402

FAST_SUBSET = (
    "tests/harness/test_docs_honesty.py",
    "tests/harness/test_friction_log_fields.py",
    "tests/harness/test_notice.py",
    "tests/harness/test_addon_draft.py",
    "tests/contract/test_tool_descriptions_simulated.py",
    "tests/contract/test_tool_descriptions_overlap.py",
    "tests/contract/test_protocol_conformance.py",
)
README_COMMANDS = (
    "python tasks.py setup",
    "python tasks.py serve",
    "python tasks.py verify",
    "python tasks.py readiness",
    "python tasks.py demo-three-days",
)
SCANNED = ("README.md", "docs/*.md", "skills/**/*.md", "docs/addon-package/addon.json")
SKIPPED_SCAN = ("docs/DEVPOST_FRICTION_PASTE.md", "docs/DEVPOST_FRICTION_PASTE_SHORT.md", "docs/TELUGU_REVIEW.md")
FORBIDDEN = {
    "production-ready": re.compile(r"production[- ]ready", re.I),
    "enterprise-grade": re.compile(r"enterprise[- ]grade", re.I),
    "zero-hallucination": re.compile(r"zero[- ]hallucination", re.I),
    "guaranteed": re.compile(r"\bguarantee[sd]?\b", re.I),
    "real-time": re.compile(r"real-?time", re.I),
    "claim that Alexa+ runs this": re.compile(
        r"\b(works|runs|running|deployed|live|available|certified)\b[^.\n]{0,25}\b(on|in|through|with)\b[^.\n]{0,10}alexa\+",
        re.I,
    ),
    "claim that Telugu voice works through Alexa+": re.compile(
        r"telugu[^.\n]{0,40}(voice|speech|spoken)[^.\n]{0,60}alexa\+|alexa\+[^.\n]{0,60}telugu[^.\n]{0,20}(voice|speech)",
        re.I,
    ),
}
# A line that says the word in order to rule it out is not a claim.
NEGATION = re.compile(
    r"\b(never|not|no|none|nothing|without|cannot|can't|doesn't|does not|don't|isn't|forbidden|unverified|exists? no)\b|n't\b",
    re.I,
)
SIMULATED_TOOLS = ("plan_sale", "plan_feed", "prepare_vet_handoff")


def scan_text(name: str, text: str) -> list[str]:
    """Forbidden claims in ``text``: (file:line word) for each line that says one without a negation."""
    hits = []
    lines = text.splitlines()
    for number, line in enumerate(lines, 1):
        context = (
            lines[number - 2] + " " if number > 1 else ""
        ) + line  # a wrapped sentence keeps its "no" on the line before
        for word, pattern in FORBIDDEN.items():
            if pattern.search(line) and not NEGATION.search(context):
                hits.append(f"{name}:{number} {word}")
    return hits


def scan_files() -> list[str]:
    hits: list[str] = []
    for pattern in SCANNED:
        for path in sorted(ROOT.glob(pattern)):
            rel = path.relative_to(ROOT).as_posix()
            if rel in SKIPPED_SCAN or "/evidence/" in rel:
                continue
            hits += scan_text(rel, path.read_text(encoding="utf-8"))
    return hits


def _run(args: list[str], timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def _pytest_line(output: str) -> str:
    lines = [ln for ln in output.strip().splitlines() if ln.strip()]
    return lines[-1].strip() if lines else "no output"


def collected(folder: str) -> str:
    done = _run(["-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", folder], timeout=120)
    m = re.search(r"(\d+) tests? collected", done.stdout)
    return m.group(1) if m else "?"


def notice_os(notice: str) -> str:
    m = re.search(r"^Generated on: (.+)$", notice, re.M)
    if m:
        return m.group(1).strip()
    return "not recorded in NOTICE"


def probe_rows(output: str) -> list[str]:
    rows = [ln for ln in output.splitlines() if re.match(r"^(2\d{3}-\d\d-\d\d) +\| ", ln)]
    return rows


def main() -> int:
    started = time.monotonic()
    rows: list[tuple[str, str, str]] = []

    def add(name: str, ok: bool | None, detail: str) -> None:
        rows.append((name, "INFO" if ok is None else "PASS" if ok else "FAIL", detail))

    add("license file present", (ROOT / "LICENSE").is_file(), "LICENSE (MIT)")
    notice = ROOT / "NOTICE"
    if notice.is_file():
        text = notice.read_text(encoding="utf-8")
        generated = notice_os(text)
        here = {"win32": "Windows", "linux": "Linux", "darwin": "macOS"}.get(sys.platform, sys.platform)
        add("NOTICE present", True, f"generated on: {generated}; this machine: {here}")
    else:
        add("NOTICE present", False, "run python tasks.py notices")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [c for c in README_COMMANDS if c not in readme]
    add(
        "README run steps exist",
        "## Try it now" in readme and not missing,
        "Try it now section with " + ", ".join(README_COMMANDS) if not missing else f"missing: {missing}",
    )
    hits = scan_files()
    add(
        "forbidden claims absent (README, docs, skill, listing draft)",
        not hits,
        "none found" if not hits else "; ".join(hits[:6]),
    )

    with replay.running_server() as url:
        r = replay.Replay(url)
        try:
            r.initialize_and_keep_session()
            r.initialized()
            _, tools = r.tools_list()
        finally:
            r.close()
        descriptions = {t["name"]: t.get("description", "") for t in tools}
        not_simulated = [n for n in SIMULATED_TOOLS if "simulated" not in descriptions.get(n, "").lower()]
        live_claims = [
            n for n, d in descriptions.items() if FORBIDDEN["real-time"].search(d) and not NEGATION.search(d)
        ]
        add(
            "tool descriptions say SIMULATED where data is simulated",
            not not_simulated and not live_claims,
            f"{', '.join(SIMULATED_TOOLS)} say it; no description claims real-time data"
            if not (not_simulated or live_claims)
            else f"missing: {not_simulated}; real-time claims: {live_claims}",
        )
        reqs = readiness.collect(url, 5)

    local = [q for q in reqs if q.status != readiness.NOT_CHECKABLE]
    add(
        "readiness self-check (ours, not Amazon's)",
        all(q.status == readiness.MET for q in local),
        readiness.summary_line(reqs),
    )
    latency = next(q for q in reqs if q.key == "latency")
    add(
        "replay latency (5 rounds, localhost, mock mode)",
        latency.status == readiness.MET,
        latency.detail.split(" (")[0],
    )

    probe = _run(["scripts/probe_protocol_version.py"], timeout=120)
    table = probe_rows(probe.stdout)
    add(
        "protocol probe",
        probe.returncode == 0 and len(table) == 4,
        "; ".join(" ".join(x.split()) for x in table) or probe.stderr.strip()[-200:],
    )

    counts = {f: collected(f"tests/{f}") for f in ("harness", "unit", "contract")}
    add(
        "tests collected (counted now, not typed; collected, not run)",
        all(v != "?" for v in counts.values()),
        ", ".join(f"{k} {v}" for k, v in counts.items()),
    )
    subset = _run(["-m", "pytest", "-q", "-p", "no:cacheprovider", *FAST_SUBSET], timeout=900)
    add("fast test subset", subset.returncode == 0, f"{_pytest_line(subset.stdout)} ({len(FAST_SUBSET)} files)")
    friction = _run(
        ["-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/harness/test_friction_log_fields.py"], timeout=120
    )
    add("friction log field set valid", friction.returncode == 0, _pytest_line(friction.stdout))
    secrets = _run(["scripts/scan_secrets.py"], timeout=300)
    add("secret scan", secrets.returncode == 0, _pytest_line(secrets.stdout))

    print(
        "verify: what a judge can check in one command (fast; not the full suites, which `python tasks.py check` runs)\n"
    )
    print(replay.format_table(("check", "result", "detail"), rows))
    print(f"\nFast subset run: {', '.join(Path(f).name for f in FAST_SUBSET)}")
    print(f"Runtime: {time.monotonic() - started:.0f} seconds.")
    failed = [n for n, s, _ in rows if s == "FAIL"]
    print("verify: " + ("all checks passed" if not failed else f"FAILED: {', '.join(failed)}"))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
