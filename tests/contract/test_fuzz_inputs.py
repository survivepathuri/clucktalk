"""Step 48B part B: input and protocol fuzzing over real HTTP (a fixed corpus plus Hypothesis strategies).

For every input, valid or not, the server must: answer with a status below 500; never put a Python traceback, a file
path or a pydantic message in a response; answer an invalid request with a short JSON-RPC or tool error that does not
echo the oversized input; leave the state file byte-for-byte unchanged when the answer is an error; and stay healthy
(a fresh ``initialize`` and ``tools/list`` still work). The server runs on a file-backed state so the hash is real."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from clucktalk.agents import AiServices
from clucktalk.agents.model import RulesModel
from clucktalk.agents.runner import ManualRunner
from clucktalk.server.farm_state import DemoFarmSource
from clucktalk.store.sqlite import SqliteStore
from tests.contract.conftest import FIXED_DAY, LiveServer, _start

LEAKS = re.compile(r"Traceback|File \"|site-packages|\.py\"|pydantic|ValidationError|sqlite3\.|errors\.pydantic\.dev")
MAX_ERROR_BYTES = 4000  # an error answer is short whatever was sent
FUZZ = settings(
    max_examples=120,
    derandomize=True,
    deadline=None,  # Windows timers (FL-023)
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture],
    database=None,
)


class Rig:
    def __init__(self, live: LiveServer, store_path: Path) -> None:
        self.live = live
        self.store_path = store_path
        self.sid, _ = live.initialize()

    def state(self) -> str:
        """Every row of every table, as text: the state file's content, independent of file-header bookkeeping."""
        with sqlite3.connect(f"file:{self.store_path.as_posix()}?mode=ro", uri=True) as db:
            return "\n".join(db.iterdump())

    def post_raw(self, body: bytes, **headers: str) -> httpx2.Response:
        h = self.live.headers(self.sid, **headers)
        return httpx2.post(self.live.url, content=body, headers=h, timeout=30)

    def call(self, method: str, params: Any = None, rid: Any = 7) -> httpx2.Response:
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            body["params"] = params
        return self.post_raw(json.dumps(body, ensure_ascii=False).encode("utf-8"))

    def healthy(self) -> None:
        sid, body = self.live.initialize()
        assert body["result"]["protocolVersion"] == "2025-11-25"
        listed = self.live.call(sid, "tools/list")
        assert listed["result"]["tools"], listed
        assert self.live.call(sid, "tools/call", {"name": "get_help", "arguments": {}})["result"]["content"]


@pytest.fixture(scope="module")
def rig(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Rig]:
    path = tmp_path_factory.mktemp("fuzz") / "farm.sqlite3"
    source = DemoFarmSource(clock=lambda: FIXED_DAY, store=SqliteStore(path))
    # A job queue the test drives itself: an accepted health check is never analysed in the background, so no stored
    # row changes between the "before" and "after" snapshots of an error answer (CI flake of 2026-10-03: a row went
    # from "analyzing" to "ready" in between on Windows).
    ai = AiServices(model=RulesModel(), budget=None, runner=ManualRunner())
    live, stop = _start({}, source=source, ai=ai)
    yield Rig(live, path)
    stop()
    source.store.close()


STRICT_LEAKS = re.compile(r"Traceback|File \"|site-packages|\.py\"|sqlite3\.")  # never allowed, in any answer


def assert_safe(r: httpx2.Response, what: str) -> None:
    assert r.status_code < 500, (what, r.status_code, r.text[:300])
    assert not STRICT_LEAKS.search(r.text), (what, STRICT_LEAKS.search(r.text).group(0), r.text[:300])
    assert not LEAKS.search(r.text), (what, LEAKS.search(r.text).group(0), r.text[:300])
    if r.status_code >= 400 or '"isError":true' in r.text or '"error"' in r.text[:200]:
        assert len(r.content) <= MAX_ERROR_BYTES, (what, len(r.content))  # an error never echoes the input back


