"""ADR-330 (60): the Exit dialog's market-closed answer, from the ONE market-state answer (calendar behind it),
whether the feed process runs or not. Spec basis: ADR-330 (60), ADR-212, ADR-119. No database. Answer states: open
(no sentence), closed with a day named, closed past the calendar's data (sentence without a day), no context (calendar
answer, fail closed)."""
from __future__ import annotations

import datetime
import importlib
import time
from decimal import Decimal
from http import HTTPStatus

import pytest
from httpx import ASGITransport, AsyncClient
from ofo.errors.explanations import EXPLANATIONS, ClockHmsOrDated, DayMonth, EarlierDay, TargetValue
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


def test_day_label_does_not_follow_the_host_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """#875: strftime follows the host locale; with every strftime answering in German the sentence stays English."""
    def _german(fmt: str, *args: object) -> str:
        return fmt.replace("%A", "Montag").replace("%b", "Nov.").replace("%d", "30")

    monkeypatch.setattr(time, "strftime", _german)
    _, sentence, _ = exit_market_answer(_ctx(FRIDAY_1602), FRIDAY_1602)
    assert str(sentence) == "The market is closed. Exits can be placed from 09:15 on Monday 30 Nov."


def test_dated_slots_do_not_follow_the_host_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """#875 class: the other three dated slots also keep English month names when every strftime answers in German."""
    real = time.strftime

    def _german(fmt: str, *args: object) -> str:
        return real(fmt.replace("%b", "Dez."), *args)  # type: ignore[arg-type]

    monkeypatch.setattr(time, "strftime", _german)
    at = datetime.datetime(2026, 11, 8, 15, 29, 59, tzinfo=IST)
    assert DayMonth.format(datetime.date(2026, 11, 24)) == "24 Nov"
    assert TargetValue.format(at) == "8 Nov, 15:29 IST"
    assert ClockHmsOrDated.format(EarlierDay(at)) == "8 Nov, 15:29:59"


def test_expiry_kind_unknown_pause_has_its_catalogue_sentence() -> None:
    """FD2 hand-over: the Monitoring paused reason for an unknown expiry kind is one catalogue sentence."""
    assert EXPLANATIONS["monitoring_why_expiry_kind_unknown"].text == (
        "Every exit rule is not checked because whether this trade expires weekly or monthly is not known.")


def test_expiry_kind_unknown_trigger_reason_text() -> None:
    """Coordinator 28 Nov: the trigger reason for an unknown expiry type says what is not known."""
    from ofo.errors import CATALOGUE  # noqa: PLC0415

    assert CATALOGUE["adjust_trigger_expiry_kind_unknown"].what_happened == (
        "Not checked: this trade's expiry type (weekly or monthly) is not known, so the percent stop has no value.")


def test_a_fired_leg_stop_has_past_tense_sentences() -> None:
    """UX-A03 (28 Nov): a stop that has fired says what fired, at which level and the figure at firing, then when the
    check saw it (stop_fired_at); never "If this stop fires". Keys for Lane FE2: paper_leg_stop_fired*."""
    r = importlib.import_module("ofo.errors.explanations").render_explanation
    strike = r("strike_part", strike="25400")
    leg = r("contract_display", underlying="NIFTY", day=1, month="Dec", strike=strike, instrument="PE")
    loss = r("paper_leg_stop_fired", leg=leg, level=Decimal("124.50"), figure=Decimal("5300"))
    assert loss == "Stop fired: NIFTY 1 Dec 25400 PE reached 124.50; max loss at that point Rs 5,300.00"
    assert r("paper_leg_stop_fired_unlimited", leg=leg, level=Decimal("124.50")) == (
        "Stop fired: NIFTY 1 Dec 25400 PE reached 124.50; there was no fixed maximum loss at that point")
    assert r("paper_leg_stop_fired_unknown", leg=leg, level=Decimal("124.50")) == (
        "Stop fired: NIFTY 1 Dec 25400 PE reached 124.50; the maximum loss at that point was not worked out")
    seen = datetime.datetime(2026, 11, 27, 12, 58, tzinfo=IST)
    assert r("stop_fired_at", line=loss, time=seen) == f"{loss}; seen by the check at 12:58 IST"
    assert "If this stop fires" not in loss
