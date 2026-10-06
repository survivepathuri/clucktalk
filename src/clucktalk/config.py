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
# Local farm state (profile, proposals, records). .local/ is gitignored. `python tasks.py reset-demo --yes` moves this
# file to a backups folder next to it (never deletes it) and deletes only the separate demo-clock file next to it
# (Settings.demo_clock_state_path).
DEFAULT_STATE_PATH = REPO_ROOT / ".local" / "clucktalk.sqlite3"
# The demo clock's own state file is the live file's name plus this suffix (the one place the name is built).
DEMO_CLOCK_STATE_SUFFIX = "_demo_clock"

# Hard cap on live model calls per day (user decision 2026-09-29): a lower cap may be configured, never a higher one.
AI_HARD_DAILY_CAP = 100

_TRUE = {"true", "1", "yes"}
_FALSE = {"false", "0", "no"}
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
# A bearer token (the farmer's or the MCP server's): long enough not to be guessed, safe in a link fragment.
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9._~-]{24,128}")
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
    demo_days_later: int = 0  # CLUCKTALK_DEMO_DAYS_LATER: the demo clock (0 = off); demo mode only
    # CLUCKTALK_MODE: "demo" (the fictional farm, the default) or "pilot" (the farmer's own farm file, his own state
    # file, no synthetic history). A pilot instance and a demo instance never share a state file (Step 51).
    mode: str = "demo"
    instance_name: str = "demo"  # CLUCKTALK_INSTANCE_NAME; a pilot's state file name must contain it
    pilot_farm_path: Path | None = None  # CLUCKTALK_PILOT_FARM_PATH: pilot mode only

    @property
    def is_local(self) -> bool:
        return self.host in _LOCAL_HOSTS

    @property
    def demo_clock_state_path(self) -> Path:
        """The state file used while the demo clock is on: a sibling of the live file with its own name. The demo
        clock writes shifted dates (checks, answers, proposals), so it must never share a file with the live state."""
        return self.state_path.with_name(f"{self.state_path.stem}{DEMO_CLOCK_STATE_SUFFIX}{self.state_path.suffix}")

    @property
    def active_state_path(self) -> Path:
        """The one file the server opens: the demo-clock file when the clock is on, otherwise the live file."""
        return self.demo_clock_state_path if self.demo_days_later else self.state_path


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
    directory; it must be a .sqlite3 file (reset-demo touches only such a file: it moves it to backups)."""
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
    mock_bedrock = _parse_bool(env, "MOCK_BEDROCK", default=False)
    demo_days_later = _demo_days_later(env.get("CLUCKTALK_DEMO_DAYS_LATER", "").strip(), mock_bedrock)
    port = _parse_port(env, "CLUCKTALK_PORT", 8765)
    mode, instance_name, pilot_farm_path, state_path = _mode_settings(env, mock_bedrock)
    return Settings(
        mock_bedrock=mock_bedrock,
        host=host,
        port=port,
        allowed_origins=(f"http://127.0.0.1:{port}", f"http://localhost:{port}", *extra_origins),
        auth_token=auth_token,
        aws_region=env.get("AWS_REGION", "").strip() or None,
        state_path=state_path,
        mock_bedrock_given=env.get("MOCK_BEDROCK", "").strip() != "",
        bedrock_model_id=env.get("BEDROCK_MODEL_ID", "").strip() or None,
        ai_max_calls_per_day=_ai_cap(env.get("CLUCKTALK_AI_MAX_CALLS_PER_DAY", "").strip()),
        extra_origins=extra_origins,
        demo_days_later=demo_days_later,
        mode=mode,
        instance_name=instance_name,
        pilot_farm_path=pilot_farm_path,
    )


_INSTANCE_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,23}")


def _same_folder(a: Path, b: Path) -> bool:
    return a.resolve().parent == b.resolve().parent


def _mode_settings(env: Mapping[str, str], mock_bedrock: bool) -> tuple[str, str, Path | None, Path]:
    """CLUCKTALK_MODE, the instance name, the pilot farm file and the state file, checked together (Step 51 part A).
    The demo (default) is unchanged except that it refuses anything that looks like a pilot's file. A pilot refuses to
    start unless it has its own farm file and its own state file, named after the instance and outside the demo's
    folder, so the two can never read or write the same data."""
    mode = env.get("CLUCKTALK_MODE", "").strip() or "demo"
    if mode not in ("demo", "pilot"):
        raise ConfigError(f"CLUCKTALK_MODE={mode!r} must be demo or pilot.")
    name = env.get("CLUCKTALK_INSTANCE_NAME", "").strip() or mode
    if not _INSTANCE_NAME.fullmatch(name):
        raise ConfigError(
            f"CLUCKTALK_INSTANCE_NAME={name!r} must be 1 to 24 characters: lowercase letters, digits and hyphens."
        )
    raw_state = env.get("CLUCKTALK_STATE_PATH", "").strip()
    raw_farm = env.get("CLUCKTALK_PILOT_FARM_PATH", "").strip()
    if mode == "demo":
        if raw_farm:
            raise ConfigError("CLUCKTALK_PILOT_FARM_PATH is only for CLUCKTALK_MODE=pilot; the demo uses its own seed.")
        state = _state_path(raw_state)
        if "pilot" in state.name.lower():
            raise ConfigError(
                f"CLUCKTALK_STATE_PATH={raw_state!r} looks like a pilot state file, and this is the demo instance. "
                "A pilot and a demo never share a state file."
            )
        return mode, name, None, state
    if mock_bedrock is not True or env.get("MOCK_BEDROCK", "").strip() == "":
        raise ConfigError(
            "CLUCKTALK_MODE=pilot needs MOCK_BEDROCK=true: live AI for the pilot is not built yet "
            "(the pilot health check runs the rule-based test model, labeled as such)."
        )
    if env.get("CLUCKTALK_DEMO_DAYS_LATER", "").strip():
        raise ConfigError("CLUCKTALK_DEMO_DAYS_LATER is refused in pilot mode: it changes what 'today' means.")
    if not raw_farm:
        raise ConfigError(
            "CLUCKTALK_MODE=pilot needs CLUCKTALK_PILOT_FARM_PATH (the farmer's farm file, a .json file)."
        )
    farm = Path(raw_farm)
    farm = farm if farm.is_absolute() else REPO_ROOT / farm
    if farm.suffix.lower() != ".json":
        raise ConfigError(f"CLUCKTALK_PILOT_FARM_PATH={raw_farm!r} must name a .json file.")
    if not raw_state:
        raise ConfigError("CLUCKTALK_MODE=pilot needs CLUCKTALK_STATE_PATH (the pilot's own .sqlite3 file).")
    state = _state_path(raw_state)
    if state.resolve() == DEFAULT_STATE_PATH.resolve() or _same_folder(state, DEFAULT_STATE_PATH):
        raise ConfigError(
            f"CLUCKTALK_STATE_PATH={raw_state!r} is the demo's state file or lies next to it. "
            "Put the pilot's state file in its own folder."
        )
    if name not in state.name.lower():
        raise ConfigError(
            f"CLUCKTALK_STATE_PATH={raw_state!r}: the state file name must contain the instance name {name!r}."
        )
    token = env.get("CLUCKTALK_AUTH_TOKEN", "").strip()
    if not TOKEN_PATTERN.fullmatch(token):
        raise ConfigError(
            "CLUCKTALK_MODE=pilot needs CLUCKTALK_AUTH_TOKEN, a strong token for the MCP server (24 to 128 letters, "
            "digits or . _ ~ -): without it any process on this machine, the demo instance included, could read and "
            "change the farmer's records. Make one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(32))".'
        )
    return mode, name, farm, state


def _demo_days_later(raw: str, mock_bedrock: bool) -> int:
    """The demo clock (0 to 30 days). It makes the farm's "today" untrue, so it is refused in live mode."""
    if raw == "":
        return 0
    if not raw.isdigit() or int(raw) > 30:
        raise ConfigError(f"CLUCKTALK_DEMO_DAYS_LATER={raw!r} must be a whole number of days from 0 to 30.")
    days = int(raw)
    if days and not mock_bedrock:
        raise ConfigError(
            "CLUCKTALK_DEMO_DAYS_LATER is refused outside demo mode: it changes what 'today' means. "
            "Use MOCK_BEDROCK=true for the demo, or remove CLUCKTALK_DEMO_DAYS_LATER."
        )
    return days


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
