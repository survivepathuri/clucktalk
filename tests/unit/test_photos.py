"""Placeholder photos and the health-check card (docs/DESIGN.md §14, §18; docs/SOURCES.md "Placeholder images").

There are no real photos in the repository. These tests pin that: every image is a labelled placeholder, listed as such
in SOURCES.md, and nothing user-visible claims photo triage works."""

from __future__ import annotations

import re
import struct
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from clucktalk.config import REPO_ROOT
from clucktalk.domain.photos import BY_REF, LABEL, NOT_ANALYZED, PHOTO_REFS, PLACEHOLDER_PHOTOS
from clucktalk.domain.triage import (
    CheckStatus,
    HealthCheck,
    Sign,
    TriageInput,
    floor_urgency,
    input_from_dict,
    input_to_dict,
)
from clucktalk.server.cards import HEALTH_CHECK_LABELS
from clucktalk.store.sqlite import SqliteStore

ASSETS = REPO_ROOT / "docs" / "assets"
SOURCES = (REPO_ROOT / "docs" / "SOURCES.md").read_text(encoding="utf-8")
TEMPLATE = (REPO_ROOT / "ui" / "cards" / "health_check.html").read_text(encoding="utf-8")
IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 9, 30, 10, 0, tzinfo=IST)


def test_every_registered_image_exists_and_is_a_small_valid_png():
    for p in PLACEHOLDER_PHOTOS:
        data = (ASSETS / p.filename).read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", p.filename
        width, height = struct.unpack(">II", data[16:24])
        assert (width, height) == (320, 240) and len(data) < 20_000, p.filename


def test_no_unregistered_image_sits_in_the_assets_folder():
    """Any picture in docs/assets/ must be a listed placeholder: a real photo needs its own source and license first."""
    on_disk = {f.name for f in ASSETS.iterdir() if f.is_file()}
    assert on_disk == {p.filename for p in PLACEHOLDER_PHOTOS}


def test_every_image_is_listed_in_sources_as_a_placeholder():
    for p in PLACEHOLDER_PHOTOS:
        rows = [line for line in SOURCES.splitlines() if f"docs/assets/{p.filename}" in line]
        assert len(rows) == 1, p.filename
        assert "PLACEHOLDER - not a real photo" in rows[0], p.filename
    assert "There are **no real photos** in this repository" in SOURCES


def test_the_committed_images_are_exactly_what_the_generator_draws():
    r = subprocess.run(
        [sys.executable, "-B", str(REPO_ROOT / "scripts" / "make_placeholders.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr


def test_refs_are_unique_and_never_look_like_real_photos():
    assert len(set(PHOTO_REFS)) == len(PHOTO_REFS) == len(BY_REF)
    assert all(ref.startswith("placeholder_") for ref in PHOTO_REFS)


def test_the_wording_never_claims_that_photos_are_read():
    assert "placeholder, not yet validated on real photos" in LABEL.en
    assert "not analyzed" in NOT_ANALYZED.en and "did not change the result" in NOT_ANALYZED.en
    claim = re.compile(r"\b(?:analy[sz]es|detects?|diagnos\w+|recogni[sz]es|identif\w+|reads your photo)\b", re.I)
    texts = [t.en for t in HEALTH_CHECK_LABELS.values()] + [LABEL.en]
    assert not [t for t in texts if claim.search(t)], texts
    for key, t in HEALTH_CHECK_LABELS.items():
        if "photo" in t.en.lower():
            assert "placeholder" in t.en.lower() or "validated" in t.en.lower(), key


def test_no_readme_or_help_text_claims_photo_triage():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "photo" not in readme, "README must not mention photo triage until it is validated on real photos"
    help_src = (REPO_ROOT / "src" / "clucktalk" / "server" / "tools" / "help.py").read_text(encoding="utf-8")
    assert "photo" not in help_src.lower()


def test_health_card_uses_only_labels_that_exist_and_only_its_own_read_only_tool():
    used = set(re.findall(r"\bL\.(\w+)", TEMPLATE)) | set(re.findall(r'data-l="(\w+)"', TEMPLATE))
    assert not used - HEALTH_CHECK_LABELS.keys(), used - HEALTH_CHECK_LABELS.keys()
    for kind in ("routine", "watch", "urgent", "notifiable_suspect"):  # used as L["urgency_" + kind]
        assert f"urgency_{kind}" in HEALTH_CHECK_LABELS
    assert 'const TOOL = "get_health_check"' in TEMPLATE
    assert 'L["urgency_" + sc.urgency]' in TEMPLATE  # the word next to the icon: never colour alone


def test_health_card_labels_are_bilingual_and_carry_no_numbers():
    for key, t in HEALTH_CHECK_LABELS.items():
        assert t.en.strip() and t.te.strip(), key
        assert not re.search(r"\d", t.en + t.te), key
        assert any("ఀ" <= ch <= "౿" for ch in t.te), key


def test_health_card_urgency_has_four_distinct_shapes():
    icons = re.search(r"const URGENCY_ICONS = \{(.*?)\n\};", TEMPLATE, re.S).group(1)
    shapes = {
        k: re.search(rf"{k}: '(<svg.*?</svg>)'", icons).group(1)
        for k in ("routine", "watch", "urgent", "notifiable_suspect")
    }
    assert len(set(shapes.values())) == 4


def test_health_card_marks_the_placeholder_tile_in_words():
    assert "PLACEHOLDER - not a real photo" == HEALTH_CHECK_LABELS["photo_tile"].en
    assert "L.photo_tile" in TEMPLATE and "sc.photo" in TEMPLATE


# -- storage --------------------------------------------------------------------------------------------------------
def _input(**kw) -> TriageInput:
    base = dict(
        house_id="house-2", label_en="House 2", label_te="షెడ్ 2", breed="Ross 308", age_days=23, live_birds=3870,
        signs=(Sign.COUGHING,), symptoms=None, birds_affected=None, since_days=None, deaths_latest=26,
        baseline_daily_avg=4.0, mortality_spike=True, feed_drop_pct=None, latest_record_day="2026-09-29",
    )  # fmt: skip
    return TriageInput(**{**base, **kw})


def test_a_photo_ref_survives_the_store_and_an_old_row_without_one_still_loads():
    inp = _input(photo_ref="placeholder_2")
    assert input_from_dict(input_to_dict(inp)) == inp
    old = input_to_dict(_input())
    del old["photo_ref"]  # a row written before step 1B
    assert input_from_dict(old).photo_ref is None

    store = SqliteStore(":memory:")
    check = HealthCheck(
        "chk_0123456789abcdef", "farm", "house-2", T0, CheckStatus.ANALYZING, inp,
        floor_urgency(frozenset(inp.signs), True), None, T0,
    )  # fmt: skip
    store.add_health_check(check)
    assert store.get_health_check(check.check_id).input.photo_ref == "placeholder_2"
    assert replace(check, input=_input()).input.photo_ref is None


def test_health_card_never_appends_a_possibly_missing_section_directly():
    """root.append(null) prints the word "null" on the card (found when the card was first rendered, 2026-09-30)."""
    assert not re.search(r"root\.append\((?:section|photoTile)\(", TEMPLATE)
