"""Lane L (27 Nov, T1-15 / items 1 and 3; ADR-330 (15), (35), ADR-324 (1) to (3), ADR-008).

The Paper total (Home, Positions) is ONE function of the list's rows: ``_priced`` picks the set, ``_totals`` sums
it. These tests
run the two on plain row dicts (no database) and name the set each total reads:

  total  = sum over rows that are NOT expired-open and CAN be priced (a settled/closed row counts at its booked result);
  line 1 = "N closed strategies" counted over EVERY row of the list (the rows shown with Show closed on);
  line 2 = the rows left out (expired or unpriced, a settling trade is unpriced), counted, never summed.
"""

from __future__ import annotations

from decimal import Decimal as D

from ofo.tracking import paper_decay
from ofo_app.routes.paper import _closed_text, _left_out_text, _priced, _totals

_DECAY = paper_decay.Decay(D(0), None)


def _row(booked: str, unbooked: str | None, open_count: int, state: str = "LIVE") -> dict:
    """One list row as the route builds it, only the keys the totals read."""
    total = None if unbooked is None else D(booked) + D(unbooked)
    why = None if total is not None else "prices_not_live"
    after = None if unbooked is None else D(unbooked)
    return {
        "booked": D(booked),
        "unbooked": after,
        "total": total,
        "total_after": total,
        "charges_paid": D(0),
        "charges_to_close": D(0),
        "after_charges_reason": why,
        "unbooked_after": after,
        "booked_after": D(booked),
        "booked_after_reason": None,
        "charges": D(0),
        "charges_reason": None,
        "open_count": open_count,
        "state": state,
        "as_of": None,
        "pause_reason": None,
    }


def _list_totals(rows: list[dict], expired: int = 0) -> dict:
    kept = _priced(list(range(len(rows))), rows, booked_alone=True)
    closed = sum(1 for s in rows if s["open_count"] == 0 or s["state"] == "EXITED")
    return _totals([rows[i] for i in kept], [_DECAY for _ in kept], expired, len(rows) - len(kept), closed)


RUNNING = lambda: _row("10", "5", 2)  # noqa: E731 - priced, open
SETTLED = lambda: _row("40", "0", 0, "EXITED")  # noqa: E731 - booked result, no open leg
SETTLING = lambda: _row("0", None, 1, "PAUSED")  # noqa: E731 - expiry passed, awaiting settlement: no price


def test_core_the_total_reads_priced_and_settled_rows_only_and_counts_the_rest():
    """CORE (item 1): running +15, settled +40, settling (no price): total 55 over the first two."""
    got = _list_totals([RUNNING(), SETTLED(), SETTLING()])
    assert got["total"] == D("55") and got["booked"] == D("50") and got["unbooked"] == D("5")
    assert (got["left_out_count"], got["closed_count"]) == (1, 1)


def test_line_states_none_left_out():
    got = _list_totals([RUNNING(), SETTLED()])
    assert (got["left_out_count"], got["left_out_text"]) == (0, None)
    assert (got["closed_count"], got["closed_text"]) == (1, "Includes 1 closed strategy.")


def test_line_states_one_left_out_unpriced():
    got = _list_totals([RUNNING(), _row("0", None, 1, "PAUSED")])
    assert got["total"] == D("15")
    assert (got["left_out_count"], got["left_out_text"]) == (1, "1 strategy left out: its price is not live.")
    assert (got["closed_count"], got["closed_text"]) == (0, None)


def test_line_states_one_settling_is_left_out_and_counted_not_summed():
    got = _list_totals([RUNNING(), SETTLED(), SETTLING()])
    assert got["total"] == D("55")  # the settling trade adds nothing
    assert got["left_out_text"] == "1 strategy left out: its price is not live."
    assert got["closed_text"] == "Includes 1 closed strategy."


def test_line_states_expired_and_unpriced_together_and_plural_closed():
    got = _list_totals([RUNNING(), SETTLED(), SETTLED(), SETTLING()], expired=1)
    assert got["left_out_text"] == "2 strategies left out: their contracts have expired or their prices are not live."
    assert got["closed_text"] == "Includes 2 closed strategies."


def test_line_states_nothing_can_be_priced_keeps_the_blank_total_with_its_reason():
    """ADR-324 (3) / (35): no running trade can be priced: no total at all (settled ones are not shown alone)."""
    got = _list_totals([SETTLING(), SETTLING()])
    assert got["total"] is None and got["total_text"] is None
    assert got["totals_reason"] == "prices_not_live"
    assert got["left_out_count"] == 0  # every member is kept so the blank total names the reason


def test_the_line_texts_are_the_catalogue_sentences():
    assert _closed_text(0) is None and _closed_text(1) == "Includes 1 closed strategy."
    assert _left_out_text(0, 0) is None


def test_item4_after_close_settled_results_with_only_unpriced_running_trades_show_the_booked_result():
    """ADR-330 (62) (27 Nov evening, owner): no running trade can be priced but a settled trade has a booked result: the
    total is that booked result (+40), with the closed line and the (35) count line; the settling trade is left out."""
    got = _list_totals([SETTLED(), SETTLING()])
    assert got["total"] == D("40") and got["booked"] == D("40")
    assert (got["left_out_count"], got["left_out_text"]) == (1, "1 strategy left out: its price is not live.")
    assert (got["closed_count"], got["closed_text"]) == (1, "Includes 1 closed strategy.")


def test_item4_many_unpriced_running_trades_are_counted_in_the_line():
    got = _list_totals([SETTLED()] + [SETTLING() for _ in range(9)])
    assert got["total"] == D("40")
    assert got["left_out_text"] == "9 strategies left out: their prices are not live."


def test_item4_neither_a_priced_trade_nor_a_booked_result_stays_blank_with_its_reason():
    got = _list_totals([SETTLING()])
    assert got["total"] is None and got["totals_reason"] == "prices_not_live"


def test_item4_the_today_total_keeps_its_own_rule_no_running_trade_priced_is_blank():
    """Opus review F1: the Today block (D-68) has no left-out line on screen, so (62) is the header's only: a closed
    trade
    alone does not make Today a figure while a trade opened today has no price."""
    rows = [SETTLED(), SETTLING()]
    assert _priced([0, 1], rows) == [0, 1]  # every member kept: the figure is blank with its reason
    assert _priced([0, 1], rows, booked_alone=True) == [0]
