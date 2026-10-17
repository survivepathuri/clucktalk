"""Mock host rules and host security settings (clucktalk.simulator), written from the design, not the code:
the intent matcher only picks the tool and passes the shed words through; the sandbox CSP is the MCP Apps
spec's restrictive default plus one documented addition (font-src data:)."""

from __future__ import annotations

import pytest

from clucktalk.config import ConfigError
from clucktalk.simulator.__main__ import load_simulator_settings
from clucktalk.simulator.app import sandbox_csp
from clucktalk.simulator.intents import is_weak_yes, match, normalise, yes_no


@pytest.mark.parametrize(
    ("utterance", "tool", "args"),
    [
        # Invocation examples and farmer phrasing (docs/DESIGN.md §5 rule 6: shed/house/kotam, Hinglish numbers)
        ("Alexa, ask CluckTalk how shed two is doing", "get_farm_status", {"house": "shed 2"}),
        ("Alexa, ask Cluck Talk how shed 2 is doing?", "get_farm_status", {"house": "shed 2"}),
        ("How's the farm today?", "get_farm_status", {}),
        ("How are all sheds doing", "get_farm_status", {}),
        ("Kotam teen kaisa hai?", "get_farm_status", {"house": "kotam teen"}),
        ("how is the second shed", "get_farm_status", {"house": "second shed"}),
        ("do number shed ka haal", "get_farm_status", {"house": "do number shed"}),
        ("house number 3 status", "get_farm_status", {"house": "house number 3"}),
        ("How is shade two doing", "get_farm_status", {"house": "shed 2"}),  # common mishearing
        ("How is shed nine doing?", "get_farm_status", {"house": "shed 9"}),  # the server decides it's unknown
        ("Feed plan for shed two", "plan_feed", {"house": "shed 2"}),
        ("how much dana do I need", "plan_feed", {}),
        ("What can you do?", "get_help", {}),
        ("help", "get_help", {}),
        # Farm mode (docs/DESIGN.md §13.1): the words pick the mode; the server confirms with a read-back
        ("Switch my farm to contract farming", "set_farm_mode", {"mode": "contract"}),
        ("change to company farming", "set_farm_mode", {"mode": "contract"}),
        ("we are integration farm now", "set_farm_mode", {"mode": "contract"}),
        ("Alexa, ask CluckTalk to switch to independent farming", "set_farm_mode", {"mode": "independent"}),
        ("make it my own farm", "set_farm_mode", {"mode": "independent"}),
        ("What kind of farm is this?", "get_farm_profile", {}),
        ("am I contract or independent", "get_farm_profile", {}),
        # Review 2026-09-28: "own" alone is not a farm mode
        ("change the feed in my own shed 2", "plan_feed", {"house": "shed 2"}),
        # Voice record book (docs/DESIGN.md §13.2): a stated number is what makes it a report, not a question.
        ("House 2, 3 birds died today", "log_daily_record", {"house": "house 2", "deaths": 3}),
        ("3 birds died in house 2", "log_daily_record", {"house": "house 2", "deaths": 3}),
        ("house two mar gaye 3", "log_daily_record", {"house": "house 2", "deaths": 3}),
        ("shed 1 no deaths today", "log_daily_record", {"house": "shed 1", "deaths": 0}),
        ("gave 2 bags of feed to house 1", "log_daily_record", {"house": "house 1", "feed_bags": 2.0}),
        ("fed 2 bags to shed 1 today", "log_daily_record", {"house": "shed 1", "feed_bags": 2.0}),
        (
            "House 2, 3 died and 2 bags of feed today",
            "log_daily_record",
            {"house": "house 2", "deaths": 3, "feed_bags": 2.0},
        ),
        (
            "house 2, no deaths, 3 bags of feed",
            "log_daily_record",
            {"house": "house 2", "deaths": 0, "feed_bags": 3.0},
        ),
        (
            "house 3 average weight 1800 grams from 10 birds weighed",
            "log_daily_record",
            {"house": "house 3", "avg_weight_g": 1800.0, "weight_sample_birds": 10},
        ),
        (
            "house 2, gave Newcastle vaccine",
            "log_daily_record",
            {"house": "house 2", "treatments": [{"kind": "vaccine", "name": "Newcastle"}]},
        ),
        (
            "shed 3 gave Amoxicillin medicine",
            "log_daily_record",
            {"house": "shed 3", "treatments": [{"kind": "medicine", "name": "Amoxicillin"}]},
        ),
        ("record book", "get_record_book", {}),
        ("who has logged today", "get_record_book", {}),
        ("what's logged today", "get_record_book", {}),
        # A question, not a report: no number given, so this stays plan_feed, never log_daily_record.
        ("how much feed does shed 2 need", "plan_feed", {"house": "shed 2"}),
        # Rule 11 review 2026-09-29: DESIGN.md §13.2 lists "feed used (bags or kg)"; kg used to fall through to
        # the generic FEED trigger and silently become a plan_feed question instead of a report.
        ("gave 100 kg of feed to house 1", "log_daily_record", {"house": "house 1", "feed_bags": 2.0}),
        # A multi-word treatment name, and a dose-shaped word rejected as a name rather than stored.
        (
            "house 2, gave Newcastle disease vaccine",
            "log_daily_record",
            {"house": "house 2", "treatments": [{"kind": "vaccine", "name": "Newcastle Disease"}]},
        ),
    ],
)
def test_utterance_to_tool(utterance, tool, args):
    intent = match(utterance)
    assert intent is not None, utterance
    assert (intent.tool, intent.arguments) == (tool, args)
    assert intent.rule  # the developer panel always shows why


