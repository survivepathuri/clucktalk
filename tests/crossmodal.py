"""Cross-modal check (docs/DESIGN.md §6): every number spoken in text_en / text_te must be a value the card
shows, i.e. a number somewhere in structuredContent. Breed names ("Ross 308") are names, not numbers, and are
removed before extraction."""

from __future__ import annotations

import re
from typing import Any

# A number not glued to a preceding letter/digit/dot/hyphen (so "house-2" IDs and "v1.2" are skipped),
# with optional thousands commas (Indian or Western) and decimals. Telugu suffixes ("23వ") may follow.
_NUMBER = re.compile(r"(?<![\w.\-])\d[\d,]*(?:\.\d+)?")
NAME_KEYS = {"breed"}


def _walk(obj: Any, numbers: set[float], names: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in NAME_KEYS and isinstance(v, str):
                names.add(v)
            _walk(v, numbers, names)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, numbers, names)
    elif isinstance(obj, bool):
        return
    elif isinstance(obj, int | float):
        numbers.add(round(float(obj), 6))


def spoken_numbers(text: str, names: set[str]) -> list[float]:
    for name in sorted(names, key=len, reverse=True):
        text = text.replace(name, " ")
    return [round(float(m.group().rstrip(",").replace(",", "")), 6) for m in _NUMBER.finditer(text)]


def unbacked_numbers(structured: dict[str, Any], *texts: str) -> list[float]:
    """Numbers spoken in ``texts`` that do not appear anywhere in ``structured``. Empty means consistent."""
    numbers: set[float] = set()
    names: set[str] = set()
    _walk(structured, numbers, names)
    return [n for t in texts for n in spoken_numbers(t, names) if n not in numbers]


def numbers_of(obj: Any, skip_keys: frozenset[str] = frozenset()) -> set[float]:
    """All numbers in ``obj``, not descending into keys in ``skip_keys``."""
    found: set[float] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in skip_keys:
                found |= numbers_of(v, skip_keys)
    elif isinstance(obj, list):
        for v in obj:
            found |= numbers_of(v, skip_keys)
    elif isinstance(obj, int | float) and not isinstance(obj, bool):
        found.add(round(float(obj), 6))
    return found


def names_of(obj: Any) -> set[str]:
    names: set[str] = set()
    _walk(obj, set(), names)
    return names


def scoped_problems(pool: set[float], names: set[str], en: str, te: str) -> list[str]:
    """Problems with one en/te text pair against one pool of card numbers: numbers the card lacks, and any
    difference between the numbers spoken in English and in Telugu."""
    en_nums, te_nums = spoken_numbers(en, names), spoken_numbers(te, names)
    problems = [f"unbacked {n} in: {en!r}" for n in en_nums if n not in pool]
    problems += [f"unbacked {n} in: {te!r}" for n in te_nums if n not in pool]
    if sorted(en_nums) != sorted(te_nums):
        problems.append(f"en/te numbers differ: {sorted(en_nums)} vs {sorted(te_nums)} in {en!r}")
    return problems


def tool_output_problems(sc: dict[str, Any]) -> list[str]:
    """Scoped cross-modal check of a get_farm_status / plan_feed structuredContent."""
    names = names_of(sc)
    top_scalars = {k: v for k, v in sc.items() if not isinstance(v, dict | list)}
    problems = scoped_problems(numbers_of(sc, frozenset({"daily"})), names, sc["text_en"], sc["text_te"])
    for item in sc.get("houses", []) + sc.get("plans", []):
        pool = numbers_of(item, frozenset({"findings", "daily"})) | numbers_of(top_scalars)
        problems += scoped_problems(pool, names, item["summary_en"], item["summary_te"])
        for f in item.get("findings", []):
            problems += scoped_problems(numbers_of(f["values"]), names, f["text_en"], f["text_te"])
    return problems
