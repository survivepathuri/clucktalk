"""Python version policy of tasks.py: 3.12 and 3.13 are supported, 3.11 and newer only warn, older exits."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import tasks  # noqa: E402


@pytest.fixture
def no_other_pythons(monkeypatch):
    monkeypatch.setattr(tasks.shutil, "which", lambda name: None)


def _as_python(monkeypatch, version: tuple[int, int, int]) -> None:
    monkeypatch.setattr(tasks.sys, "version_info", version)


@pytest.mark.parametrize("version", [(3, 12), (3, 13)])
def test_supported_versions_are_silent(version):
    assert tasks.python_support(version) == "supported"


@pytest.mark.parametrize("version", [(3, 11), (3, 14), (3, 15)])
def test_other_modern_versions_are_untested_not_refused(version):
    assert tasks.python_support(version) == "untested"


@pytest.mark.parametrize("version", [(3, 10), (3, 9), (2, 7)])
def test_old_versions_are_too_old(version):
    assert tasks.python_support(version) == "too_old"


def test_base_python_on_supported_version_is_silent(monkeypatch, capsys, no_other_pythons):
    _as_python(monkeypatch, (3, 12, 4))
    assert tasks._base_python() == [sys.executable]
    assert capsys.readouterr().out == ""


def test_base_python_on_untested_version_warns_and_continues(monkeypatch, capsys, no_other_pythons):
    _as_python(monkeypatch, (3, 14, 0))
    assert tasks._base_python() == [sys.executable]
    out = capsys.readouterr().out
    assert "untested Python version" in out and "3.14" in out


def test_base_python_below_minimum_exits_with_a_neutral_hint(monkeypatch, no_other_pythons):
    _as_python(monkeypatch, (3, 10, 0))
    with pytest.raises(SystemExit) as exc:
        tasks._base_python()
    message = str(exc.value)
    assert "3.12" in message and "3.13" in message
    assert "py install" not in message  # Windows-only hint


@pytest.mark.parametrize("version", [(3, 12), (3, 13)])
def test_venv_with_any_supported_version_is_accepted(monkeypatch, capsys, version):
    monkeypatch.setattr(tasks, "_venv_python_version", lambda: version)
    tasks._require_venv()
    assert capsys.readouterr().out == ""


def test_venv_with_untested_version_warns_and_continues(monkeypatch, capsys):
    monkeypatch.setattr(tasks, "_venv_python_version", lambda: (3, 14))
    tasks._require_venv()
    assert "untested Python version" in capsys.readouterr().out


def test_venv_too_old_or_missing_exits(monkeypatch):
    monkeypatch.setattr(tasks, "_venv_python_version", lambda: (3, 10))
    with pytest.raises(SystemExit):
        tasks._require_venv()
    monkeypatch.setattr(tasks, "_venv_python_version", lambda: None)
    with pytest.raises(SystemExit):
        tasks._require_venv()


def test_format_hint_uses_the_venv_python_of_this_os():
    assert "Scripts" not in tasks.format_hint() or tasks.os.name == "nt"
    assert str(tasks.VENV_PY.relative_to(tasks.ROOT)) in tasks.format_hint()
