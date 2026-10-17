"""The Agent Skill in skills/clucktalk/ (docs and tests only; it changes no server behaviour).

It teaches an agent how to operate CluckTalk. These tests keep it honest: it names exactly the tools the server lists,
its example phrases route where it says they do (through the Simulator's own intent rules), it breaks none of the
wording rules, and it carries no private path or secret."""

from __future__ import annotations

import asyncio
import re

import pytest

from clucktalk.config import REPO_ROOT
from clucktalk.server.app import build_mcp_server
from clucktalk.simulator.intents import match, normalise, yes_no

SKILL_DIR = REPO_ROOT / "skills" / "clucktalk"
FILES = {
    "SKILL.md": SKILL_DIR / "SKILL.md",
    "tool-routing": SKILL_DIR / "references" / "tool-routing.md",
    "safety-rules": SKILL_DIR / "references" / "safety-rules.md",
    "voice-and-cards": SKILL_DIR / "references" / "voice-and-cards.md",
    "LICENSE": SKILL_DIR / "LICENSE",
}
TEXT = {name: path.read_text(encoding="utf-8") for name, path in FILES.items()}
MAX_LINES = 500

SERVER_TOOLS = frozenset(t.name for t in asyncio.run(build_mcp_server().list_tools()))
# A tool name is a snake_case word that starts with one of the verbs the server's tools start with.
TOOL_SHAPED = re.compile(
    r"\b(?:get|plan|start|set|log|prepare|report|send|place|create|update|delete|cancel|order)_[a-z_]+\b"
)


def _tools_in(text: str) -> set[str]:
    return set(TOOL_SHAPED.findall(text))


# -- 1. tools equal tools/list ---------------------------------------------------------------------------
def test_the_server_lists_the_tools_this_skill_was_written_for():
    assert len(SERVER_TOOLS) == 14  # a new or removed tool fails here first: update the skill, then this number


@pytest.mark.parametrize("name", ["SKILL.md", "tool-routing"])
def test_the_skill_and_its_routing_table_name_every_tool_and_no_other(name):
    named = _tools_in(TEXT[name])
    assert named == SERVER_TOOLS, {"missing": SERVER_TOOLS - named, "stale": named - SERVER_TOOLS}


@pytest.mark.parametrize("name", ["safety-rules", "voice-and-cards", "LICENSE"])
def test_the_other_files_name_no_tool_the_server_does_not_have(name):
    assert _tools_in(TEXT[name]) <= SERVER_TOOLS, _tools_in(TEXT[name]) - SERVER_TOOLS


# -- 2. frontmatter and size ----------------------------------------------------------------------------
def _frontmatter(text: str) -> dict[str, str]:
    lines = text.split("\n")
    assert lines[0] == "---", "SKILL.md must start with YAML frontmatter"
    end = lines.index("---", 1)
    fields = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        assert sep and re.fullmatch(r"[a-z][a-z-]*", key), f"unexpected frontmatter line: {line!r}"
        fields[key] = value.strip().strip('"')
    return fields


def test_the_frontmatter_has_a_valid_name_and_a_useful_description():
    fm = _frontmatter(TEXT["SKILL.md"])
    assert set(fm) <= {"name", "description", "license", "compatibility", "metadata"}
    assert fm["name"] == "clucktalk" == SKILL_DIR.name
    assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", fm["name"]) and len(fm["name"]) <= 64
    description = fm["description"]
    assert 100 <= len(description) <= 1024
    assert "when" in description.lower()  # says when to use it, not only what it is


@pytest.mark.parametrize("name", ["SKILL.md", "tool-routing", "safety-rules", "voice-and-cards"])
def test_every_file_stays_under_the_line_limit(name):
    assert len(TEXT[name].split("\n")) < MAX_LINES


def test_skill_md_points_to_each_reference_file_that_exists():
    for ref in ("tool-routing", "safety-rules", "voice-and-cards"):
        assert f"references/{ref}.md" in TEXT["SKILL.md"], ref
        assert FILES[ref].is_file()


