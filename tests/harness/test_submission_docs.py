# ruff: noqa: E501  (long document text)
"""Step 54 parts B and C: the explanation documents and the submission text. Text checks only: the tool names equal the
server's, the stated first commit date comes from git, the forbidden words and private details are absent, every path a
document names exists, and every unknown is marked pending or not recorded."""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from clucktalk.server.app import build_mcp_server

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import verify  # noqa: E402

DOCS = {
    name: (ROOT / name).read_text(encoding="utf-8")
    for name in (
        "docs/ARCHITECTURE.md",
        "docs/JUDGES.md",
        "SECURITY.md",
        "docs/INDEPENDENT_REVIEW.md",
        "docs/PRODUCTION_PATH.md",
        "docs/SAFETY_MATRIX.md",
        "docs/RESULTS.md",
        "submission.md",
    )
}
TOOLS = sorted(t.name for t in asyncio.run(build_mcp_server().list_tools()))
ALL_TEXT = "\n".join(DOCS.values())
PLACEHOLDER = "[PILOT NUMBERS: to be filled on <date> from python tasks.py pilot-stats]"
FORBIDDEN = ("production-ready", "production ready", "enterprise-grade", "enterprise grade", "guaranteed", "certified")


def _words(text: str) -> set[str]:
    return set(re.findall(r"`?([a-z]+(?:_[a-z]+)+)`?", text))


def test_the_server_lists_fourteen_tools():
    assert len(TOOLS) == 14


@pytest.mark.parametrize("name", ["docs/ARCHITECTURE.md", "submission.md"])
def test_each_document_that_lists_the_tools_names_exactly_the_servers_tools(name):
    text = DOCS[name]
    listed = {w for w in _words(text) if w in TOOLS}
    assert listed == set(TOOLS), (name, sorted(set(TOOLS) - listed))
    # no tool-looking name that the server does not have, among the verbs the tools start with
    verbs = ("get_", "plan_", "set_", "log_", "start_", "prepare_", "report_")
    stray = {w for w in _words(text) if w.startswith(verbs) and w not in TOOLS}
    assert not stray, stray


def test_the_architecture_has_exactly_two_mermaid_diagrams_and_a_table_under_each():
    text = DOCS["docs/ARCHITECTURE.md"]
    blocks = re.findall(r"```mermaid\n(.*?)```", text, re.S)
    assert len(blocks) == 2 and all(b.lstrip().startswith("flowchart") for b in blocks)
    sections = text.split("```mermaid")[1:]
    for section in sections:
        assert "### What is real and what is simulated" in section.split("```", 1)[1]
    assert "SIMULATED" in blocks[0] and "Funnel" in blocks[1]
    assert "never forwarded" in blocks[1] and "usage numbers are pending" in text


def test_every_path_the_documents_name_exists():
    pattern = re.compile(r"`((?:src|tests|docs|data|scripts|deploy|skills)/[\w./-]+|[A-Z_]+\.md|NOTICE|LICENSE)`")
    missing = []
    for name, text in DOCS.items():
        for ref in set(pattern.findall(text)):
            if not (ROOT / ref).exists():
                missing.append((name, ref))
    assert not missing, missing


def test_the_documents_use_no_forbidden_word_except_to_deny_it():
    hits = [h for name, text in DOCS.items() for h in verify.scan_text(name, text)]
    assert not hits, hits
    denial = re.compile(r"\b(not|no|never|nothing|without)\b|n't")
    for name, text in DOCS.items():
        lowered = text.lower()
        for word in FORBIDDEN:
            for m in re.finditer(re.escape(word), lowered):
                line = lowered[lowered.rfind(chr(10), 0, m.start()) + 1 : lowered.find(chr(10), m.end())]
                assert denial.search(line), (name, word, line)
        assert not re.search(r"real-?time", lowered), name


def test_no_private_path_host_name_token_account_id_or_email_is_in_any_new_document():
    private_dir = "private" + "/"
    for name, text in DOCS.items():
        assert private_dir not in text and "CLAUDE.local" not in text, name
        assert (".ts" + ".net") not in text, name
        assert not re.search(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}\b", text), name
        assert not re.search(r"\b\d{12}\b", text), name
        assert not re.search(r"(AKIA|ASIA)[0-9A-Z]{16}", text), name
        assert not re.search(r"#t=[A-Za-z0-9_-]{8,}", text), name


