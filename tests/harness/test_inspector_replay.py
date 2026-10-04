"""Step 49 part A: ``python tasks.py inspector-replay`` (scripts/inspector_replay.py) is OUR replay of the flow
documented on Amazon's Local Inspector page: Accept ``application/json`` only, protocolVersion 2025-06-18, clientInfo
``addon-local-inspector``, initialized notification, tools/list, resources/read for every ui:// resource and a
tools/call for every tool. It runs on a temporary state file, never the live one, and says it is not Amazon's tool."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import tasks  # noqa: E402
from clucktalk.config import DEFAULT_STATE_PATH  # noqa: E402

spec = importlib.util.spec_from_file_location("inspector_replay_under_test", ROOT / "scripts" / "inspector_replay.py")
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)  # type: ignore[union-attr]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "absent"


# -- pure helpers --------------------------------------------------------------------------------------------------
def test_percentile_is_nearest_rank():
    values = list(range(1, 21))  # 1..20
    assert replay.percentile(values, 50) == 10 and replay.percentile(values, 95) == 19
    assert replay.percentile([7], 95) == 7 and replay.percentile([3, 1, 2], 100) == 3


def test_summarize_gives_p50_p95_max_and_all_ok_per_step():
    rounds = [[("a", 200, True, float(i)), ("b", 500, False, 1.0)] for i in range(1, 21)]
    by = {r[0]: r for r in replay.summarize(rounds)}
    assert by["a"][1:4] == (10.0, 19.0, 20.0) and by["a"][4] is True and by["b"][4] is False


def test_the_table_is_aligned():
    out = replay.format_table(("step", "ms"), [("tools/list", "4.4"), ("x", "10.0")]).splitlines()
    assert len(out) == 4 and out[0].startswith("step       | ms") and set(out[1]) <= set("-+")


# -- the exact requests, seen by a stub server ----------------------------------------------------------------------
class Stub(BaseHTTPRequestHandler):
    seen: list[tuple[dict, dict]] = []

    def log_message(self, *args):  # silence
        pass

    def do_DELETE(self):
        self.send_response(200)
        self.send_header("content-length", "0")
        self.end_headers()

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        Stub.seen.append(({k.lower(): v for k, v in self.headers.items()}, body))
        method = body["method"]
        if method == "notifications/initialized":
            self.send_response(202)
            self.send_header("content-length", "0")
            self.end_headers()
            return
        result = {
            "initialize": {"protocolVersion": "2025-06-18"},
            "tools/list": {"tools": [{"name": "get_help"}, {"name": "plan_feed"}]},
            "resources/list": {"resources": [{"uri": "ui://x/a.html"}, {"uri": "http://not-ui"}]},
        }.get(method, {"contents": []})
        data = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result}).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        if method == "initialize":
            self.send_header("mcp-session-id", "sid-1")
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def stub():
    Stub.seen = []
    server = HTTPServer(("127.0.0.1", 0), Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/mcp"
    server.shutdown()


def test_the_flow_is_the_documented_one_with_json_only_accept(stub):
    steps = replay.run_round(stub)
    methods = [b["method"] for _, b in Stub.seen]
    assert methods == [
        "initialize",
        "notifications/initialized",
        "tools/list",
        "resources/list",
        "resources/read",
        "tools/call",
        "tools/call",
    ]
    assert all(h.get("accept") == "application/json" for h, _ in Stub.seen)  # JSON ONLY, no event-stream
    init = Stub.seen[0][1]["params"]
    assert init["protocolVersion"] == "2025-06-18" and init["clientInfo"]["name"] == "addon-local-inspector"
    after = [h for h, _ in Stub.seen[1:]]
    assert all(h.get("mcp-session-id") == "sid-1" and h.get("mcp-protocol-version") == "2025-06-18" for h in after)
    assert [b["params"]["uri"] for _, b in Stub.seen if b["method"] == "resources/read"] == ["ui://x/a.html"]
    assert [s[0] for s in steps][-2:] == ["tools/call get_help", "tools/call plan_feed"]
    assert all(ok for _, _, ok, _ in steps)


def test_a_non_json_answer_is_not_ok():
    class SSE(Stub):
        def do_POST(self):
            data = b"event: message\ndata: {}\n\n"
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = HTTPServer(("127.0.0.1", 0), SSE)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        first = replay.Replay(f"http://127.0.0.1:{server.server_port}/mcp")
        step = first.initialize_and_keep_session()
    finally:
        server.shutdown()
    assert step[0] == "initialize" and step[2] is False


# -- the real thing --------------------------------------------------------------------------------------------------
def test_the_fixture_has_arguments_for_exactly_the_servers_tools():
    with replay.running_server() as url:
        r = replay.Replay(url)
        try:
            r.initialize_and_keep_session()
            r.initialized()
            _, tools = r.tools_list()
        finally:
            r.close()
    assert sorted(t["name"] for t in tools) == sorted(replay.TOOL_ARGUMENTS)


def test_a_real_run_replays_every_step_says_whose_replay_it_is_and_leaves_the_live_state_alone(capsys):
    before = _sha(DEFAULT_STATE_PATH)
    assert replay.main(rounds=2) == 0
    out = capsys.readouterr().out
    assert out.count("not Amazon's tool") == 2 and "FL-024" in out
    assert "Accept: application/json only handled correctly" in out and "): yes" in out
    for tool in replay.TOOL_ARGUMENTS:
        assert f"tools/call {tool}" in out
    assert out.count("resources/read ui://clucktalk/") >= 8  # four cards, in both tables
    assert "p95" in out and "Steps not ok: none" in out
    assert _sha(DEFAULT_STATE_PATH) == before


def test_tasks_has_the_command_and_it_takes_no_arguments(monkeypatch):
    assert tasks.COMMANDS["inspector-replay"] is tasks.inspector_replay
    monkeypatch.setattr(tasks.sys, "argv", ["tasks.py", "inspector-replay", "--rounds", "1"])
    assert tasks.main() == 2


def test_a_json_body_with_an_event_stream_content_type_is_not_ok():
    class WrongType(Stub):
        def do_POST(self):
            data = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}).encode()
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = HTTPServer(("127.0.0.1", 0), WrongType)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        step, _ = replay.Replay(f"http://127.0.0.1:{server.server_port}/mcp").tools_list()
    finally:
        server.shutdown()
    assert step[1] == 200 and step[2] is False


def test_a_step_that_is_not_ok_gives_exit_code_one_and_is_named(stub, monkeypatch, capsys):
    class Failing(Stub):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            if body["method"] == "tools/call":
                data = json.dumps(
                    {"jsonrpc": "2.0", "id": body["id"], "error": {"code": -32603, "message": "x"}}
                ).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.rfile = __import__("io").BytesIO(json.dumps(body).encode())
            self.headers.replace_header("content-length", str(len(json.dumps(body).encode())))
            super().do_POST()

    server = HTTPServer(("127.0.0.1", 0), Failing)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    from contextlib import contextmanager

    @contextmanager
    def fake_server(*_a, **_k):
        yield f"http://127.0.0.1:{server.server_port}/mcp"

    monkeypatch.setattr(replay, "running_server", fake_server)
    try:
        assert replay.main(rounds=1) == 1
    finally:
        server.shutdown()
    assert "tools/call get_help" in capsys.readouterr().out
