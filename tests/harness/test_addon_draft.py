"""Step 49b part A: the draft add-on listing (docs/addon-package/addon.json) follows the addon.json schema reference on
Amazon's Alexa+ MCP QuickStart page (last updated Jul 10, 2026, as read by the project owner): manifestVersion "1.0",
storeListing (distributionCountries, locales with name at most 30, shortDescription at most 123, fullDescription at most
4000, 3 to 4 examplePhrases of at most 200, privacyAndCompliance with https URLs, mediaAssets with the six light icon
sizes, optional dark icons, carouselImages of 600x900 with altText at most 250, optional 1200x600 banners) and
integrations (an MCP integration with an HTTPS endpoint). Image URIs are https PNG, JPG, JPEG or WEBP. Everything in
the draft is a placeholder: this checks names, counts and lengths, not an Amazon validation."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import readiness  # noqa: E402  (scripts/readiness.py)

DRAFT = json.loads((ROOT / "docs" / "addon-package" / "addon.json").read_text(encoding="utf-8"))
NOTE = (ROOT / "docs" / "addon-package" / "NOTE.md").read_text(encoding="utf-8")
SIZES = ["72x72", "64x64", "88x88", "126x126", "180x180", "241x241"]
LOC = "storeListing.locales.en-US"
OK_URI = "https://example.invalid/i.png"


def edited(path: str, value):
    """A copy of the draft with ``path`` (dots, list indexes as numbers) set to ``value``; ``...`` deletes it."""
    data = copy.deepcopy(DRAFT)
    node = data
    keys = path.split(".")
    for key in keys[:-1]:
        node = node[int(key)] if isinstance(node, list) else node[key]
    last = keys[-1]
    if value is ...:
        del node[int(last) if isinstance(node, list) else last]
    elif isinstance(node, list):
        node[int(last)] = value
    else:
        node[last] = value
    return data


def image(uri: str, size: str = "600x900", alt: str = "alt") -> dict:
    return {"uri": uri, "altText": alt, "size": size}


def icons(uri: str = OK_URI) -> list[dict]:
    return [{"size": s, "uri": uri} for s in SIZES]


# -- the committed draft ----------------------------------------------------------------------------------------------
def test_the_committed_draft_has_no_problems():
    assert readiness.validate_addon(DRAFT) == []


def test_the_draft_has_the_documented_structure_and_only_placeholders():
    assert DRAFT["manifestVersion"] == "1.0" and set(DRAFT) == {"manifestVersion", "storeListing", "integrations"}
    listing = DRAFT["storeListing"]
    assert listing["distributionCountries"] == ["US"] and set(listing) == {"distributionCountries", "locales"}
    loc = listing["locales"]["en-US"]
    assert loc["default"] == "DEFAULT" and loc["name"] == {"value": "CluckTalk"}
    assert {"shortDescription", "fullDescription", "examplePhrases", "privacyAndCompliance", "mediaAssets"} <= set(loc)
    assert [i["size"] for i in loc["mediaAssets"]["icons"]["light"]] == SIZES
    assert loc["mediaAssets"]["carouselImages"][0]["size"] == "600x900"
    assert DRAFT["integrations"][0]["type"] == "MCP"
    assert DRAFT["integrations"][0]["config"]["endpoints"]["default"]["type"] == "HTTPS"
    uris = [v for v in json.dumps(DRAFT).split('"') if v.startswith("https://")]
    assert uris and all("example.invalid" in u for u in uris)


def test_the_note_says_where_the_structure_came_from_and_that_nothing_was_deployed():
    flat = " ".join(NOTE.split())
    assert "Alexa+ MCP QuickStart page" in flat and "Jul 10, 2026" in flat
    assert "Nothing was deployed or submitted" in flat and "Alexa AI CLI was not used (FL-024)" in flat
    assert "placeholder" in flat and "FR-008" in flat and "not an Amazon validation" in flat


def test_the_example_phrases_are_phrases_the_server_gives_in_get_help():
    import inspector_replay as replay

    with replay.running_server() as url:
        r = replay.Replay(url)
        try:
            r.initialize_and_keep_session()
            r.initialized()
            _, payload = r._request("tools/call get_help", "tools/call", {"name": "get_help", "arguments": {}})
        finally:
            r.close()
    given = {c["example_en"] for c in payload["result"]["structuredContent"]["capabilities"]}
    assert set(DRAFT["storeListing"]["locales"]["en-US"]["examplePhrases"]) <= given


def test_the_draft_makes_no_claim_that_it_runs_on_alexa():
    text = DRAFT["storeListing"]["locales"]["en-US"]["fullDescription"].lower()
    assert "has not been run on an alexa+ device" in text
    for claim in ("production-ready", "enterprise-grade", "guaranteed", "certified", "real-time"):
        assert claim not in text


# -- every documented limit, at its edge ------------------------------------------------------------------------------
GOOD_C = "https://e.invalid/c.png"
EDGE_CASES = [
    (f"{LOC}.name.value", "x" * 30, None),
    (f"{LOC}.name.value", "x" * 31, "name.value is 31"),
    (f"{LOC}.name.value", "", "name.value is missing"),
    (f"{LOC}.shortDescription", "x" * 123, None),
    (f"{LOC}.shortDescription", "x" * 124, "shortDescription is 124"),
    (f"{LOC}.fullDescription", "x" * 4000, None),
    (f"{LOC}.fullDescription", "x" * 4001, "fullDescription is 4001"),
    (f"{LOC}.examplePhrases", ["a", "b"], "3 to 4 items"),
    (f"{LOC}.examplePhrases", ["a", "b", "c", "d", "e"], "3 to 4 items"),
    (f"{LOC}.examplePhrases", ["a", "b", "c", "x" * 200], None),
    (f"{LOC}.examplePhrases", ["a", "b", "c", "x" * 201], "examplePhrases[3] is 201"),
    (f"{LOC}.examplePhrases", ["a", "b", ""], "examplePhrases[2] is missing"),
    (
        f"{LOC}.privacyAndCompliance.privacyPolicyUrl",
        "http://example.invalid/p",
        "privacyPolicyUrl is not a valid https",
    ),
    (f"{LOC}.privacyAndCompliance.termsOfUseUrl", "https://", "termsOfUseUrl is not a valid https"),
    (f"{LOC}.privacyAndCompliance.termsOfUseUrl", ..., "termsOfUseUrl is not a valid https"),
    (f"{LOC}.mediaAssets.icons.light", icons()[:5], "exactly the six sizes"),
    (f"{LOC}.mediaAssets.icons.light", [*icons(), icons()[0]], "exactly the six sizes"),
    (f"{LOC}.mediaAssets.icons.light", [{"size": "100x100", "uri": OK_URI}] * 6, "six sizes"),
    (f"{LOC}.mediaAssets.icons.light.0.uri", "http://example.invalid/i.png", "light[0].uri is not an https"),
    (f"{LOC}.mediaAssets.icons.light.1.uri", "https://example.invalid/i.gif", "light[1].uri is not an https"),
    (f"{LOC}.mediaAssets.icons.light.2.uri", "https://example.invalid/i.WEBP", None),
    (f"{LOC}.mediaAssets.icons.light.2.uri", "https://example.invalid/i.jpeg", None),
    (f"{LOC}.mediaAssets.icons.dark", icons(), None),
    (f"{LOC}.mediaAssets.icons.dark", icons()[:3], "dark needs exactly the six sizes"),
    (f"{LOC}.mediaAssets.carouselImages", [], "at least one image"),
    (f"{LOC}.mediaAssets.carouselImages", [image(GOOD_C, alt="x" * 250)], None),
    (f"{LOC}.mediaAssets.carouselImages", [image(GOOD_C, alt="x" * 251)], "altText is 251"),
    (f"{LOC}.mediaAssets.carouselImages", [image(GOOD_C, size="900x600")], 'size must be "600x900"'),
    (f"{LOC}.mediaAssets.carouselImages", [image("http://e.invalid/c.png")], "uri is not an https"),
    (f"{LOC}.mediaAssets.carouselImages", [image(GOOD_C), image("https://e.invalid/d.jpg")], None),
    (f"{LOC}.mediaAssets.bannerImages", [{"uri": "https://e.invalid/b.png", "size": "1200x600"}], None),
    (
        f"{LOC}.mediaAssets.bannerImages",
        [{"uri": "https://e.invalid/b.png", "size": "1200x601"}],
        "bannerImages[0] needs",
    ),
    (f"{LOC}.name.spokenForm", {"format": "ipa", "value": "klʌktɔk"}, None),
    (f"{LOC}.name.spokenForm", {"format": "ssml", "value": "x"}, "spokenForm needs"),
    (f"{LOC}.default", "OTHER", 'default must be "DEFAULT"'),
    ("manifestVersion", "2.0", 'manifestVersion must be "1.0"'),
    ("storeListing.distributionCountries", ["US", "IN"], None),
    ("storeListing.distributionCountries", [], "distributionCountries needs"),
    ("storeListing.distributionCountries", ["USA"], "distributionCountries needs"),
    ("storeListing.distributionCountries", ["us"], "distributionCountries needs"),
    ("storeListing.locales", {}, "at least one locale"),
    ("integrations", [], "needs an MCP integration"),
    ("integrations.0.type", "REST", 'type must be "MCP"'),
    ("integrations.0.config.endpoints.default.type", "SSE", 'type "HTTPS"'),
    ("integrations.0.config.endpoints.default.uri", "http://example.invalid/mcp", "an https uri"),
]


@pytest.mark.parametrize(("path", "value", "fragment"), EDGE_CASES)
def test_each_documented_field_and_limit_is_enforced_at_its_edge(path, value, fragment):
    problems = readiness.validate_addon(edited(path, value))
    if fragment is None:
        assert problems == [], problems  # exactly at the limit, or an allowed optional part
    else:
        assert any(fragment in p for p in problems), (fragment, problems)


def test_a_second_locale_is_checked_too_and_its_code_must_look_like_one():
    data = copy.deepcopy(DRAFT)
    other = copy.deepcopy(data["storeListing"]["locales"]["en-US"])
    other["name"]["value"] = "x" * 31
    data["storeListing"]["locales"]["hi-IN"] = other
    assert any("locales.hi-IN.name.value is 31" in p for p in readiness.validate_addon(data))
    data["storeListing"]["locales"] = {"english": copy.deepcopy(DRAFT["storeListing"]["locales"]["en-US"])}
    assert any("not a locale code" in p for p in readiness.validate_addon(data))


def test_a_missing_section_is_reported_not_crashed_on():
    assert any("storeListing is missing" in p for p in readiness.validate_addon({"manifestVersion": "1.0"}))
    assert readiness.validate_addon({}) != []
    assert readiness.validate_addon({"storeListing": [], "integrations": "x"}) != []
