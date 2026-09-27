"""Single source of truth for the product name and runtime settings.

Renaming the product is a one-line change to APP_NAME (PRD Section 19, decision 1).
Settings come only from environment variables. Invalid values raise ConfigError at startup rather than
falling back silently (Rule 6).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "CluckTalk"
APP_NAME_TE = "కోడి మిత్ర"  # Telugu subtitle: pending native-speaker review (PRD Section 5)
TAGLINE_EN = "The voice farm manager for India's poultry farmers."

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"

_TRUE = {"true", "1", "yes"}
_FALSE = {"false", "0", "no"}
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ConfigError(ValueError):
    """A setting is missing or malformed. The message names the variable and the accepted values."""


@dataclass(frozen=True)
class Settings:
    mock_bedrock: bool
    host: str
    port: int
    allowed_origins: tuple[str, ...]
    auth_token: str | None
    aws_region: str | None

    @property
    def is_local(self) -> bool:
        return self.host in _LOCAL_HOSTS


def _parse_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name, "").strip().lower()
    if raw == "":
        return default
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    raise ConfigError(f"{name}={env[name]!r} is not a boolean. Use true or false.")


def _parse_port(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, "").strip()
    if raw == "":
        return default
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise ConfigError(f"{name}={raw!r} is not a valid TCP port (1-65535).")
    return int(raw)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Read settings from ``env`` (defaults to ``os.environ``).

    Mock mode is only on when MOCK_BEDROCK is set to true explicitly (Rule 6). If it is unset,
    CluckTalk runs in live mode and fails loudly without AWS configuration. It never quietly
    serves demo data.
    """
    env = os.environ if env is None else env
    host = env.get("CLUCKTALK_HOST", "").strip() or "127.0.0.1"
    auth_token = env.get("CLUCKTALK_AUTH_TOKEN", "").strip() or None
    if host not in _LOCAL_HOSTS and auth_token is None:
        raise ConfigError(
            f"CLUCKTALK_HOST={host!r} exposes the server beyond this machine, so CLUCKTALK_AUTH_TOKEN is required."
        )
    origins = tuple(o.strip() for o in env.get("CLUCKTALK_ALLOWED_ORIGINS", "").split(",") if o.strip())
    port = _parse_port(env, "CLUCKTALK_PORT", 8765)
    return Settings(
        mock_bedrock=_parse_bool(env, "MOCK_BEDROCK", default=False),
        host=host,
        port=port,
        allowed_origins=origins or (f"http://127.0.0.1:{port}", f"http://localhost:{port}"),
        auth_token=auth_token,
        aws_region=env.get("AWS_REGION", "").strip() or None,
    )
