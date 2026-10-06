"""Simulator hardening settings from the environment (Step 51 part D): tokens, the public origin, limits, the kill
switch file and the usage file. The pilot refuses to start without a good token; the demo is unchanged."""

from __future__ import annotations

from pathlib import Path

import pytest

from clucktalk.config import ConfigError
from clucktalk.simulator.__main__ import load_simulator_settings

GOOD = "pilot-secret-token-0123456789-abcdef"


def pilot_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {
        "MOCK_BEDROCK": "true",
        "CLUCKTALK_MODE": "pilot",
        "CLUCKTALK_PILOT_FARM_PATH": str(tmp_path / "farm.json"),
        "CLUCKTALK_STATE_PATH": str(tmp_path / "state" / "pilot_state.sqlite3"),
        "CLUCKTALK_SIMULATOR_TOKENS": GOOD,
    }
    env.update(extra)
    return env


def test_the_demo_needs_no_token_and_has_the_old_defaults():
    s = load_simulator_settings({"MOCK_BEDROCK": "true"})
    assert s.mode == "demo" and s.tokens == () and s.public_origin is None and s.usage_path is None
    assert s.rate_per_minute == 60 and s.max_sessions == 20


def test_a_demo_token_is_enforced_when_given():
    assert load_simulator_settings({"MOCK_BEDROCK": "true", "CLUCKTALK_SIMULATOR_TOKENS": GOOD}).tokens == (GOOD,)


def test_a_good_pilot_environment_loads_with_files_next_to_its_own_state(tmp_path):
    s = load_simulator_settings(pilot_env(tmp_path))
    assert s.mode == "pilot" and s.tokens == (GOOD,)
    assert s.usage_path == tmp_path / "state" / "usage_pilot.json"
    assert s.disabled_file == tmp_path / "state" / "DISABLED"


def test_the_pilot_refuses_to_start_without_a_token(tmp_path):
    env = pilot_env(tmp_path)
    del env["CLUCKTALK_SIMULATOR_TOKENS"]
    with pytest.raises(ConfigError, match="CLUCKTALK_SIMULATOR_TOKENS"):
        load_simulator_settings(env)
    with pytest.raises(ConfigError, match="CLUCKTALK_SIMULATOR_TOKENS"):
        load_simulator_settings(pilot_env(tmp_path, CLUCKTALK_SIMULATOR_TOKENS=" , "))


@pytest.mark.parametrize(
    "value", ["short", "has space in it 0123456789abcdef", "bad/char/0123456789abcdef0123", "a" * 200, f"{GOOD},{GOOD}"]
)
def test_weak_malformed_or_repeated_tokens_are_refused(tmp_path, value):
    with pytest.raises(ConfigError, match="CLUCKTALK_SIMULATOR_TOKENS"):
        load_simulator_settings(pilot_env(tmp_path, CLUCKTALK_SIMULATOR_TOKENS=value))


def test_several_tokens_for_several_farmers(tmp_path):
    two = f"{GOOD},{GOOD[::-1]}"
    assert load_simulator_settings(pilot_env(tmp_path, CLUCKTALK_SIMULATOR_TOKENS=two)).tokens == (GOOD, GOOD[::-1])


@pytest.mark.parametrize(
    "origin",
    [
        "http://pilot.example.org",
        "https://pilot.example.org/path",
        "https://*.example.org",
        "pilot.example.org",
        "https://",
    ],
)
def test_the_public_origin_must_be_an_exact_https_origin(tmp_path, origin):
    with pytest.raises(ConfigError, match="CLUCKTALK_PUBLIC_ORIGIN"):
        load_simulator_settings(pilot_env(tmp_path, CLUCKTALK_PUBLIC_ORIGIN=origin))


def test_a_good_public_origin_gives_the_allowed_host(tmp_path):
    s = load_simulator_settings(pilot_env(tmp_path, CLUCKTALK_PUBLIC_ORIGIN="https://pilot.example.org"))
    assert s.public_origin == "https://pilot.example.org" and "pilot.example.org" in s.hosts
    assert "https://pilot.example.org" in s.allowed_origins


@pytest.mark.parametrize(
    ("name", "bad"),
    [
        ("CLUCKTALK_RATE_PER_MINUTE", "0"),
        ("CLUCKTALK_RATE_PER_MINUTE", "x"),
        ("CLUCKTALK_RATE_PER_MINUTE", "100000"),
        ("CLUCKTALK_MAX_SESSIONS", "0"),
        ("CLUCKTALK_MAX_SESSIONS", "5000"),
    ],
)
def test_limits_must_be_sensible_whole_numbers(tmp_path, name, bad):
    with pytest.raises(ConfigError, match=name):
        load_simulator_settings(pilot_env(tmp_path, **{name: bad}))


def test_limits_can_be_set(tmp_path):
    s = load_simulator_settings(pilot_env(tmp_path, CLUCKTALK_RATE_PER_MINUTE="30", CLUCKTALK_MAX_SESSIONS="5"))
    assert (s.rate_per_minute, s.max_sessions) == (30, 5)
