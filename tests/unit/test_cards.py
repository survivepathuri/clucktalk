"""Card template rules (docs/DESIGN.md §14) checked on the source template and the label table."""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from clucktalk.config import REPO_ROOT
from clucktalk.server.cards import FARM_STATUS_LABELS
from clucktalk.server.render import num

TEMPLATE = (REPO_ROOT / "ui" / "cards" / "farm_status.html").read_text(encoding="utf-8")


def test_every_label_the_card_uses_exists():
    used = set(re.findall(r"\bL\.(\w+)", TEMPLATE)) | set(re.findall(r'data-l="(\w+)"', TEMPLATE))
    missing = used - FARM_STATUS_LABELS.keys()
    assert not missing, missing
    for level in ("ok", "watch", "alert", "unknown"):  # used as L["level_" + level]
        assert f"level_{level}" in FARM_STATUS_LABELS


def test_labels_are_bilingual_and_carry_no_numbers():
    """Every number on a card must come from structuredContent; labels only hold a {n} slot."""
    for key, t in FARM_STATUS_LABELS.items():
        assert t.en.strip() and t.te.strip(), key
        assert not re.search(r"\d", t.en + t.te), key
        assert t.en.count("{n}") == t.te.count("{n}"), key
        assert t.en.count("{d}") == t.te.count("{d}"), key
        assert any("ఀ" <= ch <= "౿" for ch in t.te), key


def test_status_is_never_colour_alone():
    """Each level has its own icon shape and a word (spec brief + Amazon CX colour-correction testing)."""
    icons = re.search(r"const ICONS = \{(.*?)\n\};", TEMPLATE, re.S).group(1)
    shapes = {lv: re.search(rf"{lv}: '(<svg.*?</svg>)'", icons).group(1) for lv in ("ok", "watch", "alert", "unknown")}
    assert len(set(shapes.values())) == 4
    assert 'L["level_" + level]' in TEMPLATE  # the word next to the icon


def _js_function(source: str, name: str) -> str:
    """The source of a top-level `function name(...) {...}` in the card (brace-matched)."""
    start = source.index(f"function {name}(")
    depth, i = 0, source.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        i += 1
        if depth == 0:
            return source[start:i]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed; the card's num() needs a JS engine")
def test_card_num_matches_the_server_formatter():
    """Runs the card's own num() (from the built bundle) in Node on values the server's render.num formats.
    Spoken and card numbers must be the same strings (docs/DESIGN.md §6)."""
    built = (REPO_ROOT / "src" / "clucktalk" / "server" / "cards" / "farm_status.html").read_text(encoding="utf-8")
    values = [0, 7, 941, 1012, 3883, 12345, 123456, 12345678, 2.9, 1.23, 38.5, 0.05, 1568.25, 100000.5, -0.5, -1234.5]
    script = (
        _js_function(built, "indianGroup")
        + _js_function(built, "num")
        + f"console.log(JSON.stringify({json.dumps(values)}.map(num)));"
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [num(v) for v in values]


def test_card_self_checks_its_number_format_against_the_server():
    """The built card embeds [value, render.num(value)] pairs and reports any mismatch at load."""
    built = (REPO_ROOT / "src" / "clucktalk" / "server" / "cards" / "farm_status.html").read_text(encoding="utf-8")
    fixtures = json.loads(re.search(r"const NUM_FIXTURES = (\[.*?\]);", built).group(1))
    assert fixtures and all(num(v) == want for v, want in fixtures)
    assert "numSelfTest();" in built and '"num-mismatch"' in built
