"""Step 51 part A: the Simulator page in pilot mode says "Pilot (real farm, prototype)", never "Demo data", and never
says the farm is fictional. The demo page is byte-identical to the file on disk."""

from __future__ import annotations

import httpx2
import pytest

from clucktalk.simulator.app import STATIC, SimulatorSettings, pilot_page
from tests.contract.conftest import _free_port
from tests.contract.test_simulator import _run


def _page(mode: str) -> tuple[str, dict]:
    port = _free_port()
    s, stop = _run(
        SimulatorSettings(port=port, mcp_url=f"http://127.0.0.1:{_free_port()}/mcp", auth_token=None, mode=mode)
    )
    try:
        page = httpx2.get(s.base + "/", timeout=10)
        state = httpx2.get(s.base + "/api/state", timeout=10).json()
        assert page.status_code == 200
        return page.text, state
    finally:
        stop()


def test_pilot_page_has_the_pilot_badge_and_no_demo_wording():
    html, state = _page("pilot")
    assert "Pilot (real farm, prototype)" in html
    assert "Demo data" not in html and "mock host" not in html and "fictional" not in html.lower()
    assert state["mode"] == "pilot"


def test_demo_page_is_the_file_on_disk_unchanged():
    html, state = _page("demo")
    assert html == (STATIC / "index.html").read_text(encoding="utf-8")
    assert "Demo data · mock host" in html and "The farm is fictional demo data." in html
    assert state["mode"] == "demo"


def test_pilot_page_replacement_fails_loud_when_the_wording_has_moved():
    with pytest.raises(RuntimeError, match="no longer has"):
        pilot_page("<html>nothing to replace</html>")
