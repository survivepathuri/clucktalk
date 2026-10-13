"""daily_deaths_rule.json (Step 51 part B): the same strict pattern as the weather rules file. No file means the feature
is off (nothing changes); a bad file at startup is a loud error; a file that goes bad while running is reported as
"unreadable" and used for nothing."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from clucktalk.server.daily_deaths import (
    DeathsRuleError,
    DeathsRuleFile,
    deaths_rule_from_env,
    load_deaths_rule,
    resolve_rule_path,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "docs" / "daily_deaths_rule.example.json"


def write(tmp_path, data) -> Path:
    p = tmp_path / "daily_deaths_rule.json"
    p.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return p


def test_no_file_means_off(tmp_path):
    assert load_deaths_rule(tmp_path / "daily_deaths_rule.json") is None


def test_the_example_file_loads_and_is_labelled_an_example():
    rule = load_deaths_rule(EXAMPLE)
    assert rule is not None and rule.is_example is True and rule.per_1000_live == Decimal("2")


def test_the_farmers_own_words_are_kept_exactly(tmp_path):
    note = "  షెడ్ లో చూడండి — 8 కంటే ఎక్కువ \n"
    rule = load_deaths_rule(write(tmp_path, {"per_1000_live": 2, "note": note}))
    assert rule.note == note and rule.is_example is False


def test_a_decimal_number_is_read_without_float_noise(tmp_path):
    rule = load_deaths_rule(write(tmp_path, '{"per_1000_live": 0.1}'))
    assert rule.per_1000_live == Decimal("0.1")


@pytest.mark.parametrize(
    "data",
    [
        "{",
        "[]",
        "null",
        {},
        {"per_1000_live": "2"},
        {"per_1000_live": True},
        {"per_1000_live": -1},
        {"per_1000_live": 0},  # Step 52: zero would flag every single death
        {"per_1000_live": 0.0},
        {"per_1000_live": -0.0},
        {"per_1000_live": 1001},
        {"per_1000_live": 2, "note": 5},
        {"per_1000_live": 2, "note": "x" * 201},
        {"per_1000_live": 2, "is_example": "yes"},
        {"per_1000_live": 2, "threshold": 3},
        {"per_1000_live": float("nan")},
    ],
)
def test_every_bad_file_is_refused(tmp_path, data):
    text = data
    with pytest.raises(DeathsRuleError):
        load_deaths_rule(write(tmp_path, text))


def test_the_path_must_be_a_json_file_and_default_is_the_docs_example():
    assert resolve_rule_path("") == ROOT / "docs" / "daily_deaths_limit.example.json"
    with pytest.raises(DeathsRuleError, match=".json"):
        resolve_rule_path("rule.txt")


def test_from_env_is_off_without_a_file_and_refuses_a_bad_one(tmp_path):
    env = {"CLUCKTALK_DAILY_DEATHS_RULE_PATH": str(tmp_path / "none.json")}
    assert deaths_rule_from_env(env) is None
    good = write(tmp_path, {"per_1000_live": 2})
    assert deaths_rule_from_env({"CLUCKTALK_DAILY_DEATHS_RULE_PATH": str(good)}) is not None
    write(tmp_path, "{")
    with pytest.raises(DeathsRuleError):
        deaths_rule_from_env({"CLUCKTALK_DAILY_DEATHS_RULE_PATH": str(good)})


def test_the_file_is_reread_when_it_changes_and_a_bad_edit_is_unreadable_not_ignored(tmp_path):
    path = write(tmp_path, {"per_1000_live": 2, "note": "a"})
    live = DeathsRuleFile(path)
    state = live.current()
    assert state.rule is not None and state.rule.note == "a" and state.unreadable is False
    write(tmp_path, {"per_1000_live": 3, "note": "b"})
    os.utime(path, ns=(10**18, 10**18 + 5))  # a different modified time, whatever the filesystem's clock resolution
    state = live.current()
    assert state.rule.per_1000_live == Decimal("3") and state.rule.note == "b"
    write(tmp_path, "{")
    os.utime(path, ns=(10**18, 10**18 + 9))
    state = live.current()
    assert state.rule is None and state.unreadable is True  # said, not silently dropped
    path.unlink()
    state = live.current()
    assert state.rule is None and state.unreadable is False  # no file: the feature is simply off


def test_the_demo_default_never_reads_a_local_file_and_is_the_example(monkeypatch):
    """A fresh clone shows the same demo story as the builder's PC: the default is the docs example, never .local."""
    seen: list[Path] = []
    real = Path.read_text

    def spy(self, *a, **k):
        seen.append(self)
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", spy)
    service = deaths_rule_from_env({})
    assert service is not None
    state = service.current()
    assert state.rule is not None and state.rule.is_example is True
    assert seen and not any(".local" in p.parts for p in seen)
