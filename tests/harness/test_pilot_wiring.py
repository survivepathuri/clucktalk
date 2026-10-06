"""Step 51 part A: the real server and Simulator started as subprocesses in pilot mode. A bad or missing farm file stops
the start with exit code 2; a good one starts a server whose answers say "not demo data"; a pilot never reads the
demo's default weather file; and the demo instance still starts exactly as before."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import probe_protocol_version as probe  # noqa: E402

HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
EXAMPLE = ROOT / "docs" / "pilot_farm.example.json"


def _env(tmp: Path, port: int, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in probe.DROPPED_ENV and not k.startswith("CLUCKTALK_")}
    env.update(
        MOCK_BEDROCK="true",
        CLUCKTALK_PORT=str(port),
        CLUCKTALK_MODE="pilot",
        CLUCKTALK_AUTH_TOKEN="mcp-secret-token-0123456789-abcdefgh",
        CLUCKTALK_PILOT_FARM_PATH=str(tmp / "farm.json"),
        CLUCKTALK_STATE_PATH=str(tmp / "state" / "pilot_state.sqlite3"),
        PYTHONPATH=str(ROOT / "src"),
        PYTHONIOENCODING="utf-8",
        PYTHONUNBUFFERED="1",
    )
    env.update(extra)
    return env


def _run_to_exit(env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-B", "-m", "clucktalk.server"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=40,
    )


def _farm(tmp: Path, data: dict | str | None = None) -> None:
    (tmp / "state").mkdir(exist_ok=True)
    if data is None:
        shutil.copy(EXAMPLE, tmp / "farm.json")
    else:
        (tmp / "farm.json").write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def _call(port: int, name: str, args: dict) -> dict:
    url = f"http://127.0.0.1:{port}/mcp"
    with httpx2.Client(timeout=20) as c:
        init = c.post(
            url,
            headers=HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "t", "version": "0"},
                },
            },
        )
        h = {**HEADERS, "mcp-session-id": init.headers["mcp-session-id"], "mcp-protocol-version": "2025-11-25"}
        c.post(url, headers=h, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        r = c.post(
            url,
            headers=h,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": args}},
        )
        c.delete(url, headers=h)
        return r.json()["result"]


def test_a_missing_pilot_farm_file_stops_the_start_with_exit_two():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "state").mkdir()
        done = _run_to_exit(_env(tmp, probe._free_port()))
        assert done.returncode == 2 and "Pilot farm file error" in done.stderr and "not found" in done.stderr


def test_a_pilot_farm_file_with_a_name_stops_the_start_and_never_falls_back_to_the_demo():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        data["name"] = "somebody"
        _farm(tmp, data)
        done = _run_to_exit(_env(tmp, probe._free_port()))
        assert done.returncode == 2 and "unknown field" in done.stderr
        assert "Endpoint:" not in done.stdout  # it never got as far as serving anything


def test_pilot_refuses_to_start_on_the_demo_state_file():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _farm(tmp)
        env = _env(tmp, probe._free_port(), CLUCKTALK_STATE_PATH=str(ROOT / ".local" / "pilot_state.sqlite3"))
        done = _run_to_exit(env)
        assert done.returncode == 2 and "demo" in done.stderr


def test_a_good_pilot_server_starts_says_pilot_and_answers_with_no_demo_data():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _farm(tmp)
        port = probe._free_port()
        log = tmp / "server.log"
        out = log.open("wb")
        proc = subprocess.Popen(
            [sys.executable, "-B", "-m", "clucktalk.server"], cwd=ROOT, env=_env(tmp, port), stdout=out, stderr=out
        )
        try:
            assert probe._wait_for_port(port, proc, 25), log.read_text(encoding="utf-8", errors="replace")
            book = _call(port, "get_record_book", {})
            out.flush()
            text = log.read_text(encoding="utf-8", errors="replace")
        finally:
            probe._stop(proc)
            out.close()
        assert "PILOT (real farm, prototype)" in text and "DEMO DATA" not in text
        assert "Weather reminders: off" in text  # no explicit path: the demo's default file is never read
        assert book["structuredContent"]["demo_data"] is False
        assert book["structuredContent"]["houses_total"] == 2
        assert (tmp / "state" / "pilot_state.sqlite3").exists()  # its own file, in its own folder


def test_a_pilot_never_reads_the_demo_default_weather_file():
    default = ROOT / ".local" / "weather_rules.json"
    existed = default.exists()
    default.parent.mkdir(exist_ok=True)
    if not existed:
        shutil.copy(ROOT / "docs" / "weather_rules.example.json", default)
    try:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _farm(tmp)
            port = probe._free_port()
            log = tmp / "server.log"
            out = log.open("wb")
            proc = subprocess.Popen(
                [sys.executable, "-B", "-m", "clucktalk.server"], cwd=ROOT, env=_env(tmp, port), stdout=out, stderr=out
            )
            try:
                assert probe._wait_for_port(port, proc, 25)
                out.flush()
                text = log.read_text(encoding="utf-8", errors="replace")
            finally:
                probe._stop(proc)
                out.close()
            assert "Weather reminders: off" in text
    finally:
        if not existed:
            default.unlink()