def is_error(r: httpx2.Response) -> bool:
    if r.status_code >= 400:
        return True
    try:
        body = r.json()
    except ValueError:
        return False
    return isinstance(body, dict) and ("error" in body or bool(body.get("result", {}).get("isError")))


def probe(rig: Rig, r: httpx2.Response, what: str, before: str) -> None:
    """The three checks every input gets; the state check applies to every answer that is an error."""
    assert_safe(r, what)
    if is_error(r):
        assert rig.state() == before, (what, "an error answer changed the saved state")


# -- a fixed corpus --------------------------------------------------------------------------------------------------
BIG = "x" * 1_000_000
NESTED = "[" * 5000 + "]" * 5000
DEEP_OBJECT = '{"a":' * 3000 + "1" + "}" * 3000
RAW_BODIES: dict[str, bytes] = {
    "empty": b"",
    "just a brace": b"{",
    "truncated": b'{"jsonrpc":"2.0","id":1,"method":"tools/li',
    "null": b"null",
    "number": b"42",
    "string": b'"hello"',
    "empty array (an empty batch)": b"[]",
    "array of junk": b"[1,2,3]",
    "null byte": b"\x00",
    "null byte in json": b'{"jsonrpc":"2.0","id":1,"method":"tools/list\x00"}',
    "invalid utf-8": b'{"jsonrpc":"2.0","id":1,"method":"\xff\xfe"}',
    "utf-8 bom": b'\xef\xbb\xbf{"jsonrpc":"2.0","id":1,"method":"ping"}',
    "nan": b'{"jsonrpc":"2.0","id":NaN,"method":"ping"}',
    "deeply nested array": NESTED.encode(),
    "deeply nested object": DEEP_OBJECT.encode(),
    "deep params": ('{"jsonrpc":"2.0","id":1,"method":"tools/call","params":' + DEEP_OBJECT + "}").encode(),
    "huge method": json.dumps({"jsonrpc": "2.0", "id": 1, "method": BIG}).encode(),
    "huge id": json.dumps({"jsonrpc": "2.0", "id": BIG, "method": "ping"}).encode(),
    "duplicate keys": b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping","method":"tools/list"}',
    "no method": b'{"jsonrpc":"2.0","id":1}',
    "method is a number": b'{"jsonrpc":"2.0","id":1,"method":5}',
    "method is a list": b'{"jsonrpc":"2.0","id":1,"method":["ping"]}',
    "wrong jsonrpc version": b'{"jsonrpc":"1.0","id":1,"method":"ping"}',
    "id is an object": b'{"jsonrpc":"2.0","id":{"a":1},"method":"ping"}',
    "id is a list": b'{"jsonrpc":"2.0","id":[1],"method":"ping"}',
    "id is a float": b'{"jsonrpc":"2.0","id":1.5,"method":"ping"}',
    "id is a huge int": b'{"jsonrpc":"2.0","id":' + b"9" * 5000 + b',"method":"ping"}',
    "params is a string": b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":"x"}',
    "params is a list": b'{"jsonrpc":"2.0","id":1,"method":"tools/call","params":[1,2]}',
    "unknown method": b'{"jsonrpc":"2.0","id":1,"method":"no/such/method"}',
    "a response, not a request": b'{"jsonrpc":"2.0","id":1,"result":{}}',
    "batch with duplicate ids": b'[{"jsonrpc":"2.0","id":1,"method":"ping"},{"jsonrpc":"2.0","id":1,"method":"ping"}]',
    "a notification with an id-less call": b'{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_help"}}',
}


@pytest.mark.parametrize("name", list(RAW_BODIES))
def test_raw_body_corpus(rig: Rig, name: str):
    before = rig.state()
    r = rig.post_raw(RAW_BODIES[name])
    probe(rig, r, name, before)
    rig.healthy()


