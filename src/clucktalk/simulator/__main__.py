"""Start the Simulator (Windows: python tasks.py run starts it together with the MCP server).

Environment: MOCK_BEDROCK must be true (the live host is not built yet); CLUCKTALK_SIMULATOR_PORT (default 8766);
CLUCKTALK_MCP_URL (default http://127.0.0.1:<CLUCKTALK_PORT>/mcp); CLUCKTALK_AUTH_TOKEN is sent when set.
"""

from __future__ import annotations

import logging
import os
import sys

from clucktalk.config import ConfigError, load_settings
from clucktalk.simulator.app import SimulatorSettings, build_app

DEFAULT_PORT = 8766


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
    return SimulatorSettings(port=port, mcp_url=mcp_url, auth_token=server.auth_token, mode=server.mode)


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
