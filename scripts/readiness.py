# ruff: noqa: E501  (long lines are requirement texts and documentation strings)
"""A self-check of the documented Alexa+ add-on requirements that can be checked on this machine.

This is OUR checklist. It is not Amazon's tool and gives no Amazon verdict. Each requirement is printed as MET, NOT MET
or NOT CHECKABLE LOCALLY, with the page it comes from. The local checks run against a temporary copy of the server
(a temporary state file, mock mode, no AWS) using the same replay as ``python tasks.py inspector-replay``.

Usage (Windows):  python tasks.py readiness [--write-doc]      (--write-doc also rewrites docs/ALEXA_READINESS.md)
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import inspector_replay as replay  # noqa: E402

ADDON_DRAFT = ROOT / "docs" / "addon-package" / "addon.json"
DOC = ROOT / "docs" / "ALEXA_READINESS.md"
MET, NOT_MET, NOT_CHECKABLE = "MET", "NOT MET", "NOT CHECKABLE LOCALLY"
NOT_AMAZON = "this is not an Amazon verdict"
OVERLAP_LIMIT = 0.7  # our own bound on the word overlap of two tool descriptions (Jaccard); not an Amazon number
ERROR_FIELDS = ("message_en", "message_te", "next_step_en", "next_step_te")

# Limits for the draft add-on listing, as given in the Step 49 brief (the Amazon page was not re-read in this repo).
LIMITS = {"name": 30, "short_description": 123, "full_description": 4000, "example_phrase": 200}
PHRASES = (3, 4)
ICONS = 6
CAROUSEL = (600, 900)

SRC_FUNCTIONAL = (
    "Functional Requirements (named in docs/SOURCES.md; the check follows the Step 49 brief, page not re-read)"
)
SRC_TOOLKIT = (
    "Alexa+ MCP Toolkit Overview (named in docs/SOURCES.md; the check follows the Step 49 brief, page not re-read)"
)
SRC_BRIEF = "not recorded in docs/SOURCES.md; the requirement is listed in the Step 49 brief, page name to be confirmed"


@dataclass
class Requirement:
    key: str
    text: str
    status: str
    detail: str
    source: str


# -- the draft add-on listing ----------------------------------------------------------------------------------------
def validate_addon(data: dict) -> list[str]:
    """Problems with the draft listing against the documented limits (an empty list means none)."""
    problems: list[str] = []

    def text(field: str, limit: int, minimum: int = 1) -> str:
        value = data.get(field)
        if not isinstance(value, str) or len(value.strip()) < minimum:
            problems.append(f"{field} is missing or empty")
            return ""
        if len(value) > limit:
            problems.append(f"{field} is {len(value)} characters, the limit is {limit}")
        return value

    text("name", LIMITS["name"])
    text("short_description", LIMITS["short_description"])
    text("full_description", LIMITS["full_description"])
    phrases = data.get("example_phrases")
    if not isinstance(phrases, list) or not PHRASES[0] <= len(phrases) <= PHRASES[1]:
        problems.append(f"example_phrases needs {PHRASES[0]} to {PHRASES[1]} entries")
    else:
        for i, p in enumerate(phrases):
            if not isinstance(p, str) or not p.strip():
                problems.append(f"example_phrases[{i}] is empty")
            elif len(p) > LIMITS["example_phrase"]:
                problems.append(f"example_phrases[{i}] is {len(p)} characters, the limit is {LIMITS['example_phrase']}")
    urls = data.get("urls")
    if not isinstance(urls, dict) or not urls:
        problems.append("urls is missing")
    else:
        for k, u in urls.items():
            if not isinstance(u, str) or not u.startswith("https://"):
                problems.append(f"urls.{k} is not an https:// URL")
    icons = data.get("icons")
    if not isinstance(icons, list) or len(icons) != ICONS:
        problems.append(f"icons needs exactly {ICONS} sizes")
    else:
        sizes = [i.get("size") for i in icons if isinstance(i, dict)]
        if len(set(sizes)) != ICONS:
            problems.append("the icon sizes must be six different ones")
        for i, icon in enumerate(icons):
            if not isinstance(icon, dict) or not str(icon.get("url", "")).startswith("https://"):
                problems.append(f"icons[{i}].url is not an https:// URL")
    carousel = data.get("carousel_image")
    if not isinstance(carousel, dict) or (carousel.get("width"), carousel.get("height")) != CAROUSEL:
        problems.append(f"carousel_image must be exactly {CAROUSEL[0]}x{CAROUSEL[1]}")
    elif not str(carousel.get("url", "")).startswith("https://"):
        problems.append("carousel_image.url is not an https:// URL")
    return problems


# -- the local checks ------------------------------------------------------------------------------------------------
def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_']+", text.lower()))


def max_overlap(descriptions: dict[str, str]) -> tuple[float, tuple[str, str]]:
    names = sorted(descriptions)
    best, pair = 0.0, ("", "")
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            wa, wb = _words(descriptions[a]), _words(descriptions[b])
            score = len(wa & wb) / len(wa | wb) if wa | wb else 0.0
            if score > best:
                best, pair = score, (a, b)
    return best, pair


def _session(url: str) -> replay.Replay:
    r = replay.Replay(url)
    r.initialize_and_keep_session()
    r.initialized()
    return r


def collect(url: str, rounds: int) -> list[Requirement]:
    reqs: list[Requirement] = []
    rounds_data = replay.collect(url, rounds)
    first = {name: (status, ok) for name, status, ok, _ in rounds_data[0]}
    summary = replay.summarize(rounds_data)

    ok_flow = all(first[s][1] for s in ("initialize", "notifications/initialized", "tools/list"))
    reqs.append(
        Requirement(
            "http",
            "Streamable HTTP endpoint works (initialize, initialized, tools/list over POST, Accept: application/json only)",
            MET if ok_flow else NOT_MET,
            f"statuses: initialize {first['initialize'][0]}, initialized {first['notifications/initialized'][0]}, "
            f"tools/list {first['tools/list'][0]}",
            SRC_TOOLKIT,
        )
    )

    s = _session(url)
    try:
        _, tools = s.tools_list()
        resources = s.resource_uris()
        # tool definitions
        bad = [
            t["name"]
            for t in tools
            if not re.fullmatch(r"[a-z][a-z0-9_]*", t.get("name", ""))
            or not (t.get("description") or "").strip()
            or (t.get("inputSchema") or {}).get("type") != "object"
        ]
        longest = max((len(t.get("description", "")) for t in tools), default=0)
        reqs.append(
            Requirement(
                "tools",
                "Every tool has a snake_case name, a description and an object input schema",
                MET if tools and not bad else NOT_MET,
                f"{len(tools)} tools; longest description {longest} characters (no Amazon limit recorded, so none judged)"
                + (f"; problems: {', '.join(bad)}" if bad else ""),
                SRC_FUNCTIONAL,
            )
        )
        score, pair = max_overlap({t["name"]: t.get("description", "") for t in tools})
        reqs.append(
            Requirement(
                "overlap",
                f"No two tool descriptions overlap (word overlap below {OVERLAP_LIMIT}, our own bound)",
                MET if score < OVERLAP_LIMIT else NOT_MET,
                f"highest overlap {score:.2f} between {pair[0]} and {pair[1]}",
                SRC_FUNCTIONAL,
            )
        )
        # error responses carry a message and a next step
        errors = []
        for name, args in (("get_farm_status", {"house": "shed 99"}), ("set_farm_mode", {"mode": "not-a-mode"})):
            _step, payload = s._request(f"tools/call {name}", "tools/call", {"name": name, "arguments": args})
            result = (payload or {}).get("result") or {}
            meta = (result.get("_meta") or {}).get("clucktalk/error") or {}
            if not (result.get("isError") and all(str(meta.get(f, "")).strip() for f in ERROR_FIELDS)):
                errors.append(name)
        reqs.append(
            Requirement(
                "errors",
                "Error responses carry a message and a next step (English and Telugu)",
                MET if not errors else NOT_MET,
                "checked an unknown shed and an invalid mode" + (f"; failed: {', '.join(errors)}" if errors else ""),
                SRC_FUNCTIONAL,
            )
        )
        # ui:// resources
        wanted = sorted(
            {((t.get("_meta") or {}).get("ui") or {}).get("resourceUri") for t in tools} - {None},
        )
        missing = []
        for uri in wanted:
            _step, payload = s._request(f"resources/read {uri}", "resources/read", {"uri": uri})
            contents = (((payload or {}).get("result") or {}).get("contents")) or []
            if not (uri in resources and contents and str(contents[0].get("text", "")).strip()):
                missing.append(uri)
        reqs.append(
            Requirement(
                "ui",
                "Every tool that declares _meta.ui.resourceUri has a readable ui:// resource",
                MET if wanted and not missing else NOT_MET,
                f"{len(wanted)} resources declared by tools"
                + (f"; unreadable: {', '.join(missing)}" if missing else ""),
                SRC_TOOLKIT,
            )
        )
    finally:
        s.close()

    p50 = max(a for _n, a, _b, _m, _g in summary)
    p95 = max(b for _n, _a, b, _m, _g in summary)
    reqs.append(
        Requirement(
            "latency",
            f"Round-trip latency under {replay.BUDGET_MS} ms",
            MET if p95 < replay.BUDGET_MS else NOT_MET,
            f"worst step over {rounds} rounds on this machine: p50 {p50:.1f} ms, p95 {p95:.1f} ms "
            "(localhost, mock mode: a network, a remote host and a real model add to this)",
            SRC_FUNCTIONAL,
        )
    )

    design = (ROOT / "docs" / "DESIGN.md").read_text(encoding="utf-8")
    declared = "Screen size classes" in design and "10 inches and below" in design and "11 inches and above" in design
    reqs.append(
        Requirement(
            "screens",
            "The two screen size classes (10 inches and below, 11 inches and above) are declared in the docs for the cards",
            MET if declared else NOT_MET,
            "declared in docs/DESIGN.md, section 14; tested sizes are all in the 10-inch-and-below class, none at 11 inches and above",
            SRC_BRIEF,
        )
    )
    try:
        draft = json.loads(ADDON_DRAFT.read_text(encoding="utf-8"))
        problems = validate_addon(draft)
    except (OSError, ValueError) as exc:
        problems = [f"cannot read {ADDON_DRAFT.name}: {exc}"]
    reqs.append(
        Requirement(
            "addon",
            "The draft add-on listing is within the documented field limits (name 30, short 123, full 4000, 3 to 4 phrases of 200, "
            "https URLs, six icon sizes, one 600x900 carousel image)",
            MET if not problems else NOT_MET,
            "docs/addon-package/addon.json (a placeholder draft, not deployed)"
            + (f"; problems: {'; '.join(problems)}" if problems else ""),
            SRC_BRIEF,
        )
    )
    for key, text in (
        ("oauth", "OAuth 2.1 with PKCE for account linking"),
        ("prm", "Protected Resource Metadata"),
        ("remote", "A remote HTTPS URL for the server"),
        ("policies", "Security and data policies"),
    ):
        reqs.append(Requirement(key, text, NOT_CHECKABLE, "not built; on the roadmap, local only today", SRC_BRIEF))
    return reqs


def summary_line(reqs: list[Requirement]) -> str:
    local = [r for r in reqs if r.status != NOT_CHECKABLE]
    met = sum(r.status == MET for r in local)
    other = len(reqs) - len(local)
    return f"{met} of {len(local)} locally checkable requirements met; {other} not checkable locally; {NOT_AMAZON}"


def render_list(reqs: list[Requirement]) -> str:
    lines = []
    for r in reqs:
        lines += [f"[{r.status}] {r.text}", f"    seen:   {r.detail}", f"    source: {r.source}"]
    return "\n".join(lines)


def render_doc(reqs: list[Requirement], rounds: int) -> str:
    out = [
        "# Alexa+ readiness: our own self-check",
        "",
        "Generated by `python tasks.py readiness --write-doc`. **This is not Amazon's tool and not an Amazon verdict.** It "
        "checks, on this machine and against a temporary copy of the server, the documented requirements that can be "
        "checked locally, and lists the ones that cannot. The Local Inspector itself was not run (FL-024); the latency "
        f"numbers come from `python tasks.py inspector-replay` ({rounds} rounds, localhost, mock mode).",
        "",
        f"**{summary_line(reqs)}.**",
        "",
        "| Status | Requirement | What was seen | Source page |",
        "|---|---|---|---|",
    ]
    out += [f"| {r.status} | {r.text} | {r.detail} | {r.source} |" for r in reqs]
    out += [
        "",
        "## What this does not show",
        "",
        "- **OAuth 2.1 with PKCE, Protected Resource Metadata and a remote HTTPS URL are roadmap.** The server runs on "
        "`127.0.0.1` for local use; off localhost it requires a bearer token, which is not Amazon's account linking.",
        "- **Security and data policies** are not written yet. The demo uses fictional farm data only.",
        "- **Tool information refreshes only on deploy.** If a tool name, description or schema changes, the add-on has to "
        "be deployed again for Alexa+ to see it; nothing here tests that.",
        "- **Nothing here ran on an Alexa+ device**, through Alexa's speech composition, or through Amazon's review.",
        "- The latency is measured on localhost with simulated data and no model call; it is not a production figure.",
        "- The draft listing in `docs/addon-package/addon.json` uses placeholder URLs and images, and its field names are "
        "this project's assumption, not Amazon's schema. Only its length limits and counts are checked "
        "(`tests/harness/test_addon_draft.py`).",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None, rounds: int = 10) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in ([], ["--write-doc"]):
        print("readiness: the only option is --write-doc.", file=sys.stderr)
        return 2
    print("This is our own self-check of the documented requirements that can be checked locally.")
    print("It is not Amazon's tool and gives no Amazon verdict. The Local Inspector itself was not run (FL-024).\n")
    try:
        with replay.running_server() as url:
            reqs = collect(url, rounds)
    except (RuntimeError, replay.httpx2.HTTPError) as exc:
        print(f"readiness: {exc}", file=sys.stderr)
        return 1
    print(render_list(reqs))
    print(f"\n{summary_line(reqs)}")
    if args == ["--write-doc"]:
        DOC.write_text(render_doc(reqs, rounds), encoding="utf-8", newline="\n")
        print(f"readiness: wrote {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
