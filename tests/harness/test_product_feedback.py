"""Step 56 and Step 57: docs/PRODUCT_FEEDBACK.md, its paste-ready copy docs/PRODUCT_FEEDBACK_DEVPOST.md and
docs/FRICTION_SUMMARY.md.
Text checks only: every tool section answers the five questions, the ten paste blocks are the builder's approved
wording and each is under 110 words, every FL and FR number named exists, the counts match the tests, the AWS
live-and-mocked statement agrees with submission.md, and the friction summary names the entries and feature requests
that exist."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FEEDBACK = (ROOT / "docs" / "PRODUCT_FEEDBACK.md").read_text(encoding="utf-8")
DEVPOST = (ROOT / "docs" / "PRODUCT_FEEDBACK_DEVPOST.md").read_text(encoding="utf-8")
SUMMARY = (ROOT / "docs" / "FRICTION_SUMMARY.md").read_text(encoding="utf-8")
PLACEHOLDER = re.compile(r"\[BUILDER TO CONFIRM: ([^\]]+)\]")
FIELDS = ("**Used for:**", "**What worked well:**", "**What needs work:**", "**Onboarding:**", "**Build again:**")


def _tool_sections() -> list[tuple[str, str]]:
    """(heading, body) for the ten numbered tool sections (the 'Also used' tools are not numbered)."""
    out = []
    for block in re.split(r"(?m)^## (?=\d+\. )", FEEDBACK)[1:]:
        heading, _, body = block.partition("\n")
        out.append((heading, re.split(r"(?m)^## ", body)[0]))
    return out


SECTIONS = _tool_sections()


def test_the_tools_are_in_the_requested_order():
    headings = [h for h, _ in SECTIONS]
    expected_starts = (
        "1. Amazon Bedrock",
        "2. AWS CLI",
        "3. AWS console, accounts, credits",
        "4. Alexa+ MCP documentation",
        "5. MCP Python SDK",
        "6. MCP Apps",
        "7. Claude Code",
        "8. The Agent Skills format",
        "9. Tailscale Funnel",
        "10. GitHub Actions",
    )
    assert len(headings) == len(expected_starts)
    for heading, start in zip(headings, expected_starts, strict=True):
        assert heading.startswith(start), (heading, start)
    paste = re.findall(r"(?m)^## (\d+)\. ", DEVPOST)
    assert paste == [str(i) for i in range(1, 11)]


@pytest.mark.parametrize(("heading", "body"), SECTIONS, ids=[h[:30] for h, _ in SECTIONS])
def test_every_tool_section_answers_the_five_questions_in_order(heading, body):
    positions = [body.find(f) for f in FIELDS]
    assert all(p >= 0 for p in positions), (heading, [f for f, p in zip(FIELDS, positions, strict=True) if p < 0])
    assert positions == sorted(positions), heading
    again = body.split("**Build again:**")[1].strip().splitlines()[0].strip().lower()
    assert again.startswith("yes"), (heading, again)  # the builder's approved verdict, never a guess


def test_no_placeholder_is_left_and_the_two_computed_answers_are_filled_in():
    both = FEEDBACK + DEVPOST
    assert not PLACEHOLDER.findall(both) and "[BEDROCK DAYS]" not in both and "BUILDER TO CONFIRM" not in both
    # first recorded attempt 2026-09-28 (FL-014, AWS_SETUP section 5), first successful call 2026-09-29 (section 5.2)
    setup = (ROOT / "docs" / "AWS_SETUP.md").read_text(encoding="utf-8")
    assert "Results 2026-09-28" in setup and "First live Converse call: Nova 2 Lite (2026-09-29" in setup
    assert "Onboarding: 1 day from first attempt to first successful call (28 to 29 September)" in DEVPOST
    sentence = (
        "on 7 October we lost about 1 hour signing in because we had created several accounts ourselves; "
        "that was our mistake, not AWS's"
    )
    assert sentence in FEEDBACK and sentence in DEVPOST
    gone = ("authenticator", "codes were rejected", "sign-in failed", "aws access was unavailable", "recovery")
    for text in (FEEDBACK, DEVPOST, SUMMARY):  # the sign-in mix-up was ours; it is not described as AWS friction
        assert not [g for g in gone if g in text.lower()]
        assert text.lower().count("signing in on 7 october") <= 1


def test_every_fl_and_fr_number_named_exists():
    log = (ROOT / "FRICTION_LOG.md").read_text(encoding="utf-8")
    log += (ROOT / "docs" / "DEV_NOTES.md").read_text(encoding="utf-8")
    requests = (ROOT / "FEATURE_REQUESTS.md").read_text(encoding="utf-8")
    for fl in set(re.findall(r"FL-\d{3}", FEEDBACK + DEVPOST)):
        assert f"## {fl}:" in log, fl
    for fr in set(re.findall(r"FR-\d{3}", FEEDBACK + DEVPOST)):
        assert f"### {fr}:" in requests, fr


def test_each_block_names_the_entries_the_records_support():
    blocks = dict(re.findall(r"(?ms)^## (\d+)\. [^\n]*\n\n(.+?)(?=^## |\Z)", DEVPOST))
    expect = {
        "1": ("FL-014", "FL-015"),
        "2": ("FL-019",),
        "3": ("FL-013", "FR-007", "FL-027"),
        "4": ("FL-026", "FL-024", "FR-004", "FR-008"),
        "5": ("FL-011", "FL-004", "FL-002"),
        "6": ("FL-007", "FL-009", "FL-008", "FL-021"),
        "7": ("FL-022", "FL-025"),
        "10": ("FL-023", "FL-025"),
    }
    for n, ids in expect.items():
        for entry in ids:
            assert entry in blocks[n], (n, entry)
    log = (ROOT / "FRICTION_LOG.md").read_text(encoding="utf-8")
    fl27 = log.split("### FL-027:")[1]
    assert "App Runner" in fl27 and "30 April 2026" in fl27  # block 3 says only this about FL-027
    assert "India" in log.split("### FL-013:")[1].split("\n### ")[0]  # block 3: account plan on an India account


def test_the_counts_in_the_blocks_match_the_tests():
    out = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/contract/test_protocol_conformance.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    collected = int(re.search(r"(\d+) tests? collected", out).group(1))
    assert f"our {collected} protocol tests pass" in DEVPOST and f"the {collected} protocol tests" in FEEDBACK
    assert "14 tools" in DEVPOST and "14 tools" in FEEDBACK


def test_sentences_the_records_do_not_support_stay_out():
    for text in (FEEDBACK, DEVPOST):
        low = text.lower()
        for gone in ("certificate log", "count double", "power cut", "one real call", "survived power"):
            assert gone not in low or "not claimed" in low, gone


def test_each_paste_block_is_under_110_words():
    blocks = re.split(r"(?m)^## ", DEVPOST)[1:]
    assert len(blocks) == 10
    for block in blocks:
        heading, _, text = block.partition("\n")
        assert len(text.split()) < 110, (heading, len(text.split()))


def test_the_aws_live_and_mocked_section_agrees_with_the_submission():
    submission = (ROOT / "submission.md").read_text(encoding="utf-8")
    section = FEEDBACK.split("## AWS services: what was live and what was mocked")[1].split("\n## ")[0]
    for needle in (
        "Amazon Nova 2 Lite",
        "us-east-1",
        "a handful of one-off calls from the AWS CLI and boto3",
        "two forced-tool-choice spike calls",
        "under two tenths of a cent",
        "every AI answer in the demo, in the golden evals and in the tests",
        "Nothing was deployed to AWS; no Lambda, no Polly, no Knowledge Base.",
        "OpenSearch Serverless is never used",
    ):
        assert needle in section, needle
        assert needle in submission, needle
    assert "**not** verified end to end" in section and "**not** verified end to end" in submission
    assert "not used in production" in FEEDBACK and "builder-reported" in section


def test_builder_reported_facts_are_marked_and_the_inspector_was_not_used():
    facts = ("App Runner", "ECS Express Mode", "30 April 2026", "Mumbai", "Google Form", "Tailscale admin console")
    for needle in facts:
        assert needle in FEEDBACK, needle
    assert FEEDBACK.count("builder-reported") >= 8
    assert "The Amazon Devices Builder Tools and the Local Inspector were **not** used" in FEEDBACK


SUMMARY_ENTRIES = ("FL-014", "FL-024", "FL-009", "FL-017", "FL-013", "FL-007", "FL-027")


def test_the_friction_summary_has_the_seven_entries_in_order_with_three_lines_each():
    headings = re.findall(r"(?m)^### (FL-\d{3})", SUMMARY)
    assert tuple(headings) == SUMMARY_ENTRIES
    log = (ROOT / "FRICTION_LOG.md").read_text(encoding="utf-8")
    requests = (ROOT / "FEATURE_REQUESTS.md").read_text(encoding="utf-8")
    for fl in SUMMARY_ENTRIES:
        assert f"### {fl}:" in log, fl
        block = SUMMARY.split(f"### {fl}")[1].split("\n### ")[0].split("\n## ")[0]
        lines = [ln for ln in block.splitlines()[1:] if ln.strip()]
        assert [ln.split(":**")[0] for ln in lines] == ["- **Who is affected", "- **What it cost us", "- **What we ask"]
        for fr in re.findall(r"FR-\d{3}", block):
            assert f"### {fr}:" in requests, fr


def test_the_readme_links_both_new_documents():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "`docs/PRODUCT_FEEDBACK.md`" in readme and "`docs/PRODUCT_FEEDBACK_DEVPOST.md`" in readme
    assert "`docs/FRICTION_SUMMARY.md`" in readme
