"""The Simulator's first screen: five one-tap starter questions (Telugu with its English gloss) and the judge view.

Every chip comes from an existing, approved catalog pair, and each one is run here against the live demo host: a chip
that the demo host does not answer with the expected tool would fail this file. The judge view and the page text are
checked from the files the browser loads (the browser half is shown in docs/evidence/2026-10-18_judge_view/)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import httpx2
import pytest

from clucktalk.simulator.app import STATIC
from clucktalk.simulator.starters import REPLIES, STARTERS
from tests.contract.test_simulator import Sim, _run, sim  # noqa: F401  (the fixture)

ROOT = Path(__file__).resolve().parents[2]
APPROVALS = json.loads((ROOT / "data" / "i18n" / "telugu_approvals.json").read_text(encoding="utf-8"))["approvals"]
EXPECTED_TOOL = {
    "How is the farm?": "get_farm_status",
    "When to sell?": "plan_sale",
    "Health check": "start_health_check",
    "Today's briefing": "get_daily_briefing",
    "Help": "get_help",
}


def test_there_are_five_starters_and_two_replies():
    assert len(STARTERS) == 5
    assert [r.text.en for r in REPLIES] == ["Yes", "No"]


@pytest.mark.parametrize("item", STARTERS + REPLIES, ids=lambda i: i.text.en)
def test_each_chip_is_an_approved_catalog_pair(item):
    assert any(a["en"] == item.text.en and a["te"] == item.text.te for a in APPROVALS)


def test_state_offers_the_chips_with_both_languages(sim: Sim):  # noqa: F811
    state = httpx2.get(sim.base + "/api/state", timeout=10).json()
    assert [(c["te"], c["en"]) for c in state["starters"]] == [(s.text.te, s.text.en) for s in STARTERS]
    assert [c["say"] for c in state["replies"]] == ["yes", "no"]


@pytest.mark.parametrize("item", STARTERS, ids=lambda i: i.text.en)
def test_each_starter_is_answered_by_the_expected_tool_with_its_telugu(sim: Sim, item):  # noqa: F811
    out = sim.turn(item.say)
    assert out["kind"] == "tool" and not out["is_error"]
    assert out["intent"]["tool"] == EXPECTED_TOOL[item.text.en]
    sc = out["result"]["structuredContent"]
    assert sc["text_te"] and out["speech"]  # a Telugu answer and the English side it is shown over


def test_the_yes_no_taps_are_offered_exactly_when_the_host_takes_the_vet_offer_up(sim: Sim):  # noqa: F811
    health = next(s for s in STARTERS if s.text.en == "Health check")
    for _ in range(40):  # the first reply to a new check says "While I check" and carries no offer sentence
        first = sim.turn(health.say)
        sc = first["result"]["structuredContent"]
        assert bool(first.get("vet_offer")) == (
            sc["handoff_offered"] is True and "Shall I send a summary" in sc["text_en"]
        )
        if first.get("vet_offer"):
            break
        assert sim.turn(REPLIES[0].say)["kind"] == "fallback"  # a yes tap here would find nothing waiting
        time.sleep(0.25)
    else:
        pytest.fail("the health check never produced the vet offer")
    yes = sim.turn(REPLIES[0].say)
    assert yes["intent"]["tool"] == "prepare_vet_handoff" and yes["awaiting_answer"] is True
    no = sim.turn(REPLIES[1].say)  # a no keeps the summary unsent
    assert no["intent"]["tool"] == "prepare_vet_handoff"


def test_the_page_has_the_banner_and_no_device_brand_names():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "Simulated Alexa+ screen. The backend is a real MCP server (Streamable HTTP)." in html
    for name in ("index.html", "app.js", "style.css"):
        text = (STATIC / name).read_text(encoding="utf-8")
        assert not re.search(r"Echo\s*(Show|Dot)", text), name
    assert "Smart display" in html and "Speaker" in html


def test_the_judge_view_is_on_by_default_and_hides_only_the_answer_gloss():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert re.search(r'id="judge"[^>]*aria-pressed="true"', html)
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "judge: true" in js and "judge-off" in js
    # no Telugu, no gloss: sayAnswer falls back to the plain English line, and the native view hides its Telugu line
    assert re.search(r"if \(!te\) return say\(", js)
    assert '$("native-te").hidden = !te' in js
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    hide = r"body\.judge-off \.transcript \.gloss,\s*body\.judge-off \.native-en\.gloss\s*\{\s*display:\s*none"
    assert re.search(hide, css)
    assert "body.judge-off .gloss" not in css and "body.judge-off .chip" not in css  # the chips keep their English


def test_telugu_text_has_a_system_font_stack_and_nothing_is_downloaded():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    stack = re.search(r"--te-font:\s*([^;]+);", css).group(1)
    assert "Noto Sans Telugu" in stack and "Nirmala UI" in stack and stack.rstrip().endswith("sans-serif")
    assert "@import" not in css and "@font-face" not in css and "url(" not in css
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert not re.search(r'(?:href|src)="https?://', html)
    assert float(re.search(r"\.native-te\s*\{[^}]*font-size:\s*(\d+)px", css).group(1)) >= 28
