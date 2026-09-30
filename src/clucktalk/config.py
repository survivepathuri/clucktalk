"""Single source of truth for the product name and runtime settings.

Renaming the product is a one-line change to APP_NAME (docs/DESIGN.md §11).
Settings come only from environment variables. Invalid values raise ConfigError at startup rather than
falling back silently (Rule 6).
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "CluckTalk"
APP_NAME_TE = "కోడి మిత్ర"  # Telugu subtitle; review status per string in docs/TELUGU_REVIEW.md
TAGLINE_EN = "The voice farm manager for India's poultry farmers."

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
# Local farm state (profile, proposals, records). .local/ is gitignored; `python tasks.py reset-demo` deletes it.
DEFAULT_STATE_PATH = REPO_ROOT / ".local" / "clucktalk.sqlite3"

# Hard cap on live model calls per day (user decision 2026-09-29): a lower cap may be configured, never a higher one.
AI_HARD_DAILY_CAP = 100

_TRUE = {"true", "1", "yes"}
_FALSE = {"false", "0", "no"}
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_ORIGIN_RE = re.compile(r"https?://(?:[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?|\[[0-9A-Fa-f:]+\])(?::[0-9]{1,5})?")


class ConfigError(ValueError):
    """A setting is missing or malformed. The message names the variable and the accepted values."""


@dataclass(frozen=True)
class Settings:
    mock_bedrock: bool
    host: str
    port: int
    allowed_origins: tuple[str, ...]  # the Origin check: the server's own loopback origins + extra_origins
    auth_token: str | None
    aws_region: str | None
    state_path: Path = DEFAULT_STATE_PATH
    mock_bedrock_given: bool = False  # MOCK_BEDROCK was set explicitly (live AI needs an explicit "false")
    bedrock_model_id: str | None = None
    ai_max_calls_per_day: int = AI_HARD_DAILY_CAP
    # Extra browser origins from CLUCKTALK_ALLOWED_ORIGINS (an explicit list, never "*"). Only these get CORS headers.
    extra_origins: tuple[str, ...] = ()

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


def _state_path(raw: str) -> Path:
    """A relative path is taken from the repo root, so the server and reset-demo agree whatever the working
    directory; it must be a .sqlite3 file (reset-demo deletes only such a file)."""
    if not raw:
        return DEFAULT_STATE_PATH
    path = Path(raw)
    path = path if path.is_absolute() else REPO_ROOT / path
    if path.suffix != ".sqlite3":
        raise ConfigError(f"CLUCKTALK_STATE_PATH={raw!r} must name a .sqlite3 file.")
    return path


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
    extra_origins = _parse_origins(env.get("CLUCKTALK_ALLOWED_ORIGINS", ""))
    port = _parse_port(env, "CLUCKTALK_PORT", 8765)
    return Settings(
        mock_bedrock=_parse_bool(env, "MOCK_BEDROCK", default=False),
        host=host,
        port=port,
        allowed_origins=(f"http://127.0.0.1:{port}", f"http://localhost:{port}", *extra_origins),
        auth_token=auth_token,
        aws_region=env.get("AWS_REGION", "").strip() or None,
        state_path=_state_path(env.get("CLUCKTALK_STATE_PATH", "").strip()),
        mock_bedrock_given=env.get("MOCK_BEDROCK", "").strip() != "",
        bedrock_model_id=env.get("BEDROCK_MODEL_ID", "").strip() or None,
        ai_max_calls_per_day=_ai_cap(env.get("CLUCKTALK_AI_MAX_CALLS_PER_DAY", "").strip()),
        extra_origins=extra_origins,
    )


def _parse_origins(raw: str) -> tuple[str, ...]:
    """CLUCKTALK_ALLOWED_ORIGINS: comma-separated exact origins (scheme://host[:port]). No wildcard, no path."""
    origins = tuple(o.strip() for o in raw.split(",") if o.strip())
    for origin in origins:
        if not _ORIGIN_RE.fullmatch(origin):
            raise ConfigError(
                f"CLUCKTALK_ALLOWED_ORIGINS has {origin!r}, which is not an exact origin. Use a comma-separated "
                "list like http://localhost:8080 (scheme, host, optional port; no '*', no path)."
            )
    return origins


def _ai_cap(raw: str) -> int:
    if raw == "":
        return AI_HARD_DAILY_CAP
    if not raw.isdigit() or int(raw) > AI_HARD_DAILY_CAP:
        raise ConfigError(
            f"CLUCKTALK_AI_MAX_CALLS_PER_DAY={raw!r} must be a whole number from 0 to {AI_HARD_DAILY_CAP} "
            "(the hard cap; it can only be lowered)."
        )
    return int(raw)


def require_live_ai(settings: Settings) -> None:
    """Live AI (the synthetic demo farm + Amazon Nova via Bedrock) starts only on an explicit choice. Mock mode
    (MOCK_BEDROCK=true) stays the default the task runner sets; an unset MOCK_BEDROCK is not a choice."""
    if settings.mock_bedrock:
        return
    if not settings.mock_bedrock_given:
        raise ConfigError(
            "MOCK_BEDROCK is not set. Use MOCK_BEDROCK=true for the demo (no AWS), or MOCK_BEDROCK=false with "
            "BEDROCK_MODEL_ID and AWS_REGION for live AI."
        )
    missing = [
        n for n, v in (("BEDROCK_MODEL_ID", settings.bedrock_model_id), ("AWS_REGION", settings.aws_region)) if not v
    ]
    if missing:
        raise ConfigError(f"Live AI (MOCK_BEDROCK=false) needs {' and '.join(missing)}.")
