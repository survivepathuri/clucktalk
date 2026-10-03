"""Step 48B part C: concurrency, and the sessions a rejected request leaves behind.

Real HTTP, real threads. Two simultaneous "yes" for one proposal produce one effect; two simultaneous health checks on
one shed both succeed and leave a consistent store; 50 parallel ``initialize`` calls give 50 distinct sessions that end;
a POST without an Accept header is answered 406 and leaves no session behind (the SDK builds a transport for it and
discards it at once); the session count is bounded by the SDK's own limit and idle timeout, pinned below."""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx2
import pytest

from clucktalk.agents.model import RulesModel
from clucktalk.domain.triage import Urgency
from tests.contract.conftest import LiveServer, _start
from tests.contract.test_follow_up_tools import _store_check
from tests.contract.test_health_tools import Rig, _rig

ROUNDS = 12
SIGNS = ["coughing", "sneezing", "gasping", "nasal_discharge", "swollen_head", "twisted_neck", "paralysis", "diarrhoea",
         "not_eating", "dull", "lame", "panting"]  # fmt: skip


@pytest.fixture
def rig():
    yield from _rig(RulesModel())


def post_tool(rig: Rig, tool: str, arguments: dict[str, Any], rid: int, timeout: float = 30) -> httpx2.Response:
    body = {"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}
    return httpx2.post(rig.live.url, json=body, headers=rig.live.headers(rig.sid), timeout=timeout)


def both_at_once(rig: Rig, tool: str, **arguments: Any) -> list[dict[str, Any]]:
    """Two calls released together by a barrier, each with its own JSON-RPC id (ids must be unique in a session; see the
    duplicate-id finding below); each result is the tool's ``result`` object."""
    barrier = threading.Barrier(2)

    def go(rid: int) -> dict[str, Any]:
        barrier.wait(timeout=10)
        return post_tool(rig, tool, arguments, rid).json()["result"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        return [f.result(timeout=40) for f in [pool.submit(go, 101), pool.submit(go, 102)]]


# -- (1) two simultaneous "yes" -------------------------------------------------------------------------------------
def test_two_simultaneous_yes_for_one_follow_up_answer_save_exactly_one_answer(rig: Rig):
    for i in range(ROUNDS):
        check_id = _store_check(rig.source, days_ago=ROUNDS + 1 - i, urgency=Urgency.WATCH)  # each one newer
        first = rig.call("report_health_follow_up", house="shed 1", outcome="same")["structuredContent"]
        assert first["status"] == "needs_confirmation"
        results = both_at_once(
            rig,
            "report_health_follow_up",
            house="shed 1",
            outcome="same",
            proposal_id=first["proposal_id"],
            answer="yes",
        )
        shown = [r["structuredContent"] for r in results]
        assert all(s["status"] == "changed" for s in shown), shown
        assert sorted(s["replayed"] for s in shown) == [False, True], shown  # one applied it, one saw it already done
        rows = rig.source.store.follow_up_answers(rig.source.farm_id, check_id)
        assert len(rows) == 1, (i, len(rows))


def test_two_simultaneous_yes_for_one_vet_handoff_send_exactly_one_handoff(rig: Rig):
    for i in range(ROUNDS):
        check_id = _store_check(rig.source, days_ago=ROUNDS + 1 - i, urgency=Urgency.URGENT)
        first = rig.call("prepare_vet_handoff", house="shed 1", check_id=check_id)["structuredContent"]
        assert first["status"] == "needs_confirmation", first
        results = both_at_once(
            rig,
            "prepare_vet_handoff",
            house="shed 1",
            check_id=check_id,
            proposal_id=first["proposal_id"],
            answer="yes",
        )
        assert all(not r.get("isError") for r in results), results
        count = rig.source.store._db.execute(
            "SELECT COUNT(*) FROM vet_handoffs WHERE check_id = ?", (check_id,)
        ).fetchone()[0]
        assert count == 1, (i, count)


# -- (2) two simultaneous health checks on one shed ------------------------------------------------------------------
def stored_checks(rig: Rig, house_id: str) -> int:
    return rig.source.store._db.execute(
        "SELECT COUNT(*) FROM health_checks WHERE house_id = ?", (house_id,)
    ).fetchone()[0]


def test_two_simultaneous_identical_health_checks_store_one_check_and_report_the_other_as_a_duplicate(rig: Rig):
    """The start is one atomic step: the same words and record-book facts within ten minutes are the same check. Each
    round uses new signs, so it is not a duplicate of the previous round's check."""
    for i in range(ROUNDS):
        results = both_at_once(rig, "start_health_check", house="shed 2", signs=[SIGNS[i]])
        assert all(not r.get("isError") for r in results), results
        shown = [r["structuredContent"] for r in results]
        assert len({s["check_id"] for s in shown}) == 1, (i, shown)
        assert sorted(s["duplicate"] for s in shown) == [False, True], (i, shown)
        assert stored_checks(rig, "house-2") == i + 1, i


def test_two_simultaneous_different_health_checks_on_one_shed_are_both_stored_and_consistent(rig: Rig):
    for i in range(ROUNDS // 2):
        barrier = threading.Barrier(2)
        signs = ([SIGNS[2 * i]], [SIGNS[2 * i + 1]])  # a different pair each round, so no round matches the last

        def go(rid: int, mine: list[str], barrier: threading.Barrier = barrier) -> dict[str, Any]:
            barrier.wait(timeout=10)
            return post_tool(rig, "start_health_check", {"house": "shed 3", "signs": mine}, rid).json()["result"]

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(go, 201 + k, signs[k]) for k in range(2)]
            results = [f.result(timeout=40) for f in futures]
        assert all(not r.get("isError") for r in results), results
        shown = [r["structuredContent"] for r in results]
        assert not any(s["duplicate"] for s in shown), shown
        assert len({s["check_id"] for s in shown}) == 2, shown  # nothing merged or lost
        for s in shown:
            stored = rig.source.store.get_health_check(s["check_id"])
            assert stored is not None and stored.house_id == "house-3"
    assert stored_checks(rig, "house-3") == ROUNDS  # every one of the 2 x (ROUNDS // 2) checks is there
    rig.runner.run_all()  # the queued triage jobs finish; the store stays consistent
    assert not rig.call("get_health_check", house="shed 3").get("isError")


# -- (3) 50 parallel initialize requests -----------------------------------------------------------------------------
def test_fifty_parallel_initialize_requests_give_fifty_distinct_working_sessions_that_all_end():
    holder: list[Any] = []
    live, stop = _start({}, customize=holder.append)
    try:
        manager = holder[0].session_manager
        base = len(manager._server_instances)

        def init(_: int) -> str:
            sid, body = live.initialize()
            assert body["result"]["protocolVersion"] == "2025-11-25"
            return sid

        with ThreadPoolExecutor(max_workers=50) as pool:
            ids = list(pool.map(init, range(50)))
        assert len(set(ids)) == 50 and all(len(i) == 32 for i in ids)
        assert len(manager._server_instances) == base + 50
        with ThreadPoolExecutor(max_workers=25) as pool:  # each session works, concurrently
            lists = list(pool.map(lambda sid: live.call(sid, "tools/list")["result"]["tools"], ids))
        assert all(lists)
        with ThreadPoolExecutor(max_workers=25) as pool:
            ends = list(pool.map(lambda sid: httpx2.delete(live.url, headers=live.headers(sid), timeout=10), ids))
        assert all(r.status_code == 200 for r in ends)
        assert len(manager._server_instances) == base
        live.initialize()  # healthy afterwards
    finally:
        stop()


# -- (4) the Accept finding: what a rejected request leaves behind --------------------------------------------------
def settled(manager: Any, expected: int | None = None, timeout: float = 5.0) -> int:
    """The session count once the server has finished discarding the transports it built for rejected requests (that
    clean-up runs on the server thread, a moment after the response; CI flake of 2026-10-03). With ``expected`` it waits
    until the count equals it; without, until the count is the same on two reads 50 ms apart. A session that is really
    kept never goes away, so a leak still fails after ``timeout`` seconds."""
    deadline = time.monotonic() + timeout
    last = len(manager._server_instances)
    while time.monotonic() < deadline:
        time.sleep(0.05)
        now = len(manager._server_instances)
        if (now == expected) if expected is not None else (now == last):
            return now
        last = now
    return len(manager._server_instances)


@pytest.fixture
def sessions():
    holder: list[Any] = []
    live, stop = _start({}, customize=holder.append)
    yield live, holder[0].session_manager
    stop()


INIT_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}},
}


