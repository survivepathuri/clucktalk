"""Step 49 part B: the draft add-on listing (docs/addon-package/addon.json) is a placeholder example, validated against
the field limits from the brief: name at most 30 characters, short description at most 123, full description at most
4000, 3 to 4 example phrases of at most 200, https URLs, six icon sizes and one 600x900 carousel image. Its example
phrases are phrases the server itself gives in get_help."""

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


def changed(**edits):
    data = copy.deepcopy(DRAFT)
    data.update(edits)
    return data


def test_the_committed_draft_has_no_problems():
    assert readiness.validate_addon(DRAFT) == []


def test_the_draft_says_it_is_a_placeholder_and_not_amazons_schema():
    note = DRAFT["_draft_notice"]
    assert "NOT DEPLOYED" in note and "not Amazon's addon.json schema" in note and "placeholder" in note
    assert all("example.invalid" in u for u in DRAFT["urls"].values())


@pytest.mark.parametrize(
    ("edit", "fragment"),
    [
        ({"name": "x" * 30}, None),
        ({"name": "x" * 31}, "name is 31"),
        ({"name": ""}, "name is missing"),
        ({"short_description": "x" * 123}, None),
        ({"short_description": "x" * 124}, "short_description is 124"),
        ({"full_description": "x" * 4000}, None),
        ({"full_description": "x" * 4001}, "full_description is 4001"),
        ({"example_phrases": ["a", "b"]}, "3 to 4 entries"),
        ({"example_phrases": ["a", "b", "c", "d", "e"]}, "3 to 4 entries"),
        ({"example_phrases": ["a", "b", "c", "x" * 200]}, None),
        ({"example_phrases": ["a", "b", "c", "x" * 201]}, "example_phrases[3] is 201"),
        ({"example_phrases": ["a", "b", ""]}, "example_phrases[2] is empty"),
        ({"urls": {"endpoint": "http://example.invalid/mcp"}}, "urls.endpoint is not an https"),
        ({"urls": {}}, "urls is missing"),
        ({"icons": DRAFT["icons"][:5]}, "exactly 6"),
        ({"icons": DRAFT["icons"] + DRAFT["icons"][:1]}, "exactly 6"),
        ({"icons": [DRAFT["icons"][0]] * 6}, "six different"),
        ({"carousel_image": {"width": 600, "height": 901, "url": "https://example.invalid/c.png"}}, "600x900"),
        ({"carousel_image": {"width": 900, "height": 600, "url": "https://example.invalid/c.png"}}, "600x900"),
        (
            {"carousel_image": {"width": 600, "height": 900, "url": "http://example.invalid/c.png"}},
            "carousel_image.url",
        ),
    ],
)
def test_each_documented_limit_is_enforced_at_its_edge(edit, fragment):
    problems = readiness.validate_addon(changed(**edit))
    if fragment is None:
        assert problems == []  # exactly at the limit is allowed
    else:
        assert any(fragment in p for p in problems), problems


def test_an_icon_with_an_http_url_is_a_problem():
    icons = copy.deepcopy(DRAFT["icons"])
    icons[2]["url"] = "http://example.invalid/icon.png"
    assert any("icons[2].url" in p for p in readiness.validate_addon(changed(icons=icons)))


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
    assert set(DRAFT["example_phrases"]) <= given


def test_the_draft_makes_no_claim_that_it_runs_on_alexa():
    text = DRAFT["full_description"].lower()
    assert "has not been run on an alexa+ device" in text
    for claim in ("production-ready", "enterprise-grade", "guaranteed", "certified", "real-time"):
        assert claim not in text