def test_the_skill_folder_has_an_mit_license():
    assert TEXT["LICENSE"].startswith("MIT License")
    assert "Permission is hereby granted, free of charge" in TEXT["LICENSE"]


def test_the_skill_says_plainly_it_teaches_operation_and_does_not_claim_alexa_plus_runs_it():
    head = "\n".join(TEXT["SKILL.md"].split("\n")[:40])
    assert "does not claim" in head and "Alexa+" in head
    assert "operate CluckTalk" in head
    for text in TEXT.values():  # nowhere may it say the reverse
        assert not re.search(r"Alexa\+\s+(?:already\s+)?(?:runs|hosts|ships|supports|is running)\s+CluckTalk", text)


# -- 3. the wording rules ---------------------------------------------------------------------------------
MEDICINES = re.compile(
    r"\b(?:enrofloxacin|tylosin|doxycycline|oxytetracycline|amoxicillin|colistin|ivermectin|paracetamol|"
    r"gentamicin|ciprofloxacin|norfloxacin|furazolidone|sulfa\w*|tetracycline|penicillin|erythromycin|"
    r"neomycin|levamisole|albendazole|piperazine|ampicillin|lincomycin|spectinomycin|florfenicol|"
    r"vitamin\s+[a-ek]|electrolytes?|oral rehydration)\b",
    re.IGNORECASE,
)
DOSE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|ml|mcg|µg|cc|iu|grams? per|g/l|ppm)\b", re.IGNORECASE)
REASSURANCE = re.compile(
    r"\b(?:fine|healthy|recovered|recovering|all good|no need|nothing to worry|don't worry|do not worry|normal now"
    r"|safe now|out of danger|no problem|good news|improving)\b",
    re.IGNORECASE,
)
SAMPLE_OR_LAB = re.compile(r"\b(?:labs?|laborator\w*|samples?|swabs?|test results?)\b", re.IGNORECASE)
REARING_ADVICE = re.compile(
    r"\b(?:isolate|separate|disinfect|cull|ventilate|improve ventilation|increase ventilation|give (?:more )?water"
    r"|change the litter|lower the temperature|raise the temperature)\b",
    re.IGNORECASE,
)
PROMISE = re.compile(
    r"\b(?:i'?ll|i will|we'?ll|we will|it will|clucktalk will|will)\s+(?:remind|notify|call|message|text|contact|alert|"
    r"ping|follow up)\b|\byou(?:'ll| will)\s+(?:get|receive|hear)\s+(?:a\s+)?(?:reminder|notification|call|message)\b",
    re.IGNORECASE,
)
RULES = {
    "medicine name": MEDICINES,
    "dose": DOSE,
    "reassurance": REASSURANCE,
    "sample or lab": SAMPLE_OR_LAB,
    "rearing advice": REARING_ADVICE,
    "promise of a reminder or proactive contact": PROMISE,
}


@pytest.mark.parametrize("name", list(FILES))
@pytest.mark.parametrize("rule", list(RULES))
def test_the_wording_rules_hold_over_every_skill_file(name, rule):
    hits = [m.group(0) for m in RULES[rule].finditer(TEXT[name])]
    assert not hits, f"{name}: {rule}: {hits}"


def test_the_wording_scan_itself_catches_what_it_should():
    """Guards the scan: if a rule stopped matching, the test above would pass for the wrong reason."""
    bad = {
        "medicine name": "give enrofloxacin",
        "dose": "5 ml per bird",
        "reassurance": "the birds are fine, don't worry",
        "sample or lab": "send a sample to the lab",
        "rearing advice": "isolate the sick birds and improve ventilation",
        "promise of a reminder or proactive contact": "I will remind you tomorrow",
    }
    for rule, sentence in bad.items():
        assert RULES[rule].search(sentence), rule


