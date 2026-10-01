"""Session 5 review finding M4: the sale card's bilingual labels must not be glued ("Todayఈరోజు", "Weightబరువు",
"FCRFCR", "Net vs todayఈరోజుతో"). Separator and spacing only: no new string, no new request."""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from clucktalk.config import REPO_ROOT
from clucktalk.server.cards import SALE_PLAN_LABELS

SOURCE = (REPO_ROOT / "ui" / "cards" / "sale_plan.html").read_text(encoding="utf-8")
BUILT = (REPO_ROOT / "src" / "clucktalk" / "server" / "cards" / "sale_plan.html").read_text(encoding="utf-8")
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")


def _js_function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    depth, i = 0, source.index("{", start)
    while True:
        depth += {"{": 1, "}": -1}.get(source[i], 0)
        i += 1
        if depth == 0:
            return source[start:i]


@pytest.mark.parametrize("text", [SOURCE, BUILT], ids=["source", "built"])
def test_no_label_is_joined_with_an_empty_separator(text):
    assert not re.search(r'bi\([^()]*,\s*""\s*\)', text), "bi(x, '') glues the two languages together"


@pytest.mark.parametrize("text", [SOURCE, BUILT], ids=["source", "built"])
def test_the_stacked_labels_put_telugu_on_its_own_line(text):
    assert re.search(r'\.detail \.row \.l \[lang="te"\]\s*\{[^}]*display:\s*block', text)
    assert re.search(r'el\("span", \{ lang: "en" \}, t\.en\), " ", el\("span", \{ lang: "te" \}', text)  # a space too


@pytest.mark.parametrize("text", [SOURCE, BUILT], ids=["source", "built"])
def test_a_label_that_is_the_same_in_both_languages_is_shown_once(text):
    assert SALE_PLAN_LABELS["fcr"].en == SALE_PLAN_LABELS["fcr"].te == "FCR"  # the glossary word, same in both
    assert text.count("if (t.te === t.en) return") == 2  # bi() and stacked() both skip the duplicate


def _run(snippet: str) -> list:
    script = (
        "const document = { createElement: (t) => ({ tag: t, kids: [], attrs: {}, nodeType: 1, className: '',"
        " setAttribute(k, v) { this.attrs[k] = v; }, addEventListener() {}, append(k) { this.kids.push(k); } }),"
        " createTextNode: (s) => ({ text: s, nodeType: 3 }) };\n"
        + _js_function(SOURCE, "el")
        + _js_function(SOURCE, "bi")
        + _js_function(SOURCE, "stacked")
        + "\nconst text = (n) => typeof n === 'string' ? n : Array.isArray(n) ? n.map(text).join('')"
        " : n.nodeType === 3 ? n.text : n.kids.map(text).join('');\n" + snippet
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True, encoding="utf-8").stdout
    return json.loads(out)


@NODE
def test_the_label_helpers_never_glue_the_two_languages():
    labels = {k: {"en": v.en, "te": v.te} for k, v in SALE_PLAN_LABELS.items()}
    rows = _run(
        f"const L = {json.dumps(labels, ensure_ascii=False)};"
        "console.log(JSON.stringify(['today', 'weight', 'fcr', 'net_vs_today'].map("
        "(k) => [text(bi(L[k])), text(stacked(L[k], 'l'))])));"
    )
    for key, (spoken, stacked_text) in zip(("today", "weight", "fcr", "net_vs_today"), rows, strict=True):
        en, te = SALE_PLAN_LABELS[key].en, SALE_PLAN_LABELS[key].te
        if en == te:
            assert spoken == stacked_text == en  # shown once, never "FCRFCR"
        else:
            assert f"{en}{te}" not in spoken and f"{en}{te}" not in stacked_text, (key, spoken, stacked_text)
            assert en in stacked_text and te in stacked_text


@NODE
def test_the_today_bar_label_has_a_separator():
    out = _run('const L = {today: {en: "Today", te: "ఈరోజు"}}; console.log(JSON.stringify(text(bi(L.today))));')
    assert out == "Today · ఈరోజు"
