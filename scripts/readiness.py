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
from urllib.parse import urlparse

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

# The addon.json structure and limits, from the schema reference on Amazon's Alexa+ MCP QuickStart page (last updated
# Jul 10, 2026), as read by the project owner (the page itself was not visible to the tool that wrote this).
LIMITS = {"name": 30, "shortDescription": 123, "fullDescription": 4000, "examplePhrase": 200, "altText": 250}
PHRASES = (3, 4)
ICON_SIZES = ("72x72", "64x64", "88x88", "126x126", "180x180", "241x241")
CAROUSEL_SIZE = "600x900"
BANNER_SIZE = "1200x600"
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")

SRC_FUNCTIONAL = (
    "Functional Requirements (named in docs/SOURCES.md; the check follows the Step 49 brief, page not re-read)"
)
SRC_TOOLKIT = (
    "Alexa+ MCP Toolkit Overview (named in docs/SOURCES.md; the check follows the Step 49 brief, page not re-read)"
)
SRC_QUICKSTART = (
    "Alexa+ MCP QuickStart, https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html "
    "(last updated Jul 10, 2026; as read by the project owner)"
)
SRC_INSPECTOR = (
    "Alexa+ Add-on Local Inspector, https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-local-inspector.html "
    "(last updated Aug 3, 2026; as read by the project owner)"
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
def _https(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _image_uri(value: object) -> bool:
    return _https(value) and urlparse(str(value)).path.lower().endswith(IMAGE_EXTENSIONS)


def _text(problems: list[str], where: str, value: object, limit: int, required: bool = True) -> None:
    if not isinstance(value, str) or (required and not value.strip()):
        problems.append(f"{where} is missing or empty")
    elif len(value) > limit:
        problems.append(f"{where} is {len(value)} characters, the limit is {limit}")


def _icons(problems: list[str], where: str, icons: object) -> None:
    if not isinstance(icons, list) or sorted(i.get("size") for i in icons if isinstance(i, dict)) != sorted(ICON_SIZES):
        problems.append(f"{where} needs exactly the six sizes {', '.join(ICON_SIZES)}")
        return
    for i, icon in enumerate(icons):
        if not _image_uri(icon.get("uri")):
            problems.append(f"{where}[{i}].uri is not an https PNG, JPG, JPEG or WEBP URL")


def _locale(problems: list[str], code: str, loc: object) -> None:
    at = f"storeListing.locales.{code}"
    if not isinstance(loc, dict):
        problems.append(f"{at} is not an object")
        return
    if loc.get("default") != "DEFAULT":
        problems.append(f'{at}.default must be "DEFAULT"')
    name = loc.get("name")
    _text(problems, f"{at}.name.value", name.get("value") if isinstance(name, dict) else None, LIMITS["name"])
    spoken = name.get("spokenForm") if isinstance(name, dict) else None
    if spoken is not None and not (
        isinstance(spoken, dict) and spoken.get("format") == "ipa" and str(spoken.get("value", "")).strip()
    ):
        problems.append(f'{at}.name.spokenForm needs format "ipa" and a value')
    _text(problems, f"{at}.shortDescription", loc.get("shortDescription"), LIMITS["shortDescription"])
    _text(problems, f"{at}.fullDescription", loc.get("fullDescription"), LIMITS["fullDescription"])
    phrases = loc.get("examplePhrases")
    if not isinstance(phrases, list) or not PHRASES[0] <= len(phrases) <= PHRASES[1]:
        problems.append(f"{at}.examplePhrases needs {PHRASES[0]} to {PHRASES[1]} items")
    else:
        for i, phrase in enumerate(phrases):
            _text(problems, f"{at}.examplePhrases[{i}]", phrase, LIMITS["examplePhrase"])
    legal = loc.get("privacyAndCompliance")
    for field in ("privacyPolicyUrl", "termsOfUseUrl"):
        if not (isinstance(legal, dict) and _https(legal.get(field))):
            problems.append(f"{at}.privacyAndCompliance.{field} is not a valid https URL")
    media = loc.get("mediaAssets")
    icons = media.get("icons") if isinstance(media, dict) else None
    if not isinstance(icons, dict):
        problems.append(f"{at}.mediaAssets.icons is missing")
    else:
        _icons(problems, f"{at}.mediaAssets.icons.light", icons.get("light"))
        if icons.get("dark") is not None:
            _icons(problems, f"{at}.mediaAssets.icons.dark", icons.get("dark"))
    carousel = media.get("carouselImages") if isinstance(media, dict) else None
    if not isinstance(carousel, list) or not carousel:
        problems.append(f"{at}.mediaAssets.carouselImages needs at least one image")
    else:
        for i, image in enumerate(carousel):
            where = f"{at}.mediaAssets.carouselImages[{i}]"
            if not isinstance(image, dict):
                problems.append(f"{where} is not an object")
                continue
            if not _image_uri(image.get("uri")):
                problems.append(f"{where}.uri is not an https PNG, JPG, JPEG or WEBP URL")
            _text(problems, f"{where}.altText", image.get("altText"), LIMITS["altText"])
            if image.get("size") != CAROUSEL_SIZE:
                problems.append(f'{where}.size must be "{CAROUSEL_SIZE}"')
    for i, image in enumerate((media.get("bannerImages") if isinstance(media, dict) else None) or []):
        where = f"{at}.mediaAssets.bannerImages[{i}]"
        if not (isinstance(image, dict) and _image_uri(image.get("uri")) and image.get("size") == BANNER_SIZE):
            problems.append(f'{where} needs an https image uri and size "{BANNER_SIZE}"')


def validate_addon(data: dict) -> list[str]:
    """Problems with the draft listing against the structure and limits of the addon.json schema reference on Amazon's
    Alexa+ MCP QuickStart page (an empty list means none). Field names, counts and lengths only: not an Amazon check."""
    problems: list[str] = []
    if data.get("manifestVersion") != "1.0":
        problems.append('manifestVersion must be "1.0"')
    listing = data.get("storeListing")
    if not isinstance(listing, dict):
        problems.append("storeListing is missing")
        listing = {}
    countries = listing.get("distributionCountries")
    if (
        not isinstance(countries, list)
        or not countries
        or not all(isinstance(c, str) and re.fullmatch(r"[A-Z]{2}", c) for c in countries)
    ):
        problems.append("storeListing.distributionCountries needs ISO 3166-1 alpha-2 codes such as US")
    locales = listing.get("locales")
    if not isinstance(locales, dict) or not locales:
        problems.append("storeListing.locales needs at least one locale")
    else:
        for code, loc in locales.items():
            if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", str(code)):
                problems.append(f"locale {code!r} is not a locale code such as en-US")
            _locale(problems, str(code), loc)
    integrations = data.get("integrations")
    if not isinstance(integrations, list) or not integrations:
        problems.append("integrations needs an MCP integration")
    else:
        for i, item in enumerate(integrations):
            endpoint = (
                ((item.get("config") or {}).get("endpoints") or {}).get("default") if isinstance(item, dict) else None
            )
            if not (isinstance(item, dict) and item.get("type") == "MCP"):
                problems.append(f'integrations[{i}].type must be "MCP"')
            if not (isinstance(endpoint, dict) and endpoint.get("type") == "HTTPS" and _https(endpoint.get("uri"))):
                problems.append(f'integrations[{i}].config.endpoints.default needs type "HTTPS" and an https uri')
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
            SRC_QUICKSTART,
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
            "(server times on localhost in mock mode; Amazon's 500 ms requirement is a round trip that includes the "
            "network, so we do not claim to meet it end to end)",
            SRC_QUICKSTART,
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
            SRC_INSPECTOR,
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
            "The draft add-on listing follows the documented addon.json structure and limits (name 30, short 123, full 4000, "
            "3 to 4 phrases of 200, https URLs, six icon sizes, a 600x900 carousel image with alt text)",
            MET if not problems else NOT_MET,
            "docs/addon-package/addon.json (a placeholder draft, not deployed; structure from the QuickStart page, not an Amazon validation)"
            + (f"; problems: {'; '.join(problems)}" if problems else ""),
            SRC_QUICKSTART,
        )
    )
    for key, text in (
        ("oauth", "OAuth 2.1 with PKCE for account linking"),
        ("prm", "Protected Resource Metadata"),
        ("remote", "A remote HTTPS URL for the server"),
        ("policies", "Security and data policies"),
    ):
        source = SRC_QUICKSTART + ", authentication checklist" if key in ("oauth", "prm") else SRC_BRIEF
        reqs.append(Requirement(key, text, NOT_CHECKABLE, "not built; on the roadmap, local only today", source))
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
        "- **Latency:** our p50 and p95 are server times on localhost in mock mode, and Amazon's 500 ms requirement is a round "
        "trip that includes the network, so we do not claim to meet it end to end. There is no model call and the data is simulated.",
        "- The draft listing in `docs/addon-package/addon.json` follows the `addon.json` schema reference on the QuickStart "
        "page (as read by the project owner) and uses placeholder URLs and images; nothing was deployed and the Alexa AI CLI "
        "was not used (FL-024). Only its field names, counts and length limits are checked "
        "(`tests/harness/test_addon_draft.py`), which is not an Amazon validation. See `docs/addon-package/NOTE.md`.",
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