@pytest.mark.parametrize("utterance", ["", "   ", "What's the weather today?", "play some music", "Alexa"])
def test_no_rule_no_tool(utterance):
    """Unbuilt or out-of-scope requests get the host fallback, never a guessed tool call."""
    assert match(utterance) is None


def test_what_can_you_do_is_help_not_a_shed():
    """'do' is also Hinglish for two; it only counts next to a shed word."""
    assert match("what can you do").tool == "get_help"


def test_sandbox_csp_default_is_the_spec_default_plus_inline_fonts():
    csp = dict(d.split(" ", 1) for d in sandbox_csp(None).split("; "))
    assert csp == {
        "default-src": "'none'",
        "script-src": "'self' 'unsafe-inline'",
        "style-src": "'self' 'unsafe-inline'",
        "img-src": "'self' data:",
        "media-src": "'self' data:",
        "font-src": "'self' data:",
        "connect-src": "'none'",
        "frame-src": "'none'",
        "base-uri": "'self'",
        "object-src": "'none'",
        "form-action": "'none'",  # host hardening: default-src does not cover form posts
        "frame-ancestors": "'none'",  # no embedder given: nobody may frame the proxy
    }


def test_sandbox_csp_lets_only_the_simulator_page_embed_the_proxy():
    csp = sandbox_csp({}, ("http://127.0.0.1:8766", "http://localhost:8766"))
    assert "frame-ancestors http://127.0.0.1:8766 http://localhost:8766" in csp


def test_sandbox_csp_adds_declared_https_origins_and_drops_anything_else():
    csp = sandbox_csp(
        {
            "connectDomains": ["https://api.example.com", "http://insecure.example", "*"],
            "resourceDomains": ["https://*.cdn.example", "javascript:alert(1)", "https://ok.example; script-src *"],
        }
    )
    assert "connect-src https://api.example.com;" in csp + ";"
    assert "font-src 'self' data: https://*.cdn.example" in csp
    for bad in ("http://insecure.example", " * ", "javascript:", "ok.example"):
        assert bad not in csp, bad


def test_strict_sandbox_csp_is_the_spec_default_without_a_font_src():
    """Strict mode = a host that applies the spec default literally: font-src falls back to default-src 'none'."""
    csp = dict(d.split(" ", 1) for d in sandbox_csp(None, strict=True).split("; "))
    assert "font-src" not in csp
    assert csp["default-src"] == "'none'"
    assert {k: csp[k] for k in ("script-src", "style-src", "img-src", "media-src", "connect-src")} == {
        "script-src": "'self' 'unsafe-inline'",
        "style-src": "'self' 'unsafe-inline'",
        "img-src": "'self' data:",
        "media-src": "'self' data:",
        "connect-src": "'none'",
    }


def test_strict_sandbox_csp_allows_fonts_only_from_declared_origins():
    csp = sandbox_csp({"resourceDomains": ["https://fonts.example", "http://insecure.example"]}, strict=True)
    directives = dict(d.split(" ", 1) for d in csp.split("; "))
    assert directives["font-src"] == "https://fonts.example"  # no 'self', no data:
    assert "insecure" not in csp


def test_simulator_refuses_live_mode_until_aws_setup():
    with pytest.raises(ConfigError, match="AWS setup"):
        load_simulator_settings({})
    with pytest.raises(ConfigError, match="AWS setup"):
        load_simulator_settings({"MOCK_BEDROCK": "false"})


