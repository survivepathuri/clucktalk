import pytest

from clucktalk.domain.errors import UnknownHouse
from clucktalk.domain.houses import resolve_house
from tests.unit.helpers import farm_with, layer_house


@pytest.fixture
def farm():
    return farm_with(*(layer_house([0], [100.0], number=n) for n in (1, 2, 3)))


@pytest.mark.parametrize(
    "spoken",
    [
        "shed two",
        "House 2",
        "kotam 2",
        "kottam two",
        "house no. 2",
        "shed number 2",
        "do number",
        "second shed",
        "2",
        "house-2",
    ],
)
def test_farmer_vocabulary_resolves(farm, spoken):
    assert resolve_house(farm, spoken).number == 2


@pytest.mark.parametrize("spoken", ["shed nine", "shed two three", "big shed", ""])
def test_unknown_or_ambiguous_is_refused_with_real_labels(farm, spoken):
    with pytest.raises(UnknownHouse) as exc:
        resolve_house(farm, spoken)
    assert "House 1, House 2, House 3" in exc.value.next_step
