"""Simulator contract: the host side of voice/text -> MCP tools/call -> spoken answer + card, over real HTTP.

The Simulator runs under uvicorn on a free 127.0.0.1 port and talks to the live CluckTalk MCP server fixture.
The browser half (speech, sandboxed card, cross-modal self-check) is verified in the recorded end-to-end run
(docs/evidence/); these tests pin the backend contract it relies on.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import httpx2
import pytest
import uvicorn

from clucktalk.server.cards import FARM_STATUS_URI
from clucktalk.simulator.app import FALLBACK_SPEECH, UNAVAILABLE_SPEECH, SimulatorSettings, build_app, sandbox_csp
from tests.contract.conftest import _free_port


class Sim:
    def __init__(self, port: int) -> None:
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self.origin = self.base

    def turn(self, utterance: str, device: str = "show", **extra) -> dict:
        r = httpx2.post(
            self.base + "/api/turn",
            json={"utterance": utterance, "device": device, **extra},
            headers={"origin": self.origin},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        return r.json()


def _run(settings: SimulatorSettings) -> tuple[Sim, callable]:
    uv = uvicorn.Server(uvicorn.Config(build_app(settings), host="127.0.0.1", port=settings.port, log_level="warning"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not uv.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("simulator did not start")
        time.sleep(0.02)

    def stop() -> None:
        uv.should_exit = True
        thread.join(timeout=10)

    return Sim(settings.port), stop


@pytest.fixture(scope="module")
def sim(live) -> Iterator[Sim]:
    s, stop = _run(SimulatorSettings(port=_free_port(), mcp_url=live.url, auth_token=None))
    yield s
    stop()


@pytest.fixture(scope="module")
def sim_without_server() -> Iterator[Sim]:
    dead = _free_port()  # nothing listens here
    s, stop = _run(SimulatorSettings(port=_free_port(), mcp_url=f"http://127.0.0.1:{dead}/mcp", auth_token=None))
    yield s
    stop()


def test_invocation_example_reaches_the_tool_and_returns_speech_and_card(sim):
    out = sim.turn("Alexa, ask CluckTalk how shed two is doing")
    assert out["kind"] == "tool"
    assert out["intent"]["tool"] == "get_farm_status"
    assert out["intent"]["arguments"] == {"house": "shed two"}
    result = out["result"]
    assert result["isError"] is False
    # What the device speaks is exactly the tool's content text (no host rewording of numbers).
    assert out["speech"] == " ".join(c["text"] for c in result["content"] if c["type"] == "text")
    assert out["speech"].startswith("House 2 needs attention now.")
    assert out["card"]["uri"] == FARM_STATUS_URI
    assert out["card"]["tool"]["name"] == "get_farm_status"


def test_developer_panel_gets_the_exact_wire_exchange(sim):
    out = sim.turn("How is shed two doing?")
    call = out["exchanges"][-1]
    assert call["request"]["method"] == "tools/call"
    assert call["request"]["params"] == {"name": "get_farm_status", "arguments": {"house": "shed two"}}
    assert call["http_status"] == 200 and call["response"]["result"] == out["result"]
    assert out["timing"]["mcp_ms"] > 0


def test_echo_dot_gets_the_same_answer_and_no_card(sim):
    show, dot = sim.turn("How is shed two doing?", "show"), sim.turn("How is shed two doing?", "dot")
    assert dot["card"] is None
    assert dot["speech"] == show["speech"]
    for word in ("screen", "card", "tap", "see below", "shown"):
        assert word not in dot["speech"].lower(), word


def test_unknown_shed_is_spoken_safely(sim):
    out = sim.turn("How is shed nine doing?")
    assert out["kind"] == "tool" and out["is_error"] is True
    assert "shed nine" in out["speech"] and "House 1" in out["speech"]
    for leak in ("get_farm_status", "Error", "{", "house_id"):
        assert leak not in out["speech"], leak


def test_no_matching_tool_gets_the_host_fallback_and_no_mcp_call(sim):
    out = sim.turn("What's the weather today?")
    assert out["kind"] == "fallback" and out["speech"] == FALLBACK_SPEECH
    assert out["exchanges"] == [] and out["intent"] is None


def test_server_down_is_said_plainly(sim_without_server):
    out = sim_without_server.turn("How is shed two doing?")
    assert out["kind"] == "unavailable" and out["speech"] == UNAVAILABLE_SPEECH
    assert out["result"] is None and out["card"] is None


def test_simulated_delay_is_applied_and_reported(sim):
    out = sim.turn("How is shed one doing?", simulate_delay_ms=300)
    assert out["timing"]["simulated_delay_ms"] == 300
    assert out["timing"]["backend_ms"] >= 300


def test_card_resource_is_served_to_the_page(sim):
    r = httpx2.get(sim.base + "/api/resource", params={"uri": FARM_STATUS_URI}, timeout=10)
    assert r.status_code == 200
    assert r.json()["content"]["mimeType"] == "text/html;profile=mcp-app"
    assert httpx2.get(sim.base + "/api/resource", params={"uri": "file:///etc/passwd"}).status_code == 400


def _view(sim, body: dict) -> httpx2.Response:
    return httpx2.post(sim.base + "/api/view-request", json=body, headers={"origin": sim.origin})


def test_card_tap_is_forwarded_as_tools_call(sim):
    r = _view(
        sim,
        {
            "method": "tools/call",
            "params": {"name": "get_farm_status", "arguments": {"house": "house-1"}},
            "card_uri": FARM_STATUS_URI,
        },
    )
    assert r.status_code == 200
    assert r.json()["response"]["result"]["structuredContent"]["houses"][0]["house_id"] == "house-1"


@pytest.mark.parametrize(
    "card_uri",
    [None, "ui://clucktalk/other-card.html"],
)
def test_a_card_may_only_call_the_tool_that_owns_it(sim, card_uri):
    """Taps must never reach tools the card does not own (later: order confirmation needs a spoken 'yes')."""
    call = {"method": "tools/call", "params": {"name": "get_farm_status", "arguments": {}}, "card_uri": card_uri}
    assert _view(sim, call).status_code == 400
    other_tool = {"method": "tools/call", "params": {"name": "plan_feed", "arguments": {}}, "card_uri": FARM_STATUS_URI}
    assert _view(sim, other_tool).status_code == 400


@pytest.mark.parametrize(
    "body",
    [
        {"method": "tools/list", "params": {}},
        {"method": "ui/open-link", "params": {"url": "https://example.com"}},
        {"method": "tools/call", "params": {"name": "no_such_tool", "arguments": {}}},
        {"method": "resources/read", "params": {"uri": "file:///etc/passwd"}},
    ],
)
def test_card_requests_outside_the_allowed_set_are_refused(sim, body):
    assert _view(sim, {**body, "card_uri": FARM_STATUS_URI}).status_code == 400


def test_api_refuses_other_origins_and_hosts(sim):
    body = {"utterance": "How is shed two doing?"}
    assert httpx2.post(sim.base + "/api/turn", json=body).status_code == 403  # no Origin
    evil = httpx2.post(sim.base + "/api/turn", json=body, headers={"origin": "http://evil.example"})
    assert evil.status_code == 403
    other_port = httpx2.post(sim.base + "/api/turn", json=body, headers={"origin": "http://127.0.0.1:1"})
    assert other_port.status_code == 403
    assert httpx2.get(sim.base + "/", headers={"host": "attacker.example"}).status_code == 421
    # The card sandbox runs on the other loopback name; its origin must not be able to call the API.
    sandbox_origin = f"http://localhost:{sim.port}"
    assert httpx2.post(sim.base + "/api/turn", json=body, headers={"origin": sandbox_origin}).status_code == 403


def test_api_takes_json_only(sim):
    """A plain HTML form (text/plain, urlencoded) cannot drive the API, even from an allowed origin."""
    r = httpx2.post(
        sim.base + "/api/turn",
        content='{"utterance": "How is shed two doing?"}',
        headers={"origin": sim.origin, "content-type": "text/plain"},
    )
    assert r.status_code == 415


@pytest.mark.parametrize(
    "body",
    ['["not", "an", "object"]', '{"utterance": 5}', '{"utterance": "hi", "simulate_delay_ms": "slow"}', "{bad json"],
)
def test_malformed_turn_is_a_400_not_a_crash(sim, body):
    r = httpx2.post(
        sim.base + "/api/turn", content=body, headers={"origin": sim.origin, "content-type": "application/json"}
    )
    assert r.status_code == 400


def test_sandbox_is_served_with_the_spec_csp(sim):
    r = httpx2.get(sim.base.replace("127.0.0.1", "localhost") + "/sandbox", headers={"host": f"localhost:{sim.port}"})
    assert r.status_code == 200
    assert r.headers["content-security-policy"] == sandbox_csp({}, (sim.origin, f"http://localhost:{sim.port}"))


def test_sandbox_strict_mode_serves_the_strict_csp(sim):
    r = httpx2.get(
        sim.base.replace("127.0.0.1", "localhost") + "/sandbox?strict=1", headers={"host": f"localhost:{sim.port}"}
    )
    assert r.status_code == 200
    csp = r.headers["content-security-policy"]
    assert csp == sandbox_csp({}, (sim.origin, f"http://localhost:{sim.port}"), strict=True)
    assert "font-src" not in csp


@pytest.fixture
def sim_fresh(fresh) -> Iterator[Sim]:
    """A Simulator on a server with its own state store, for turns that change the farm."""
    s, stop = _run(SimulatorSettings(port=_free_port(), mcp_url=fresh.live.url, auth_token=None))
    yield s
    stop()


def test_spoken_mode_switch_needs_yes_and_yes_goes_to_the_same_tool_with_the_id(sim_fresh):
    """docs/DESIGN.md §5.1 end to end through the host: read-back, then "haan" answers it."""
    first = sim_fresh.turn("Switch my farm to contract farming")
    assert first["intent"]["tool"] == "set_farm_mode" and first["intent"]["arguments"] == {"mode": "contract"}
    sc = first["result"]["structuredContent"]
    assert sc["status"] == "needs_confirmation" and first["awaiting_answer"] is True
    assert first["speech"].startswith("Switch your farm to contract farming?")
    yes = sim_fresh.turn("haan")
    assert yes["intent"]["tool"] == "set_farm_mode"
    assert yes["intent"]["arguments"] == {"mode": "contract", "proposal_id": sc["proposal_id"], "answer": "yes"}
    assert yes["result"]["structuredContent"]["status"] == "changed"
    assert "contract farm" in sim_fresh.turn("What kind of farm is this?")["speech"]
    assert "Ask your supervisor for" in sim_fresh.turn("feed plan for shed two")["speech"]


def test_no_keeps_the_farm_and_a_later_yes_answers_nothing(sim_fresh):
    sim_fresh.turn("change to contract farming")
    no = sim_fresh.turn("nahi")
    assert no["intent"]["arguments"]["answer"] == "no"
    assert no["result"]["structuredContent"]["status"] == "cancelled"
    late = sim_fresh.turn("yes")
    assert late["kind"] == "fallback" and late["exchanges"] == []  # nothing pending: no tool call at all
    assert "independent farm" in sim_fresh.turn("am I contract or independent")["speech"]


def test_moving_on_drops_the_pending_read_back(sim_fresh):
    sim_fresh.turn("switch to contract farming")
    sim_fresh.turn("how is shed two doing")  # the farmer moved on
    stray = sim_fresh.turn("yes")
    assert stray["kind"] == "fallback" and stray["exchanges"] == []


def test_a_reported_record_needs_a_yes_then_shows_up_in_the_record_book(sim_fresh):
    """docs/DESIGN.md §13.2 end to end through the host: report, read-back, "haan", then get_record_book."""
    first = sim_fresh.turn("House 1, 3 birds died and 2 bags of feed today")
    assert first["intent"]["tool"] == "log_daily_record"
    assert first["intent"]["arguments"] == {"house": "house 1", "deaths": 3, "feed_bags": 2.0}
    sc = first["result"]["structuredContent"]
    assert sc["status"] == "needs_confirmation" and first["awaiting_answer"] is True
    assert "3 died" in first["speech"] and "2 bags of feed" in first["speech"]

    yes = sim_fresh.turn("haan")
    assert yes["intent"]["tool"] == "log_daily_record"
    assert yes["intent"]["arguments"] == {
        **first["intent"]["arguments"],
        "proposal_id": sc["proposal_id"],
        "answer": "yes",
    }
    assert yes["result"]["structuredContent"]["status"] == "changed"

    book = sim_fresh.turn("record book")
    assert book["intent"] == {"tool": "get_record_book", "arguments": {}, "rule": book["intent"]["rule"]}
    entry = next(e for e in book["result"]["structuredContent"]["entries"] if e["number"] == 1)
    assert entry["logged"] is True and entry["record"]["deaths"] == 3
