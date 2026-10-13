"""Step 52 part C: the phone page's own logic, run for real in Node against a hand-made DOM
(tests/harness/pilot_page_checks.js). Acknowledge the notice first (nothing runs before), the token flow, the device
id, the 401 message, the add or replace buttons. It is not a browser: layout, fonts and the keyboard are not covered.
Without Node the tests are SKIPPED, loudly."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
NODE = shutil.which("node")


@pytest.fixture(scope="module")
def results() -> dict[str, str]:
    if NODE is None:
        pytest.skip("node is not installed: the phone page's logic was NOT exercised (install Node to run these)")
    done = subprocess.run(
        [NODE, str(HERE / "pilot_page_checks.js")], capture_output=True, text=True, encoding="utf-8", timeout=60
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


SCENARIOS = [
    "nothing_runs_before_the_notice_is_acknowledged",
    "the_notice_has_all_seven_items_and_one_big_button",
    "acknowledging_opens_the_page_and_is_remembered_per_device",
    "new_wording_asks_again",
    "without_local_storage_it_asks_every_time_and_still_works",
    "the_token_is_read_from_the_fragment_removed_and_sent",
    "no_token_means_the_open_your_link_message",
    "a_401_on_a_turn_shows_the_message_too",
    "the_question_shows_add_and_replace_and_hides_the_plain_yes",
    "an_ordinary_read_back_shows_yes_and_no_only",
    "the_device_id_is_kept_and_sent_as_the_session",
    "the_device_id_falls_back_to_the_tab_without_local_storage",
    "an_alert_status_gets_one_red_bar_with_icon_word_shed_deaths_and_the_vet_line_and_the_rest_below",
    "the_bar_shows_only_the_alert_codes_own_text_when_it_is_not_the_farmers_death_limit",
    "the_bar_is_never_shown_on_ok_or_watch_or_without_houses",
    "the_briefings_alert_items_get_the_bar_too",
    "a_deaths_count_from_another_day_is_not_shown_as_todays",
    "the_sell_price_is_one_big_number_and_the_rule_line_is_small_and_nothing_is_lost",
    "the_sell_question_and_other_answers_get_no_price_emphasis",
    "a_warning_has_a_word_and_an_icon_marker_not_only_a_colour_and_your_own_words_have_none",
    "the_notice_text_is_on_the_screen_once_and_not_in_a_strip_under_the_header",
    "the_input_has_a_telugu_placeholder_and_the_send_button_a_word",
    "the_log_keeps_only_the_newest_answers",
    "a_read_back_says_tap_where_the_server_text_says_say_and_is_unchanged_otherwise",
]


@pytest.mark.parametrize("name", SCENARIOS)
def test_the_page_scenario(results, name):
    assert results.get(name) == "ok", results.get(name, "scenario did not run")


def test_every_scenario_in_the_script_is_listed_here(results):
    assert sorted(results) == sorted(SCENARIOS)
