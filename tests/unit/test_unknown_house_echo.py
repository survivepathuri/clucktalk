"""Review finding L2 (Step 47C, option b): an unknown house name is never echoed raw into speech. It is cleaned
(letters and digits of any script, single spaces; control characters, emoji and markup removed) and shortened to 24
characters before the existing sentence says it. Normal names are unchanged."""

from __future__ import annotations

import pytest

from clucktalk.domain.errors import SPOKEN_NAME_LIMIT, UnknownHouse, spoken_name

LABELS = (["House 1", "House 2"], ["షెడ్ 1", "షెడ్ 2"])


def _err(ref: str) -> UnknownHouse:
    return UnknownHouse(ref, *LABELS)


@pytest.mark.parametrize("name", ["shed nine", "House 9", "kotam 7", "shed two three", "big shed", "షెడ్ తొమ్మిది", "షెడ్ 9"])
def test_normal_names_are_unchanged(name):
    assert spoken_name(name) == name
    err = _err(name)
    assert f"called {name}." in err.customer_message and f"{name} అనే" in err.customer_message_te


def test_the_limit_is_24_characters():
    assert SPOKEN_NAME_LIMIT == 24


@pytest.mark.parametrize("ref", ["x" * 1000, "షెడ్ " * 200, "a b " * 500, "9" * 100])
def test_very_long_names_are_shortened(ref):
    out = spoken_name(ref)
    assert 0 < len(out) <= SPOKEN_NAME_LIMIT
    err = _err(ref)
    assert ref not in err.customer_message and ref not in err.customer_message_te
    assert len(err.customer_message) < 80 and len(err.customer_message_te) < 120


def test_a_long_telugu_name_stays_telugu_and_does_not_start_with_a_dangling_mark():
    out = spoken_name("తెలుగు" * 40)
    assert len(out) <= SPOKEN_NAME_LIMIT and out[0].isalpha()


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("shed\n9", "shed 9"),
        ("shed\x009\x07", "shed 9"),
        ("shed\t\t  9", "shed 9"),
        ("sh​ed 9", "shed 9"),  # zero-width space
        ("shed‮9", "shed9"),  # right-to-left override: invisible, dropped
        ("shed 🐔 9", "shed 9"),
        ("🐔🐔🐔shed 9🐔", "shed 9"),
        ("shed 9 👨‍👩‍👧", "shed 9"),
        ("<b>shed</b> 9", "shed 9"),
        ("<script>alert(1)</script>", "alert 1"),
        ("shed [9] {x} & 'q' \"r\"", "shed 9 x q r"),
        ("  shed   9  ", "shed 9"),
    ],
)
def test_control_characters_emoji_and_markup_are_removed(raw, clean):
    assert spoken_name(raw) == clean
    spoken = _err(raw).customer_message + _err(raw).customer_message_te
    for bad in ("\n", "\x00", "\x07", "​", "‮", "🐔", "<", ">", "&", "\t"):
        assert bad not in spoken


@pytest.mark.parametrize("ref", ["", "   ", "🐔", "🐔🐔🐔", "\x00\x01\x02", "<>", "!!!???", "​‍"])
def test_nothing_left_after_cleaning_gives_an_empty_name_never_the_raw_text(ref):
    assert spoken_name(ref) == ""
    err = _err(ref)
    for field in (err.customer_message, err.customer_message_te, err.next_step, err.next_step_te):
        assert "🐔" not in field and "\x00" not in field and "<" not in field


def test_the_real_labels_are_still_listed_and_untouched():
    err = _err("x" * 500)
    assert "House 1, House 2" in err.next_step and "షెడ్ 1, షెడ్ 2" in err.next_step_te


def test_the_stored_reference_is_the_cleaned_one():
    assert _err("<b>shed</b>\n9🐔").reference == "shed 9"


def test_a_leading_combining_mark_is_dropped():
    assert spoken_name("\u0c3fషెడ్ 9") == "షెడ్ 9"
    assert spoken_name("\u0301shed") == "shed"
    assert spoken_name("shed \u0301 9") == "shed 9"


def test_the_cut_never_leaves_a_trailing_space():
    assert spoken_name("a" * 23 + " bcd") == "a" * 23