TOOL_CALLS: dict[str, dict[str, Any]] = {
    "unknown tool": {"name": "no_such_tool", "arguments": {}},
    "tool name is a number": {"name": 5, "arguments": {}},
    "tool name is huge": {"name": BIG, "arguments": {}},
    "arguments is a string": {"name": "get_farm_status", "arguments": "x"},
    "arguments is a list": {"name": "get_farm_status", "arguments": [1]},
    "arguments is null": {"name": "get_farm_status", "arguments": None},
    "house is a number": {"name": "get_farm_status", "arguments": {"house": 7}},
    "house is a list": {"name": "get_farm_status", "arguments": {"house": ["shed 1"]}},
    "house is an object": {"name": "get_farm_status", "arguments": {"house": {"a": 1}}},
    "house is huge": {"name": "get_farm_status", "arguments": {"house": BIG}},
    "house has null bytes": {"name": "get_farm_status", "arguments": {"house": "shed\x00 1"}},
    "house is deeply nested": {"name": "get_farm_status", "arguments": {"house": json.loads("[" * 200 + "]" * 200)}},
    "extra argument": {"name": "get_farm_status", "arguments": {"house": "shed 1", "evil": "x" * 100}},
    "signs is a huge array": {
        "name": "start_health_check",
        "arguments": {"house": "shed 1", "signs": ["coughing"] * 200_000},
    },
    "signs has unknown values": {
        "name": "start_health_check",
        "arguments": {"house": "shed 1", "signs": ["nonsense", 5, None]},
    },
    "signs is a string": {"name": "start_health_check", "arguments": {"house": "shed 1", "signs": "coughing"}},
    "outcome is wrong": {"name": "report_health_follow_up", "arguments": {"house": "shed 1", "outcome": "fine"}},
    "outcome is a list": {"name": "report_health_follow_up", "arguments": {"house": "shed 1", "outcome": ["better"]}},
    "proposal id is malformed": {
        "name": "report_health_follow_up",
        "arguments": {"house": "shed 1", "outcome": "better", "proposal_id": "x" * 5000, "answer": "yes"},
    },
    "answer without a proposal": {"name": "prepare_vet_handoff", "arguments": {"house": "shed 1", "answer": "yes"}},
    "deaths is huge": {"name": "log_daily_record", "arguments": {"house": "shed 1", "deaths": 10**30}},
    "deaths is negative": {"name": "log_daily_record", "arguments": {"house": "shed 1", "deaths": -5}},
    "deaths is a float": {"name": "log_daily_record", "arguments": {"house": "shed 1", "deaths": 1.5}},
    "deaths is NaN text": {"name": "log_daily_record", "arguments": {"house": "shed 1", "deaths": "NaN"}},
    "date is not a date": {"name": "log_daily_record", "arguments": {"house": "shed 1", "day": "31/02/9999"}},
}


@pytest.mark.parametrize("name", list(TOOL_CALLS))
def test_tool_call_corpus(rig: Rig, name: str):
    before = rig.state()
    r = rig.call("tools/call", TOOL_CALLS[name])
    probe(rig, r, name, before)
    rig.healthy()


# House names: typos, look-alikes, other scripts, emoji, markup. None may crash, leak, or change state when refused.
HOUSE_NAMES = [
    "shde 1", "shed one", "SHED 1", "House1", "shed  1", "shed 01", "shed ١", "shed １", "ѕhed 1", "shеd 1",  # noqa: RUF001
    "shed 1​", "‮shed 1", "షెడ్ 1", "షెడ్ ౧", "షెడ్‌ 1", "🐔 1", "🐔", "<script>alert(1)</script>",
    "shed 1; DROP TABLE records;--", "' OR 1=1 --", "../../etc/passwd", "{{7*7}}", "%s%s%s%n", "\n\n", " ", "",
    "shed 999", "shed -1", "shed 1e3", "0", "-0", "NaN", "null", "None", "true", "x" * 10_000,
]  # fmt: skip


