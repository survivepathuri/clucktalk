"""Placeholder photos for health-check photo input (docs/DESIGN.md §18, step 1B).

There are NO real photos in this repository yet. Each entry is a clearly labelled placeholder image in
``docs/assets/`` (drawn by ``scripts/make_placeholders.py``, listed in ``docs/SOURCES.md`` as "PLACEHOLDER - not a
real photo"). Photo input is not validated on real photos, so the demo rules never read a photo and a photo can
never change a triage result: it is recorded with the check and shown as attached, nothing more.
"""

from __future__ import annotations

from dataclasses import dataclass

from clucktalk.i18n import Text

LABEL = Text(
    "Photo input (placeholder, not yet validated on real photos)",
    "ఫోటో ఇన్‌పుట్ (ప్లేస్‌హోల్డర్, నిజమైన ఫోటోలపై ఇంకా పరీక్షించలేదు)",
)
NOT_ANALYZED = Text(
    "A placeholder photo is attached. It was not analyzed, and it did not change the result.",
    "ఒక ప్లేస్‌హోల్డర్ ఫోటో జత చేయబడింది. దాన్ని విశ్లేషించలేదు, ఫలితాన్ని అది మార్చలేదు.",
)


@dataclass(frozen=True)
class PlaceholderPhoto:
    ref: str
    filename: str
    colour: tuple[int, int, int]


PLACEHOLDER_PHOTOS: tuple[PlaceholderPhoto, ...] = (
    PlaceholderPhoto("placeholder_1", "placeholder_1.png", (70, 90, 130)),
    PlaceholderPhoto("placeholder_2", "placeholder_2.png", (120, 70, 90)),
    PlaceholderPhoto("placeholder_3", "placeholder_3.png", (90, 110, 70)),
)
PHOTO_REFS: tuple[str, ...] = tuple(p.ref for p in PLACEHOLDER_PHOTOS)
BY_REF: dict[str, PlaceholderPhoto] = {p.ref: p for p in PLACEHOLDER_PHOTOS}