def test_a_post_with_no_accept_for_json_is_406_and_leaves_no_session_behind_pinned_finding(
    sessions: tuple[LiveServer, Any],
):
    """FINDING (answered): the SDK builds a transport for a request with no session id before it checks Accept, so the
    406 carries an ``mcp-session-id`` header and the log says "Created new transport". The session is not kept: the
    count does not grow, however many are sent, and the id in the header is not usable (404). No leak."""
    live, manager = sessions
    before = settled(manager)
    ids = []
    for _ in range(25):
        r = httpx2.post(
            live.url,
            json=INIT_BODY,
            headers={"content-type": "application/json", "accept": "text/event-stream"},
            timeout=10,
        )
        assert r.status_code == 406
        ids.append(r.headers.get("mcp-session-id"))
    assert settled(manager, before) == before
    stray = next(i for i in ids if i)
    assert live.post({"jsonrpc": "2.0", "id": 2, "method": "ping"}, session_id=stray).status_code == 404


@pytest.mark.parametrize(
    ("what", "kwargs", "status"),
    [
        ("a non-JSON content type", {"content": b"{}", "headers": {"content-type": "text/plain"}}, 400),
        ("malformed JSON", {"content": b"{", "headers": {"content-type": "application/json"}}, 400),
        ("a body that is not a request", {"content": b"null", "headers": {"content-type": "application/json"}}, 400),
        ("a foreign Origin", {"json": INIT_BODY, "headers": {"origin": "http://evil.example"}}, 403),
        ("an unsupported version header", {"json": INIT_BODY, "headers": {"mcp-protocol-version": "2026-07-28"}}, 400),
    ],
)
def test_no_other_rejected_request_leaves_a_session_behind(sessions: tuple[LiveServer, Any], what, kwargs, status):
    live, manager = sessions
    before = settled(manager)
    headers = {"accept": "application/json, text/event-stream", **kwargs.pop("headers")}
    for _ in range(10):
        assert httpx2.post(live.url, headers=headers, timeout=10, **kwargs).status_code == status, what
    assert settled(manager, before) == before, what


