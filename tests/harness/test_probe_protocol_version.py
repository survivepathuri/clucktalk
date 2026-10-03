"""Step 48A part B: ``python tasks.py probe-protocol-version`` (scripts/probe_protocol_version.py) starts the server on
a temporary state file, sends ``initialize`` for four protocol versions, prints what it saw and stops the server. It
never opens the live farm state, and it exits non-zero when the server does not start."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import tasks  # noqa: E402
from clucktalk.config import DEFAULT_STATE_PATH  # noqa: E402

SCRIPT = ROOT / "scripts" / "probe_protocol_version.py"
VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")

spec = importlib.util.spec_from_file_location("probe_protocol_version_under_test", SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)  # type: ignore[union-attr]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "absent"


def _run_script(env_extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), **env_extra}
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120
    )


def test_the_real_run_prints_one_row_per_version_and_exits_zero(tmp_path):
    r = _run_script({"CLUCKTALK_STATE_PATH": str(tmp_path / "live.sqlite3")})
    assert r.returncode == 0, r.stdout + r.stderr
    rows = {}
    for line in r.stdout.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if cells and cells[0] in VERSIONS:
            rows[cells[0]] = cells[1:]
    assert tuple(rows) == VERSIONS  # in the order asked, each once
    # Pinned as observed (tests/contract/test_protocol_conformance.py): HTTP 200, answered with the requested version.
    assert rows == {v: ["200", v] for v in VERSIONS}


def test_it_never_touches_the_live_state_file_or_its_neighbours(tmp_path):
    live = tmp_path / "live.sqlite3"
    live.write_bytes(b"not a database: if anything opened this file, the server would fail to start")
    default_before = _sha(DEFAULT_STATE_PATH)  # the repo's real default state file, if it exists
    before = {p.name: _sha(p) for p in tmp_path.iterdir()}
    r = _run_script({"CLUCKTALK_STATE_PATH": str(live), "CLUCKTALK_DEMO_DAYS_LATER": ""})
    assert r.returncode == 0, r.stdout + r.stderr
    assert {p.name: _sha(p) for p in tmp_path.iterdir()} == before  # same bytes, no journal, no demo-clock sibling
    assert _sha(DEFAULT_STATE_PATH) == default_before


def test_the_state_file_it_uses_is_a_temporary_one_and_is_removed(tmp_path):
    live = tmp_path / "live.sqlite3"
    r = _run_script({"CLUCKTALK_STATE_PATH": str(live)})
    line = next(x for x in r.stdout.splitlines() if x.startswith("Temporary state file:"))
    used = Path(line.split(":", 1)[1].strip())
    assert used.suffix == ".sqlite3"
    assert used != live and used != DEFAULT_STATE_PATH
    assert ROOT not in used.parents  # never inside the repo
    assert not used.exists() and not used.parent.exists()  # cleaned up


def test_it_ignores_a_demo_clock_or_a_token_in_the_environment(tmp_path):
    r = _run_script(
        {
            "CLUCKTALK_STATE_PATH": str(tmp_path / "live.sqlite3"),
            "CLUCKTALK_DEMO_DAYS_LATER": "3",
            "CLUCKTALK_AUTH_TOKEN": "some-token",
            "MOCK_BEDROCK": "false",
        }
    )
    assert r.returncode == 0, r.stdout + r.stderr
    # A kept token would answer 401 to every request, and a kept "live AI" setting would stop the server at start.
    assert r.stdout.count("| 200 ") == len(VERSIONS), r.stdout


def test_it_exits_non_zero_and_says_why_when_the_server_does_not_start(capsys):
    exits_at_once = [sys.executable, "-c", "import sys; print('boom on start'); sys.exit(3)"]
    assert probe.main(server_command=exits_at_once, start_seconds=5) == 1
    err = capsys.readouterr().err
    assert "did not start" in err and "boom on start" in err


def test_it_exits_non_zero_when_the_server_never_listens(capsys):
    sleeps = [sys.executable, "-c", "import time; time.sleep(30)"]
    assert probe.main(server_command=sleeps, start_seconds=1) == 1
    assert "did not start" in capsys.readouterr().err


def test_the_table_has_a_header_and_shows_a_failed_request_as_a_dash():
    text = probe.format_table([("2025-11-25", 200, "2025-11-25"), ("2024-11-05", 400, None)])
    lines = text.splitlines()
    assert [c.strip() for c in lines[0].split("|")] == ["Requested", "HTTP status", "Server answered with"]
    assert [c.strip() for c in lines[2].split("|")] == ["2025-11-25", "200", "2025-11-25"]
    assert [c.strip() for c in lines[3].split("|")] == ["2024-11-05", "400", "-"]


def test_the_probe_server_process_is_stopped_afterwards(tmp_path):
    r = _run_script({"CLUCKTALK_STATE_PATH": str(tmp_path / "live.sqlite3")})
    port_line = next(x for x in r.stdout.splitlines() if x.startswith("Server: "))
    port = int(port_line.rsplit(":", 1)[1].split("/")[0])
    import socket

    with socket.socket() as s:
        s.settimeout(0.5)
        assert s.connect_ex(("127.0.0.1", port)) != 0


def test_tasks_has_the_command_and_takes_no_arguments(monkeypatch):
    assert tasks.COMMANDS["probe-protocol-version"] is tasks.probe_protocol_version
    monkeypatch.setattr(tasks.sys, "argv", ["tasks.py", "probe-protocol-version", "--x"])
    assert tasks.main() == 2
    assert "probe-protocol-version" in tasks.__doc__


def test_the_readme_names_the_command_in_one_line():
    lines = [x for x in (ROOT / "README.md").read_text(encoding="utf-8").splitlines() if "probe-protocol-version" in x]
    assert len(lines) == 1


def test_the_answered_column_is_what_the_server_said_not_what_was_asked(monkeypatch, capsys):
    answers = {"2025-11-25": (200, "2025-11-25"), "2025-06-18": (200, "2025-11-25"), "2025-03-26": (400, None)}
    monkeypatch.setattr(probe, "_wait_for_port", lambda port, proc, seconds: True)
    monkeypatch.setattr(probe, "_initialize", lambda url, version: answers.get(version, (200, "2024-11-05")))
    sleeps = [sys.executable, "-c", "import time; time.sleep(30)"]
    assert probe.main(server_command=sleeps, start_seconds=1) == 0
    table = capsys.readouterr().out
    rows = {c[0]: c[1:] for c in ([x.strip() for x in ln.split("|")] for ln in table.splitlines()) if c[0] in VERSIONS}
    assert rows == {
        "2025-11-25": ["200", "2025-11-25"],
        "2025-06-18": ["200", "2025-11-25"],
        "2025-03-26": ["400", "-"],
        "2024-11-05": ["200", "2024-11-05"],
    }


def test_it_exits_non_zero_and_says_which_version_when_a_request_fails(monkeypatch, capsys):
    def refuse(url, version):
        raise probe.httpx2.ConnectError("connection refused")

    monkeypatch.setattr(probe, "_wait_for_port", lambda port, proc, seconds: True)
    monkeypatch.setattr(probe, "_initialize", refuse)
    sleeps = [sys.executable, "-c", "import time; time.sleep(30)"]
    assert probe.main(server_command=sleeps, start_seconds=1) == 1
    assert "2025-11-25 failed" in capsys.readouterr().err
