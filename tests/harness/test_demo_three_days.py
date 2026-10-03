"""Step 47B part D: ``python tasks.py demo-three-days`` (scripts/demo_three_days.py) builds the demo-clock state file
for the "three days later" recording by making the Session 4 MCP calls over real HTTP (day 0: a watch check on shed one
and an urgent check on shed two; day 1: the "worse" answer on shed two), then prints the serve command and the
basic-host URLs. It never opens the live state file, refuses live mode, and never overwrites a demo-clock file."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import tasks  # noqa: E402
from clucktalk.domain.follow_up import Outcome  # noqa: E402
from clucktalk.domain.triage import Urgency  # noqa: E402
from clucktalk.store.sqlite import SqliteStore  # noqa: E402

spec = importlib.util.spec_from_file_location("demo_three_days_under_test", ROOT / "scripts" / "demo_three_days.py")
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)  # type: ignore[union-attr]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def farm(monkeypatch, tmp_path):
    live = tmp_path / "farm.sqlite3"
    SqliteStore(live).close()  # the farmer's live file exists already
    monkeypatch.setenv("CLUCKTALK_STATE_PATH", str(live))
    monkeypatch.setenv("MOCK_BEDROCK", "true")
    monkeypatch.setenv("CLUCKTALK_DEMO_DAYS_LATER", "")
    return live, tmp_path / "farm_demo_clock.sqlite3"


def test_it_builds_the_demo_clock_file_and_leaves_the_live_file_byte_identical(farm, capsys):
    live, demo_file = farm
    before = _sha(live)
    assert demo.main() == 0
    assert demo_file.exists() and _sha(live) == before
    out = capsys.readouterr().out
    assert "python tasks.py serve --demo-days-later 3" in out
    assert "http://localhost:8080" in out and "http://127.0.0.1:8765/mcp" in out
    assert str(live) not in out.replace(str(demo_file), "")  # the live path is never mentioned as used


def test_the_file_holds_the_session_4_story(farm):
    _, demo_file = farm
    assert demo.main() == 0
    store = SqliteStore(demo_file, demo_clock=True)  # it is marked as a demo-clock file
    farm_id = store._db.execute("SELECT farm_id FROM health_checks").fetchone()["farm_id"]
    rows = store._db.execute("SELECT house_id FROM health_checks ORDER BY house_id").fetchall()
    assert [r["house_id"] for r in rows] == ["house-1", "house-2"]
    answers = store._db.execute("SELECT house_id, said FROM follow_up_answers").fetchall()
    assert [(a["house_id"], a["said"]) for a in answers] == [("house-2", Outcome.WORSE.value)]
    assert store.latest_health_check(farm_id, "house-1").floor.urgency is Urgency.WATCH
    assert store.latest_health_check(farm_id, "house-2").floor.urgency is Urgency.URGENT


def test_it_refuses_live_mode_and_creates_nothing(monkeypatch, farm, capsys):
    live, demo_file = farm
    monkeypatch.setenv("MOCK_BEDROCK", "false")
    before = _sha(live)
    assert demo.main() == 2
    assert "MOCK_BEDROCK" in capsys.readouterr().err
    assert not demo_file.exists() and _sha(live) == before


def test_it_refuses_to_overwrite_an_existing_demo_clock_file(farm, capsys):
    _, demo_file = farm
    SqliteStore(demo_file, demo_clock=True).close()
    before = _sha(demo_file)
    assert demo.main() == 2
    assert "reset-demo" in capsys.readouterr().err
    assert _sha(demo_file) == before


def test_reset_demo_clears_the_file_it_built(farm):
    live, demo_file = farm
    assert demo.main() == 0 and demo_file.exists()
    assert tasks.reset_demo(["--yes"]) == 0
    assert not demo_file.exists() and not live.exists()


def test_tasks_has_the_command_and_takes_no_arguments(monkeypatch):
    assert tasks.COMMANDS["demo-three-days"] is tasks.demo_three_days
    monkeypatch.setattr(tasks.sys, "argv", ["tasks.py", "demo-three-days", "--demo-days-later", "3"])
    assert tasks.main() == 2


def test_the_readme_has_the_three_commands_section():
    text = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
    assert "## See three days later in 3 commands" in text
    for command in ("python tasks.py demo-three-days", "python tasks.py serve --demo-days-later 3"):
        assert command in text
    assert "python tasks.py reset-demo" in text
