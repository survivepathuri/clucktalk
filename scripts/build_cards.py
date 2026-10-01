"""Build the MCP App cards: inline the bundled font and the fixed bilingual labels into each card template.

Source:  ui/cards/<card>.html   (edit this)
Output:  src/clucktalk/server/cards/<card>.html   (committed; served by the MCP server as a ui:// resource)

The MCP Apps default CSP allows no external requests, so the card must be one self-contained HTML document.
The font is Noto Sans Telugu 2.005 (SIL Open Font License 1.1, see ui/fonts/README.md), inlined as data: URIs.
The server stamps its own demo/live mode into the placeholder ``"@SERVER_DEMO@"`` at startup, so it stays.

Usage (Windows):
    <venv python> scripts/build_cards.py           rebuild every card
    <venv python> scripts/build_cards.py --check   exit 1 if a built card is out of date (harness test)
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from clucktalk.config import APP_NAME, APP_NAME_TE  # noqa: E402
from clucktalk.server.cards import (  # noqa: E402
    BRIEFING_LABELS,
    CARDS_DIR,
    FARM_STATUS_LABELS,
    HEALTH_CHECK_LABELS,
    SALE_PLAN_LABELS,
)
from clucktalk.server.render import num  # noqa: E402

TEMPLATES = ROOT / "ui" / "cards"
FONTS = ROOT / "ui" / "fonts"
FONT_FAMILY = "Noto Sans Telugu CT"  # a private family name, so the card can tell whether *our* copy loaded
FONT_FILES = ((400, "NotoSansTelugu-Regular.otf"), (700, "NotoSansTelugu-Bold.otf"))
CARDS = {
    "farm_status.html": FARM_STATUS_LABELS,
    "sale_plan.html": SALE_PLAN_LABELS,
    "health_check.html": HEALTH_CHECK_LABELS,
    "briefing.html": BRIEFING_LABELS,
}


def _script_json(obj: object) -> str:
    """JSON safe to embed in an inline <script> (no '</' sequence can close the tag)."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True).replace("</", "<\\/")


def font_faces() -> str:
    rules = []
    for weight, name in FONT_FILES:
        data = base64.b64encode((FONTS / name).read_bytes()).decode("ascii")
        rules.append(
            f'@font-face {{ font-family: "{FONT_FAMILY}"; font-weight: {weight}; font-style: normal; '
            f'font-display: swap; src: url("data:font/otf;base64,{data}") format("opentype"); }}'
        )
    return "\n".join(rules)


NUM_FIXTURE_VALUES = (0, 7, 88, 88.0, 941, 1012, 3883, 4862, 12345, 123456, 12345678, 2.9, 1.23, 38.5, 0.05,
                      1568.25, 100000.5, -0.5, -3, -1234.5)  # fmt: skip


def num_fixtures() -> list[list]:
    """[value, spoken form] pairs from the server's own formatter; the card checks its num() against them."""
    return [[v, num(v)] for v in NUM_FIXTURE_VALUES]


def build(template: str, labels: dict) -> str:
    # The template is read as text whatever line endings the checkout stored (a Windows editor may save CRLF); the
    # output is always LF, on every OS (a CRLF template used to skip the header line below).
    template = template.replace("\r\n", "\n")
    replacements = {
        '"@NUM_FIXTURES@"': _script_json(num_fixtures()),
        "/*@FONT_FACES@*/": font_faces(),
        '"@LABELS@"': _script_json({k: {"en": t.en, "te": t.te} for k, t in labels.items()}),
        '"@APP@"': _script_json({"name": APP_NAME, "name_te": APP_NAME_TE}),
    }
    out = template
    for token, value in replacements.items():
        if out.count(token) != 1:
            raise SystemExit(f"template must contain {token!r} exactly once")
        out = out.replace(token, value)
    if out.count('"@SERVER_DEMO@"') != 1:
        raise SystemExit('template must contain "@SERVER_DEMO@" exactly once (the server fills it)')
    header = "<!-- Built by scripts/build_cards.py from ui/cards/. Do not edit; edit the template and rebuild. -->\n"
    out = out.replace("<!doctype html>\n", "<!doctype html>\n" + header, 1)
    if header not in out or "\r" in out:
        raise SystemExit("the built card must carry its header line and contain no carriage return")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if a built card is out of date")
    args = parser.parse_args()
    stale = []
    for name, labels in CARDS.items():
        built = build((TEMPLATES / name).read_bytes().decode("utf-8"), labels).encode("utf-8")
        target = CARDS_DIR / name
        if args.check:
            if not target.exists() or target.read_bytes() != built:
                stale.append(name)
        else:
            target.write_bytes(built)  # bytes, UTF-8, LF: identical on every OS (no newline translation)
            print(f"built {target.relative_to(ROOT).as_posix()} ({len(built):,} bytes)")
    if stale:
        print(f"Out of date: {', '.join(stale)}. Run: {sys.executable} scripts/build_cards.py", file=sys.stderr)
        return 1
    if args.check:
        print("cards up to date")
    return 0


if __name__ == "__main__":
    sys.exit(main())
