"""Number and date wording shared by the tools.

Cross-modal rule (docs/DESIGN.md §6): tools first build their structured output with voice-friendly rounded
values, then render ``text_en`` / ``text_te`` from that output only. Every number spoken is therefore a value
the card shows. Numbers are written with Western digits in both languages (common in Telugu print).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

WEEKDAY_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
WEEKDAY_TE = ("సోమవారం", "మంగళవారం", "బుధవారం", "గురువారం", "శుక్రవారం", "శనివారం", "ఆదివారం")


def indian_group(n: int) -> str:
    """12345678 -> '1,23,45,678' (Indian digit grouping: last three, then pairs)."""
    sign, s = ("-", str(-n)) if n < 0 else ("", str(n))
    if len(s) <= 3:
        return sign + s
    head, tail = s[:-3], s[-3:]
    pairs = []
    while len(head) > 2:
        pairs.insert(0, head[-2:])
        head = head[:-2]
    return sign + ",".join([head, *pairs, tail])


def num(x: float | int | Decimal) -> str:
    """Spoken form of a structured value: integers grouped, decimals without trailing zeros."""
    if isinstance(x, bool):
        raise TypeError("booleans are not numbers here")
    d = Decimal(str(x))
    if d == d.to_integral_value():
        return indian_group(int(d))
    sign = "-" if d < 0 else ""  # kept apart: int("-0") would lose the sign of -0.5
    whole, frac = f"{abs(d).normalize():f}".split(".")
    return f"{sign}{indian_group(int(whole))}.{frac}"


def rupees(x: Decimal | float | int) -> str:
    d = Decimal(str(x))
    if d == d.to_integral_value():
        return "₹" + indian_group(int(d))
    whole, frac = f"{d.quantize(Decimal('0.01')):f}".split(".")
    return f"₹{indian_group(int(whole))}.{frac}"


def plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def weekday_en(d: date) -> str:
    return WEEKDAY_EN[d.weekday()]


def weekday_te(d: date) -> str:
    return WEEKDAY_TE[d.weekday()]