def test_simulator_settings():
    s = load_simulator_settings({"MOCK_BEDROCK": "true"})
    assert (s.port, s.mcp_url) == (8766, "http://127.0.0.1:8765/mcp")
    assert s.origins == {"http://127.0.0.1:8766", "http://localhost:8766"}
    with pytest.raises(ConfigError, match="same|both"):
        load_simulator_settings({"MOCK_BEDROCK": "true", "CLUCKTALK_SIMULATOR_PORT": "8765"})
    with pytest.raises(ConfigError, match="port"):
        load_simulator_settings({"MOCK_BEDROCK": "true", "CLUCKTALK_SIMULATOR_PORT": "99999"})


@pytest.mark.parametrize(
    ("utterance", "answer"),
    [
        ("yes", "yes"), ("Yes.", "yes"), ("haan", "yes"), ("haan ji", "yes"), ("avunu", "yes"),
        ("no", "no"), ("nahi", "no"), ("vaddu", "no"), ("cancel", "no"),
        # Not an explicit answer: never sent as one (docs/DESIGN.md §5.1)
        ("yes and how is shed two", None), ("maybe", None), ("how is shed two doing", None), ("", None),
        ("ha", None),  # review: too short to count as an explicit yes (could be a laugh)
    ],
)  # fmt: skip
def test_only_a_whole_yes_or_no_counts_as_an_answer(utterance, answer):
    assert yes_no(utterance) == answer


def test_a_bare_yes_is_not_an_intent():
    assert match("yes") is None and match("haan") is None


@pytest.mark.parametrize(
    "utterance", ["we're not a contract farm", "don't switch to contract", "never change to independent farming"]
)
def test_a_negated_mode_sentence_never_starts_a_switch(utterance):
    """Review 2026-09-28 (Low): negations matched as a switch request."""
    intent = match(utterance)
    assert intent is None or intent.tool != "set_farm_mode"


def test_a_dose_word_is_never_stored_as_a_treatment_name():
    """Rule 11 review 2026-09-29: "gave 5 ml vaccine" used to store name="Ml"."""
    intent = match("house 1 gave 5 ml vaccine")
    assert intent is None or "treatments" not in intent.arguments


def test_a_treatment_without_a_real_name_is_never_guessed():
    """ "gave the vaccine" has no name to record; falls back rather than inventing one (docs/DESIGN.md §5 rule 4:
    never guess)."""
    intent = match("house 1 gave the vaccine")
    assert intent is None or intent.tool != "log_daily_record"


def test_a_weight_without_a_bird_count_still_reaches_the_tools_own_clarifying_error():
    """Rule 11 review 2026-09-29: dropping the weight silently sent a weight-only report to get_farm_status
    instead. Sending avg_weight_g alone reaches log_daily_record, which asks for the bird count itself
    (WeightSampleNeedsBirdCount) rather than the host guessing one or staying silent."""
    intent = match("house 2 average weight 1800 grams")
    assert intent.tool == "log_daily_record"
    assert intent.arguments == {"house": "house 2", "avg_weight_g": 1800.0}


@pytest.mark.parametrize(
    ("utterance", "args"),
    [
        # Health triage (docs/DESIGN.md §18): the farmer's words map onto closed-list signs; their own words go too
        ("Shed 2 birds are coughing and not eating", {"house": "shed 2", "signs": ["coughing", "not_eating"]}),
        ("kotam do mein khansi aur dast", {"house": "kotam do", "signs": ["coughing", "diarrhoea"]}),
        (
            "house two swollen heads and blue combs, birds dying suddenly",
            {"house": "house 2", "signs": ["swollen_head", "discoloured_comb", "sudden_deaths"]},
        ),
        ("shed one birds panting a lot", {"house": "shed 1", "signs": ["panting"]}),
        ("shed 3 twisted neck and drooping wings", {"house": "shed 3", "signs": ["twisted_neck", "paralysis"]}),
    ],
)
def test_signs_of_illness_start_a_health_check(utterance, args):
    intent = match(utterance)
    assert intent.tool == "start_health_check"
    assert {k: intent.arguments[k] for k in ("house", "signs")} == args
    assert intent.arguments["symptoms"]  # the farmer's own words, for the agent's delimited data block


@pytest.mark.parametrize(
    ("utterance", "tool", "args"),
    [
        ("is the shed 2 health check ready", "get_health_check", {"house": "shed 2"}),
        ("what did the health check find for house two", "get_health_check", {"house": "house 2"}),
        ("send the shed 2 health check to my vet", "prepare_vet_handoff", {"house": "shed 2"}),
        ("shed two report vet ko bhej do", "prepare_vet_handoff", {"house": "shed 2"}),
    ],
)
def test_health_check_follow_ups(utterance, tool, args):
    intent = match(utterance)
    assert (intent.tool, intent.arguments) == (tool, args)


