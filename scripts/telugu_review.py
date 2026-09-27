"""Generate docs/TELUGU_REVIEW.md: every Telugu string in the code with its English counterpart, plus rendered
example answers from the demo farm, for review by a native speaker.

Usage (Windows):
    .venv\\Scripts\\python scripts\\telugu_review.py          write docs/TELUGU_REVIEW.md
    .venv\\Scripts\\python scripts\\telugu_review.py --check  exit 1 if the file is out of date (used by a harness test)
"""

from __future__ import annotations

import argparse
import ast
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "clucktalk"
OUT = ROOT / "docs" / "TELUGU_REVIEW.md"
EXAMPLE_DAY = date(2026, 9, 29)  # fixed, so the file only changes when wording changes


def has_telugu(s: str) -> bool:
    return any("\u0c00" <= ch <= "\u0c7f" for ch in s)


def text_of(node: ast.AST) -> str | None:
    """A string literal or f-string as reviewable text; f-string fields shown as {name}."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            elif isinstance(v, ast.FormattedValue):
                parts.append("{" + ast.unparse(v.value) + "}")
        return "".join(parts)
    return None


def _strings_in(node: ast.AST) -> list[tuple[ast.AST, str]]:
    """Top-level string children of a call/tuple/list, in source order (implicit concatenation is one node)."""
    kids = node.args if isinstance(node, ast.Call) else getattr(node, "elts", [])
    kids = list(kids) + ([k.value for k in node.keywords] if isinstance(node, ast.Call) else [])
    return [(k, t) for k in kids if (t := text_of(k)) is not None]


def _assigned_name(stmt: ast.stmt) -> str | None:
    target = stmt.targets[0] if isinstance(stmt, ast.Assign) else getattr(stmt, "target", None)
    return target.id if isinstance(target, ast.Name) else None


def collect(path: Path) -> list[dict]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    rows, seen = [], set()

    def english_for(node: ast.AST) -> str | None:
        parent = parents.get(node)
        if isinstance(parent, ast.keyword):  # Text(en=..., te=...)
            parent = parents.get(parent)
        # 1. Same call/tuple: pair the i-th Telugu string with the i-th English string.
        if isinstance(parent, ast.Call | ast.Tuple | ast.List):
            strings = _strings_in(parent)
            te = [n for n, t in strings if has_telugu(t)]
            en = [t for n, t in strings if not has_telugu(t)]
            if node in te and len(te) == len(en):
                return en[te.index(node)]
        # 2. Dict literal: English key -> Telugu value.
        if isinstance(parent, ast.Dict) and node in parent.values:
            key = parent.keys[parent.values.index(node)]
            return text_of(key) if key is not None else None
        # 3. `x_te = ...` / `te = ...` next to `x_en = ...` / `en = ...` in the same block.
        stmt = node
        while stmt in parents and not isinstance(stmt, ast.stmt):
            stmt = parents[stmt]
        name = _assigned_name(stmt) if isinstance(stmt, ast.Assign | ast.AugAssign) else None
        if name and ("te" in name.split("_")):
            want = "_".join("en" if p == "te" else p for p in name.split("_"))
            block = parents.get(stmt)
            body = getattr(block, "body", []) + getattr(block, "orelse", [])
            if stmt in body:
                for prev in reversed(body[: body.index(stmt)]):
                    if isinstance(prev, ast.Assign | ast.AugAssign) and _assigned_name(prev) == want:
                        strings = [text_of(n) for n in ast.walk(prev.value) if text_of(n) is not None]
                        if strings:
                            return strings[0]
        # 4. NAME_TE = "..." next to NAME = "..." (e.g. APP_NAME_TE / APP_NAME).
        if isinstance(stmt, ast.Assign) and name and name.endswith("_TE") and stmt.value is node:
            for other in tree.body:
                if isinstance(other, ast.Assign) and _assigned_name(other) in (name[:-3], name[:-3] + "_EN"):
                    return text_of(other.value)
        # 5. A `..._te` function/property next to its `..._en` twin in the same class.
        func = stmt
        while func in parents and not isinstance(func, ast.FunctionDef):
            func = parents[func]
        if isinstance(func, ast.FunctionDef) and func.name.endswith("_te"):
            owner = parents.get(func)
            for sib in getattr(owner, "body", []):
                if isinstance(sib, ast.FunctionDef) and sib.name == func.name[:-3] + "_en":
                    found = [text_of(n) for n in ast.walk(sib) if text_of(n) is not None]
                    if found:
                        return found[0]
        # 6. WEEKDAY_TE-style constant tuples next to WEEKDAY_EN.
        if isinstance(parent, ast.Tuple):
            holder = parents.get(parent)
            name = _assigned_name(holder) if isinstance(holder, ast.Assign) else None
            if name and name.endswith("_TE"):
                for other in ast.walk(tree):
                    if isinstance(other, ast.Assign) and _assigned_name(other) == name[:-3] + "_EN":
                        elts = getattr(other.value, "elts", [])
                        idx = parent.elts.index(node)
                        if idx < len(elts):
                            return text_of(elts[idx])
        return None

    for node in ast.walk(tree):
        t = text_of(node)
        if t is None or not has_telugu(t) or id(node) in seen:
            continue
        # Skip string parts that belong to an enclosing f-string (reported once, as the whole f-string).
        parent = parents.get(node)
        if isinstance(parent, ast.JoinedStr | ast.FormattedValue):
            continue
        seen.add(id(node))
        rows.append(
            {
                "where": f"{path.relative_to(ROOT).as_posix()}:{node.lineno}",
                "line": node.lineno,
                "te": t,
                "en": english_for(node),
            }
        )
    return sorted(rows, key=lambda r: r["line"])


def _cell(s: str | None) -> str:
    if s is None:
        return "_(no English pair found; see file)_"
    return s.replace("|", "\\|").replace("\n", " ")


def rendered_examples() -> list[tuple[str, str, str]]:
    sys.path.insert(0, str(ROOT / "src"))
    from clucktalk.server.farm_state import DemoFarmSource
    from clucktalk.server.tools import CapabilityRegistry
    from clucktalk.server.tools.farm_status import build_status
    from clucktalk.server.tools.feed import build_plan
    from clucktalk.server.tools.help import build_help

    src = DemoFarmSource(clock=lambda: EXAMPLE_DAY)
    out = []
    help_out = build_help(CapabilityRegistry())
    out.append(("get_help (no farm tools registered)", help_out.text_en, help_out.text_te))
    for label, ref in (("whole farm", None), ("House 1", "shed 1"), ("House 2", "shed 2"), ("House 3", "shed 3")):
        s = build_status(src, ref)
        out.append((f"get_farm_status, {label}", s.text_en, s.text_te))
    for label, ref in (("whole farm", None), ("House 2", "shed 2"), ("House 3", "shed 3")):
        p = build_plan(src, ref, 7)
        out.append((f"plan_feed, {label}, 7 days", p.text_en, p.text_te))
    return out


def render() -> str:
    lines = [
        "# Telugu review",
        "",
        "Every Telugu string in CluckTalk, with the English it must match. Generated by `scripts/telugu_review.py`;",
        "do not edit this file by hand (a harness test fails when it is out of date). To correct a string, change it",
        "in the source file shown under **Where**, or write the fix in the **Reviewer** column and hand the file back.",
        "",
        "- `{name}` marks a value filled in at run time (a number, a shed label, a breed). Keep it in your wording.",
        "- Numbers are written with Western digits in both languages, and must stay identical to the English.",
        "- Status: all Telugu below is **pending native-speaker review**",
        "  (`TE_REVIEWED = False` in `src/clucktalk/i18n`).",
        "",
        "## 1. Strings in the code",
        "",
        "| # | English | Telugu | Where | Reviewer |",
        "|---|---|---|---|---|",
    ]
    n = 0
    for path in sorted(SRC.rglob("*.py")):
        for row in collect(path):
            n += 1
            lines.append(f"| {n} | {_cell(row['en'])} | {_cell(row['te'])} | `{row['where']}` |  |")
    lines += [
        "",
        f"## 2. Whole answers as a farmer would hear or read them (demo farm, {EXAMPLE_DAY.isoformat()})",
        "",
        "Check that each sentence reads naturally as a whole, not only string by string.",
        "",
        "| # | Answer | English | Telugu | Reviewer |",
        "|---|---|---|---|---|",
    ]
    for i, (label, en, te) in enumerate(rendered_examples(), start=1):
        lines.append(f"| {i} | {label} | {_cell(en)} | {_cell(te)} |  |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = render()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("docs/TELUGU_REVIEW.md is out of date: run scripts/telugu_review.py", file=sys.stderr)
            return 1
        print("docs/TELUGU_REVIEW.md is up to date.")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
