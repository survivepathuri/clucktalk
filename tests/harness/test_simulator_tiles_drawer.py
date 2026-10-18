"""The Simulator's tiles (the farmer page's palette), the developer drawer and the host hint, from the static files.

The tiles must stay readable (WCAG AA: 4.5:1 for text, 3:1 for the borders against what is behind them); the
developer panel must push the page instead of lying over the chips; the host hint must not suggest that Telugu
answers are spoken."""

from __future__ import annotations

import colorsys
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "src" / "clucktalk" / "simulator" / "static"
HUES = {"starter/chip 1": 192, "2": 280, "3": 170, "4": 62, "5": 38, "No": 205}


def css() -> str:
    return re.sub(r"/\*.*?\*/", "", (STATIC / "style.css").read_text(encoding="utf-8"), flags=re.S)


def body_of(selector: str, text: str | None = None) -> str:
    found = [
        body for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", text or css()) if selector == " ".join(sel.split())
    ]
    if not found:
        raise AssertionError(f"no CSS rule for {selector}")
    return " ".join(found)  # every rule written for exactly this selector list


def prop(body: str, name: str) -> str:
    return re.search(rf"{re.escape(name)}:\s*([^;]+);", body).group(1).strip()


def luminance(rgb: tuple[float, float, float]) -> float:
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def hsl(h: float, s: float, light: float) -> tuple[float, float, float]:
    return colorsys.hls_to_rgb(h / 360, light, s)


def hexrgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def ratio(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def pct(value: str) -> float:
    return float(value.rstrip("%")) / 100


def tile_vars() -> dict[str, str]:
    body = body_of(".home, .chips, .replies")
    return {k: prop(body, k) for k in ("--ts", "--tl", "--tbs", "--tbl", "--tx", "--tg")}


def test_tile_text_and_gloss_reach_aa_on_every_tile_colour():
    v = tile_vars()
    for name, hue in HUES.items():
        sat = pct(v["--ts"]) if name != "No" else 0.20
        bg = hsl(hue, sat, pct(v["--tl"]))
        hover = hsl(hue, sat, pct(prop(body_of(".home, .chips, .replies"), "--tlh")))
        for surface in (bg, hover):
            assert ratio(hexrgb(v["--tx"]), surface) >= 4.5, name
            assert ratio(hexrgb(v["--tg"]), surface) >= 4.5, name


def test_the_yes_tile_is_white_on_the_pilot_green_and_reaches_aa():
    green = hexrgb(prop(body_of(":root"), "--yes"))
    assert ratio((1, 1, 1), green) >= 4.5
    assert "var(--yes)" in body_of(".chip.reply:nth-child(1), .chip.reply:nth-child(1):hover")


def test_tile_borders_stand_out_from_the_page_and_the_screen_by_3_to_1():
    v = tile_vars()
    page = hexrgb("#eceae4")  # the page behind the chips under the transcript (--page)
    screen = hexrgb("#1d3b52")  # the lightest part of the dark device screen behind the starters
    home_border = body_of(".home")
    for hue in (192, 280, 170, 62, 38):
        chip_border = hsl(hue, pct(v["--tbs"]), pct(v["--tbl"]))
        assert ratio(chip_border, page) >= 3, hue
        starter_border = hsl(hue, pct(prop(home_border, "--tbs")), pct(prop(home_border, "--tbl")))
        assert ratio(starter_border, screen) >= 3, hue


def test_the_tiles_are_big_with_a_large_telugu_label_and_a_smaller_english_gloss():
    for tile, label_min, gloss_min in ((".starter", 30, 18), (".chip.reply", 26, 17), (".chip", 20, 14)):
        q = int(re.search(r"font-size:\s*(\d+)px", body_of(f"{tile} .q")).group(1))
        g = int(re.search(r"font-size:\s*(\d+)px", body_of(f"{tile} .gloss")).group(1))
        assert q >= label_min and gloss_min <= g < q, tile
    assert int(re.search(r"min-height:\s*(\d+)px", body_of(".starter")).group(1)) >= 96
    assert int(re.search(r"min-height:\s*(\d+)px", body_of(".chip")).group(1)) >= 56


def test_the_developer_panel_is_a_drawer_that_pushes_the_page_and_starts_closed():
    text = css()
    drawer = body_of('.dev[data-open="true"]', text)
    assert "right: 0" in drawer and "bottom: 0" in drawer and "var(--drawer-w)" in drawer
    assert "padding-right: var(--drawer-w)" in body_of("body.dev-open", text)
    assert "dev-open" in (STATIC / "app.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="dev" data-open="false"' in html and 'id="dev-body" hidden' in html


def test_the_drawer_toggle_flips_open_hidden_aria_and_the_body_class_and_the_url_option_opens_it():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    toggle = js[js.index('$("dev-toggle").addEventListener') :].split("});", 1)[0]
    for needle in (
        "dataset.open = String(open)",
        '$("dev-body").hidden = !open',
        "aria-expanded",
        'classList.toggle("dev-open", open)',
        "applyPreset()",
    ):
        assert needle in toggle, needle
    assert re.search(r'q\.get\("dev"\) === "1"\) \$\("dev-toggle"\)\.click\(\)', js)


def test_two_columns_keep_the_taps_on_screen_and_one_column_pins_them_to_the_window_bottom():
    text = css()
    wide = text[text.index("@container (min-width: 1040px)") :]
    assert "flex-direction: row" in wide and "height: calc(100vh" in wide
    assert "min-height: 0" in wide and "max-height: none" in wide  # the transcript scrolls inside its own column
    assert "position: sticky" in body_of(".replies", text) and "bottom:" in body_of(".replies", text)


def test_the_host_hint_does_not_suggest_spoken_telugu():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "Type below or use the microphone (English). English answers are read aloud when Sound is on." in html
    assert "Answers are spoken" not in html and "appears on screen" not in html
