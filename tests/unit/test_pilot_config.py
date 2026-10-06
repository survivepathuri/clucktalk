"""Pilot mode settings (Step 51 part A): CLUCKTALK_MODE=pilot is a separate instance. It never shares a state file with
the demo, never runs the demo clock, and refuses to start on anything unclear. The demo instance is unchanged."""

from __future__ import annotations

from pathlib import Path

import pytest

from clucktalk.config import DEFAULT_STATE_PATH, ConfigError, load_settings

FARM = "/data/pilot/farm.json"


def pilot_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {
        "MOCK_BEDROCK": "true",
        "CLUCKTALK_MODE": "pilot",
        "CLUCKTALK_PILOT_FARM_PATH": str(tmp_path / "farm.json"),
        "CLUCKTALK_STATE_PATH": str(tmp_path / "pilot_state.sqlite3"),
        "CLUCKTALK_AUTH_TOKEN": "mcp-secret-token-0123456789-abcdefgh",
    }
    env.update(extra)
    return env


def test_default_is_demo_and_unchanged():
    s = load_settings({"MOCK_BEDROCK": "true"})
    assert s.mode == "demo" and s.pilot_farm_path is None and s.state_path == DEFAULT_STATE_PATH


def test_a_good_pilot_environment_loads(tmp_path):
    s = load_settings(pilot_env(tmp_path))
    assert s.mode == "pilot" and s.instance_name == "pilot"
    assert s.pilot_farm_path == tmp_path / "farm.json"
    assert s.state_path == tmp_path / "pilot_state.sqlite3"


def test_unknown_mode_is_refused():
    with pytest.raises(ConfigError, match="CLUCKTALK_MODE"):
        load_settings({"MOCK_BEDROCK": "true", "CLUCKTALK_MODE": "live"})


@pytest.mark.parametrize("drop", ["CLUCKTALK_PILOT_FARM_PATH", "CLUCKTALK_STATE_PATH"])
def test_pilot_needs_its_own_farm_file_and_state_path(tmp_path, drop):
    env = pilot_env(tmp_path)
    del env[drop]
    with pytest.raises(ConfigError, match=drop):
        load_settings(env)


@pytest.mark.parametrize("value", ["false", ""])
def test_pilot_needs_mock_true_because_live_ai_is_not_built_for_pilot(tmp_path, value):
    with pytest.raises(ConfigError, match="MOCK_BEDROCK"):
        load_settings(pilot_env(tmp_path, MOCK_BEDROCK=value))


def test_pilot_refuses_the_demo_clock(tmp_path):
    with pytest.raises(ConfigError, match="DEMO_DAYS_LATER"):
        load_settings(pilot_env(tmp_path, CLUCKTALK_DEMO_DAYS_LATER="3"))


def test_pilot_state_file_name_must_contain_the_instance_name(tmp_path):
    with pytest.raises(ConfigError, match="instance name"):
        load_settings(pilot_env(tmp_path, CLUCKTALK_STATE_PATH=str(tmp_path / "farm_state.sqlite3")))
    s = load_settings(
        pilot_env(tmp_path, CLUCKTALK_INSTANCE_NAME="pilot2", CLUCKTALK_STATE_PATH=str(tmp_path / "x_pilot2.sqlite3"))
    )
    assert s.instance_name == "pilot2"


def test_pilot_refuses_the_demo_state_file_and_its_folder():
    demo_dir = DEFAULT_STATE_PATH.parent
    for path in (DEFAULT_STATE_PATH, demo_dir / "pilot_state.sqlite3"):
        env = {
            "MOCK_BEDROCK": "true",
            "CLUCKTALK_MODE": "pilot",
            "CLUCKTALK_PILOT_FARM_PATH": FARM,
            "CLUCKTALK_STATE_PATH": str(path),
        }
        with pytest.raises(ConfigError, match="demo"):
            load_settings(env)


def test_pilot_refuses_a_path_that_reaches_the_demo_folder_through_dots():
    sneaky = DEFAULT_STATE_PATH.parent / "sub" / ".." / "pilot_state.sqlite3"
    env = {
        "MOCK_BEDROCK": "true",
        "CLUCKTALK_MODE": "pilot",
        "CLUCKTALK_PILOT_FARM_PATH": FARM,
        "CLUCKTALK_STATE_PATH": str(sneaky),
    }
    with pytest.raises(ConfigError, match="demo"):
        load_settings(env)


def test_demo_refuses_a_pilot_state_file_and_a_pilot_farm_file(tmp_path):
    with pytest.raises(ConfigError, match="pilot"):
        load_settings({"MOCK_BEDROCK": "true", "CLUCKTALK_STATE_PATH": str(tmp_path / "pilot_state.sqlite3")})
    with pytest.raises(ConfigError, match="CLUCKTALK_PILOT_FARM_PATH"):
        load_settings({"MOCK_BEDROCK": "true", "CLUCKTALK_PILOT_FARM_PATH": FARM})


@pytest.mark.parametrize("name", ["Pilot", "pi lot", "pilot/../x", "p" * 25])
def test_instance_name_is_a_short_lowercase_word(tmp_path, name):
    with pytest.raises(ConfigError, match="CLUCKTALK_INSTANCE_NAME"):
        load_settings(pilot_env(tmp_path, CLUCKTALK_INSTANCE_NAME=name))


# -- Step 52 part B: the MCP server never runs without a strong token in pilot mode ----------------------------------
@pytest.mark.parametrize(
    "value", ["", "   ", "short", "has space in it 0123456789abcdef", "bad/char/0123456789abcdef0123", "a" * 200]
)
def test_the_pilot_refuses_to_start_without_a_strong_mcp_token(tmp_path, value):
    with pytest.raises(ConfigError, match="CLUCKTALK_AUTH_TOKEN"):
        load_settings(pilot_env(tmp_path, CLUCKTALK_AUTH_TOKEN=value))


def test_the_pilot_refuses_a_missing_mcp_token(tmp_path):
    env = pilot_env(tmp_path)
    del env["CLUCKTALK_AUTH_TOKEN"]
    with pytest.raises(ConfigError, match="CLUCKTALK_AUTH_TOKEN"):
        load_settings(env)


def test_a_strong_mcp_token_is_accepted_and_kept(tmp_path):
    s = load_settings(pilot_env(tmp_path, CLUCKTALK_AUTH_TOKEN="Zz9._~-" * 5))
    assert s.auth_token == "Zz9._~-" * 5


def test_the_demo_still_starts_without_an_mcp_token():
    assert load_settings({"MOCK_BEDROCK": "true"}).auth_token is None
