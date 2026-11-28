"""Lane FE3 (28 Nov 2026), item 6 (PC note 27 Nov 09:43, UX-A03; ADR-330 (3b), (6); ADR-003): the stored message of a
FIRED leg stop says what happened, in the past tense, with the figure at the fill: never "If this stop fires, max loss
becomes ... (now ...)" with the figure from before the fire.

Real case: the condor of ``test_stop_fired_message`` (short call stop at 140.70). The tick fills at 141.00: the stored
text now ends "Stop fired: <leg> reached 140.70; max loss at that point Rs 12,025.00" (the figure the Stops panel's
route gives for an exit at 141.00); a gap to 180.00 gives Rs 14,560.00, the fill's figure, not the level's.
"""
from __future__ import annotations

from ofo_app import actionable_alerts as aa
from test_paper_monitor import _alerts
from test_stop_fired_message import LONG_CALL, SHORT_CALL, _fire_leg, db  # noqa: F401 - fixture

FUTURE = ("If this stop fires", "becomes", "(now Rs", "would")


async def test_core_a_fired_leg_stop_names_the_figure_at_the_fill_in_the_past_tense(db):  # noqa: F811
    _m, stored, _ids, fires = await _fire_leg(db, SHORT_CALL, "140.70", "141.00")
    [(_title, text)] = await _alerts(db, stored.id)
    print("TEXT", text)
    assert fires == 1
    assert text.endswith("reached 140.70; max loss at that point Rs 12,025.00"), text
    assert "Stop fired: " in text and "exited at 141.00" in text
    assert not any(w in text for w in FUTURE), text


async def test_a_gapped_fill_gives_the_figure_of_the_fill_not_the_level(db):  # noqa: F811
    _m, stored, _ids, fires = await _fire_leg(db, SHORT_CALL, "140.70", "180.00")
    [(_title, text)] = await _alerts(db, stored.id)
    assert fires == 1 and text.endswith("reached 140.70; max loss at that point Rs 14,560.00"), text
    assert "12,025.00" not in text and not any(w in text for w in FUTURE)


async def test_a_stop_that_leaves_a_sold_option_bare_says_there_was_no_fixed_maximum(db):  # noqa: F811
    _m, stored, _ids, fires = await _fire_leg(db, LONG_CALL, "5.00", "5.50")
    [(_title, text)] = await _alerts(db, stored.id)
    print("TEXT", text)
    assert fires == 1 and text.endswith("; there was no fixed maximum loss at that point"), text
    assert not any(w in text for w in FUTURE)


async def test_the_stored_line_reads_back_through_the_history(db):  # noqa: F811
    _m, stored, _ids, _fires = await _fire_leg(db, SHORT_CALL, "140.70", "141.00")
    rows = [a for a in await aa.history(db, stored.user_ref) if a.strategy_id == stored.id]
    assert len(rows) == 1 and rows[0].kind == "stop_fired"
