"""Step 49 part C: ``python tasks.py verify`` (scripts/verify.py) prints one table of what a judge can check, fast; the
README has the "Try it now" commands, the known limitations and a claims table whose evidence exists."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import verify  # noqa: E402

import tasks  # noqa: E402

README = (ROOT / "README.md").read_text(encoding="utf-8")


# -- the forbidden-claims scan ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("line", "word"),
    [
        ("CluckTalk is production-ready.", "production-ready"),
        ("An enterprise grade farm manager.", "enterprise-grade"),
        ("A zero-hallucination assistant.", "zero-hallucination"),
        ("Accuracy is guaranteed.", "guaranteed"),
        ("It shows real-time market prices.", "real-time"),
        ("CluckTalk runs on Alexa+ today.", "claim that Alexa+ runs this"),
        ("It works through Alexa+ in every home.", "claim that Alexa+ runs this"),
        ("Telugu voice works through Alexa+ now.", "claim that Telugu voice works through Alexa+"),
        ("Alexa+ speaks Telugu voice answers.", "claim that Telugu voice works through Alexa+"),
    ],
)
def test_each_forbidden_claim_is_found(line, word):
    assert f"x.md:1 {word}" in verify.scan_text("x.md", line)


@pytest.mark.parametrize(
    "line",
    [
        "Descriptions never claim real-time or live data.",
        "It does not claim that Alexa+ runs CluckTalk.",
        "Nothing here has run on Alexa+ today.",
        "No Telugu voice has been tested through Alexa+.",
        "We make no guaranteed claim.",
        "Real time is read only in now_ist.",
    ],
)
def test_a_line_that_rules_a_claim_out_is_not_a_claim(line):
    assert verify.scan_text("x.md", line) == []


def test_the_repository_text_has_no_forbidden_claim():
    assert verify.scan_files() == []


def test_the_scan_covers_the_readme_the_docs_the_skill_and_the_listing_draft():
    files = {p.relative_to(ROOT).as_posix() for pattern in verify.SCANNED for p in ROOT.glob(pattern)}
    assert {"README.md", "docs/DESIGN.md", "docs/ALEXA_READINESS.md", "docs/addon-package/addon.json"} <= files
    assert any(f.startswith("skills/") for f in files)


# -- helpers ---------------------------------------------------------------------------------------------
def test_notice_os_reads_the_generated_on_line_or_says_it_is_not_recorded():
    assert verify.notice_os("x\nGenerated on: Windows\ny") == "Windows"
    assert verify.notice_os("nothing") == "not recorded in NOTICE"


def test_probe_rows_keeps_only_the_four_version_rows():
    head = "Server: x\n\nRequested | HTTP status | Server answered with\n-----\n"
    out = head + "2025-11-25 | 200 | 2025-11-25\n2024-11-05 | 200 | 2024-11-05\n"
    assert len(verify.probe_rows(out)) == 2


def test_the_command_exists_and_takes_no_arguments(monkeypatch):
    assert tasks.COMMANDS["verify"] is tasks.verify
    monkeypatch.setattr(tasks.sys, "argv", ["tasks.py", "verify", "--all"])
    assert tasks.main() == 2


# -- the README ------------------------------------------------------------------------------------------
def test_the_readme_has_the_try_it_now_commands_the_limits_and_the_claims_table():
    for heading in ("## Try it now", "## Known limitations", "## What is verified, unverified and simulated"):
        assert heading in README
    top = README.split("## Quick start")[0]
    for command in verify.README_COMMANDS:
        assert command in top
    assert "mcp-inspector" in top and "--method tools/list" in top and "--method tools/call" in top
    assert top.index("## Try it now") < top.index("## Known limitations") < top.index("## What is verified")


# The one sentence allowed to type counts: "Automated tests: <total> (<parts>); counts from the full verify ..."
TEST_LINE = re.compile(
    r"^Automated tests: ([\d,]+) \(([\d,]+) harness, ([\d,]+) unit, ([\d,]+) contract\); "
    r"counts from the full verify recorded in docs/RESULTS\.md\.$",
    re.MULTILINE,
)


def test_the_readme_does_not_type_test_counts():
    lines = TEST_LINE.findall(README)
    assert len(lines) == 1, "exactly one 'Automated tests:' line is allowed in the README"
    total, *parts = (int(n.replace(",", "")) for n in lines[0])
    assert total == sum(parts), "the typed total must equal the sum of its parts"
    rest = TEST_LINE.sub("", README)
    assert not re.search(r"\b\d{2,4} (unit|contract|harness|golden)\b", rest), "counts come from verify, not the README"


def _claim_rows() -> list[tuple[str, str, str]]:
    section = README.split("## What is verified, unverified and simulated")[1].split("\n## ")[0]
    rows = [ln for ln in section.splitlines() if ln.startswith("|") and not ln.startswith("|---") and "Claim" not in ln]
    return [tuple(c.strip() for c in ln.strip("|").split("|")[:3]) for ln in rows]  # type: ignore[misc]


def test_every_claim_has_a_status_and_every_evidence_path_exists():
    rows = _claim_rows()
    assert len(rows) >= 15
    for claim, status, evidence in rows:
        assert status.split(" ")[0] in {"VERIFIED", "UNVERIFIED", "SIMULATED", "NOT"}, (claim, status)
        for ref in re.findall(r"`([^`]+)`", evidence):
            if ref.startswith("python tasks.py"):
                assert ref.split()[2] in tasks.COMMANDS, ref
                continue
            path = ref.split("::")[0].split(" ")[0]
            if "/" in path or path.endswith(".md") or path.endswith(".py") or path.endswith(".json"):
                assert (ROOT / path).exists(), (claim, ref)


def test_the_status_words_cover_all_three_kinds_the_brief_asks_for():
    statuses = {s.split(" ")[0] for _, s, _ in _claim_rows()}
    assert {"VERIFIED", "UNVERIFIED", "SIMULATED"} <= statuses


# -- the real run ----------------------------------------------------------------------------------------
def test_a_real_run_prints_the_table_the_subset_the_runtime_and_exits_zero(capsys):
    assert verify.main() == 0
    out = capsys.readouterr().out
    for name in (
        "license file present",
        "NOTICE present",
        "README run steps exist",
        "forbidden claims absent",
        "tool descriptions say SIMULATED",
        "readiness self-check",
        "replay latency",
        "protocol probe",
        "tests collected",
        "fast test subset",
        "friction log field set valid",
        "secret scan",
    ):
        assert name in out, name
    assert "FAIL" not in out and "all checks passed" in out
    assert "Fast subset run:" in out and re.search(r"Runtime: \d+ seconds", out)
    assert int(re.search(r"(\d+) passed in [\d.]+s \(7 files\)", out).group(1)) >= 100  # the subset really ran
    assert "not Amazon's" in out and re.search(r"harness \d+, unit \d+, contract \d+", out)


def test_a_failing_row_gives_exit_code_one_and_names_it(capsys, monkeypatch):
    monkeypatch.setattr(verify, "scan_files", lambda: ["README.md:1 guaranteed"])
    monkeypatch.setattr(verify, "FAST_SUBSET", ("tests/harness/test_friction_log_fields.py",))
    assert verify.main() == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and "README.md:1 guaranteed" in out and "FAILED: forbidden claims absent" in out


def test_the_listed_commands_and_simulated_tools_are_the_documented_ones():
    assert verify.README_COMMANDS == (
        "python tasks.py setup",
        "python tasks.py serve",
        "python tasks.py verify",
        "python tasks.py readiness",
        "python tasks.py demo-three-days",
    )
    assert verify.SIMULATED_TOOLS == ("plan_sale", "plan_feed", "prepare_vet_handoff")
    assert len(verify.FAST_SUBSET) == 7 and all((ROOT / f).exists() for f in verify.FAST_SUBSET)


def test_a_wrapped_sentence_keeps_its_negation_from_the_line_before():
    text = "No Telugu voice has been tested\nthrough Alexa+ at all."
    assert verify.scan_text("x.md", text) == []
    assert verify.scan_text("x.md", "Fine.\nTelugu voice works through Alexa+.") != []
