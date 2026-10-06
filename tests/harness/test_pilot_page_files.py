"""The pilot page files (Step 51 part C): the page holds no wording of its own (every word comes from the server's i18n,
so every Telugu line is pending review in docs/TELUGU_REVIEW.md), says nothing about demo data, and chips never send a
sentence."""

from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[2] / "src" / "clucktalk" / "simulator" / "static"
TELUGU = re.compile("[ఀ-౿]")


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_the_page_files_hold_no_telugu_of_their_own():
    for name in ("pilot.html", "pilot.js", "pilot.css"):
        assert not TELUGU.search(read(name)), f"{name} has Telugu text that is not in the reviewed i18n"


def test_the_page_never_says_demo_or_fictional_and_loads_only_its_own_files():
    html = read("pilot.html")
    for name in ("pilot.html", "pilot.js"):
        text = read(name).lower()
        assert "demo data" not in text and "mock host" not in text and "fictional" not in text
    assert re.findall(r'(?:src|href)="([^"]+)"', html) == ["/static/pilot.css", "/static/pilot.js"]
    assert "http://" not in html and "https://" not in html and "<iframe" not in html


def test_a_chip_sends_an_id_and_numbers_not_a_sentence():
    js = read("pilot.js")
    assert "post({ chip, params })" in js and 'post({ chip: "yes" })' in js and 'post({ chip: "no" })' in js
    # the only call that sends typed text is the form submit
    assert len(re.findall(r"post\(\{ utterance", js)) == 1


def test_the_write_buttons_are_the_read_back_buttons_and_there_is_no_other_way_to_confirm():
    js = read("pilot.js")
    assert js.count('chip: "yes"') == 1 and js.count('chip: "no"') == 1
    assert "innerHTML" not in js and "eval(" not in js  # farmer and server text is only ever shown as text


def test_the_token_comes_from_the_link_fragment_is_removed_from_the_address_and_sent_as_a_bearer_header():
    js = read("pilot.js")
    assert "location.hash" in js and "history.replaceState" in js
    assert js.count('authorization: "Bearer "') == 1 and js.count("auth(") >= 3
    assert "location.search" in js  # the fragment is dropped, the rest of the address is kept
    assert "ct_token" not in "".join(re.findall(r"localStorage[^;]*;", js))  # the token lives for this tab only
    for call in re.findall(r"fetch\([^)]*\)", js):
        assert "auth(" in js[js.index(call) : js.index(call) + 200], call


def test_the_add_and_replace_buttons_send_their_own_chips_and_the_plain_yes_is_hidden_for_the_question():
    js, html = read("pilot.js"), read("pilot.html")
    assert 'post({ chip: "add" })' in js and 'post({ chip: "replace" })' in js
    assert 'id="add"' in html and 'id="replace"' in html
    assert '$("yes").hidden = !!choice;' in js and "structuredContent.choice" in js


def test_a_stable_device_id_in_local_storage_is_the_session_and_the_token_is_not_stored_there():
    js = read("pilot.js")
    assert 'localStorage.getItem("ct_device")' in js and 'localStorage.setItem("ct_device"' in js
    assert 'sessionStorage.getItem("ct_session")' in js  # the fallback without local storage
    assert "const SESSION = sessionId();" in js
    assert 'localStorage.setItem("ct_token"' not in js and 'localStorage.getItem("ct_token")' not in js
    assert 'sessionStorage.setItem("ct_token"' in js
