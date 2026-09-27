"""The Simulator's MCP client: raw JSON-RPC over Streamable HTTP, protocol 2025-11-25 (docs/DESIGN.md §2).

Deliberately not a high-level SDK client: the developer panel shows the exact messages on the wire. Like an
MCP Apps host, it advertises the ``io.modelcontextprotocol/ui`` extension, learns each tool's
``_meta.ui.resourceUri`` from ``tools/list``, and reads ``ui://`` resources once (hosts may cache them).
Failures are raised as ``McpUnavailable`` with the reason; nothing is ever substituted (Rule 6).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx2

logger = logging.getLogger("clucktalk.simulator")

PROTOCOL_VERSION = "2025-11-25"
APPS_EXTENSION = "io.modelcontextprotocol/ui"
APP_MIME_TYPE = "text/html;profile=mcp-app"
ACCEPT = "application/json, text/event-stream"


class McpUnavailable(RuntimeError):
    """The MCP server could not be reached or answered with an HTTP/protocol failure."""


@dataclass
class Exchange:
    """One JSON-RPC request and its response, as sent and received, with the measured round trip."""

    request: dict[str, Any]
    response: dict[str, Any] | None
    status: int
    ms: float

    def as_dict(self) -> dict[str, Any]:
        return {"request": self.request, "response": self.response, "http_status": self.status, "ms": round(self.ms, 1)}


class McpClient:
    def __init__(self, url: str, auth_token: str | None = None, client_name: str = "CluckTalk Simulator") -> None:
        self.url = url
        self._auth = auth_token
        self._client_name = client_name
        self._http = httpx2.AsyncClient(timeout=15)
        self._session: str | None = None
        self._next_id = 1
        self.tools: dict[str, dict[str, Any]] = {}
        self._resources: dict[str, dict[str, Any]] = {}
        self.server_info: dict[str, Any] = {}

    async def aclose(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict[str, str]:
        h = {"content-type": "application/json", "accept": ACCEPT}
        if self._session:
            h["mcp-session-id"] = self._session
            h["mcp-protocol-version"] = PROTOCOL_VERSION
        if self._auth:
            h["authorization"] = f"Bearer {self._auth}"
        return h

    async def _post(self, body: dict[str, Any]) -> Exchange:
        start = time.perf_counter()
        try:
            r = await self._http.post(self.url, json=body, headers=self._headers())
        except httpx2.HTTPError as err:  # connection refused, timeout, ...
            logger.warning("MCP server unreachable at %s: %s", self.url, err)
            raise McpUnavailable(f"CluckTalk MCP server not reachable at {self.url} ({type(err).__name__})") from err
        ms = (time.perf_counter() - start) * 1000
        payload = r.json() if r.content and r.headers.get("content-type", "").startswith("application/json") else None
        return Exchange(request=body, response=payload, status=r.status_code, ms=ms)

    def _take_id(self) -> int:
        rid = self._next_id
        self._next_id += 1
        return rid

    async def connect(self) -> list[Exchange]:
        """initialize -> notifications/initialized -> tools/list. Returns the exchanges for the log."""
        self._session = None
        start = time.perf_counter()
        body = {
            "jsonrpc": "2.0",
            "id": self._take_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"extensions": {APPS_EXTENSION: {"mimeTypes": [APP_MIME_TYPE]}}},
                "clientInfo": {"name": self._client_name, "version": "0.1.0"},
            },
        }
        try:
            r = await self._http.post(self.url, json=body, headers=self._headers())
        except httpx2.HTTPError as err:
            logger.warning("MCP server unreachable at %s: %s", self.url, err)
            raise McpUnavailable(f"CluckTalk MCP server not reachable at {self.url} ({type(err).__name__})") from err
        init = Exchange(
            body, r.json() if r.status_code == 200 else None, r.status_code, (time.perf_counter() - start) * 1000
        )
        if r.status_code != 200 or not init.response or "result" not in init.response:
            raise McpUnavailable(f"initialize failed (HTTP {r.status_code})")
        result = init.response["result"]
        if result.get("protocolVersion") != PROTOCOL_VERSION:
            raise McpUnavailable(
                f"server negotiated protocol {result.get('protocolVersion')!r}, not {PROTOCOL_VERSION}"
            )
        session = r.headers.get("mcp-session-id")
        if not session:
            raise McpUnavailable("server did not assign an Mcp-Session-Id")
        self._session = session
        self.server_info = result.get("serverInfo", {})
        note = await self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        if note.status != 202:
            raise McpUnavailable(f"notifications/initialized was not accepted (HTTP {note.status})")
        listing = await self._post({"jsonrpc": "2.0", "id": self._take_id(), "method": "tools/list"})
        if not listing.response or "result" not in listing.response:
            raise McpUnavailable(f"tools/list failed (HTTP {listing.status})")
        self.tools = {t["name"]: t for t in listing.response["result"]["tools"]}
        self._resources.clear()
        return [init, note, listing]

    def resource_uri(self, tool: str) -> str | None:
        ui = ((self.tools.get(tool) or {}).get("_meta") or {}).get("ui") or {}
        uri = ui.get("resourceUri")
        return uri if isinstance(uri, str) and uri.startswith("ui://") else None

    async def request(self, method: str, params: dict[str, Any] | None = None) -> list[Exchange]:
        """One request. Reconnects once if the session is gone (server restarted), and says so in the log."""
        log: list[Exchange] = []
        if self._session is None:
            log += await self.connect()
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": self._take_id(), "method": method}
        if params is not None:
            body["params"] = params
        ex = await self._post(body)
        if ex.status == 404:  # unknown session: the server restarted
            logger.info("MCP session expired; reconnecting")
            log.append(ex)
            log += await self.connect()
            body["id"] = self._take_id()
            ex = await self._post(body)
        log.append(ex)
        if ex.status != 200 or ex.response is None:
            raise McpUnavailable(f"{method} failed (HTTP {ex.status})")
        return log

    async def read_ui_resource(self, uri: str) -> tuple[dict[str, Any], list[Exchange]]:
        """The ``ui://`` resource content item (text + mimeType + _meta), cached per session."""
        if uri in self._resources:
            return self._resources[uri], []
        log = await self.request("resources/read", {"uri": uri})
        response = log[-1].response or {}
        contents = (response.get("result") or {}).get("contents") or []
        if not contents or contents[0].get("mimeType") != APP_MIME_TYPE or "text" not in contents[0]:
            raise McpUnavailable(f"resources/read for {uri} did not return {APP_MIME_TYPE} text")
        self._resources[uri] = contents[0]
        return contents[0], log
