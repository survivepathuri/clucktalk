"""``get_help``: the "What can you do?" intent (onboarding, docs/DESIGN.md §6)."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict

from clucktalk.config import APP_NAME, APP_NAME_TE
from clucktalk.i18n import HELP_INTRO, HELP_NOTHING_YET, HELP_TRY
from clucktalk.server.tools import CapabilityRegistry

# Voice-only rule: never read out more than 5 options (docs/DESIGN.md §6).
MAX_SPOKEN_EXAMPLES = 5


class CapabilityOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str
    title_en: str
    title_te: str
    example_en: str


class GetHelpOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_en: str
    text_te: str
    capabilities: list[CapabilityOut]


DESCRIPTION = (
    f"Use when the farmer asks what {APP_NAME} can do, how to use it, or says 'help'. "
    "Takes no input. Returns a short spoken introduction and example questions for the farm tools "
    "that are available right now."
)


def build_help(registry: CapabilityRegistry) -> GetHelpOutput:
    intro_en = HELP_INTRO.en.format(app_en=APP_NAME, app_te=APP_NAME_TE)
    intro_te = HELP_INTRO.te.format(app_en=APP_NAME, app_te=APP_NAME_TE)
    caps = [
        CapabilityOut(tool_name=c.tool_name, title_en=c.title.en, title_te=c.title.te, example_en=c.example_en)
        for c in registry.items
    ]
    if caps:
        spoken = "; ".join(f"'{c.example_en}'" for c in caps[:MAX_SPOKEN_EXAMPLES])
        text_en = f"{intro_en} {HELP_TRY.en} {spoken}."
        text_te = f"{intro_te} {HELP_TRY.te} " + "; ".join(c.title_te for c in caps[:MAX_SPOKEN_EXAMPLES]) + "."
    else:
        text_en = f"{intro_en} {HELP_NOTHING_YET.en}"
        text_te = f"{intro_te} {HELP_NOTHING_YET.te}"
    return GetHelpOutput(text_en=text_en, text_te=text_te, capabilities=caps)


def register(server: MCPServer, registry: CapabilityRegistry) -> None:
    @server.tool(
        name="get_help",
        title="What can you do?",
        description=DESCRIPTION,
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False),
    )
    def get_help() -> Annotated[CallToolResult, GetHelpOutput]:
        out = build_help(registry)
        return CallToolResult(
            content=[TextContent(type="text", text=out.text_en)],
            structured_content=out.model_dump(mode="json"),
        )
