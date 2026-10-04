"""Step 49 part B: ``python tasks.py readiness`` is our own self-check of the documented Alexa+ requirements that can be
checked locally. It is not Amazon's tool, never uses the words CERTIFIED, CONDITIONAL or NOT_CERTIFIED, prints MET, NOT
MET or NOT CHECKABLE LOCALLY per requirement with its source page, and ends with the one summary line."""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import readiness  # noqa: E402  (scripts/readiness.py)

import tasks  # noqa: E402

FORBIDDEN = re.compile(r"NOT_CERTIFIED|CERTIFIED|CONDITIONAL", re.I)
SUMMARY = re.compile(
    r"^\d+ of \d+ locally checkable requirements met; \d+ not checkable locally; this is not an Amazon verdict$", re.M
)


def req(status):
    return readiness.Requirement("k", "text", status, "detail", "source")


def test_the_summary_line_has_the_documented_shape_and_counts():
    reqs = [req("MET"), req("MET"), req("NOT MET"), req("NOT CHECKABLE LOCALLY"), req("NOT CHECKABLE LOCALLY")]
    assert readiness.summary_line(reqs) == (
        "2 of 3 locally checkable requirements met; 2 not checkable locally; this is not an Amazon verdict"
    )


def test_the_list_shows_status_detail_and_source_for_each_requirement():
    out = readiness.render_list([req("NOT CHECKABLE LOCALLY")])
    assert "[NOT CHECKABLE LOCALLY] text" in out and "seen:   detail" in out and "source: source" in out


def test_overlap_is_highest_for_the_two_most_alike_descriptions():
    score, pair = readiness.max_overlap(
        {"a": "feed plan for the week", "b": "feed plan for the week ahead", "c": "vet hand off message"}
    )
    assert pair == ("a", "b") and 0.7 < score < 1


def test_a_real_run_prints_every_requirement_the_summary_and_the_disclaimer(capsys, tmp_path, monkeypatch):
    doc = ROOT / "docs" / "ALEXA_READINESS.md"
    before = hashlib.sha256(doc.read_bytes()).hexdigest()
    assert readiness.main([], rounds=2) == 0
    out = capsys.readouterr().out
    assert not FORBIDDEN.search(out)
    assert "not Amazon's tool" in out and "FL-024" in out
    assert out.count("[MET]") + out.count("[NOT MET]") == 8 and out.count("[NOT CHECKABLE LOCALLY]") == 4
    for item in (
        "OAuth 2.1 with PKCE",
        "Protected Resource Metadata",
        "remote HTTPS URL",
        "Security and data policies",
    ):
        assert "[NOT CHECKABLE LOCALLY] " in out and item in out
    assert out.count("    source: ") == 12
    assert SUMMARY.search(out) and "8 of 8 locally checkable requirements met; 4 not checkable" in out
    assert hashlib.sha256(doc.read_bytes()).hexdigest() == before  # without --write-doc the doc is not touched


def test_a_draft_that_breaks_a_limit_is_reported_not_met(capsys, tmp_path, monkeypatch):
    import json

    data = json.loads((ROOT / "docs" / "addon-package" / "addon.json").read_text(encoding="utf-8"))
    data["storeListing"]["locales"]["en-US"]["name"]["value"] = "x" * 31
    bad = tmp_path / "addon.json"
    bad.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(readiness, "ADDON_DRAFT", bad)
    assert readiness.main([], rounds=1) == 0
    out = capsys.readouterr().out
    assert "[NOT MET] The draft add-on listing" in out and "name.value is 31 characters" in out
    assert "7 of 8 locally checkable requirements met" in out


def test_a_missing_screen_declaration_is_reported_not_met(capsys, monkeypatch):
    real = readiness.Path.read_text

    def fake(self, *a, **k):
        text = real(self, *a, **k)
        return text.replace("Screen size classes", "Screens") if self.name == "DESIGN.md" else text

    monkeypatch.setattr(readiness.Path, "read_text", fake)
    readiness.main([], rounds=1)
    assert "[NOT MET] The two screen size classes" in capsys.readouterr().out


def test_write_doc_writes_the_generated_document(tmp_path, monkeypatch):
    target = tmp_path / "READY.md"
    monkeypatch.setattr(readiness, "DOC", target)
    monkeypatch.setattr(readiness.Path, "relative_to", lambda self, other: self, raising=False)
    assert readiness.main(["--write-doc"], rounds=1) == 0
    text = target.read_text(encoding="utf-8")
    assert "\r" not in text and not FORBIDDEN.search(text)
    assert "not Amazon's tool and not an Amazon verdict" in text and re.search(SUMMARY.pattern.strip("^$"), text)


def test_the_committed_document_says_what_is_roadmap_and_what_is_not_shown():
    text = (ROOT / "docs" / "ALEXA_READINESS.md").read_text(encoding="utf-8")
    assert not FORBIDDEN.search(text)
    assert "roadmap" in text and "refreshes only on deploy" in text and "placeholder" in text
    assert "Nothing here ran on an Alexa+ device" in text
    assert text.count("NOT CHECKABLE LOCALLY") >= 4 and "| MET |" in text


def test_other_arguments_are_refused_and_tasks_has_the_command(monkeypatch):
    assert readiness.main(["--force"]) == 2
    assert tasks.COMMANDS["readiness"] is tasks.readiness and tasks.readiness(["--force"]) == 2


def test_a_latency_over_the_budget_is_reported_not_met(capsys, monkeypatch):
    monkeypatch.setattr(readiness.replay, "BUDGET_MS", 0.0001)
    readiness.main([], rounds=1)
    assert "[NOT MET] Server-side latency under" in capsys.readouterr().out


def test_overlapping_descriptions_are_reported_not_met(capsys, monkeypatch):
    monkeypatch.setattr(readiness, "OVERLAP_LIMIT", 0.0)
    readiness.main([], rounds=1)
    assert "[NOT MET] No two tool descriptions overlap" in capsys.readouterr().out


def test_an_error_without_a_required_field_is_reported_not_met(capsys, monkeypatch):
    monkeypatch.setattr(readiness, "ERROR_FIELDS", (*readiness.ERROR_FIELDS, "no_such_field"))
    readiness.main([], rounds=1)
    out = capsys.readouterr().out
    assert "[NOT MET] Error responses carry a message and a next step" in out and "failed: get_farm_status" in out


def test_the_latency_is_stated_as_a_server_time_not_amazons_round_trip():
    sentence = (
        "Our p50 and p95 are server times on localhost in mock mode, and Amazon's 500 ms requirement is a round trip "
        "that includes the network, so we do not claim to meet it end to end."
    )
    readme = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    assert readme.count(sentence) >= 2  # in the replay paragraph and in the known limitations
    doc = " ".join((ROOT / "docs" / "ALEXA_READINESS.md").read_text(encoding="utf-8").split())
    assert sentence.lower() in doc.lower()


def test_the_sources_page_records_the_quickstart_and_the_local_inspector_pages():
    sources = (ROOT / "docs" / "SOURCES.md").read_text(encoding="utf-8")
    assert "mcp-toolkit-quickstart.html" in sources and "Jul 10, 2026" in sources
    assert "mcp-toolkit-local-inspector.html" in sources and "Aug 3, 2026" in sources
    assert "2025-06-18" in sources and "10 inches and below" in sources and "500 ms round-trip" in sources
    doc = (ROOT / "docs" / "ALEXA_READINESS.md").read_text(encoding="utf-8")
    assert "mcp-toolkit-quickstart.html" in doc and "mcp-toolkit-local-inspector.html" in doc
