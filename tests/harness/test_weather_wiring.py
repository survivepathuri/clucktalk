"""Step 50W-B part C: the real server (a subprocess) reads the weather rules file at startup. No file: the feature is
off and the answers carry nothing weather-related. With the committed example file: simulated, example-labelled lines
(they appear only when the simulated forecast crosses the example numbers at the time of day the test runs). A bad
file stops the start with exit code 2. The live Open-Meteo adapter is never called here: no tool is called when it is
switched on."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import probe_protocol_version as probe  # noqa: E402

HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}


def _start(extra_env: dict[str, str], tmp: Path):
    port = probe._free_port()
    env = {k: v for k, v in os.environ.items() if k not in probe.DROPPED_ENV and not k.startswith("CLUCKTALK_WEATHER")}
    env.update(
        MOCK_BEDROCK="true",
        CLUCKTALK_PORT=str(port),
        CLUCKTALK_STATE_PATH=str(tmp / "weather_wiring.sqlite3"),
        PYTHONPATH=str(ROOT / "src"),
        PYTHONIOENCODING="utf-8",
        PYTHONUNBUFFERED="1",  # the startup banner reaches the log file at once
        **extra_env,
    )
    log = tmp / "server.log"
    out = log.open("wb")
    proc = subprocess.Popen([sys.executable, "-B", "-m", "clucktalk.server"], cwd=ROOT, env=env, stdout=out, stderr=out)
    return proc, port, log, out


def _status(port: int) -> dict:
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
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "get_farm_status", "arguments": {}},
            },
        )
        c.delete(url, headers=h)
        return r.json()["result"]["structuredContent"]


def _run(extra_env: dict[str, str], ask: bool = True) -> tuple[dict | None, str]:
    with tempfile.TemporaryDirectory() as d:
        proc, port, log, out = _start(extra_env, Path(d))
        try:
            if not probe._wait_for_port(port, proc, 25):
                out.flush()
                return None, log.read_text(encoding="utf-8", errors="replace")
            time.sleep(0.2)
            status = _status(port) if ask else None
            out.flush()
            return status, log.read_text(encoding="utf-8", errors="replace")
        finally:
            probe._stop(proc)
            out.close()


def test_no_rules_file_means_the_feature_is_off_and_the_answer_has_no_weather():
    status, log = _run({"CLUCKTALK_WEATHER_RULES_PATH": str(ROOT / ".local" / "no_such_weather_rules.json")})
    assert status is not None and "weather_reminders" not in status and "Forecast" not in status["text_en"]
    assert "Weather reminders: off (no rules file" in log


def test_the_example_file_gives_simulated_example_labelled_lines_only():
    status, log = _run({"CLUCKTALK_WEATHER_RULES_PATH": str(ROOT / "docs" / "weather_rules.example.json")})
    assert "Weather reminders: ON, 2 rule(s) from the farmer's file, SIMULATED forecast" in log
    assert isinstance(status["weather_reminders"], list) and len(status["weather_reminders"]) <= 2
    for line in status["weather_reminders"]:
        assert line["simulated"] is True and line["is_example"] is True and line["source"] == "simulated"
        assert line["text_en"].startswith(
            "Demo data. Forecast (hourly, outdoors at your farm's location, source: Simulated;"
        )
        assert line["text_en"] in status["text_en"]


def test_a_bad_rules_file_stops_the_start_with_exit_code_two_and_a_clear_message():
    with tempfile.TemporaryDirectory() as d:
        bad = Path(d) / "weather_rules.json"
        bad.write_text(json.dumps({"latitude": 1, "longitude": 2, "rules": [{"id": "x"}]}), encoding="utf-8")
        env = {
            **os.environ,
            "MOCK_BEDROCK": "true",
            "CLUCKTALK_PORT": str(probe._free_port()),
            "PYTHONPATH": str(ROOT / "src"),
        }
        env.pop("CLUCKTALK_DEMO_DAYS_LATER", None)
        env.update(CLUCKTALK_WEATHER_RULES_PATH=str(bad), CLUCKTALK_STATE_PATH=str(Path(d) / "s.sqlite3"))
        done = subprocess.run(
            [sys.executable, "-B", "-m", "clucktalk.server"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    assert done.returncode == 2 and "Weather configuration error" in done.stderr and "stat" in done.stderr
    assert "Traceback" not in done.stderr


def test_the_live_flag_starts_the_server_without_asking_any_weather_service():
    with tempfile.TemporaryDirectory() as d:
        rules = Path(d) / "weather_rules.json"
        rules.write_text(json.dumps({"latitude": 1, "longitude": 2, "rules": []}), encoding="utf-8")
        status, log = _run({"CLUCKTALK_WEATHER_RULES_PATH": str(rules), "CLUCKTALK_WEATHER_LIVE": "true"}, ask=False)
    assert (
        status is None
        and "Weather reminders: ON, 0 rule(s) from the farmer's file, live Open-Meteo forecast (opt-in)" in log
    )
