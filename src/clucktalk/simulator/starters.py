"""The one-tap starter questions on the Simulator's first screen (demo mode).

Each chip shows a Telugu question with its English gloss. Both come from the existing catalog pairs in
``clucktalk.i18n.pilot`` (nothing is written here), so a chip can never show a Telugu line without its English side.
``say`` is the English sentence the Simulator sends when the chip is tapped: the demo host understands English text
only, so the chip does not claim to send Telugu. For four of the five chips ``say`` is the catalog gloss itself; the
health check sends a sample sick-bird report, because the bare gloss "Health check" is not a sentence the demo host
routes to that tool (it is checked in tests/unit/test_simulator_starters.py).

Left out on purpose: the schedule questions ("What day is it today?", "When is the next vaccination?") need the pilot
farm file, and "Birds after the check" is only answered once a follow-up is due; the demo host answers neither.
``REPLIES`` are the yes and no taps that appear while the host waits for an answer (the vet-summary offer, a read-back).
"""

from __future__ import annotations

from dataclasses import dataclass

from clucktalk.i18n import Text
from clucktalk.i18n.pilot import (
    CHIP_BRIEFING,
    CHIP_HEALTH,
    CHIP_HELP,
    CHIP_SALE,
    CHIP_STATUS,
    NO_BUTTON,
    YES_BUTTON,
)

HEALTH_SAY = "Shed two birds are coughing and not eating"


@dataclass(frozen=True)
class Starter:
    text: Text
    say: str


STARTERS = (
    Starter(CHIP_STATUS, CHIP_STATUS.en),
    Starter(CHIP_SALE, CHIP_SALE.en),
    Starter(CHIP_HEALTH, HEALTH_SAY),
    Starter(CHIP_BRIEFING, CHIP_BRIEFING.en),
    Starter(CHIP_HELP, CHIP_HELP.en),
)
REPLIES = (Starter(YES_BUTTON, "yes"), Starter(NO_BUTTON, "no"))


def as_json(items: tuple[Starter, ...]) -> list[dict[str, str]]:
    return [{"te": s.text.te, "en": s.text.en, "say": s.say} for s in items]
