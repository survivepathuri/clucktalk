"""Resolve how a farmer names a house ("shed two", "kotam 2", "house no. 2", "do number") to a House.

Synonyms follow docs/DESIGN.md §5, rule 6 (shed / house / kotam) and cover Hinglish numbers.
Ambiguous or unknown references raise UnknownHouse with the list of real labels. Never guess.
"""

from __future__ import annotations

import re

from clucktalk.domain.errors import UnknownHouse
from clucktalk.domain.models import Farm, House

HOUSE_WORDS = {"house", "shed", "kotam", "kottam", "kotham", "coop", "no", "number", "the", "my"}
NUMBER_WORDS = {
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    # Hinglish
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
}  # fmt: skip


def parse_house_number(reference: str) -> int | None:
    """Extract the house number from a spoken reference, or None if there is not exactly one."""
    tokens = re.findall(r"[a-z]+|\d+", reference.lower())
    numbers = []
    for tok in tokens:
        if tok.isdigit():
            numbers.append(int(tok))
        elif tok in NUMBER_WORDS:
            numbers.append(NUMBER_WORDS[tok])
        elif tok not in HOUSE_WORDS:
            return None  # unexpected word: don't guess
    return numbers[0] if len(numbers) == 1 else None


def resolve_house(farm: Farm, reference: str) -> House:
    ref = reference.strip()
    for house in farm.houses:
        if ref == house.house_id:
            return house
    number = parse_house_number(ref)
    for house in farm.houses:
        if house.number == number:
            return house
    ordered = sorted(farm.houses, key=lambda h: h.number)
    raise UnknownHouse(ref, [h.label_en for h in ordered], [h.label_te for h in ordered])
