import pytest

from clucktalk import config
from clucktalk.config import ConfigError, load_settings


def test_name_is_a_single_constant():
    assert config.APP_NAME == "CluckTalk"


def test_mock_mode_is_off_unless_explicitly_enabled():
    # Rule 6: mock data only when MOCK_BEDROCK=true is set explicitly.
    assert load_settings({}).mock_bedrock is False
    assert load_settings({"MOCK_BEDROCK": "true"}).mock_bedrock is True
    assert load_settings({"MOCK_BEDROCK": "FALSE"}).mock_bedrock is False


def test_malformed_boolean_fails_loudly():
    with pytest.raises(ConfigError, match="MOCK_BEDROCK"):
        load_settings({"MOCK_BEDROCK": "maybe"})


def test_local_defaults_bind_to_localhost():
    s = load_settings({})
    assert s.host == "127.0.0.1" and s.is_local
    assert s.port == 8765
    assert s.allowed_origins == ("http://127.0.0.1:8765", "http://localhost:8765")


@pytest.mark.parametrize("port", ["abc", "0", "70000"])
def test_invalid_port_fails_loudly(port):
    with pytest.raises(ConfigError, match="CLUCKTALK_PORT"):
        load_settings({"CLUCKTALK_PORT": port})


def test_non_local_host_requires_auth_token():
    # docs/DESIGN.md §4: localhost bind in local mode, auth token when exposed.
    with pytest.raises(ConfigError, match="CLUCKTALK_AUTH_TOKEN"):
        load_settings({"CLUCKTALK_HOST": "0.0.0.0"})
    s = load_settings({"CLUCKTALK_HOST": "0.0.0.0", "CLUCKTALK_AUTH_TOKEN": "t"})
    assert not s.is_local


def test_origin_allow_list_is_parsed():
    s = load_settings({"CLUCKTALK_ALLOWED_ORIGINS": " http://a.test , http://b.test ,"})
    assert s.allowed_origins == ("http://a.test", "http://b.test")


def test_state_path_default_relative_and_suffix():
    """Review 2026-09-28 (Low): server and reset-demo must resolve the same file from any working directory."""
    from clucktalk.config import DEFAULT_STATE_PATH, REPO_ROOT

    assert load_settings({}).state_path == DEFAULT_STATE_PATH
    assert load_settings({"CLUCKTALK_STATE_PATH": "x/state.sqlite3"}).state_path == REPO_ROOT / "x" / "state.sqlite3"
    with pytest.raises(ConfigError, match="sqlite3"):
        load_settings({"CLUCKTALK_STATE_PATH": "notes.txt"})


def test_ai_daily_cap_defaults_to_the_hard_cap_and_can_only_go_lower():
    """User decision 2026-09-29: hard cap 100 model calls/day; a lower cap may be configured, never a higher one."""
    assert load_settings({}).ai_max_calls_per_day == 100
    assert load_settings({"CLUCKTALK_AI_MAX_CALLS_PER_DAY": "20"}).ai_max_calls_per_day == 20
    for bad in ("101", "-1", "lots"):
        with pytest.raises(ConfigError, match="CLUCKTALK_AI_MAX_CALLS_PER_DAY"):
            load_settings({"CLUCKTALK_AI_MAX_CALLS_PER_DAY": bad})


def test_live_ai_needs_an_explicit_setting_model_and_region():
    """Mock stays the default; live AI (demo farm + Nova) only via MOCK_BEDROCK=false given explicitly."""
    from clucktalk.config import require_live_ai

    with pytest.raises(ConfigError, match="MOCK_BEDROCK"):
        require_live_ai(load_settings({}))  # unset is not an explicit choice
    with pytest.raises(ConfigError, match="BEDROCK_MODEL_ID"):
        require_live_ai(load_settings({"MOCK_BEDROCK": "false", "AWS_REGION": "us-east-1"}))
    with pytest.raises(ConfigError, match="AWS_REGION"):
        require_live_ai(load_settings({"MOCK_BEDROCK": "false", "BEDROCK_MODEL_ID": "m"}))
    live = load_settings({"MOCK_BEDROCK": "false", "BEDROCK_MODEL_ID": "m", "AWS_REGION": "us-east-1"})
    require_live_ai(live)
    assert live.bedrock_model_id == "m" and not live.mock_bedrock