def test_the_pilot_placeholder_is_used_exactly_and_no_pilot_number_is_invented():
    assert PLACEHOLDER in DOCS["submission.md"] and PLACEHOLDER in DOCS["docs/RESULTS.md"]
    pilot = DOCS["submission.md"].split("## The farmer pilot")[1].split("## Challenges")[0]
    assert not re.search(r"\b\d+ (days|records|alerts|farmers)\b", pilot), pilot
    assert (
        f"A pilot link was shared with one farmer on 7 October 2026; usage numbers are pending {PLACEHOLDER}." in pilot
    )
    assert "Nothing about uptime, speed or reliability has been measured." in pilot
    assert not re.search(r"\b(uses it|used it daily|every day|reliabl[ey] (ran|runs))\b", pilot), pilot


TELUGU_DOCS = ("submission.md", "README.md", "docs/JUDGES.md", "docs/RESULTS.md")


def test_one_telugu_sentence_with_generated_numbers_in_every_judge_facing_document():
    import results  # scripts/results.py; the numbers come from docs/TELUGU_REVIEW.md

    sentence = results.telugu_sentence((ROOT / "docs" / "TELUGU_REVIEW.md").read_text(encoding="utf-8"))
    assert "not recorded" not in sentence
    for name in TELUGU_DOCS:
        text = " ".join((ROOT / name).read_text(encoding="utf-8").split())
        assert sentence in text, name
        assert "first 82" not in text and "until a native speaker approves" not in text, name
        assert "not yet reviewed by a native speaker" not in text, name


