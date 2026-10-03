"""Step 47B part B: `python tasks.py reset-demo` clears BOTH state files, and a real server start with the demo clock
prints the demo-clock file (never the live one) and leaves the live file byte-identical; started without the clock on a
demo-clock file it refuses with a clear error and exit code 2."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import tasks  # noqa: E402
from clucktalk.store.sqlite import SqliteStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _make(path: Path, demo_clock: bool) -> None:
    SqliteStore(path, demo_clock=demo_clock).close()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_reset_demo_clears_both_files_and_only_those(monkeypatch, tmp_path, capsys):
    live, demo = tmp_path / "farm.sqlite3", tmp_path / "farm_demo_clock.sqlite3"
    other = tmp_path / "notes.txt"
    other.write_text("keep me", encoding="utf-8")
    _make(live, False)
    _make(demo, True)
    monkeypatch.setenv("CLUCKTALK_STATE_PATH", str(live))
    monkeypatch.setenv("MOCK_BEDROCK", "true")
    assert tasks.reset_demo(["--yes"]) == 0
    assert not live.exists() and not demo.exists() and other.exists()
    out = capsys.readouterr().out
    assert str(live) in out and str(demo) in out


def test_reset_demo_works_when_only_one_of_the_two_exists(monkeypatch, tmp_path):
    live, demo = tmp_path / "farm.sqlite3", tmp_path / "farm_demo_clock.sqlite3"
    _make(demo, True)
    monkeypatch.setenv("CLUCKTALK_STATE_PATH", str(live))
    assert tasks.reset_demo(["--yes"]) == 0 and not demo.exists()
    _make(live, False)
    assert tasks.reset_demo(["--yes"]) == 0 and not live.exists()


def test_reset_demo_with_nothing_to_reset_says_so(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CLUCKTALK_STATE_PATH", str(tmp_path / "farm.sqlite3"))
    assert tasks.reset_demo(["--yes"]) == 0
    assert "nothing to reset" in capsys.readouterr().out


def _server(env: dict[str, str], port: int) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "clucktalk.server"],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",  # a piped stdout is block-buffered: the banner would not arrive
            "CLUCKTALK_PORT": str(port),
            "MOCK_BEDROCK": "true",
            **env,
        },  # fmt: skip
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )


def _banner(proc: subprocess.Popen, until: str, seconds: float = 40.0) -> str:
    """Server output up to the first line containing ``until``; a real deadline (a reader thread), never a hang."""
    import queue
    import threading

    lines: queue.Queue[str | None] = queue.Queue()

    def pump() -> None:
        for line in proc.stdout:
            lines.put(line.rstrip())
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()
    seen, deadline = [], time.time() + seconds
    while time.time() < deadline:
        try:
            line = lines.get(timeout=1)
        except queue.Empty:
            continue
        if line is None:
            break
        seen.append(line)
        if until in line:
            break
    return "\n".join(seen)


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_real_server_start_with_the_demo_clock_uses_only_the_demo_clock_file(tmp_path):
    live = tmp_path / "farm.sqlite3"
    _make(live, False)
    before = _sha(live)
    proc = _server({"CLUCKTALK_STATE_PATH": str(live), "CLUCKTALK_DEMO_DAYS_LATER": "3"}, _free_port())
    try:
        banner = _banner(proc, "Farm state:")
    finally:
        proc.terminate()
        proc.wait(timeout=20)
    assert "DEMO CLOCK: +3 days" in banner
    assert f"Farm state: {tmp_path / 'farm_demo_clock.sqlite3'}" in banner
    assert f"Farm state: {live}" not in banner
    assert (tmp_path / "farm_demo_clock.sqlite3").exists()
    assert _sha(live) == before  # the live file was never written


def test_a_real_server_start_without_the_clock_on_a_demo_clock_file_is_refused(tmp_path):
    demo = tmp_path / "farm_demo_clock.sqlite3"
    _make(demo, True)
    proc = _server({"CLUCKTALK_STATE_PATH": str(demo)}, _free_port())
    out, _ = proc.communicate(timeout=60)
    assert proc.returncode == 2
    assert "State store error" in out and "demo-clock" in out and "reset-demo" in out
