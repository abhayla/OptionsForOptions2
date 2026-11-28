"""Lane FE2 (28 Nov 2026), coordinator hand-over 4 (Lane FB2, PC note UX-A03): the row the monitor stores for a FIRED
stop says what happened, with the figure at firing, never the future tense of the stop's preview ("If this stop fires,
max loss becomes ... (now ...)"). Spec basis: ADR-330 (3b), (6), (19)(b); ADR-003 (decision support, no advice).

``tests_app/test_stop_fired_message.py`` was never run before this lane; it passes on this head (4 tests). These add the
exact figure at firing: a normal fill and a gapped fill.
"""
from __future__ import annotations

from test_paper_monitor import _alerts
from test_stop_fired_message import SHORT_CALL, _fire_leg, db  # noqa: F401 - fixture

FUTURE_WORDS = ("If this stop fires", "becomes", "(now Rs", "would")


async def test_a_fired_stop_row_names_the_fill_and_never_the_future_tense(db):  # noqa: F811
    _m, stored, _ids, fires = await _fire_leg(db, SHORT_CALL, "140.70", "141.00")
    [(_title, text)] = await _alerts(db, stored.id)
    print("TEXT", text)
    assert fires == 1
    assert "exited at 141.00" in text, "the figure at firing, not the stop level 140.70"
    assert not any(w in text for w in FUTURE_WORDS), text


async def test_a_gapped_fill_row_names_the_gapped_price_not_the_level(db):  # noqa: F811
    _m, stored, _ids, fires = await _fire_leg(db, SHORT_CALL, "140.70", "180.00")
    [(_title, text)] = await _alerts(db, stored.id)
    assert fires == 1 and "exited at 180.00" in text
    assert not any(w in text for w in FUTURE_WORDS), text