def test_the_author_name_is_only_in_the_license_files():
    """The git author's personal name may stand only where a license names its copyright holder."""
    names = subprocess.run(["git", "log", "--format=%an"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    authors = {n for n in names.stdout.splitlines() if n.strip()}
    if names.returncode != 0 or not authors:
        pytest.skip("not a git checkout: no author name to look for")
    found = set()
    for author in authors:
        done = subprocess.run(["git", "grep", "-l", "-F", "-e", author], cwd=ROOT, capture_output=True, text=True)
        found |= set(done.stdout.split())
    assert found <= {"LICENSE", "NOTICE", "skills/clucktalk/LICENSE"}, sorted(found)  # paths only, never the name


def test_the_doing_well_wording_is_scoped_to_demo_mode_and_row_seven_makes_no_fit_claim():
    matrix = DOCS["docs/SAFETY_MATRIX.md"]
    assert "In **pilot mode**, a shed with no alert" in matrix and "In demo mode a shed with no alert" in matrix
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert (
        "In demo mode a shed with no alert is still described as doing well; pilot mode says: no alert from the checks "
        "I can make." in readme
    )
    assert "so it fits his farm by definition" not in matrix


# -- submission.md --------------------------------------------------------------------------------------------
def test_the_taglines_are_three_and_at_most_sixty_characters():
    section = DOCS["submission.md"].split("## Tagline options")[1].split("## Opening sentence")[0]
    lines = re.findall(r"^\d\. (.+)$", section, re.M)
    assert len(lines) == 3 and all(len(s) <= 60 for s in lines), [(s, len(s)) for s in lines]


def test_the_opening_sentence_names_the_track_technology():
    section = DOCS["submission.md"].split("## Opening sentence")[1].split("## Inspiration")[0]
    for needle in (
        "self-hosted MCP server",
        "Streamable HTTP",
        "2025-11-25",
        "Alexa+",
        "simulated Alexa+ web experience",
    ):
        assert needle in section, needle


def test_the_inspiration_is_three_sentences_with_no_identity():
    section = DOCS["submission.md"].split("## Inspiration")[1].split("## What it does")[0].strip()
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", section) if s]
    assert len(sentences) == 3, sentences


def test_the_first_commit_date_in_the_submission_is_the_one_git_reports():
    first = subprocess.run(
        ["git", "log", "--reverse", "--format=%ad", "--date=short"], cwd=ROOT, capture_output=True, text=True
    ).stdout.split()[0]
    section = DOCS["submission.md"].split("## What changed during the hackathon")[1].split("## Built with")[0]
    assert f"The first commit is dated {first}" in section
    assert f"The first commit is dated {first}" in DOCS["docs/RESULTS.md"]


def test_the_submission_has_every_devpost_field_in_order():
    headings = re.findall(r"^## (.+)$", DOCS["submission.md"], re.M)
    assert headings == [
        "Project name",
        "Tagline options (60 characters or fewer)",
        "Opening sentence",
        "Inspiration",
        "What it does",
        "How it uses the track technology",
        "How we built it",
        "How we trust it",
        "The farmer pilot",
        "Challenges",
        "What changed during the hackathon",
        "Built with",
        "Amazon requirements",
    ]


def test_the_amazon_requirements_table_has_an_evidence_or_pending_for_every_row():
    table = DOCS["submission.md"].split("## Amazon requirements")[1]
    rows = [
        ln for ln in table.splitlines() if ln.startswith("|") and not ln.startswith("|---") and "Requirement" not in ln
    ]
    assert len(rows) >= 7
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        assert len(cells) == 3 and all(cells), row
        assert "pending" in row.lower() or "`" in cells[2] or "not claimed" in row.lower(), row
    for placeholder in ("[VIDEO URL: pending", "[CONTRIBUTION URL: pending]", "[SECOND REPOSITORY URL: pending]"):
        assert placeholder in table, placeholder


def test_the_submission_says_what_was_live_on_aws_and_what_was_mocked():
    section = DOCS["submission.md"].split("## How we built it")[1].split("## How we trust it")[0]
    for needle in (
        "Amazon Nova 2 Lite",
        "handful of one-off calls",
        "Mocked:",
        "not** verified end to end",
        "OpenSearch Serverless",
    ):
        assert needle in section, needle
    assert "Nothing was deployed to AWS" in section


# -- security, production path, judges ---------------------------------------------------------------------
def test_security_has_a_threat_table_the_reviews_what_is_not_protected_and_a_placeholder_contact():
    text = DOCS["SECURITY.md"]
    for heading in (
        "## Threat model",
        "## What the independent reviews found",
        "## What is not protected",
        "## Reporting an issue",
    ):
        assert heading in text, heading
    assert "[SECURITY CONTACT: to be added before the repository is made public]" in text
    for needle in ("personal Windows PC", "no OAuth", "No human security audit", "policies were not published"):
        assert needle.lower() in text.lower(), needle


def test_every_item_of_the_production_path_is_marked_not_done():
    rows = [ln for ln in DOCS["docs/PRODUCTION_PATH.md"].splitlines() if re.match(r"^\| \d+ \|", ln)]
    assert len(rows) >= 14
    assert all(ln.rstrip().endswith("**Not done** |") for ln in rows)
    text = DOCS["docs/PRODUCTION_PATH.md"].lower()
    for item in (
        "oauth 2.1",
        "remote https",
        "self-service",
        "growth target",
        "selling plan",
        "native telugu",
        "per-farmer accounts",
        "privacy and data-law",
    ):
        assert item in text, item


def test_the_judges_guide_has_the_three_commands_and_links_the_claims_table():
    text = DOCS["docs/JUDGES.md"]
    for cmd in ("python tasks.py setup", "python tasks.py serve", "python tasks.py verify"):
        assert cmd in text
    assert "What is verified, unverified and simulated" in text and "src/clucktalk/simulator/" in text
    assert "src/clucktalk/server/tools/" in text and "Known limits" in text


def test_the_independent_review_page_lists_the_rounds_of_the_data_file():
    data = json.loads((ROOT / "data" / "results" / "review_rounds.json").read_text(encoding="utf-8"))
    table = DOCS["docs/INDEPENDENT_REVIEW.md"]
    assert len(re.findall(r"^\| \d+ \|", table, re.M)) == len(data["rounds"])
    assert "not human" in table.lower() or "AI agent" in table
