"""The Simulator's developer panel is a small pill while it is closed.

At 1280x800 the closed panel was 560 px wide and sat over the bottom of the device frame and the start of the
transcript; closed, it now takes only the room of its own words. Open, it is as wide as before. Checked from the CSS."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "src" / "clucktalk" / "simulator" / "static"


def rule(selector: str) -> str:
    css = re.sub(r"/\*.*?\*/", "", (STATIC / "style.css").read_text(encoding="utf-8"), flags=re.S)
    for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        if selector in [s.strip() for s in sel.split(",")]:
            return body
    raise AssertionError(f"no CSS rule for {selector}")


def test_the_closed_panel_takes_only_the_room_of_its_own_words():
    assert "width: auto" in rule('.dev[data-open="false"]')
    assert "width: auto" in rule('.dev[data-open="false"] .dev-toggle')


def test_the_open_panel_keeps_its_width_and_the_toggle_stays_a_big_enough_target():
    assert "width: min(560px" in rule(".dev")
    assert float(re.search(r"min-height:\s*([\d.]+)px", rule(".dev-toggle")).group(1)) >= 44


def test_the_markup_starts_the_panel_closed():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="dev" data-open="false"' in html
