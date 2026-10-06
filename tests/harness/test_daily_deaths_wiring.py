"""Step 51 part B: the real server (a subprocess) reads the farmer's daily deaths rule file at startup. No file: the
feature is off. A good file: it is on. A bad file stops the start with exit code 2. A pilot reads a rule file only from
an explicit path, never the demo's default location."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import probe_protocol_version as probe  # noqa: E402

EXAMPLE_RULE = ROOT / "docs" / "daily_deaths_rule.example.json"
EXAMPLE_FARM = ROOT / "docs" / "pilot_farm.example.json"


def _env(tmp: Path, port: int, pilot: bool, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in probe.DROPPED_ENV and not k.startswith("CLUCKTALK_")}
    env.update(
        MOCK_BEDROCK="true",
        CLUCKTALK_PORT=str(port),
        CLUCKTALK_STATE_PATH=str(tmp / "state" / ("pilot_state.sqlite3" if pilot else "deaths_wiring.sqlite3")),
        PYTHONPATH=str(ROOT / "src"),
        PYTHONIOENCODING="utf-8",
        PYTHONUNBUFFERED="1",
    )
    if pilot:
        env.update(
            CLUCKTALK_MODE="pilot",
            CLUCKTALK_PILOT_FARM_PATH=str(tmp / "farm.json"),
            CLUCKTALK_AUTH_TOKEN="mcp-secret-token-0123456789-abcdefgh",
        )
    env.update(extra)
    return env


def _banner(env: dict[str, str], tmp: Path) -> tuple[str, int | None]:
    """Start the server, read its banner until the port answers, stop it. Returns (log text, exit code or None)."""
    log = tmp / "server.log"
    out = log.open("wb")
    proc = subprocess.Popen([sys.executable, "-B", "-m", "clucktalk.server"], cwd=ROOT, env=env, stdout=out, stderr=out)
    try:
        port = int(env["CLUCKTALK_PORT"])
        ok = probe._wait_for_port(port, proc, 25)
        code = None if ok else proc.poll()
        out.flush()
        return log.read_text(encoding="utf-8", errors="replace"), code
    finally:
        probe._stop(proc)
        out.close()


def _setup(tmp: Path) -> None:
    (tmp / "state").mkdir()
    shutil.copy(EXAMPLE_FARM, tmp / "farm.json")


def test_no_rule_file_means_off():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _setup(tmp)
        env = _env(tmp, probe._free_port(), False, CLUCKTALK_DAILY_DEATHS_RULE_PATH=str(tmp / "none.json"))
        text, _ = _banner(env, tmp)
        assert "Daily deaths rule: off (no rule file; no level is changed)" in text


def test_a_good_rule_file_turns_it_on_and_a_bad_one_stops_the_start():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        _setup(tmp)
        good = tmp / "daily_deaths_rule.json"
        shutil.copy(EXAMPLE_RULE, good)
        env = _env(tmp, probe._free_port(), False, CLUCKTALK_DAILY_DEATHS_RULE_PATH=str(good))
        text, _ = _banner(env, tmp)
        assert "Daily deaths rule: ON" in text
        good.write_text(json.dumps({"per_1000_live": "two"}), encoding="utf-8")
        done = subprocess.run(
            [sys.executable, "-B", "-m", "clucktalk.server"],
            cwd=ROOT,
            env=_env(tmp, probe._free_port(), False, CLUCKTALK_DAILY_DEATHS_RULE_PATH=str(good)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=40,
        )
        assert done.returncode == 2 and "Daily deaths rule error" in done.stderr and "per_1000_live" in done.stderr


def test_a_pilot_reads_a_rule_file_only_from_an_explicit_path():
    default = ROOT / ".local" / "daily_deaths_rule.json"
    existed = default.exists()
    default.parent.mkdir(exist_ok=True)
    if not existed:
        shutil.copy(EXAMPLE_RULE, default)
    try:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _setup(tmp)
            text, _ = _banner(_env(tmp, probe._free_port(), True), tmp)
            assert "Daily deaths rule: off" in text  # the demo's default file exists, and the pilot ignores it
            explicit = tmp / "daily_deaths_rule.json"
            shutil.copy(EXAMPLE_RULE, explicit)
            env = _env(tmp, probe._free_port(), True, CLUCKTALK_DAILY_DEATHS_RULE_PATH=str(explicit))
            text, _ = _banner(env, tmp)
            assert "Daily deaths rule: ON" in text
    finally:
        if not existed:
            default.unlink()
