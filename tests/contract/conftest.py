"""Contract tests run the real ASGI app under uvicorn on a free 127.0.0.1 port and speak raw MCP JSON-RPC
over HTTP, so they check the wire format a client actually sees (docs/DESIGN.md §4-§5)."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx2
import pytest
import uvicorn
from mcp.server.mcpserver import MCPServer

from clucktalk.config import load_settings
from clucktalk.server.app import MCP_PATH, TARGET_PROTOCOL_VERSION, build_app, build_mcp_server

ACCEPT = "application/json, text/event-stream"
LEAK_SECRET = "internal-detail-7f3a"  # the crash probe raises this; it must never reach the client


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class LiveServer:
    base: str
    port: int
    token: str | None = None

    @property
    def url(self) -> str:
        return self.base + MCP_PATH

    def headers(self, session_id: str | None = None, **extra: str) -> dict[str, str]:
        h = {"content-type": "application/json", "accept": ACCEPT}
        if session_id:
            h["mcp-session-id"] = session_id
            h["mcp-protocol-version"] = TARGET_PROTOCOL_VERSION
        if self.token:
            h["authorization"] = f"Bearer {self.token}"
        h.update(extra)
        return h

    def post(self, body: dict[str, Any], session_id: str | None = None, **extra: str) -> httpx2.Response:
        return httpx2.post(self.url, json=body, headers=self.headers(session_id, **extra), timeout=10)

    def initialize(self, version: str = TARGET_PROTOCOL_VERSION) -> tuple[str, dict[str, Any]]:
        r = self.post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": version,
                    "capabilities": {},
                    "clientInfo": {"name": "contract-test", "version": "0"},
                },
            }
        )
        assert r.status_code == 200, r.text
        sid = r.headers.get("mcp-session-id")
        assert sid, "server must assign an Mcp-Session-Id"
        n = self.post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session_id=sid)
        assert n.status_code == 202, n.text
        return sid, r.json()

    def call(self, session_id: str, method: str, params: dict[str, Any] | None = None, rid: int = 2) -> dict[str, Any]:
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            body["params"] = params
        r = self.post(body, session_id=session_id)
        assert r.status_code == 200, r.text
        return r.json()


def _start(env: dict[str, str], customize: Callable[[MCPServer], None] | None = None) -> tuple[LiveServer, Callable]:
    port = _free_port()
    settings = load_settings({"MOCK_BEDROCK": "true", "CLUCKTALK_PORT": str(port), **env})
    server = build_mcp_server()
    if customize:
        customize(server)
    config = uvicorn.Config(build_app(settings, server), host=settings.host, port=port, log_level="warning")
    uv = uvicorn.Server(config)
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not uv.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("test server did not start")
        time.sleep(0.02)

    def stop() -> None:
        uv.should_exit = True
        thread.join(timeout=10)

    return LiveServer(base=f"http://127.0.0.1:{port}", port=port, token=settings.auth_token), stop


def _add_crash_probe(server: MCPServer) -> None:
    @server.tool(name="crash_probe", description="Test-only tool that always raises.")
    def crash_probe() -> str:
        raise RuntimeError(f"db password rejected: {LEAK_SECRET}")


@pytest.fixture(scope="session")
def live() -> Iterator[LiveServer]:
    srv, stop = _start({})
    yield srv
    stop()


@pytest.fixture(scope="session")
def live_with_probe() -> Iterator[LiveServer]:
    srv, stop = _start({}, customize=_add_crash_probe)
    yield srv
    stop()


@pytest.fixture(scope="session")
def live_with_token() -> Iterator[LiveServer]:
    srv, stop = _start({"CLUCKTALK_AUTH_TOKEN": "test-token-not-a-secret"})
    yield srv
    stop()
