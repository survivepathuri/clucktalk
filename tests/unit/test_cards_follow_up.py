"""The follow-up on the cards and the "Demo clock" marker (docs/DESIGN.md §14, §18), checked on the source templates and
the label tables: state as an icon AND a word, English plus Telugu, the sentence shown verbatim (so the card's number
is the spoken number), no new request, and the marker only when the server sends it."""

from __future__ import annotations

import re

import pytest

from clucktalk.config import REPO_ROOT
from clucktalk.server.cards import BRIEFING_LABELS, FARM_STATUS_LABELS, HEALTH_CHECK_LABELS, SALE_PLAN_LABELS

CARDS = REPO_ROOT / "ui" / "cards"
BUILT = REPO_ROOT / "src" / "clucktalk" / "server" / "cards"
NAMES = ("briefing", "farm_status", "health_check", "sale_plan")
LABELS = {
    "briefing": BRIEFING_LABELS,
    "farm_status": FARM_STATUS_LABELS,
    "health_check": HEALTH_CHECK_LABELS,
    "sale_plan": SALE_PLAN_LABELS,
}


def _template(name: str) -> str:
    return (CARDS / f"{name}.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", NAMES)
def test_every_label_a_card_uses_exists(name):
    text = _template(name)
    used = set(re.findall(r"\bL\.(\w+)", text)) | set(re.findall(r'data-l="(\w+)"', text))
    assert not used - LABELS[name].keys(), (name, used - LABELS[name].keys())


def test_the_follow_up_word_is_the_same_pair_on_the_briefing_and_the_farm_status():
    assert BRIEFING_LABELS["follow_up"] == FARM_STATUS_LABELS["follow_up"]
    assert BRIEFING_LABELS["follow_up"].en == "Follow-up" and BRIEFING_LABELS["follow_up"].te.strip()


def test_the_chip_reuses_existing_state_words_instead_of_new_translations():
    # due -> REMINDER, escalated -> ALERT, lapsed -> UNKNOWN: pairs already on the briefing / farm status card
    assert FARM_STATUS_LABELS["level_info"] == BRIEFING_LABELS["level_info"]
    assert (FARM_STATUS_LABELS["level_alert"], FARM_STATUS_LABELS["level_unknown"]) == (
        BRIEFING_LABELS["level_alert"],
        FARM_STATUS_LABELS["level_unknown"],
    )


# -- the farm status chip ---------------------------------------------------------------------------
def test_the_chip_shows_each_state_as_an_icon_and_a_word_never_colour_alone():
    text = _template("farm_status")
    chip = text[text.index("function followUpChip") : text.index("// ---------- views")]
    states = dict(re.findall(r'(due|escalated|lapsed): \{ icon: "(\w+)"', chip))
    assert set(states) == {"due", "escalated", "lapsed"} and len(set(states.values())) == 3
    for icon in states.values():
        assert re.search(rf"^\s*{icon}: '<svg", text, re.M), icon  # the icon exists
    for word in ("level_info", "level_alert", "level_unknown"):
        assert f"L.{word}" in chip
    assert "L.follow_up" in chip and "icon(state.icon)" in chip


def test_the_chip_shows_the_spoken_sentence_verbatim_with_no_arithmetic():
    text = _template("farm_status")
    chip = text[text.index("function followUpChip") : text.index("// ---------- views")]
    assert "f.text_en" in chip and "f.text_te" in chip
    assert "days_ago" not in chip and "due_day" not in chip  # no number is worked out on the card


def test_the_chip_is_on_the_tile_and_on_the_shed_detail_and_names_itself_for_a_screen_reader():
    text = _template("farm_status")
    assert text.count("      followUpChip(h),") == 1  # in the tile, before the least important line
    assert text.count("root.append(followUpChip(h))") == 1  # and in the shed detail view
    assert "h.follow_up.text_en" in text  # the tile's accessible name includes the sentence
    assert 'role: "group"' in text[text.index("function followUpChip") :]


def test_the_chip_shows_nothing_for_a_follow_up_with_nothing_to_say():
    chip = _template("farm_status")
    chip = chip[chip.index("function followUpChip") : chip.index("// ---------- views")]
    assert "!state || !f.text_en" in chip and "return null" in chip


# -- the briefing slide -----------------------------------------------------------------------------
def test_a_briefing_follow_up_item_has_its_own_icon_and_the_word_follow_up():
    text = _template("briefing")
    assert re.search(r'item\.category === "follow_up"[^\n]*icon\("followup"\)[^\n]*bi\(L\.follow_up\)', text)
    assert re.search(r"^\s*followup: '<svg", text, re.M)


def test_the_briefing_slide_shows_the_item_sentence_verbatim():
    text = _template("briefing")
    slide = text[text.index("function slide(") : text.index("function briefingView")]
    assert "item.text_en" in slide and "item.text_te" in slide and "days_ago" not in slide


# -- the demo-clock marker ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", NAMES)
def test_every_card_shows_the_marker_only_when_the_server_sends_it(name):
    text = _template(name)
    badges = text[text.index("function badges(") : text.index("function header(")]
    assert 'lastResult._meta["clucktalk/demo_clock"]' in badges
    assert "if (!m) return demo;" in badges  # off: exactly the old badge, nothing else
    assert "m.label_en" in badges and "m.label_te" in badges  # the words come from the server, not a card label
    assert "data-xm-skip" in badges  # the "+3" is not a farm number the cross-modal check should compare
    assert "badges(sc)" in text[text.index("function header(") :]


@pytest.mark.parametrize("name", NAMES)
def test_the_built_card_has_no_new_external_request(name):
    built = (BUILT / f"{name}.html").read_text(encoding="utf-8")
    assert "badges(sc)" in built
    assert (
        not re.search(r"""(?:src|href)=["']https?:""", built)
        and "fetch(" not in built
        and "XMLHttpRequest" not in built
    )
