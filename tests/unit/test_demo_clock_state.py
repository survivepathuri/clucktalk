"""Step 47B part B (user decision 2026-10-01): when the demo clock is on, the server uses a SEPARATE state file; it
never opens or writes the live state file; no fake records are ever created; a demo-clock file opened WITHOUT the demo
clock is refused with a clear error (and a live file is refused WITH it); the live file stays byte-identical."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from clucktalk.config import DEFAULT_STATE_PATH, ConfigError, load_settings
from clucktalk.domain.profile import ContractTerms
from clucktalk.server.app import open_state_store
from clucktalk.server.farm_state import IST, DemoClock, DemoFarmSource
from clucktalk.store import StoreError
from clucktalk.store.sqlite import SqliteStore

DEMO = {"MOCK_BEDROCK": "true", "CLUCKTALK_DEMO_DAYS_LATER": "3"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    return {"MOCK_BEDROCK": "true", "CLUCKTALK_STATE_PATH": str(tmp_path / "live.sqlite3"), **extra}


# -- the two paths ----------
def test_without_the_demo_clock_the_live_file_is_the_active_file():
    s = load_settings({"MOCK_BEDROCK": "true"})
    assert s.active_state_path == s.state_path == DEFAULT_STATE_PATH


def test_with_the_demo_clock_the_active_file_is_a_different_demo_clock_file():
    s = load_settings(DEMO)
    assert s.state_path == DEFAULT_STATE_PATH
    assert s.active_state_path == s.demo_clock_state_path != s.state_path
    assert s.demo_clock_state_path.parent == s.state_path.parent and s.demo_clock_state_path.suffix == ".sqlite3"
    assert "demo_clock" in s.demo_clock_state_path.name


def test_a_custom_state_path_gets_its_own_derived_demo_clock_path(tmp_path):
    s = load_settings(_env(tmp_path, CLUCKTALK_DEMO_DAYS_LATER="2"))
    assert s.state_path == tmp_path / "live.sqlite3"
    assert s.demo_clock_state_path == tmp_path / "live_demo_clock.sqlite3"
    assert s.active_state_path == s.demo_clock_state_path


def test_live_mode_still_refuses_the_demo_clock():
    with pytest.raises(ConfigError, match="CLUCKTALK_DEMO_DAYS_LATER.*MOCK_BEDROCK=true"):
        load_settings({"MOCK_BEDROCK": "false", "CLUCKTALK_DEMO_DAYS_LATER": "3"})


# -- the marker and the refusals ----------
def test_a_new_demo_clock_file_is_marked_as_one_in_its_metadata(tmp_path):
    path = tmp_path / "d.sqlite3"
    SqliteStore(path, demo_clock=True)
    con = sqlite3.connect(path)
    assert con.execute("SELECT value FROM meta WHERE key = 'demo_clock'").fetchone() == ("1",)
    con.close()


def test_a_demo_clock_file_can_be_reopened_with_the_demo_clock(tmp_path):
    path = tmp_path / "d.sqlite3"
    SqliteStore(path, demo_clock=True)
    SqliteStore(path, demo_clock=True)


def test_a_demo_clock_file_is_refused_without_the_demo_clock_and_left_untouched(tmp_path):
    path = tmp_path / "d.sqlite3"
    SqliteStore(path, demo_clock=True)
    before = _sha(path)
    with pytest.raises(StoreError, match="demo-clock") as err:
        SqliteStore(path)
    assert "reset-demo" in str(err.value) and "--demo-days-later" in str(err.value)
    assert _sha(path) == before


def test_a_live_file_is_refused_with_the_demo_clock_and_left_untouched(tmp_path):
    path = tmp_path / "live.sqlite3"
    SqliteStore(path)  # a live file: no marker
    before = _sha(path)
    with pytest.raises(StoreError, match="live state file"):
        SqliteStore(path, demo_clock=True)
    assert _sha(path) == before


def test_the_default_store_is_unchanged_and_in_memory_works():
    store = SqliteStore()  # no path, no flag: what every existing test and the Simulator use
    assert store.records("farm", "house-1") == ()


# -- open_state_store: what the server does at startup ----------
def test_the_server_opens_only_the_demo_clock_file_when_the_clock_is_on(tmp_path):
    live = tmp_path / "live.sqlite3"
    SqliteStore(live)  # the farmer's real file exists already
    before = _sha(live)
    settings = load_settings(_env(tmp_path, CLUCKTALK_DEMO_DAYS_LATER="3"))
    store = open_state_store(settings)
    assert Path(store.path) == settings.demo_clock_state_path and Path(store.path) != live
    assert _sha(live) == before


def test_the_server_opens_the_live_file_when_the_clock_is_off(tmp_path):
    settings = load_settings(_env(tmp_path))
    assert Path(open_state_store(settings).path) == tmp_path / "live.sqlite3"


def test_starting_without_the_clock_on_a_demo_clock_file_is_refused_clearly(tmp_path):
    demo = tmp_path / "live_demo_clock.sqlite3"
    open_state_store(load_settings(_env(tmp_path, CLUCKTALK_DEMO_DAYS_LATER="3")))
    assert demo.exists()
    with pytest.raises(StoreError, match="demo-clock"):
        open_state_store(load_settings({**_env(tmp_path), "CLUCKTALK_STATE_PATH": str(demo)}))


def test_a_demo_clock_run_never_changes_the_live_file_even_after_writes(tmp_path):
    live = tmp_path / "live.sqlite3"
    seeded = DemoFarmSource(store=SqliteStore(live))  # the live file with its profile row etc.
    seeded.snapshot()
    before = _sha(live)
    settings = load_settings(_env(tmp_path, CLUCKTALK_DEMO_DAYS_LATER="3"))
    store = open_state_store(settings)
    clock = DemoClock(3, real_now=lambda: datetime(2026, 10, 1, 10, 0, tzinfo=IST))
    source = DemoFarmSource(store=store, demo_clock=clock)
    source.snapshot()
    assert source.demo_clock_days == 3
    assert _sha(live) == before
    assert settings.demo_clock_state_path.exists()


def test_a_real_write_in_a_demo_clock_run_lands_in_the_demo_file_and_the_live_file_stays_byte_identical(tmp_path):
    live = tmp_path / "live.sqlite3"
    DemoFarmSource(store=SqliteStore(live)).snapshot()
    before = _sha(live)
    settings = load_settings(_env(tmp_path, CLUCKTALK_DEMO_DAYS_LATER="3"))
    store = open_state_store(settings)
    terms = ContractTerms("farm-1", Decimal("6"), Decimal("1.7"), Decimal("0.1"), Decimal("0.1"),
                          datetime(2026, 10, 1, 10, 0, tzinfo=IST))  # fmt: skip
    store.save_contract_terms(terms)
    store.close()
    assert _sha(live) == before
    reopened = SqliteStore(settings.demo_clock_state_path, demo_clock=True)
    assert reopened.get_contract_terms("farm-1") == terms
