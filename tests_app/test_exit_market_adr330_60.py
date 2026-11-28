"""ADR-330 (60): the Exit dialog's market-closed answer, from the ONE market-state answer (calendar behind it),
whether the feed process runs or not. Spec basis: ADR-330 (60), ADR-212, ADR-119. No database. Answer states: open
(no sentence), closed with a day named, closed past the calendar's data (sentence without a day), no context (calendar
answer, fail closed)."""
from __future__ import annotations

import datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.market_calendar import is_market_open
from ofo.marketdata.kite_provider import IST
from ofo_app.exit_market import exit_market_answer
from ofo_app.main import create_app
from ofo_app.routes.outcome import MarketContext, get_answer_clock, get_market_context

SATURDAY_1602 = datetime.datetime(2026, 11, 28, 16, 2, tzinfo=IST)  # a Saturday: the next open is Monday 30 Nov 09:15
FRIDAY_1602 = datetime.datetime(2026, 11, 27, 16, 2, tzinfo=IST)  # the real case: 27 Nov 16:02, after the close
WEDNESDAY_1000 = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=IST)  # open
PAST_CALENDAR = datetime.datetime(2031, 3, 5, 10, 0, tzinfo=IST)


class _Feed:  # a provider whose feed answers market_closed by the same calendar: "feed running"
    def market_closed(self, at: datetime.datetime) -> bool:
        return not is_market_open(at)


class _Provider:
    feed = _Feed()


def _ctx(at: datetime.datetime) -> MarketContext:
    return MarketContext(_Provider(), lambda: at, Decimal("0.065"))  # type: ignore[arg-type]


def test_closed_after_the_close_names_the_next_trading_day_with_a_feed() -> None:
    closed, sentence, opens = exit_market_answer(_ctx(FRIDAY_1602), FRIDAY_1602)
    assert closed is True
    assert str(sentence) == "The market is closed. Exits can be placed from 09:15 on Monday 30 Nov."
    assert opens == datetime.datetime(2026, 11, 30, 9, 15, tzinfo=IST)


def test_same_answer_with_no_feed_process() -> None:
    assert exit_market_answer(None, FRIDAY_1602)[:2] == exit_market_answer(_ctx(FRIDAY_1602), FRIDAY_1602)[:2]
    assert exit_market_answer(None, SATURDAY_1602)[0] is True


def test_open_market_has_no_sentence() -> None:
    assert exit_market_answer(_ctx(WEDNESDAY_1000), WEDNESDAY_1000) == (False, None, None)
    assert exit_market_answer(None, WEDNESDAY_1000) == (False, None, None)


def test_past_the_calendar_is_closed_with_no_day_never_a_guess() -> None:
    closed, sentence, opens = exit_market_answer(None, PAST_CALENDAR)
    assert closed is True
    assert str(sentence) == "The market is closed. Exits can be placed when it opens."
    assert opens is None


@pytest.mark.asyncio
async def test_route_answers_the_sentence() -> None:
    app = create_app()
    app.dependency_overrides[get_answer_clock] = lambda: (lambda: FRIDAY_1602)
    app.dependency_overrides[get_market_context] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/market/exit-state")
    assert r.status_code == HTTPStatus.OK
    body = r.json()
    assert body["closed"] is True
    assert body["sentence"] == "The market is closed. Exits can be placed from 09:15 on Monday 30 Nov."
    assert body["next_open_at"].startswith("2026-11-30T09:15:00")


# FD4 item 5: the same line for ENTRIES. The wording lives in the catalogue (Lane FC3's explanations.py, which FD4
# may not edit): the two templates are in RESULTS-lane-fd4.md "For the owner lane". Until they land the field is null.
ENTRIES_DAY = "Orders can be placed from 09:15 on Monday 30 Nov."
ENTRIES_NO_DAY = "Orders can be placed when it opens."


def _entries_template_landed() -> bool:
    from ofo.errors.explanations import render_explanation  # noqa: PLC0415
    try:
        render_explanation("exit_market_closed_entries", day=datetime.date(2026, 11, 30))
    except ValueError as exc:
        assert "unknown explanation template id" in str(exc)
        return False
    return True


@pytest.mark.asyncio
async def test_route_carries_entries_sentence_beside_sentence_for_the_same_day() -> None:
    app = create_app()
    app.dependency_overrides[get_answer_clock] = lambda: (lambda: FRIDAY_1602)
    app.dependency_overrides[get_market_context] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        body = (await ac.get("/api/market/exit-state")).json()
    assert "entries_sentence" in body
    assert body["sentence"] == "The market is closed. Exits can be placed from 09:15 on Monday 30 Nov."  # as before
    assert body["entries_sentence"] == (ENTRIES_DAY if _entries_template_landed() else None)  # never a guess


@pytest.mark.asyncio
async def test_entries_sentence_is_null_while_the_market_is_open() -> None:
    app = create_app()
    app.dependency_overrides[get_answer_clock] = lambda: (lambda: WEDNESDAY_1000)
    app.dependency_overrides[get_market_context] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        body = (await ac.get("/api/market/exit-state")).json()
    assert (body["closed"], body["sentence"], body["entries_sentence"]) == (False, None, None)


def test_entries_sentence_has_no_day_past_the_calendar_and_never_builds_text_here(monkeypatch) -> None:
    from ofo_app import exit_market  # noqa: PLC0415

    asked: list[tuple] = []

    def fake(template_id, **slots):
        asked.append((template_id, slots))
        return template_id
    monkeypatch.setattr(exit_market, "render_explanation", fake)
    assert exit_market.entries_sentence(None) == "exit_market_closed_entries_no_day"
    opens = datetime.datetime(2026, 11, 30, 9, 15, tzinfo=IST)
    assert exit_market.entries_sentence(opens) == "exit_market_closed_entries"
    assert asked == [("exit_market_closed_entries_no_day", {}),
                     ("exit_market_closed_entries", {"day": datetime.date(2026, 11, 30)})]  # the catalogue builds it

    def unknown(template_id, **_slots):
        raise ValueError(f"unknown explanation template id {template_id!r}")
    monkeypatch.setattr(exit_market, "render_explanation", unknown)
    assert exit_market.entries_sentence(opens) is None  # template not landed: null, never a guess

    def broken(template_id, **_slots):
        raise ValueError("explanation needs slots ['day'], got []")
    monkeypatch.setattr(exit_market, "render_explanation", broken)
    with pytest.raises(ValueError, match="needs slots"):
        exit_market.entries_sentence(opens)  # a real fault is never hidden as "not landed"
