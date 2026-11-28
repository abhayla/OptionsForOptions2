"""Lane TF item 1 (I-51), ADR-330 (55): the leg-stop warning is three SHORT lines and the loss figure that a bare sold
put produces says it is a theoretical worst case. Real case 27 Nov 09:34, trade B-N1: the warning showed a loss figure
(Rs 16,62,316.50, now Rs 1,732.25) without saying what case the figure stands for, and it was read as an error.

Through the route, the replay market and the app's iron condor of test_leg_stop_risk.py (65 units a leg), so the lines
are the server's own (ADR-008), never rebuilt in the test. Every test is rolled back."""
from __future__ import annotations

from http import HTTPStatus

import pytest
from test_leg_stop_risk import (
    LONG_CALL,
    LONG_PUT,
    SHORT_CALL,
    SHORT_PUT,
    _ask,
    _book,
    _orders,
)

MAX_LINE = 80  # characters; the longest real line is "Max loss then: Rs 14,45,535.00 (worst case: NIFTY at zero)." (59)
THREE = 3
BOOK_ORDERS = 4  # the four legs of the book, nothing added by a read
FIGURES = 2  # the "Rs" of the now line and of the then line


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def test_a_bare_put_gives_three_short_lines_and_names_the_figure_a_worst_case(db):
    app, stored, ids = await _book(db)
    reply = await _ask(app, stored.id, ids[LONG_PUT], "5.00")
    assert reply.status_code == HTTPStatus.OK, reply.text
    lines = reply.json()["warning_lines"]
    assert len(lines) == THREE
    assert all(len(line) <= MAX_LINE for line in lines), [len(line) for line in lines]
    assert all("\n" not in line for line in lines)  # each fact on its own line
    assert lines[0].endswith("is left without protection.")
    assert lines[1] == "Max loss now: Rs 2,860.00."
    assert lines[2] == "Max loss then: Rs 14,45,535.00 (worst case: NIFTY at zero)."
    assert "becomes" not in " ".join(lines)  # the old one-sentence form is gone for a bare option


async def test_the_old_sentence_form_never_carries_the_bare_put_figure(db):
    """The 27 Nov 09:34 form was one sentence with the figure and no case; it must not come back in warning_text."""
    app, stored, ids = await _book(db)
    body = (await _ask(app, stored.id, ids[LONG_PUT], "5.00")).json()
    assert body["warning_text"] == "\n".join(body["warning_lines"])
    assert "max loss becomes" not in body["warning_text"]
    assert body["warning_text"].count("Rs") == FIGURES  # now, then: nothing else


async def test_a_bare_call_prints_no_amount_at_all_only_the_case(db):
    app, stored, ids = await _book(db)
    lines = (await _ask(app, stored.id, ids[LONG_CALL], "5.00")).json()["warning_lines"]
    assert len(lines) == THREE and all(len(line) <= MAX_LINE for line in lines)
    assert lines[2] == "Max loss then: no upper limit (worst case: NIFTY keeps rising)."
    assert "Rs" not in lines[2]


@pytest.mark.parametrize("level", ["0.05", "5.00", "20.00", "33.95"])
async def test_every_level_on_the_long_put_keeps_the_shape_and_the_label(db, level):
    """Whatever the level, a figure that is the index-at-zero loss carries the words that say so."""
    app, stored, ids = await _book(db)
    lines = (await _ask(app, stored.id, ids[LONG_PUT], level)).json()["warning_lines"]
    assert len(lines) == THREE and all(len(line) <= MAX_LINE for line in lines)
    assert lines[2].startswith("Max loss then: Rs ")
    assert lines[2].endswith("(worst case: NIFTY at zero).")


@pytest.mark.parametrize("leg", [SHORT_CALL, SHORT_PUT])
async def test_a_stop_that_leaves_nothing_bare_has_no_lines_and_no_worst_case_words(db, leg):
    app, stored, ids = await _book(db)
    body = (await _ask(app, stored.id, ids[leg], "100.00")).json()
    assert body["warning_lines"] is None
    assert "worst case" not in (body["warning_text"] or "")
    assert await _orders(db, stored.id) == BOOK_ORDERS  # read only
