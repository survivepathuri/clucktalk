"""Commit A (appearance only): the pilot page's look is set in its CSS and its words come from the i18n.

These checks read the files. The page's own logic is in test_pilot_page_behaviour.py; layout and fonts are checked by
screenshots, not here."""

from __future__ import annotations

import re
from pathlib import Path

from clucktalk.i18n.pilot import PILOT_UI
from clucktalk.server.cards import FARM_STATUS_LABELS

STATIC = Path(__file__).resolve().parents[2] / "src" / "clucktalk" / "simulator" / "static"
LATIN = re.compile("[A-Za-z]")
NEW_KEYS = ("alert", "deaths_today", "vet_today", "warn_tag", "placeholder", "send", "say_suffix", "tap_suffix")


def css() -> str:
    return (STATIC / "pilot.css").read_text(encoding="utf-8")


def html() -> str:
    return (STATIC / "pilot.html").read_text(encoding="utf-8")


def rule(selector: str) -> str:
    """The declarations of the first CSS rule whose selector list contains ``selector`` exactly."""
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css(), flags=re.S)):
        if selector in [s.strip() for s in sel.split(",")]:
            return body
    raise AssertionError(f"no CSS rule for {selector}")


def test_the_page_loads_the_new_words_from_the_i18n_and_every_one_is_telugu_with_no_stray_english():
    for key in NEW_KEYS:
        assert key in PILOT_UI, key
        t = PILOT_UI[key]
        assert t.te.strip() and t.en.strip()
        assert not LATIN.search(t.te), f"{key}: Latin letters in the Telugu {t.te!r}"


def test_the_alert_word_and_the_deaths_label_are_the_cards_own_wording():
    assert PILOT_UI["alert"] == FARM_STATUS_LABELS["level_alert"]
    assert PILOT_UI["deaths_today"] == FARM_STATUS_LABELS["deaths_today"]


def test_the_vet_line_is_the_phrase_of_the_servers_own_rule_sentence():
    assert PILOT_UI["vet_today"].te in "ఈరోజే కోళ్లను డాక్టర్ దగ్గరికి తీసుకెళ్లండి; తదుపరి సందర్శన వరకు ఆగకండి."


def test_the_alert_bar_is_red_big_and_has_focus_free_text_not_only_a_colour():
    body = rule(".alertbar")
    assert "var(--no)" in body and "border" in body
    assert float(re.search(r"font-size:\s*([\d.]+)rem", rule(".alertbar .big")).group(1)) >= 1.6  # shed and deaths
    assert rule(".alertbar .icon")  # the warning sign is its own element: shape and word, not only colour


def test_the_sell_price_is_big_and_the_rule_line_is_small_and_grey():
    assert float(re.search(r"font-size:\s*([\d.]+)rem", rule(".price")).group(1)) >= 2
    small = rule(".rule")
    assert "var(--muted)" in small and float(re.search(r"font-size:\s*([\d.]+)rem", small).group(1)) <= 0.9


def test_bubbles_are_tinted_bot_answers_have_a_left_accent_and_a_warning_carries_its_word():
    assert "border-left" in rule(".bubble") and "var(--accent)" in rule(".bubble")
    assert "background" in rule(".bubble.you")
    tag = rule(".bubble[data-tag]::before")
    assert "attr(data-tag)" in tag  # the word comes from the i18n through the attribute, not from the CSS


def test_every_button_and_the_input_show_a_focus_ring():
    focus = css()
    assert re.search(r"button:focus-visible", focus) and re.search(r"input:focus-visible", focus)
    assert "outline" in rule("button:focus-visible")


def test_the_badge_shows_the_telugu_label_on_the_page_and_keeps_the_english_and_the_truth():
    page = html()
    badge = re.search(r'<span class="badge" id="badge"[^>]*>(.*?)</span>\s*</header>', page, re.S)
    assert badge, "the badge element moved"
    inner = badge.group(1)
    assert "@BADGE_TE@" in inner and "@BADGE_EN@" in inner  # both visible in the element, not only a title
    assert 'lang="te"' in inner


def test_there_is_no_strip_with_the_notice_text_under_the_header_and_the_send_button_has_an_id():
    page = html()
    assert 'id="notice"' not in page and "aria-labelledby" not in page
    assert 'id="send"' in page
