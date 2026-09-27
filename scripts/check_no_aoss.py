"""Rule 1 guard: fail if anything provisions or references Amazon OpenSearch Serverless (AOSS).

AOSS bills always-on capacity and can drain the hackathon AWS credit, so CluckTalk never uses it.

Scans:
  1. Synthesized CloudFormation templates in ``cdk.out/`` (``*.template.json``) for any
     resource whose ``Type`` starts with the AOSS CloudFormation namespace.
  2. Infrastructure and source files (``infra/``, ``src/``, ``scripts/``, ``skills/``) for
     AOSS identifiers: the CloudFormation namespace, the CDK module name, the IAM action
     prefix, and the Bedrock Knowledge Base storage-type constant.

Exit codes: 0 = clean, 1 = AOSS found, 2 = a scan target could not be read.
Usage (Windows):  python scripts\\check_no_aoss.py [--root PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Built from parts so this file never matches its own patterns.
_NS = "OpenSearch" + "Serverless"
CFN_TYPE_PREFIX = f"AWS::{_NS}::"
SOURCE_PATTERNS = [
    re.compile(re.escape(CFN_TYPE_PREFIX)),
    # CDK module (aws_opensearch...), boto3 client name. No leading \b: "_" is a word char.
    re.compile(r"opensearch[_-]?" + "serverless", re.IGNORECASE),
    re.compile(r"[\"']" + "aoss" + r":[A-Za-z*]"),  # IAM actions, e.g. "aoss:APIAccessAll"
    re.compile("OPENSEARCH_" + "SERVERLESS"),  # Bedrock KB storageConfiguration.type
]
SOURCE_DIRS = ("infra", "src", "scripts", "skills")
SOURCE_SUFFIXES = {".py", ".ts", ".js", ".mjs", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".env"}
SKIP_DIR_NAMES = {"node_modules", ".venv", "__pycache__", "cdk.out", ".git"}


def _find_cfn_violations(template_path: Path) -> list[str]:
    data = json.loads(template_path.read_text(encoding="utf-8"))
    resources = data.get("Resources", {}) if isinstance(data, dict) else {}
    return [
        f"{template_path}: resource '{logical_id}' has type {res.get('Type')}"
        for logical_id, res in resources.items()
        if isinstance(res, dict) and str(res.get("Type", "")).startswith(CFN_TYPE_PREFIX)
    ]


def _find_source_violations(path: Path) -> list[str]:
    hits = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        for pattern in SOURCE_PATTERNS:
            if pattern.search(line):
                hits.append(f"{path}:{lineno}: {line.strip()[:120]}")
                break
    return hits


def _iter_source_files(root: Path, self_path: Path):
    for dir_name in SOURCE_DIRS:
        base = root / dir_name
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if any(part in SKIP_DIR_NAMES for part in path.relative_to(root).parts):
                continue
            if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES and path.resolve() != self_path:
                yield path


def scan(root: Path) -> tuple[list[str], list[str], dict[str, int]]:
    """Return (violations, read_errors, counts) for the repo at ``root``."""
    violations: list[str] = []
    errors: list[str] = []
    counts = {"templates": 0, "source_files": 0}
    self_path = Path(__file__).resolve()

    cdk_out = root / "cdk.out"
    if cdk_out.is_dir():
        for template in sorted(cdk_out.rglob("*.template.json")):
            counts["templates"] += 1
            try:
                violations.extend(_find_cfn_violations(template))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"{template}: could not parse template ({exc})")

    for path in _iter_source_files(root, self_path):
        counts["source_files"] += 1
        try:
            violations.extend(_find_source_violations(path))
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{path}: could not read file ({exc})")

    return violations, errors, counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args(argv)

    violations, errors, counts = scan(args.root.resolve())
    templates_note = (
        f"{counts['templates']} CloudFormation template(s)"
        if (args.root / "cdk.out").is_dir()
        else "no cdk.out/ yet (run 'cdk synth' to include templates)"
    )
    print(f"AOSS check: scanned {templates_note} and {counts['source_files']} source file(s).")

    for err in errors:
        print(f"  ERROR  {err}", file=sys.stderr)
    for v in violations:
        print(f"  FOUND  {v}", file=sys.stderr)

    if violations:
        print("AOSS check FAILED: OpenSearch Serverless is forbidden (CLAUDE.md Rule 1).", file=sys.stderr)
        return 1
    if errors:
        print("AOSS check INCOMPLETE: some files could not be scanned.", file=sys.stderr)
        return 2
    print("AOSS check passed: no OpenSearch Serverless found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
