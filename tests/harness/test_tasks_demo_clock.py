"""``python tasks.py serve|run --demo-days-later N`` sets CLUCKTALK_DEMO_DAYS_LATER for the server (demo clock)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import tasks  # noqa: E402


def _run_main(monkeypatch, *argv):
    seen = {}
    monkeypatch.setattr(
        tasks, "COMMANDS", {**tasks.COMMANDS, "serve": lambda: seen.setdefault("env", dict(tasks.os.environ)) and 0}
    )
    monkeypatch.setattr(tasks.sys, "argv", ["tasks.py", *argv])
    monkeypatch.setenv("CLUCKTALK_DEMO_DAYS_LATER", "")  # restored at teardown, so main() cannot leak it
    code = tasks.main()
    return code, seen


def test_the_flag_sets_the_env_var_for_serve(monkeypatch):
    code, seen = _run_main(monkeypatch, "serve", "--demo-days-later", "3")
    assert code == 0 and seen["env"]["CLUCKTALK_DEMO_DAYS_LATER"] == "3"


def test_without_the_flag_nothing_is_set(monkeypatch):
    code, seen = _run_main(monkeypatch, "serve")
    assert code == 0 and seen["env"]["CLUCKTALK_DEMO_DAYS_LATER"] == ""


@pytest.mark.parametrize(
    "argv",
    [
        ["serve", "--demo-days-later"],
        ["serve", "--demo-days-later", "x"],
        ["serve", "--bogus"],
        ["check", "--demo-days-later", "3"],
    ],
)
def test_a_bad_or_misplaced_flag_prints_usage_and_exits_2(monkeypatch, capsys, argv):
    code, _ = _run_main(monkeypatch, *argv)
    assert code == 2 and "demo-days-later" in capsys.readouterr().out
