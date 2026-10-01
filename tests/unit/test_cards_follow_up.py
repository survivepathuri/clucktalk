"""The follow-up on the cards and the "Demo clock" marker (docs/DESIGN.md §14, §18), checked on the source templates and
the label tables: state as an icon AND a word, English plus Telugu, the sentence shown verbatim (so the card's number
is the spoken number), no new request, and the marker only when the server sends it."""

from __future__ import annotations

import json
import re
import shutil
import subprocess

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
    # due -> WATCH (watch check) or ALERT (urgent or reportable), escalated -> ALERT, lapsed -> UNKNOWN: the level
    # words of the briefing, the same pairs on both cards. Never REMINDER: nothing here reminds the farmer.
    for word in ("level_watch", "level_alert"):  # the briefing's own words for the same items
        assert FARM_STATUS_LABELS[word] == BRIEFING_LABELS[word], word
    assert FARM_STATUS_LABELS["level_unknown"].en == "UNKNOWN"  # a lapsed follow-up: no answer, so not known
    assert "level_info" not in FARM_STATUS_LABELS  # the farm status card no longer carries the REMINDER word


# -- the farm status chip ---------------------------------------------------------------------------
def _chip_source() -> str:
    text = _template("farm_status")
    return text[text.index("function followUpChip") : text.index("// ---------- views")]


def test_the_chip_shows_each_state_as_an_icon_and_a_word_never_colour_alone():
    chip = _chip_source()
    states = dict(re.findall(r'(due|escalated|lapsed): (?:high \? "\w+" : )?"(\w+)"', chip))
    assert states == {"due": "watch", "escalated": "alert", "lapsed": "unknown"}, states
    assert 'high ? "alert" : "watch"' in chip  # a due follow-up on an urgent or reportable check is ALERT
    assert 'f.urgency === "urgent" || f.urgency === "notifiable_suspect"' in chip
    text = _template("farm_status")
    for icon in ("watch", "alert", "unknown"):
        assert re.search(rf"^\s*{icon}: '<svg", text, re.M), icon  # the icon exists
    assert 'L["level_" + level]' in chip and "icon(level)" in chip and "L.follow_up" in chip


def test_the_chip_never_says_reminder():
    chip = _chip_source()
    assert "level_info" not in chip and "REMINDER" not in chip.upper()


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
    assert "!level || !f.text_en" in chip and "return null" in chip


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


# -- the chip, run for real (Node, a fake DOM): the word and icon for every state and urgency -----------------------
def _js_function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    depth, i = 0, source.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        i += 1
        if depth == 0:
            return source[start:i]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_the_chip_word_and_icon_for_every_state_and_urgency_run_in_node():
    source = _template("farm_status")
    labels = {k: {"en": v.en, "te": v.te} for k, v in FARM_STATUS_LABELS.items()}
    script = (
        "const document = { createElement: (t) => ({ tag: t, kids: [], attrs: {}, nodeType: 1, className: '',"
        " setAttribute(k, v) { this.attrs[k] = v; }, addEventListener() {}, append(k) { this.kids.push(k); } }),"
        " createTextNode: (s) => ({ text: s, nodeType: 3 }) };\n"
        f"const L = {json.dumps(labels, ensure_ascii=False)};\n"
        "const icon = (name) => ({ nodeType: 1, tag: 'icon', name, kids: [] });\n"
        + _js_function(source, "el")
        + _js_function(source, "bi")
        + _js_function(source, "stacked")
        + _js_function(source, "followUpChip")
        + "\nconst words = (n) => typeof n === 'string' ? n : Array.isArray(n) ? n.map(words).join('')"
        " : n.nodeType === 3 ? n.text : n.tag === 'icon' ? '[' + n.name + ']' : n.kids.map(words).join('');\n"
        "const out = [];\n"
        "for (const state of ['scheduled', 'due', 'closed', 'escalated', 'lapsed'])\n"
        "  for (const urgency of ['watch', 'urgent', 'notifiable_suspect']) {\n"
        "    const f = { state, urgency, text_en: 'EN sentence', text_te: 'TE sentence' };\n"
        "    const chip = followUpChip({ follow_up: f });\n"
        "    out.push([state, urgency, chip && chip.className, chip && words(chip.kids[0])]);\n"
        "  }\n"
        "console.log(JSON.stringify(out));"
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True, encoding="utf-8").stdout
    rows = {(s, u): (cls, h) for s, u, cls, h in json.loads(out)}
    watch, alert, unknown = (FARM_STATUS_LABELS[k] for k in ("level_watch", "level_alert", "level_unknown"))

    def head(icon: str, word) -> str:  # English, a visible separator, Telugu: also in plain text, never glued
        return f"[{icon}]Follow-up: {word.en} · ఫాలో-అప్: {word.te}"

    for urgency in ("watch", "urgent", "notifiable_suspect"):
        assert rows[("scheduled", urgency)] == (None, None) and rows[("closed", urgency)] == (None, None)
        assert rows[("escalated", urgency)][1] == head("alert", alert)
        assert rows[("lapsed", urgency)][1] == head("unknown", unknown)
    assert rows[("due", "watch")] == ("fu fu-due", head("watch", watch))
    for urgency in ("urgent", "notifiable_suspect"):
        assert rows[("due", urgency)] == ("fu fu-due fu-high", head("alert", alert))
    assert not any("REMINDER" in (r[1] or "") for r in rows.values())
