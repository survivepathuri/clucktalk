"""python tasks.py pilot-stats (Step 51 part D): aggregate numbers only, from the anonymous usage file."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from clucktalk.usage import UsageCounters, format_stats

ROOT = Path(__file__).resolve().parents[2]


def make(tmp_path: Path) -> Path:
    path = tmp_path / "usage_pilot.json"
    c = UsageCounters(path, today=lambda: date(2026, 10, 9))
    c.record_turn()
    c.record_answer("yes", applied_record=True)
    c.record_answer("no", applied_record=False)
    c.record_result("get_farm_status", {"level": "watch"})
    c.record_result("get_farm_status", {"level": "alert"})
    c.record_result("get_farm_status", {"level": "alert"})
    return path


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "tasks.py", "pilot-stats", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def test_the_stats_print_only_aggregate_numbers(tmp_path):
    path = make(tmp_path)
    done = run(["--usage", str(path)])
    assert done.returncode == 0, done.stderr
    out = done.stdout
    assert "Days used: 1" in out and "Records confirmed: 1" in out
    assert "Alerts shown: 3 (watch 1, alert 2)" in out
    assert "Confirmations: 1" in out and "Cancellations: 1" in out
    assert "Confirmations versus cancellations: 1 to 1" in out
    assert "2026-10-09" not in out  # not even the date: only how many days
    assert "house" not in out.lower() and "shed" not in out.lower()


def test_format_stats_handles_zero_and_never_divides():
    text = format_stats(
        {
            "days_used": [],
            "records_confirmed": 0,
            "alerts_shown": {"watch": 0, "alert": 0},
            "confirmations": 0,
            "cancellations": 0,
        }
    )
    assert "Days used: 0" in text and "Confirmations versus cancellations: 0 to 0" in text


def test_a_missing_file_says_so_and_a_damaged_file_is_reported_not_repaired(tmp_path):
    missing = run(["--usage", str(tmp_path / "nope.json")])
    assert missing.returncode == 1 and "no usage file" in missing.stderr.lower()
    bad = tmp_path / "bad.json"
    bad.write_text("{ nope", encoding="utf-8")
    done = run(["--usage", str(bad)])
    assert done.returncode == 1 and "usage" in done.stderr.lower()
    assert bad.read_text(encoding="utf-8") == "{ nope"


def test_the_command_takes_nothing_else(tmp_path):
    assert run(["--bogus"]).returncode == 2
    assert run([]).returncode in (1, 2)  # no default file is guessed: it must be named


def test_the_usage_file_format_is_the_documented_one(tmp_path):
    data = json.loads(make(tmp_path).read_text(encoding="utf-8"))
    assert set(data) == {"days_used", "records_confirmed", "alerts_shown", "confirmations", "cancellations"}
