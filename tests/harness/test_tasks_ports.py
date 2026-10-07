"""Step 58: ``python tasks.py run`` and ``serve`` check that their ports are free before starting anything.

A busy MCP port (default 8765) or Simulator port (default 8766) gives one clear line that names the port and the
variable to change (cmd, PowerShell, bash/zsh), a non-zero exit code, and no started process."""

from __future__ import annotations

import socket
import sys
from contextlib import closing, contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import tasks  # noqa: E402


class Started(Exception):
    """Raised by the fake process starters: the command got past the port check."""


def _free_port() -> int:
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def _busy_port():
    """A port that something is listening on."""
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        s.listen()
        yield s.getsockname()[1]


@pytest.fixture
def starts(monkeypatch):
    """No venv is needed, and every attempt to start a process is recorded and stopped."""
    calls: list[str] = []

    def fake(*args, **kwargs):
        calls.append("start")
        raise Started

    monkeypatch.setattr(tasks, "_require_venv", lambda: None)
    monkeypatch.setattr(tasks.subprocess, "Popen", fake)
    monkeypatch.setattr(tasks.subprocess, "call", fake)
    monkeypatch.setenv("MOCK_BEDROCK", "true")
    return calls


def _ports(monkeypatch, mcp: int, sim: int) -> None:
    monkeypatch.setenv("CLUCKTALK_PORT", str(mcp))
    monkeypatch.setenv("CLUCKTALK_SIMULATOR_PORT", str(sim))


def test_the_probe_sees_a_listening_port_as_busy_and_a_free_one_as_free():
    with _busy_port() as port:
        assert tasks._port_in_use(port) is True
    assert tasks._port_in_use(_free_port()) is False


def test_run_starts_when_both_ports_are_free(monkeypatch, starts):
    _ports(monkeypatch, _free_port(), _free_port())
    with pytest.raises(Started):
        tasks.run()
    assert starts == ["start"]


def test_serve_starts_when_its_port_is_free(monkeypatch, starts):
    _ports(monkeypatch, _free_port(), _free_port())
    with pytest.raises(Started):
        tasks.serve()
    assert starts == ["start"]


def test_run_with_a_busy_mcp_port_starts_nothing_and_names_the_port(monkeypatch, starts, capsys):
    with _busy_port() as busy:
        _ports(monkeypatch, busy, _free_port())
        assert tasks.run() != 0
    err = capsys.readouterr().err
    assert starts == []
    assert f"port {busy}" in err and "CLUCKTALK_PORT" in err and "CLUCKTALK_SIMULATOR_PORT" not in err


def test_run_with_a_busy_simulator_port_starts_nothing_and_names_the_port(monkeypatch, starts, capsys):
    with _busy_port() as busy:
        _ports(monkeypatch, _free_port(), busy)
        assert tasks.run() != 0
    err = capsys.readouterr().err
    assert starts == []
    assert f"port {busy}" in err and "CLUCKTALK_SIMULATOR_PORT" in err


def test_serve_with_a_busy_mcp_port_starts_nothing(monkeypatch, starts, capsys):
    with _busy_port() as busy:
        _ports(monkeypatch, busy, _free_port())
        assert tasks.serve() != 0
    assert starts == [] and f"port {busy}" in capsys.readouterr().err


def test_serve_does_not_care_about_the_simulator_port(monkeypatch, starts):
    with _busy_port() as busy:
        _ports(monkeypatch, _free_port(), busy)
        with pytest.raises(Started):
            tasks.serve()


def test_the_message_is_one_line_with_the_syntax_for_all_three_shells(monkeypatch, starts, capsys):
    with _busy_port() as busy:
        _ports(monkeypatch, busy, _free_port())
        tasks.run()
    lines = [ln for ln in capsys.readouterr().err.splitlines() if ln.strip()]
    assert len(lines) == 1
    line = lines[0]
    assert "set CLUCKTALK_PORT=" in line  # cmd
    assert "$env:CLUCKTALK_PORT=" in line  # PowerShell
    assert "export CLUCKTALK_PORT=" in line  # bash and zsh
    assert line.startswith("run:") and "already in use" in line


def test_the_suggested_port_is_not_the_busy_one(monkeypatch, starts, capsys):
    with _busy_port() as busy:
        _ports(monkeypatch, busy, _free_port())
        tasks.run()
    assert f"CLUCKTALK_PORT={busy}" not in capsys.readouterr().err


def test_custom_port_variables_are_respected_not_the_defaults(monkeypatch, starts, capsys):
    """The defaults 8765 and 8766 may or may not be free here; only the variables decide."""
    with _busy_port() as busy_mcp, _busy_port() as busy_sim:
        _ports(monkeypatch, busy_mcp, busy_sim)
        assert tasks.run() != 0
        assert f"port {busy_mcp}" in capsys.readouterr().err
    _ports(monkeypatch, _free_port(), _free_port())
    with pytest.raises(Started):
        tasks.run()


def test_empty_port_variables_fall_back_to_the_defaults(monkeypatch, starts):
    monkeypatch.setenv("CLUCKTALK_PORT", "")
    monkeypatch.setenv("CLUCKTALK_SIMULATOR_PORT", "")
    seen = []
    monkeypatch.setattr(tasks, "_port_in_use", lambda port: seen.append(port) or False)
    with pytest.raises(Started):
        tasks.run()
    assert seen == [8765, 8766]


def test_an_invalid_port_value_is_left_to_the_server_to_report(monkeypatch, starts):
    monkeypatch.setenv("CLUCKTALK_PORT", "not-a-port")
    monkeypatch.setenv("CLUCKTALK_SIMULATOR_PORT", str(_free_port()))
    with pytest.raises(Started):
        tasks.serve()


class _FakeSocket:
    """Records setsockopt and bind; used to check the probe's per-OS behaviour on any machine."""

    opts: list = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def setsockopt(self, *args):
        _FakeSocket.opts.append(args)

    def bind(self, address):
        _FakeSocket.opts.append(("bind", address))


@pytest.mark.parametrize(("os_name", "reuse"), [("nt", False), ("posix", True)])
def test_so_reuseaddr_is_set_off_windows_only(monkeypatch, os_name, reuse):
    _FakeSocket.opts = []
    monkeypatch.setattr(tasks.socket, "socket", _FakeSocket)
    monkeypatch.setattr(tasks.os, "name", os_name)
    assert tasks._port_in_use(8765) is False
    monkeypatch.undo()
    assert (("bind", ("127.0.0.1", 8765)) in _FakeSocket.opts) and (len(_FakeSocket.opts) == (2 if reuse else 1))
