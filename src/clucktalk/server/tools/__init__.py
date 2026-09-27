"""One module per customer intent (docs/DESIGN.md §5, rule 1).

Each tool module exposes ``register(server, registry)``. A tool that should appear in "what can you do?"
adds a ``Capability`` to the registry when it registers, so help only ever lists tools that exist
(docs/DESIGN.md §5, rule 8).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from clucktalk.i18n import Text


@dataclass(frozen=True)
class Capability:
    tool_name: str
    title: Text
    example_en: str  # an utterance that the golden suite also covers


@dataclass
class CapabilityRegistry:
    items: list[Capability] = field(default_factory=list)

    def add(self, capability: Capability) -> None:
        if any(c.tool_name == capability.tool_name for c in self.items):
            raise ValueError(f"capability for {capability.tool_name!r} registered twice")
        self.items.append(capability)