def test_an_initialize_that_is_never_ended_keeps_its_session_until_the_idle_timeout_pinned(
    sessions: tuple[LiveServer, Any],
):
    """Sessions that clients open and never end are the only way the count grows: each lives until the SDK's idle
    timeout (30 minutes) and at most 10,000 are open at once, then new ones get 503. Both are SDK defaults (we pass
    none); the server is bound to 127.0.0.1 by default and needs a bearer token off localhost."""
    live, manager = sessions
    assert manager.session_idle_timeout == 30 * 60
    assert manager.max_sessions == 10_000
    before = settled(manager)
    for _ in range(5):
        live.initialize()
    assert settled(manager, before + 5) == before + 5  # never ended: still open


# -- a finding from this part: two requests in flight with the same JSON-RPC id --------------------------------------
def test_two_overlapping_requests_with_the_same_id_leave_one_unanswered_pinned_finding(rig: Rig):
    """FINDING: if a client sends two requests at once with the same JSON-RPC id in one session, one is answered and
    the other never is (observed: no answer in 40 s; this test waits 3 s). The SDK keys its replies by id. The
    protocol requires unique ids, so this is a client bug, but the unanswered request holds its connection open. Other
    requests on the session, and the session itself, keep working. Reported; not changed."""
    barrier = threading.Barrier(2)

    def go(_: int) -> str:
        barrier.wait(timeout=10)
        try:
            r = post_tool(rig, "get_help", {}, rid=5, timeout=3)
            return (
                str(r.status_code) if "Session terminated" in r.text or r.status_code == 200 else f"other {r.text[:80]}"
            )
        except httpx2.ReadTimeout:
            return "unanswered"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(go, [0, 1]))
    # One request is answered. The other either stays unanswered or, when the first one's clean-up closes the stream
    # they share, is answered 500 with the SDK's own "Session terminated before the request completed" (seen on CI,
    # Windows 3.13, 2026-10-03; never in 40 local runs). Never two answers, and no other status or text.
    assert outcomes in (["200", "unanswered"], ["200", "500"]), outcomes
    assert not rig.call("get_help").get("isError")  # the session still serves new requests
    ended = httpx2.delete(rig.live.url, headers=rig.live.headers(rig.sid), timeout=10)
    assert ended.status_code == 200  # and can still be ended