@pytest.mark.parametrize(
    ("utterance", "signs"),
    [
        ("shed 2 no sudden deaths, just coughing", ["coughing"]),
        ("shed 2 not coughing but not eating", ["not_eating"]),  # "not eating" is itself a sign
        ("shed 2 birds are not eating", ["not_eating"]),
        ("shed 2 without any coughing, some diarrhoea", ["diarrhoea"]),
        ("shed 2 no more coughing, birds dying suddenly", ["coughing", "sudden_deaths"]),  # only a direct "no X"
    ],
)
def test_a_directly_negated_sign_is_not_reported(utterance, signs):
    """Rule 11 review 2026-09-30 L5: "no sudden deaths, just coughing" used to report sudden deaths."""
    assert match(utterance).arguments["signs"] == signs


def test_signs_without_a_shed_are_not_guessed():
    assert match("birds are coughing") is None  # the host asks which shed rather than guessing


def test_a_dose_question_never_reaches_a_record_or_a_number():
    intent = match("shed 2 birds coughing, which antibiotic and how many ml should I give")
    assert intent.tool == "start_health_check"
    assert "treatments" not in intent.arguments


@pytest.mark.parametrize(
    "utterance",
    [
        "do a health check on shed 2, birds are coughing",
        "shed 2 ki jaanch karo, murgi khansi",
        "shed 2 birds coughing, send doctor",
    ],
)
def test_signs_win_over_result_and_vet_words(utterance):
    """Rule 11 finding 4: a sick-bird report must start a check, never lose its signs to a follow-up intent."""
    intent = match(utterance)
    assert intent.tool == "start_health_check" and "coughing" in intent.arguments["signs"]


@pytest.mark.parametrize(
    ("utterance", "args"),
    [
        ("Alexa, ask CluckTalk for today's briefing", {}),
        ("give me the daily briefing", {}),
        ("what's my briefing", {}),
        ("morning briefing please", {}),
        ("briefing", {}),
        ("more", {"more": True}),
        ("tell me more", {"more": True}),
        ("what else", {"more": True}),
    ],
)
def test_briefing_intents(utterance, args):
    intent = match(utterance)
    assert intent is not None and intent.tool == "get_daily_briefing" and intent.arguments == args


@pytest.mark.parametrize(
    "utterance", ["how is shed two doing", "briefing for shed 2 health check", "more feed for shed 1"]
)
def test_briefing_words_do_not_steal_other_intents(utterance):
    intent = match(utterance)
    assert intent is None or intent.tool != "get_daily_briefing"


@pytest.mark.parametrize(
    ("said", "normalised"),
    [
        ("five birds died in shed one", "5 birds died in shed 1"),
        ("Shed Two", "shed 2"),
        ("twenty birds died in house ten", "20 birds died in house 10"),
        ("twenty five birds died in shed three", "25 birds died in shed 3"),
        ("thirty-two bags of feed for shed four", "32 bags of feed for shed 4"),
        ("nineteen birds dead shed nine", "19 birds dead shed 9"),
        ("kotam do", "kotam do"),  # Hindi words stay for the house rules
    ],
)
def test_english_number_words_become_digits(said, normalised):
    assert normalise(said) == normalised


def test_a_spoken_record_matches_the_typed_one():
    spoken, typed = match("five birds died in shed one"), match("5 birds died in shed 1")
    assert spoken is not None and typed is not None
    assert (
        (spoken.tool, spoken.arguments)
        == (typed.tool, typed.arguments)
        == ("log_daily_record", {"house": "shed 1", "deaths": 5})
    )


@pytest.mark.parametrize(
    "said",
    [
        "how much medicine for shed 2",
        "what dose of antibiotic should I give shed two",
        "how many ml per litre for shed 1",
    ],
)
def test_dose_questions_go_to_the_health_check_with_no_guessed_signs(said):
    intent = match(said)
    assert intent is not None and intent.tool == "start_health_check"
    assert intent.arguments["signs"] == [] and intent.arguments["symptoms"] == said


def test_a_dose_question_is_not_read_as_a_treatment_record():
    intent = match("how much medicine should I give for shed two")
    assert intent is not None and intent.tool != "log_daily_record"
    assert match("gave newcastle vaccine in shed 2").tool == "log_daily_record"  # a real report still records


@pytest.mark.parametrize("said", ["ok", "okay", "sure", "please do"])
def test_mild_acceptance_words_are_weak(said):
    assert is_weak_yes(said) and yes_no(said) == "yes"


@pytest.mark.parametrize("said", ["yes", "yeah", "yep", "yes please", "haan", "confirm"])
def test_explicit_yes_words_are_not_weak(said):
    assert not is_weak_yes(said) and yes_no(said) == "yes"