# -- 4. nothing private, nothing secret -------------------------------------------------------------------
@pytest.mark.parametrize("name", list(FILES))
def test_no_private_path_and_no_secret_in_any_skill_file(name):
    text = TEXT[name]
    assert not re.search(r"private[/\\]|CLAUDE\.local|PRIVATE_RULES|PROGRESS\.md|WEEK\d_PLAN", text), name
    assert not re.search(r"\bAKIA[0-9A-Z]{16}\b|aws_secret_access_key|-----BEGIN [A-Z ]*PRIVATE KEY", text), name
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text), f"{name}: an email address"
    assert not re.search(r"\b\d{12}\b", text), f"{name}: a 12-digit number (an AWS account id?)"
    assert not re.search(r"(?i)\b(?:token|secret|password)\s*[:=]\s*\S{8,}", text), name


# -- 5. every example phrase routes where the table says it does ---------------------------------------------
ROW = re.compile(r'^\|\s*"(?P<phrase>[^"]+)"\s*\|\s*(?P<what>[^|]+?)\s*\|\s*(?P<args>[^|]*?)\s*\|\s*$', re.MULTILINE)
ARG = re.compile(r"`(\w+)=([^`]+)`")
ROUTES = [(m["phrase"], m["what"], m["args"]) for m in ROW.finditer(TEXT["tool-routing"])]
TOOL_ROUTES = [r for r in ROUTES if not r[1].startswith("answer:")]
ANSWER_ROUTES = [r for r in ROUTES if r[1].startswith("answer:")]
# The host rules in the Simulator cover every tool except this one (it needs four numbers the farmer reads out).
NOT_ROUTED_BY_THE_SIMULATOR = {"set_contract_terms"}


def test_there_are_example_phrases_for_every_tool_the_simulator_routes():
    routed = {re.sub(r"[`\s]", "", what) for _, what, _ in TOOL_ROUTES}
    assert routed == SERVER_TOOLS - NOT_ROUTED_BY_THE_SIMULATOR, routed ^ (SERVER_TOOLS - NOT_ROUTED_BY_THE_SIMULATOR)
    assert len(TOOL_ROUTES) >= 25 and len(ANSWER_ROUTES) >= 4


@pytest.mark.parametrize(("phrase", "what", "args"), TOOL_ROUTES)
def test_each_example_phrase_routes_to_the_stated_tool_with_the_stated_arguments(phrase, what, args):
    stated = what.strip("` ")
    intent = match(phrase)
    assert intent is not None, f"the Simulator rules do not route {phrase!r}"
    assert intent.tool == stated, f"{phrase!r} routes to {intent.tool}, the skill says {stated}"
    for key, value in ARG.findall(args):
        actual = intent.arguments.get(key)
        expected = normalise(value) if key == "house" else value.lower()  # "shed one" is sent as "shed 1"
        assert str(actual).lower() == expected, f"{phrase!r}: {key}={actual!r}, the skill says {value}"


@pytest.mark.parametrize(("phrase", "what", "args"), ANSWER_ROUTES)
def test_each_answer_word_is_the_yes_or_no_the_table_says(phrase, what, args):
    assert yes_no(phrase) == what.removeprefix("answer:").strip(), phrase
    assert match(phrase) is None  # on its own it is no tool call: it only answers a pending read-back


# -- the README and VERSIONS changes that came with the skill ----------------------------------------------------
README = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
VERSIONS = (REPO_ROOT / "docs" / "VERSIONS.md").read_text(encoding="utf-8")


def test_the_readme_gives_install_steps_for_the_four_agents_and_marks_what_is_unverified():
    section = README[README.index("Agent Skill") :]
    for path in (".claude/skills/", ".kiro/skills/", ".cursor/skills/", ".github/skills/"):
        assert path in section, path
    assert section.lower().count("unverified") >= 2
    assert "does not claim" in section and "Alexa+" in section


def test_strands_and_agentcore_are_described_as_available_not_used():
    rows = [line for line in VERSIONS.split("\n") if line.startswith(("| `strands-agents`", "| `bedrock-agentcore`"))]
    assert len(rows) == 2
    for row in rows:
        assert "available, not used by this project" in row, row
        assert "| verified |" not in row, row