@pytest.mark.parametrize(
    "tool", ["get_farm_status", "get_health_check", "report_health_follow_up", "prepare_vet_handoff"]
)
@pytest.mark.parametrize("house", HOUSE_NAMES, ids=lambda h: repr(h)[:24])
def test_odd_house_names(rig: Rig, tool: str, house: str):
    args: dict[str, Any] = {"house": house}
    if tool == "report_health_follow_up":
        args["outcome"] = "better"
    before = rig.state()
    r = rig.call("tools/call", {"name": tool, "arguments": args})
    probe(rig, r, f"{tool} {house[:30]!r}", before)


def test_the_server_is_healthy_after_the_whole_corpus(rig: Rig):
    rig.healthy()


# -- Hypothesis ------------------------------------------------------------------------------------------------------
json_values = st.recursive(
    st.none()
    | st.booleans()
    | st.integers(-(10**40), 10**40)
    | st.floats(allow_nan=False, allow_infinity=False)
    | st.text(max_size=60),
    lambda children: st.lists(children, max_size=5) | st.dictionaries(st.text(max_size=12), children, max_size=5),
    max_leaves=25,
)
tool_names = st.sampled_from(
    [
        "get_help", "get_farm_status", "get_daily_briefing", "get_health_check", "start_health_check",
        "report_health_follow_up", "prepare_vet_handoff", "log_daily_record", "plan_sale", "plan_feed",
        "get_farm_profile", "set_farm_mode", "set_contract_terms", "get_record_book", "no_such_tool",
    ]
)  # fmt: skip
arg_names = st.sampled_from(["house", "outcome", "signs", "deaths", "day", "proposal_id", "answer", "mode", "x"])


@FUZZ
@given(st.binary(max_size=2000))
def test_random_bytes_are_never_a_500(rig: Rig, body: bytes):
    before = rig.state()
    probe(rig, rig.post_raw(body), repr(body[:40]), before)


@FUZZ
@given(json_values)
def test_random_json_values_are_never_a_500(rig: Rig, value: Any):
    before = rig.state()
    r = rig.post_raw(json.dumps(value).encode())
    probe(rig, r, json.dumps(value)[:60], before)


@FUZZ
@given(tool_names, st.one_of(json_values, st.dictionaries(arg_names, json_values, max_size=5)))
def test_random_tool_arguments_are_never_a_500(rig: Rig, tool: str, arguments: Any):
    before = rig.state()
    r = rig.call("tools/call", {"name": tool, "arguments": arguments})
    probe(rig, r, f"{tool} {json.dumps(arguments)[:60]}", before)


@FUZZ
@given(st.text(max_size=80), st.sampled_from(["get_farm_status", "get_health_check", "plan_sale", "plan_feed"]))
def test_random_house_names_are_never_a_500(rig: Rig, name: str, tool: str):
    before = rig.state()
    r = rig.call("tools/call", {"name": tool, "arguments": {"house": name}})
    probe(rig, r, f"{tool} {name!r}", before)


@FUZZ
@given(st.text(max_size=40), json_values, json_values)
def test_random_methods_and_params_are_never_a_500(rig: Rig, method: str, params: Any, rid: Any):
    before = rig.state()
    r = rig.call(method, params, rid=rid)
    probe(rig, r, f"{method!r}", before)


def test_still_healthy_after_the_random_runs(rig: Rig):
    rig.healthy()


def test_duplicate_request_ids_in_two_calls_each_get_their_own_answer(rig: Rig):
    first = rig.call("tools/call", {"name": "get_help", "arguments": {}}, rid=1)
    second = rig.call("tools/call", {"name": "get_help", "arguments": {}}, rid=1)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"] == 1


