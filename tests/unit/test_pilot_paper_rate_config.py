"""The optional ``sale_price_below_paper_rate_inr`` farm-file field: the farmer's own rule (his price is the paper rate
minus a fixed amount). Validated like the feed price; absent means nothing changes."""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from clucktalk.pilot import PilotFarmError, load_pilot_farm_file, parse_pilot_farm

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = json.loads((ROOT / "docs" / "pilot_farm.example.json").read_text(encoding="utf-8"))


def farm(**changes):
    data = copy.deepcopy(EXAMPLE)
    data.update(changes)
    return data


def test_the_delta_is_read_as_a_decimal():
    assert parse_pilot_farm(farm(sale_price_below_paper_rate_inr="20")).sale_price_below_paper_rate == Decimal("20")
    assert parse_pilot_farm(farm(sale_price_below_paper_rate_inr="0")).sale_price_below_paper_rate == Decimal("0")


def test_an_absent_delta_is_none_and_nothing_else_changes():
    data = farm()
    data.pop("sale_price_below_paper_rate_inr", None)
    config = parse_pilot_farm(data)
    assert config.sale_price_below_paper_rate is None
    assert config.simulated_live_bird_price_per_kg == Decimal("90")


@pytest.mark.parametrize("bad", ["-1", "abc", "", 20, None, True, "NaN", "Infinity", "100000", "1e9"])
def test_an_invalid_delta_is_refused_with_its_name(bad):
    with pytest.raises(PilotFarmError, match="sale_price_below_paper_rate_inr"):
        parse_pilot_farm(farm(sale_price_below_paper_rate_inr=bad))


def test_the_simulated_price_may_be_left_out_only_with_a_delta_and_no_verified_curve():
    data = farm(sale_price_below_paper_rate_inr="20")
    del data["simulated_live_bird_price_per_kg_inr"]
    config = parse_pilot_farm(data)
    assert config.simulated_live_bird_price_per_kg is None

    no_delta = farm()
    no_delta.pop("sale_price_below_paper_rate_inr")
    del no_delta["simulated_live_bird_price_per_kg_inr"]
    with pytest.raises(PilotFarmError, match="simulated_live_bird_price_per_kg_inr"):
        parse_pilot_farm(no_delta)

    with_curve = copy.deepcopy(data)
    with_curve["houses"][0]["breed"] = "Ross 308"
    with pytest.raises(PilotFarmError, match="simulated_live_bird_price_per_kg_inr"):
        parse_pilot_farm(with_curve)


def test_the_example_file_carries_the_example_delta():
    config = load_pilot_farm_file(ROOT / "docs" / "pilot_farm.example.json")
    assert config.sale_price_below_paper_rate == Decimal("20")
