"""REQ-163 AC-1..AC-3: ofo.engine.adjust_history on scenario ADJ-13 laid out as scripts/seed_scenario.py places it.

Expected figures are the scenario generator's engine-free values in tests/fixtures/adjust_scenarios/ADJ-13.json
(position.booked_pnl 962, the history legs' booked -1176.5 / 2138.5, credit_received 5141.50, expected.premium_left
7156.50, expected.pnl_now -2015 at broker.quote's last prices), never a value read back from the code under test.
"""
from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
from decimal import Decimal

import pytest
from ofo.engine.adjust_history import HistoryOrder, adjustment_history
from ofo.errors.explanations import render_explanation

FIXTURE = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "adjust_scenarios" / "ADJ-13.json"
DOC = json.loads(FIXTURE.read_text(encoding="utf-8"), parse_float=Decimal)
POS = DOC["position"]
CLOCK = datetime.datetime.fromisoformat(POS["entry"]["clock"])
HOUR = datetime.timedelta(hours=1)
ADJ_1_AT = datetime.datetime.fromisoformat(POS["adjustment_times"]["1"])
_spec = importlib.util.spec_from_file_location(
    "seed_scenario", pathlib.Path(__file__).resolve().parents[2] / "scripts" / "seed_scenario.py")
SEED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SEED)


def _sym(leg: dict) -> str:
    return f"{leg['type']}{leg['strike']}"


def seeded_orders() -> list[HistoryOrder]:
    """ADJ-13 placed by scripts/seed_scenario.py's own ``placement_batches``: entry batch, then adjustment 1."""
    return [HistoryOrder(_sym(leg), side, leg["quantity"], Decimal(price), kind, at)
            for at, batch in SEED.placement_batches(POS, CLOCK) for side, leg, price, kind in batch]


def live_prices() -> dict[str, Decimal]:
    by_symbol = {leg["tradingsymbol"]: _sym(leg) for leg in POS["legs"]}
    return {by_symbol[q["tradingsymbol"]]: Decimal(str(q["last_price"])).quantize(Decimal("0.01"))
            for q in DOC["broker"]["quote"]["legs"]}


def test_adj13_rows_and_totals_to_the_paisa():  # AC-1, AC-2, attack 1 and 5
    h = adjustment_history(seeded_orders(), live_prices(), adjustments_max=2)
    assert [r.step for r in h.rows] == ["entry", "adjustment"]
    assert [r.at for r in h.rows] == [CLOCK, ADJ_1_AT]
    entry, adj = h.rows
    assert entry.booked == Decimal("0")
    assert adj.booked == Decimal("-1176.50") + Decimal("2138.50") == Decimal("962.00") == Decimal(POS["booked_pnl"])
    assert sum(Decimal(x["booked"]) for x in POS["history"]) == adj.booked
    # entry: put spread 22400/22600 (+1202.50) and call spread 23450/23650 (+2782.00); adjustment: close the put
    # spread (-240.50) and open 22700/22900 (+1397.50); engine-free arithmetic on the fixture's prices
    assert entry.cash == Decimal("3984.50") and adj.cash == Decimal("1157.00")
    t = h.totals
    assert t.booked == sum(r.booked for r in h.rows) == Decimal("962.00")
    assert t.credit == sum(r.cash for r in h.rows) == Decimal(POS["credit_received"]) == Decimal("5141.50")
    assert t.premium_left == Decimal(DOC["expected"]["premium_left"]) == Decimal("7156.50")
    assert t.pnl == Decimal(DOC["expected"]["pnl_now"]) == Decimal("-2015")
    assert t.open_pnl == Decimal("-2977.00") and t.pnl == t.booked + t.open_pnl
    assert (t.adjustments_used, t.adjustments_max) == (POS["adjustments_used"], 2) == (1, 2)
    assert all(r.fill == "paper" and r.rule_id is None for r in h.rows)
    assert t.charges is None  # no per-order charges given


def test_off_by_one_paisa_in_an_exit_fails_the_expected_booked():  # attack 1
    orders = seeded_orders()
    orders[4] = HistoryOrder(orders[4].instrument_id, orders[4].side, orders[4].quantity,
                             orders[4].price + Decimal("0.01"), "exit", orders[4].placed_at)
    assert adjustment_history(orders, live_prices(), adjustments_max=2).totals.booked != Decimal("962.00")


def test_no_history_is_an_entry_row_only():
    legs = [o for o in seeded_orders() if o.placed_at == CLOCK]
    h = adjustment_history(legs, {}, adjustments_max=None)
    assert [r.step for r in h.rows] == ["entry"]
    assert h.totals.booked == 0 and h.totals.adjustments_used == 0 and h.totals.adjustments_max is None
    assert h.totals.credit == Decimal("3984.50")


