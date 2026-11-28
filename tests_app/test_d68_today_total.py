"""D-68 (ADR-320 point 6, GC-ICLIVE-E): the Positions header gets a "Today" total for the trades opened or closed today,
leaving out scenario strategies; "today" is the current day in IST; the figure follows the paused rule of REQ-109 AC-5.

Real case: N-6 (condors C9 164, all): the header Booked P&L +7,496.11 (14:47) against the T1123 completed nets of
-7,783.16 (9 rows): it took in old Scenario PATH-xx trades and the booked parts of trades still open. No real strategy
rows are in a fixture, so the rule is driven on the route's own pure functions with the real shape of the figures.

Rule for a trade opened on an earlier day: it counts only if it was CLOSED today ("opened or closed today"); a
trade opened yesterday and still open, and one closed yesterday, are out. The sum is ``paper._totals`` (the
function the header's own totals use), so there is one reader and the sum is exact decimal; a paused
strategy pauses the figure (never partial).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

from ofo.tracking import paper_decay
from ofo_app.routes import paper

UTC = datetime.UTC
NOW = datetime.datetime(2026, 11, 25, 9, 20, tzinfo=UTC)  # 25 Nov 2026, 14:50 IST


def _s(total_after: str | None, unbooked: str | None = "10.00", reason: str | None = None) -> dict:
    """One strategy's figures in the shape the list builds (the fields ``_totals`` reads)."""
    after = None if total_after is None else D(total_after)
    return {"booked": D("5.00"), "unbooked": None if unbooked is None else D(unbooked), "pause_reason": reason,
            "charges": D("1.00"), "charges_reason": None, "total": None if after is None else after + D("3.00"),
            "total_after": after, "charges_paid": D("2.00"), "charges_to_close": D("1.00"),
            "after_charges_reason": None if after is not None else "prices_not_live",
            "booked_after": D("3.00"), "unbooked_after": D("9.00"), "as_of": None}


def _item(figures: dict, opened: datetime.datetime, closed: datetime.datetime | None = None,
          scenario: str | None = None):
    return paper.TodayItem(figures, paper_decay.Decay(D(0), None), opened, closed, scenario)


def _at(day: int, hour: int = 4, minute: int = 0) -> datetime.datetime:
    return datetime.datetime(2026, 11, day, hour, minute, tzinfo=UTC)


def today(items):
    return paper.today_totals(items, NOW.astimezone(paper.IST).date())


def test_value_the_total_is_the_exact_sum_of_the_trades_opened_today():
    got = today([_item(_s("100.10"), _at(25)), _item(_s("-30.05"), _at(25, 5))])
    assert (got["count"], got["total_after"], got["total_after_text"]) == (2, D("70.05"), "+70.05")
    assert got["empty_text"] is None


def test_a_scenario_strategy_is_left_out():
    got = today([_item(_s("100.10"), _at(25)), _item(_s("999.99"), _at(25), scenario="PATH-07")])
    assert (got["count"], got["total_after"]) == (1, D("100.10"))


def test_opened_yesterday_and_still_open_is_left_out():
    got = today([_item(_s("100.10"), _at(25)), _item(_s("500.00"), _at(24))])
    assert (got["count"], got["total_after"]) == (1, D("100.10"))


def test_closed_yesterday_is_left_out_and_opened_yesterday_closed_today_counts():
    got = today([_item(_s("40.00"), _at(23), closed=_at(24, 6)),  # closed yesterday: out
                 _item(_s("7.50"), _at(24, 6), closed=_at(25, 5))])  # opened yesterday, closed today: in
    assert (got["count"], got["total_after"]) == (1, D("7.50"))


def test_the_ist_day_boundary_not_the_utc_day():
    # 24 Nov 23:50 UTC is 25 Nov 05:20 IST: today. 24 Nov 18:00 UTC is 24 Nov 23:30 IST: yesterday.
    # 25 Nov 18:40 UTC is 26 Nov 00:10 IST: tomorrow
    got = today([_item(_s("1.00"), _at(24, 23, 50)), _item(_s("2.00"), _at(24, 18, 0)),
                 _item(_s("4.00"), _at(25, 18, 40))])
    assert (got["count"], got["total_after"]) == (1, D("1.00"))


def test_paused_one_trade_without_a_live_price_pauses_the_figure_with_the_reason_never_a_partial_sum():
    items = [_item(_s("100.10"), _at(25)), _item(_s(None, unbooked=None, reason="prices_not_live"), _at(25, 5))]
    got = today(items)
    assert got["count"] == len(items)
    assert (got["total"], got["total_after"], got["totals_reason"]) == (None, None, "prices_not_live")
    assert got["after_charges_reason"] == "prices_not_live"


def test_nothing_today_says_so_and_is_not_a_zero_figure():
    got = today([_item(_s("100.10"), _at(24)), _item(_s("1.00"), _at(25), scenario="PATH-01")])
    assert got["count"] == 0 and got["empty_text"] == "No trades opened or closed today."
    assert today([])["count"] == 0


class _Snap:
    def __init__(self, valuation):
        self.valuation = valuation


def test_the_day_is_the_trading_day_of_the_snapshot_so_a_saturday_answer_shows_fridays_trades():
    saturday = datetime.datetime(2026, 11, 28, 6, 0, tzinfo=UTC)  # Sat 28 Nov, 11:30 IST
    friday_close = datetime.datetime(2026, 11, 27, 10, 0, tzinfo=UTC)  # the last quote: Fri 27 Nov 15:30 IST
    day = paper.today_day([_Snap(friday_close), None], saturday)
    assert day == datetime.date(2026, 11, 27)
    got = paper.today_totals([_item(_s("12.00"), _at(27, 5)), _item(_s("1.00"), _at(26, 5))], day)
    assert (got["count"], got["total_after"]) == (1, D("12.00"))


def test_a_weekday_answer_is_unchanged_and_no_snapshot_falls_back_to_the_answers_own_india_date():
    live = datetime.datetime(2026, 11, 25, 9, 0, tzinfo=UTC)
    assert paper.today_day([_Snap(live)], NOW) == datetime.date(2026, 11, 25)
    assert paper.today_day([None], NOW) == datetime.date(2026, 11, 25)
    assert paper.today_day([], NOW) == datetime.date(2026, 11, 25)