# -- findings F1 and F2 (fixed in Step 48C); F3 to F5 are pinned as observed ------------------------------------------
def test_a_body_that_is_not_a_json_rpc_request_gets_a_short_fixed_error_finding_f1_fixed(rig: Rig):
    """FINDING F1 (Step 48B), fixed in Step 48C: ``null``, ``42``, ``[]``, a missing method, a wrong ``jsonrpc`` value
    and the like answered 400 with pydantic's text, a link and the input value. Now one short fixed error; the full
    set is in test_protocol_errors.py."""
    for body in (b"null", b"42", b"[]", b'{"jsonrpc":"2.0","id":1}', b'{"jsonrpc":"1.0","id":1,"method":"ping"}'):
        r = rig.post_raw(body)
        assert r.status_code == 400 and r.json()["error"]["code"] == -32600, (body, r.status_code, r.text[:120])
        assert "pydantic" not in r.text and len(r.content) < 200


def test_an_unknown_method_is_not_echoed_back_finding_f2_fixed(rig: Rig):
    """FINDING F2 (Step 48B), fixed in Step 48C: ``Method not found`` carried the requested method name in ``data``,
    however long (1 MB in, 1 MB out). Now a small standard error without the name."""
    r = rig.post_raw(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "no/such/method"}).encode())
    assert r.json()["error"] == {"code": -32601, "message": "Method not found"}
    big = rig.post_raw(RAW_BODIES["huge method"])
    assert big.json()["error"]["code"] == -32601 and len(big.content) < 200


def test_a_request_body_over_the_size_limit_is_413_and_the_server_stays_healthy(rig: Rig):
    r = rig.post_raw(b'{"jsonrpc":"2.0","id":1,"method":"ping","params":{"x":"' + b"x" * 10_000_000 + b'"}}')
    assert r.status_code == 413 and r.text == "Request body too large"
    rig.healthy()


def test_a_request_id_that_is_an_object_a_list_or_a_float_is_accepted_without_an_answer_pinned_finding_f3(rig: Rig):
    """FINDING F3: JSON-RPC allows only a string, a number or null as an id. These are answered 202 with an empty body
    (treated like a notification) instead of an Invalid Request error. Harmless here, and not a 500."""
    for name in ("id is an object", "id is a list", "id is a float", "nan"):
        r = rig.post_raw(RAW_BODIES[name])
        assert r.status_code == 202 and r.content == b"", name


# -- shed names: a typo or a look-alike is refused or lands on the shed it names, never on another ---------------------
DIGITS = {
    1: ["1", "١", "１", "౧", "१"],  # ASCII, Arabic-Indic, fullwidth, Telugu, Devanagari
    2: ["2", "٢", "２", "౨", "२"],
    3: ["3", "٣", "３", "౩", "३"],
}
PREFIXES = ["", "shed ", "House ", "kotam ", "షెడ్ ", "\U0001f414 ", "-", "the ", "my shed no. ", "shed​ "]
SUFFIXES = ["", " ", "!", "?", ".", "​"]


def resolved(rig: Rig, name: str) -> str | None:
    """The house id a name lands on in a one-shed status, or None when the name is refused."""
    r = rig.call("tools/call", {"name": "get_farm_status", "arguments": {"house": name}})
    assert_safe(r, repr(name))
    result = r.json()["result"]
    if result.get("isError"):
        return None
    houses = result["structuredContent"]["houses"]
    return houses[0]["house_id"] if len(houses) == 1 else "whole-farm"


@FUZZ
@given(
    st.sampled_from([1, 2, 3]).flatmap(lambda n: st.tuples(st.just(n), st.sampled_from(DIGITS[n]))),
    st.sampled_from(PREFIXES),
    st.sampled_from(SUFFIXES),
)
def test_a_name_with_one_number_resolves_to_that_shed_or_is_refused(rig: Rig, number_digit, prefix: str, suffix: str):
    number, digit = number_digit
    assert resolved(rig, f"{prefix}{digit}{suffix}") in (f"house-{number}", None)


