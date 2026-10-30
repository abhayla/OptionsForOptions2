"""``ofo.marketdata.kite_quote_time.quote_time``: Kite's REST quote timestamp, every answer state named.

Moved out of ``ofo_app.execute_plan`` so the REST index spot read reaches no order module (GC-ADJ1 order closure);
these pin that the move kept the reading and refuses every other shape (fail closed).
"""
from __future__ import annotations

import datetime

import pytest
from ofo.marketdata.kite_quote_time import quote_time
from ofo.timeutil import IST


def test_the_kite_timestamp_is_read_as_an_aware_ist_time():
    assert quote_time({"timestamp": "2026-10-30 11:00:00"}) == datetime.datetime(2026, 10, 30, 11, 0, 0, tzinfo=IST)
    assert quote_time({"timestamp": "2026-10-30 11:00:00"}).utcoffset() == datetime.timedelta(hours=5, minutes=30)


@pytest.mark.parametrize("quote", [
    {},                                           # absent
    {"timestamp": None},                          # stated as null
    {"timestamp": 1761802200},                    # a number, not Kite's text
    {"timestamp": ""},                            # empty
    {"timestamp": "2026-10-30"},                  # date only
    {"timestamp": "2026-10-30T11:00:00"},         # another ISO shape
    {"timestamp": "2026-10-30 11:00:00+05:30"},   # with a zone
    {"timestamp": "2026-10-30 1:00:00"},          # not zero padded
    {"timestamp": "2026-13-01 10:00:00"},         # not a real date
    {"timestamp": "2026-10-30 11:00:00\n"},       # trailing text
])
def test_any_other_answer_is_none_never_a_guessed_time(quote):
    assert quote_time(quote) is None

