"""Step 52 part B: what the pilot host does not serve. The card forwarding routes and the English demo page are off in
pilot mode (the phone page needs neither); the demo is unchanged."""

from __future__ import annotations

import httpx2

from clucktalk.simulator.app import SimulatorSettings
from tests.contract.conftest import _free_port
from tests.contract.test_pilot_hardening import TOKEN, rig, start  # noqa: F401  (the shared hardened pilot rig)
from tests.contract.test_simulator import _run

AUTH = {"authorization": f"Bearer {TOKEN}"}


def test_the_card_routes_are_not_found_in_pilot_mode_even_with_the_token(rig):  # noqa: F811
    post = httpx2.post(
        rig.base + "/api/view-request",
        json={"method": "tools/call", "params": {"name": "get_farm_status", "arguments": {}}, "card_uri": "ui://x"},
        headers={**AUTH, "origin": rig.base},
        timeout=20,
    )
    assert post.status_code == 404
    got = httpx2.get(rig.base + "/api/resource?uri=ui://clucktalk/farm-status", headers=AUTH, timeout=20)
    assert got.status_code == 404


def test_the_english_demo_page_is_not_served_on_a_pilot_host(rig):  # noqa: F811
    assert httpx2.get(rig.base + "/static/index.html", timeout=10).status_code == 404
    page = httpx2.get(rig.base + "/", timeout=10)
    assert page.status_code == 200 and "Demo data" not in page.text


def test_the_phone_pages_own_files_are_still_served(rig):  # noqa: F811
    for name in ("pilot.js", "pilot.css", "pilot.html"):
        assert httpx2.get(rig.base + f"/static/{name}", timeout=10).status_code == 200


def test_an_unhardened_pilot_also_has_them_off(tmp_path):
    for r in start(tmp_path, tokens=()):
        assert httpx2.get(r.base + "/static/index.html", timeout=10).status_code == 404
        post = httpx2.post(
            r.base + "/api/view-request", json={"method": "tools/call"}, headers={"origin": r.base}, timeout=20
        )
        assert post.status_code == 404


def test_the_demo_still_serves_the_english_page_and_the_card_routes():
    s, stop = _run(
        SimulatorSettings(port=_free_port(), mcp_url=f"http://127.0.0.1:{_free_port()}/mcp", auth_token=None)
    )
    try:
        assert httpx2.get(s.base + "/static/index.html", timeout=10).status_code == 200
        r = httpx2.post(s.base + "/api/view-request", json={"method": "nope"}, headers={"origin": s.base}, timeout=10)
        assert r.status_code == 400  # as before: the route exists and judges the request
        assert httpx2.get(s.base + "/api/resource?uri=http://x", timeout=10).status_code == 400
    finally:
        stop()
