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


# What farmers say when they mean every house; treated like an omitted `house` argument.
WHOLE_FARM_WORDS = {"", "all", "all houses", "all sheds", "every house", "every shed", "whole farm", "the farm", "farm"}


def whole_farm_or(house_ref: str | None) -> str | None:
    """None (whole farm) for an omitted, empty, or 'all' reference; otherwise the reference unchanged."""
    if house_ref is None or house_ref.strip().lower() in WHOLE_FARM_WORDS:
        return None
    return house_ref


def unavailable_text(u) -> Text:
    """Spoken line for a house that could not be checked. Its message may already name the house."""
    en = u.message_en if u.label_en in u.message_en else f"For {u.label_en}: {u.message_en}"
    te = u.message_te if u.label_te in u.message_te else f"{u.label_te}: {u.message_te}"
    return Text(en, te)
