"""Step 56: docs/PRODUCT_FEEDBACK.md, its paste-ready copy docs/PRODUCT_FEEDBACK_DEVPOST.md and
docs/FRICTION_SUMMARY.md.
Text checks only: every tool section answers the five questions, every builder verdict is a placeholder that the
questions list collects, each paste block is under 110 words, the AWS live-and-mocked statement agrees with
submission.md, and the friction summary names the entries and feature requests that exist."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FEEDBACK = (ROOT / "docs" / "PRODUCT_FEEDBACK.md").read_text(encoding="utf-8")
DEVPOST = (ROOT / "docs" / "PRODUCT_FEEDBACK_DEVPOST.md").read_text(encoding="utf-8")
SUMMARY = (ROOT / "docs" / "FRICTION_SUMMARY.md").read_text(encoding="utf-8")
PLACEHOLDER = re.compile(r"\[BUILDER TO CONFIRM: ([^\]]+)\]")
FIELDS = ("**Used for:**", "**What worked well:**", "**What needs work:**", "**Onboarding:**", "**Build again:**")


def _tool_sections() -> list[tuple[str, str]]:
    """(heading, body) for every numbered tool section and every tool under section 11."""
    out = []
    for block in re.split(r"(?m)^## (?=\d+\. )", FEEDBACK)[1:]:
        heading, _, body = block.partition("\n")
        subs = re.split(r"(?m)^### ", body)
        if len(subs) > 1:
            out += [tuple(s.partition("\n")[::2]) for s in subs[1:]]
        else:
            out.append((heading, body.split("\n## ")[0]))
    return out


SECTIONS = _tool_sections()


def test_the_tools_are_in_the_requested_order():
    headings = [h for h, _ in SECTIONS]
    expected_starts = (
        "1. Amazon Bedrock",
        "2. AWS CLI",
        "3. AWS Lightsail, AWS App Runner",
        "4. Alexa+ MCP documentation",
        "5. The simulated Alexa+ path",
        "6. MCP Python SDK",
        "7. MCP Apps",
        "8. MCP Inspector",
        "9. Claude Code",
        "10. The Agent Skills format",
        "Hypothesis",
        "Tailscale Funnel",
        "GitHub Actions",
        "12. Other libraries",
    )
    assert len(headings) == len(expected_starts)
    for heading, start in zip(headings, expected_starts, strict=True):
        assert heading.startswith(start), (heading, start)


@pytest.mark.parametrize(("heading", "body"), SECTIONS, ids=[h[:30] for h, _ in SECTIONS])
def test_every_tool_section_answers_the_five_questions_in_order(heading, body):
    positions = [body.find(f) for f in FIELDS]
    assert all(p >= 0 for p in positions), (heading, [f for f, p in zip(FIELDS, positions, strict=True) if p < 0])
    assert positions == sorted(positions), heading
    again = body.split("**Build again:**")[1].strip().splitlines()[0]
    assert PLACEHOLDER.fullmatch(again.strip()), (heading, again)  # a verdict is never written for the builder


def test_every_placeholder_is_in_the_numbered_questions_list_once_and_in_order():
    asked = PLACEHOLDER.findall(FEEDBACK)
    listed = re.findall(r"(?m)^(\d+)\. (.+)$", DEVPOST.split("## QUESTIONS FOR THE BUILDER")[1])
    assert [int(n) for n, _ in listed] == list(range(1, len(asked) + 1))
    assert [q for _, q in listed] == asked
    in_blocks = PLACEHOLDER.findall(DEVPOST.split("## QUESTIONS FOR THE BUILDER")[0])
    assert set(in_blocks) == set(asked), set(asked) ^ set(in_blocks)
    assert "hours" in " ".join(asked)  # the time lost on 7 October is asked, never guessed


def test_each_paste_block_is_under_110_words():
    body = DEVPOST.split("## QUESTIONS FOR THE BUILDER")[0]
    blocks = re.split(r"(?m)^## ", body)[1:]
    assert len(blocks) >= 14
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