@FUZZ
@given(
    st.sampled_from([1, 2, 3]),
    st.sampled_from([1, 2, 3]),
    st.sampled_from(["{} {}", "shed {} shed {}", "{} and {}", "shed {} or {}", "{}-{}"]),
)
def test_a_name_with_two_numbers_is_always_refused(rig: Rig, a: int, b: int, shape: str):
    name = shape.format(DIGITS[a][0], DIGITS[b][0])
    assert resolved(rig, name) is None, name  # never guess which of the two sheds is meant


ACCEPTED = {  # pinned: how the resolver reads these today (domain/houses.py ignores symbols and non-Latin words)
    "shed one": "house-1", "SHED 1": "house-1", "House1": "house-1", "shed 01": "house-1", "the first shed": "house-1",
    "shed ١": "house-1", "shed １": "house-1", "షెడ్ 1": "house-1",
    "shed 1​": "house-1", "shed 2": "house-2", "shed three": "house-3", "3": "house-3",
}  # fmt: skip
REFUSED = [
    "shde 1", "ѕhed 1", "shеd 1", "shed 999", "shed 1e3", "shed 1 please", "0", "-0", "NaN", "None", "true",
    "\U0001f414", "<script>alert(1)</script>", "' OR 1=1 --", "../../etc/passwd", "{{7*7}}", "%s%s%s%n",
]  # fmt: skip


@pytest.mark.parametrize("name", list(ACCEPTED), ids=lambda n: repr(n)[:20])
def test_the_names_the_resolver_accepts_land_on_the_right_shed(rig: Rig, name: str):
    assert resolved(rig, name) == ACCEPTED[name]


@pytest.mark.parametrize("name", REFUSED, ids=lambda n: repr(n)[:20])
def test_typos_look_alikes_and_attack_strings_are_refused_not_guessed(rig: Rig, name: str):
    assert resolved(rig, name) is None


def test_a_minus_sign_or_an_emoji_before_the_number_is_ignored_pinned_finding_f4(rig: Rig):
    """FINDING F4: the resolver reads only ASCII letters and digit runs, so ``shed -1`` and ``<chicken emoji> 1``
    land on shed 1 (the minus sign and the emoji are dropped). It never lands on a different shed, and a mutating
    tool still reads the shed back before it saves. Reported; not changed."""
    assert resolved(rig, "shed -1") == "house-1"
    assert resolved(rig, "\U0001f414 1") == "house-1"


# -- the protocol-version header -------------------------------------------------------------------------------------
HANDSHAKE_VERSIONS = {"2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"}
HEADER_CORPUS = [
    "2026-07-28",
    "1999-01-01",
    "",
    "x" * 8000,
    "2025-11-25,2025-06-18",
    "latest",
    "0",
    "null",
]


def with_version_header(rig: Rig, value: str) -> httpx2.Response:
    headers = rig.live.headers(rig.sid)
    headers["mcp-protocol-version"] = value
    body = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"}).encode()
    return httpx2.post(rig.live.url, content=body, headers=headers, timeout=10)


@pytest.mark.parametrize("value", HEADER_CORPUS, ids=lambda v: repr(v)[:20])
def test_an_unknown_protocol_version_header_is_a_400_with_a_short_json_rpc_error(rig: Rig, value: str):
    before = rig.state()
    r = with_version_header(rig, value)
    assert_safe(r, repr(value)[:30])
    assert r.status_code == 400 and r.json()["error"]["code"] == -32600, (value[:20], r.status_code)
    assert "2025-11-25" in r.json()["error"]["message"] and len(r.content) < 400
    assert rig.state() == before


@FUZZ
@given(st.text(alphabet=st.characters(min_codepoint=33, max_codepoint=126), max_size=40))
def test_random_protocol_version_headers_are_never_a_500(rig: Rig, value: str):
    r = with_version_header(rig, value)
    assert_safe(r, repr(value))
    assert r.status_code == (200 if value in HANDSHAKE_VERSIONS else 400), (value, r.status_code)
