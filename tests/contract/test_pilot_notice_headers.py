"""Step 52 part C: the first-open notice (all seven items, one acknowledgement, versioned), the 401 message that works
without a token, and the security headers the app sends itself for the pilot (CSP, Referrer-Policy, nosniff)."""

from __future__ import annotations

import re

import httpx2
import pytest

from clucktalk.i18n.pilot import NOTICE_ITEMS, OPEN_LINK, PILOT_NOTICE, notice_version
from clucktalk.simulator.app import SimulatorSettings
from tests.contract.conftest import _free_port
from tests.contract.test_pilot_hardening import TOKEN, rig, start  # noqa: F401  (the shared hardened pilot rig)
from tests.contract.test_simulator import _run

AUTH = {"authorization": f"Bearer {TOKEN}"}
CSP = "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


def test_the_ui_gives_all_seven_notice_items_in_english_and_telugu_and_a_version(rig):  # noqa: F811
    ui = httpx2.get(rig.base + "/api/pilot/ui", headers=AUTH, timeout=20).json()
    assert len(ui["notice_items"]) == 7 and ui["notice_version"] == notice_version()
    assert all(i["en"].strip() and i["te"].strip() and i["en"] != i["te"] for i in ui["notice_items"])
    assert ui["strings"]["notice_title"]["te"].strip() and ui["strings"]["ack"]["te"].strip()


def test_the_seven_items_say_what_they_must_say():
    en = [t.en.lower() for t in NOTICE_ITEMS]
    assert "this is a test" in en[0] and "not a veterinary service" in en[0]
    assert "call your vet" in en[1]
    assert "reminder" in en[2] and "not a diagnosis" in en[2]
    assert "general" in en[3] and "may not fit your birds" in en[3]
    assert "speech service" in en[4] and "never hears your voice" in en[4]  # his keyboard's voice typing
    assert "we keep" in en[5] and "builder" in en[5] and "can read" in en[5]  # what is stored, and who can read it
    assert "delete" in en[6] and "at any time" in en[6]
    assert NOTICE_ITEMS[4] is PILOT_NOTICE


def test_the_version_changes_with_any_word_of_the_notice(monkeypatch):
    import clucktalk.i18n.pilot as pilot_words
    from clucktalk.i18n import Text

    before = notice_version()
    changed = (*NOTICE_ITEMS[:-1], Text(en=NOTICE_ITEMS[-1].en + " ", te=NOTICE_ITEMS[-1].te))
    monkeypatch.setattr(pilot_words, "NOTICE_ITEMS", changed)
    assert notice_version() != before
    monkeypatch.setattr(
        pilot_words, "NOTICE_ITEMS", (*NOTICE_ITEMS[:-1], Text(en=NOTICE_ITEMS[-1].en, te=NOTICE_ITEMS[-1].te + "x"))
    )
    assert notice_version() not in (before,)


def test_the_page_carries_the_open_your_link_message_without_any_token(rig):  # noqa: F811
    html = httpx2.get(rig.base + "/", timeout=10).text
    assert OPEN_LINK.te in html and OPEN_LINK.en in html and 'id="fatal"' in html
    assert "@OPEN_LINK" not in html and "@BADGE" not in html and "@APP_NAME" not in html
    assert httpx2.get(rig.base + "/api/pilot/ui", timeout=10).status_code == 401  # and the data itself still needs it


@pytest.mark.parametrize(
    "path", ["/", "/static/pilot.js", "/static/pilot.css", "/healthz", "/api/state", "/nothing-here"]
)
def test_the_pilot_sends_its_own_security_headers_on_everything(rig, path):  # noqa: F811
    r = httpx2.get(rig.base + path, headers=AUTH, timeout=10)
    assert r.headers["content-security-policy"] == CSP
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_the_headers_are_on_errors_too_and_not_duplicated(rig):  # noqa: F811
    for r in (
        httpx2.get(rig.base + "/api/state", timeout=10),
        httpx2.post(rig.base + "/api/turn", json={}, timeout=10),
    ):
        assert r.status_code in (401, 403)
        assert r.headers.get_list("content-security-policy") == [CSP]


def test_the_page_needs_nothing_the_csp_forbids(rig):  # noqa: F811
    html = httpx2.get(rig.base + "/", timeout=10).text
    assert "<style" not in html and not re.search(r"\sstyle=", html) and not re.search(r"\son\w+=", html)
    assert re.findall(r"<script[^>]*>", html) == ['<script src="/static/pilot.js">']


def test_the_demo_sends_no_such_headers_and_is_unchanged():
    s, stop = _run(
        SimulatorSettings(port=_free_port(), mcp_url=f"http://127.0.0.1:{_free_port()}/mcp", auth_token=None)
    )
    try:
        r = httpx2.get(s.base + "/", timeout=10)
        assert "content-security-policy" not in r.headers and "referrer-policy" not in r.headers
    finally:
        stop()