def test_settle_is_its_own_row_labelled_by_kind():
    t0 = CLOCK
    orders = [HistoryOrder("PE22900", "SELL", 130, Decimal("16.85"), "open", t0),
              HistoryOrder("PE22900", "BUY", 130, Decimal("0"), "settle", t0 + 3 * HOUR)]
    h = adjustment_history(orders, {}, adjustments_max=2)
    assert [r.step for r in h.rows] == ["entry", "settle"]
    assert h.rows[1].booked == Decimal("2190.50")  # (16.85 - 0) x 130, engine-free
    assert h.totals.adjustments_used == 0 and h.totals.open_pnl == 0 and h.totals.premium_left == 0


def test_unconfirmed_adjustment_is_pending_and_out_of_the_totals():  # AC-3, attack 2
    orders = [HistoryOrder(o.instrument_id, o.side, o.quantity, o.price, o.kind, o.placed_at,
                           "unconfirmed" if o.placed_at == ADJ_1_AT else "paper") for o in seeded_orders()]
    h = adjustment_history(orders, {"PE22400": Decimal("1.40"), "PE22600": Decimal("3.25"),
                                    "CE23450": Decimal("60.00"), "CE23650": Decimal("22.25")}, adjustments_max=2)
    pending = h.rows[1]
    assert pending.fill == "unconfirmed" and pending.booked is None
    assert h.totals.booked == 0 and h.totals.credit == Decimal("3984.50") and h.totals.adjustments_used == 0


def test_failed_beats_unconfirmed_in_one_row():
    t = CLOCK
    orders = [HistoryOrder("A", "SELL", 65, Decimal("10.00"), "open", t, "failed"),
              HistoryOrder("B", "BUY", 65, Decimal("5.00"), "open", t, "unconfirmed")]
    h = adjustment_history(orders, {}, adjustments_max=None)
    assert h.rows[0].fill == "failed" and h.totals.booked == 0 and h.totals.credit == 0


def test_missing_price_keeps_booked_and_nulls_open():  # attack 3
    prices = live_prices()
    prices.pop(next(iter(prices)))
    t = adjustment_history(seeded_orders(), prices, adjustments_max=2).totals
    assert t.booked == Decimal("962.00")
    assert t.open_pnl is None and t.pnl is None and t.premium_left is None


@pytest.mark.parametrize("bad", [10.45, "10.45", 10])
def test_a_float_price_raises(bad):  # attack 4
    with pytest.raises(ValueError):
        HistoryOrder("A", "BUY", 65, bad, "open", CLOCK)  # type: ignore[arg-type]


def test_a_float_live_price_or_charge_raises():  # attack 4
    with pytest.raises(ValueError):
        adjustment_history(seeded_orders(), {"PE22700": 12.15}, adjustments_max=2)  # type: ignore[dict-item]
    with pytest.raises(ValueError):
        adjustment_history(seeded_orders(), live_prices(), adjustments_max=2,
                           per_order_charges=[0.5] * 8)  # type: ignore[list-item]


def test_charges_total_is_the_sum_of_rows():
    per = [Decimal("1.25")] * 8
    h = adjustment_history(seeded_orders(), live_prices(), adjustments_max=2, per_order_charges=per)
    assert [r.charges for r in h.rows] == [Decimal("5.00"), Decimal("5.00")]
    assert h.totals.charges == Decimal("10.00")


def test_suggestion_link_present_names_the_rule():
    t = CLOCK
    orders = [HistoryOrder("A", "SELL", 65, Decimal("10.00"), "open", t),
              HistoryOrder("A", "BUY", 65, Decimal("4.00"), "exit", t + HOUR, rule_id="R-02")]
    h = adjustment_history(orders, {}, adjustments_max=1)
    assert h.rows[0].rule_id is None and h.rows[1].rule_id == "R-02"
    assert h.rows[1].booked == Decimal("390.00")  # (10 - 4) x 65


def test_no_orders_raises():
    with pytest.raises(ValueError):
        adjustment_history([], {}, adjustments_max=None)


def test_words_are_exact():
    assert render_explanation("adjust_history_paper_fill") == "Paper - not sent to Zerodha"
    assert render_explanation("adjust_history_own_change") == "Your own change"
    assert render_explanation("adjust_history_pending") == "pending"


def test_ids_out_of_time_order_still_group_by_placed_at():
    """Batches are every order of one placed_at, whatever the id order (measured: an earlier seed interleaved them)."""
    o = seeded_orders()
    interleaved = [o[0], o[4], o[1], o[5], o[2], o[6], o[3], o[7]]
    h = adjustment_history(interleaved, live_prices(), adjustments_max=2)
    assert [r.step for r in h.rows] == ["entry", "adjustment"]
    assert h.rows[1].booked == Decimal("962.00") and h.totals.credit == Decimal("5141.50")
