"""Structured error contract (docs/DESIGN.md §5, rule 4).

Every failed tool call returns ``isError: true`` with:
- ``content``: one customer-safe sentence plus one next step, in English (what Alexa speaks);
- ``_meta["clucktalk/error"]``: the same message and next step in English and Telugu;
- no ``structuredContent``: MCP 2025-11-25 says structured results MUST conform to the tool's outputSchema,
  with no exemption for errors, and MCP Inspector 2.8.0 enforces that on error results too.
Never codes, tool names, JSON, IDs, or exception text.

``SafeToolErrors`` is the backstop for failures the tool did not describe itself: argument validation
(which the SDK reports with field names and the tool name) and unexpected crashes (which the SDK reports as
"Error executing tool <name>"). The original text is logged on the server only.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import jsonschema
from mcp.server import ServerRequestContext
from mcp.server.context import CallNext, HandlerResult
from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent

from clucktalk.domain.errors import DomainError
from clucktalk.i18n import BAD_REQUEST_ERROR, BAD_REQUEST_NEXT_STEP, GENERIC_ERROR, GENERIC_NEXT_STEP, Text

logger = logging.getLogger("clucktalk.server")

ERROR_META_KEY = "clucktalk/error"  # _meta key: prefix "clucktalk/" + name (MCP _meta naming)
DEMO_CLOCK_META_KEY = "clucktalk/demo_clock"


def demo_clock_marker(days: int) -> dict[str, Any]:
    """The visible "Demo clock: +N days" marker (docs/DESIGN.md section 18). It rides in ``_meta``, not in
    ``structuredContent``, because every tool's output schema is closed. Only built when the clock is on."""
    unit = "day" if days == 1 else "days"
    return {"days_later": days, "label_en": f"Demo clock: +{days} {unit}", "label_te": f"డెమో గడియారం: +{days} రోజులు"}


def error_result(message: Text, next_step: Text) -> CallToolResult:
    """The only way CluckTalk builds a failed tool result."""
    return CallToolResult(
        content=[TextContent(type="text", text=f"{message.en} {next_step.en}")],
        meta={
            ERROR_META_KEY: {
                "message_en": message.en,
                "message_te": message.te,
                "next_step_en": next_step.en,
                "next_step_te": next_step.te,
            }
        },
        is_error=True,
    )


def domain_error_result(err: DomainError) -> CallToolResult:
    """A described domain failure (unknown shed, too few records, ...) in the same contract shape."""
    return error_result(Text(err.customer_message, err.customer_message_te), Text(err.next_step, err.next_step_te))


def _wire(result: CallToolResult) -> dict[str, Any]:
    """Wire form for a 2025-11-25 connection. A middleware result bypasses the SDK's per-version shaping
    (mcp/server/runner.py: "trusted to return its own well-formed result"), so drop the 2026-era
    ``resultType`` field here. The protocol gate keeps modern connections out (app.ProtocolVersionGate)."""
    return result.model_dump(by_alias=True, mode="json", exclude_none=True, exclude={"result_type"})


def is_contract_error(result: CallToolResult) -> bool:
    meta = result.meta
    return bool(result.is_error) and isinstance(meta, dict) and isinstance(meta.get(ERROR_META_KEY), dict)


class SafeToolErrors:
    """Server middleware for ``tools/call``: validate arguments against the advertised ``inputSchema`` first,
    then replace any error result that does not follow the contract with a safe one."""

    def __init__(
        self,
        strict_arguments_for: frozenset[str] = frozenset(),
        demo_clock_days: Callable[[], int] = lambda: 0,
    ) -> None:
        # Tools whose unknown argument names are refused instead of ignored: a retired argument must never be
        # silently dropped (set_contract_terms once took mortality_allowance_pct).
        self._strict = strict_arguments_for
        self._demo_clock_days = demo_clock_days  # the marker is added to every result only while this is above 0
        self._server: MCPServer | None = None
        self._validators: dict[str, jsonschema.protocols.Validator] | None = None

    def bind(self, server: MCPServer) -> None:
        """Attach after the server exists (MCPServer takes middleware in its constructor)."""
        self._server = server

    async def _validator_for(self, tool_name: str) -> jsonschema.protocols.Validator | None:
        if self._server is None:
            raise RuntimeError("SafeToolErrors used before bind(server)")
        if self._validators is None:
            validators = {}
            for tool in await self._server.list_tools():
                cls = jsonschema.validators.validator_for(tool.input_schema)
                cls.check_schema(tool.input_schema)
                validators[tool.name] = cls(tool.input_schema)
            self._validators = validators
        return self._validators.get(tool_name)

    async def __call__(self, ctx: ServerRequestContext[Any, Any], call_next: CallNext) -> HandlerResult:
        if ctx.method != "tools/call" or ctx.request_id is None:
            return await call_next(ctx)

        params = ctx.params if isinstance(ctx.params, dict) else {}
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        validator = await self._validator_for(tool_name) if isinstance(tool_name, str) else None
        if validator is not None:
            problems = sorted(
                {"/".join(str(p) for p in e.absolute_path) or "(root)" for e in validator.iter_errors(arguments)}
            )
            if tool_name in self._strict and isinstance(arguments, dict):
                known = set(validator.schema.get("properties", {}))
                problems += sorted(f"{name} (not accepted)" for name in set(arguments) - known)
            if problems:
                # Field paths only: the rejected values are the caller's data.
                logger.info("tools/call %r rejected arguments at %s", tool_name, problems)
                return self._marked(_wire(error_result(BAD_REQUEST_ERROR, BAD_REQUEST_NEXT_STEP)))

        result = await call_next(ctx)
        parsed = CallToolResult.model_validate(result) if isinstance(result, dict) else result
        if isinstance(parsed, CallToolResult) and parsed.is_error and not is_contract_error(parsed):
            original = " ".join(c.text for c in parsed.content if isinstance(c, TextContent))
            logger.warning("tools/call %r failed without a contract error; replaced. Original: %r", tool_name, original)
            return self._marked(_wire(error_result(GENERIC_ERROR, GENERIC_NEXT_STEP)))
        return self._marked(result)

    def _marked(self, result: HandlerResult) -> HandlerResult:
        """Add the demo-clock marker to a result's ``_meta`` while the clock is on; otherwise return it untouched."""
        days = self._demo_clock_days()
        if days <= 0:
            return result
        marker = demo_clock_marker(days)
        if isinstance(result, CallToolResult):
            result.meta = {**(result.meta or {}), DEMO_CLOCK_META_KEY: marker}
        elif isinstance(result, dict):
            result["_meta"] = {**(result.get("_meta") or {}), DEMO_CLOCK_META_KEY: marker}
        return result
