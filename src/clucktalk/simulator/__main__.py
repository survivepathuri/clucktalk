"""Start the Simulator (Windows: python tasks.py run starts it together with the MCP server).

Environment: MOCK_BEDROCK must be true (the live host is not built yet); CLUCKTALK_SIMULATOR_PORT (default 8766);
CLUCKTALK_MCP_URL (default http://127.0.0.1:<CLUCKTALK_PORT>/mcp); CLUCKTALK_AUTH_TOKEN is sent when set.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

from clucktalk.config import TOKEN_PATTERN, ConfigError, load_settings
from clucktalk.simulator.app import SimulatorSettings, build_app

DEFAULT_PORT = 8766
_PUBLIC_ORIGIN = re.compile(r"https://[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?")
MAX_TOKENS = 10


def _whole(env: dict[str, str], name: str, default: int, low: int, high: int) -> int:
    raw = env.get(name, "").strip()
    if raw == "":
        return default
    if not raw.isdigit() or not low <= int(raw) <= high:
        raise ConfigError(f"{name}={raw!r} must be a whole number from {low} to {high}.")
    return int(raw)


def _tokens(env: dict[str, str], pilot: bool) -> tuple[str, ...]:
    tokens = tuple(t.strip() for t in env.get("CLUCKTALK_SIMULATOR_TOKENS", "").split(",") if t.strip())
    if pilot and not tokens:
        raise ConfigError(
            "CLUCKTALK_MODE=pilot needs CLUCKTALK_SIMULATOR_TOKENS: one bearer token per farmer, comma separated, each "
            "24 to 128 letters, digits or . _ ~ - (make one with: "
            'python -c "import secrets; print(secrets.token_urlsafe(32))").'
        )
    if (
        len(tokens) > MAX_TOKENS
        or len(set(tokens)) != len(tokens)
        or not all(TOKEN_PATTERN.fullmatch(t) for t in tokens)
    ):
        raise ConfigError(
            "CLUCKTALK_SIMULATOR_TOKENS must be at most 10 different tokens of 24 to 128 letters, digits or . _ ~ -."
        )
    return tokens


def load_simulator_settings(env: dict[str, str] | None = None) -> SimulatorSettings:
    env = dict(os.environ) if env is None else env
    server = load_settings(env)  # same validation as the server (port, token, mock flag)
    if not server.mock_bedrock:
        raise ConfigError(
            "The Simulator's live host (Bedrock + Polly) needs the AWS setup, which is not done yet. "
            "Set MOCK_BEDROCK=true for the demo (python tasks.py run does this)."
        )
    raw = env.get("CLUCKTALK_SIMULATOR_PORT", "").strip()
    if raw and (not raw.isdigit() or not 1 <= int(raw) <= 65535):
        raise ConfigError(f"CLUCKTALK_SIMULATOR_PORT={raw!r} is not a valid TCP port (1-65535).")
    port = int(raw) if raw else DEFAULT_PORT
    if port == server.port:
        raise ConfigError(f"The Simulator and the MCP server cannot both use port {port}.")
    mcp_url = env.get("CLUCKTALK_MCP_URL", "").strip() or f"http://127.0.0.1:{server.port}/mcp"
    pilot = server.mode == "pilot"
    tokens = _tokens(env, pilot)
    if server.auth_token is not None and server.auth_token in tokens:
        raise ConfigError(
            "CLUCKTALK_AUTH_TOKEN (the MCP server's) must be different from every CLUCKTALK_SIMULATOR_TOKENS token."
        )
    public = env.get("CLUCKTALK_PUBLIC_ORIGIN", "").strip()
    if public and not _PUBLIC_ORIGIN.fullmatch(public):
        raise ConfigError(
            f"CLUCKTALK_PUBLIC_ORIGIN={public!r} must be an exact https origin like https://pilot.example.org."
        )
    state_dir = server.state_path.parent
    disabled = env.get("CLUCKTALK_DISABLED_FILE", "").strip()
    usage = env.get("CLUCKTALK_USAGE_PATH", "").strip()
    return SimulatorSettings(
        port=port,
        mcp_url=mcp_url,
        auth_token=server.auth_token,
        mode=server.mode,
        tokens=tokens,
        public_origin=public or None,
        rate_per_minute=_whole(env, "CLUCKTALK_RATE_PER_MINUTE", 60, 1, 6000),
        max_sessions=_whole(env, "CLUCKTALK_MAX_SESSIONS", 20, 1, 1000),
        disabled_file=Path(disabled) if disabled else state_dir / "DISABLED",
        farm_path=server.pilot_farm_path if pilot else None,
        usage_path=(Path(usage) if usage else state_dir / f"usage_{server.instance_name}.json") if pilot else None,
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = load_simulator_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    import uvicorn

    label = "PILOT (real farm, prototype)" if settings.mode == "pilot" else "DEMO DATA (MOCK_BEDROCK=true)"
    print(f"Simulator | mode: {label} | MCP server: {settings.mcp_url}")
    print(f"Open: http://127.0.0.1:{settings.port}/")
    uvicorn.run(build_app(settings), host="127.0.0.1", port=settings.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
