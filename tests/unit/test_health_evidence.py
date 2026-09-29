"""Rule 11 finding 9: when a shed's records can't be used, the check says it runs on the signs alone."""

from __future__ import annotations

from datetime import date

from clucktalk.domain.models import House, HouseKind
from clucktalk.domain.triage import Sign
from clucktalk.server.tools.health import _evidence_text, _input


def test_unusable_records_are_said_not_hidden():
    house = House("house-9", 9, HouseKind.BROILER, "Ross 308", date(2026, 9, 20), 1000, 0, 500.0, ())
    inp = _input(house, date(2026, 9, 29), (Sign.COUGHING,), None, None, None)
    assert inp.records_used is False and inp.deaths_latest is None
    text = _evidence_text(inp)
    assert "signs alone" in text.en and text.te
