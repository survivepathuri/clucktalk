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
