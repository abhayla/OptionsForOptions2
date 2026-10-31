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
    assert h.totals.adjustments_used == 0 and h.totals.open_pnl == 0
    assert h.totals.premium_left is None and h.totals.premium_reason == "no_option_leg"


def test_unconfirmed_adjustment_is_pending_and_out_of_the_totals():  # AC-3, attack 2
    orders = [HistoryOrder(o.instrument_id, o.side, o.quantity, o.price, o.kind, o.placed_at,
                           "unconfirmed" if o.placed_at == ADJ_1_AT else "paper") for o in seeded_orders()]
    h = adjustment_history(orders, {"PE22400": Decimal("1.40"), "PE22600": Decimal("3.25"),
                                    "CE23450": Decimal("60.00"), "CE23650": Decimal("22.25")}, adjustments_max=2)
    pending = h.rows[1]
    assert pending.fill == "unconfirmed" and pending.booked is None
    assert h.totals.booked == 0 and h.totals.credit == Decimal("3984.50") and h.totals.adjustments_used == 0
    assert (h.totals.open_pnl, h.totals.pnl, h.totals.premium_left) == (None, None, None)
    assert (h.totals.open_reason, h.totals.premium_reason) == ("pending", "pending")


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


# ---- review round (Opus money review): futures, debit books, pending, input refusals, batch order -------------------

def _scenario_orders(doc: dict) -> list[HistoryOrder]:
    pos = doc["position"]
    clock = datetime.datetime.fromisoformat(pos["entry"]["clock"])
    return [HistoryOrder(leg.get("tradingsymbol") or f"{leg['type']}{leg['strike']}{leg['expiry']}", side,
                         int(leg["quantity"]), Decimal(price), kind, at,
                         is_option=leg["type"] != "FUT")
            for at, batch in SEED.placement_batches(pos, clock) for side, leg, price, kind in batch]


def test_every_library_scenario_matches_the_generators_credit_and_premium_left():
    """tests/adjust_scenarios_gen.py: credit_received = the option legs' cash (open_cash + hist_cash, futures out);
    premium_left = the open option legs' value, None for a debit (net long premium) book. 44 of 44 agree."""
    checked, bad, negative = 0, {}, []
    for path in sorted(FIXTURE.parent.glob("ADJ-*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
        quotes = {q["tradingsymbol"]: Decimal(str(q["last_price"])).quantize(Decimal("0.01"))
                  for q in (doc.get("broker", {}).get("quote") or {}).get("legs", [])
                  if q.get("last_price") is not None}
        t = adjustment_history(_scenario_orders(doc), quotes, adjustments_max=None).totals
        want_credit = Decimal(str(doc["position"]["credit_received"]))
        left = doc["expected"].get("premium_left")
        want_left = None if left is None else Decimal(str(left))
        if want_left is not None and want_left < 0:  # the generator prints a negative figure for a short family
            want_left = None  # whose options are net long (ADJ-37, ADJ-38); the product rule shows none (review 2)
            negative.append((doc["id"], t.premium_reason))
        if t.credit != want_credit or t.premium_left != want_left:
            bad[doc["id"]] = (t.credit, want_credit, t.premium_left, want_left)
        checked += 1
    assert (checked, bad) == (44, {})
    assert negative == [("ADJ-37", "net_long_premium"), ("ADJ-38", "net_long_premium")]


def test_a_future_is_not_premium():
    orders = [HistoryOrder("FUT", "BUY", 65, Decimal("23000.00"), "open", CLOCK, is_option=False),
              HistoryOrder("CE23500", "SELL", 65, Decimal("120.00"), "open", CLOCK)]
    t = adjustment_history(orders, {"FUT": Decimal("23050.00"), "CE23500": Decimal("100.00")},
                           adjustments_max=None).totals
    assert t.credit == Decimal("7800.00") and t.premium_left == Decimal("6500.00")  # 120 x 65, 100 x 65
    assert t.open_pnl == Decimal("3250.00") + Decimal("1300.00")  # the future 50 x 65 + the short call 20 x 65


def test_a_futures_only_book_has_no_premium():
    orders = [HistoryOrder("FUT", "BUY", 65, Decimal("23000.00"), "open", CLOCK, is_option=False)]
    t = adjustment_history(orders, {"FUT": Decimal("23050.00")}, adjustments_max=None).totals
    assert t.credit == 0 and t.premium_left is None and t.premium_reason == "no_option_leg"


def test_a_debit_book_has_no_premium_left_to_earn():
    orders = [HistoryOrder("CE23000", "BUY", 65, Decimal("150.00"), "open", CLOCK)]
    t = adjustment_history(orders, {"CE23000": Decimal("140.00")}, adjustments_max=None).totals
    assert t.credit == Decimal("-9750.00") and t.premium_left is None and t.premium_reason == "net_long_premium"


def test_a_confirmed_row_after_a_pending_row_on_the_same_contract_keeps_the_totals_pending():
    orders = [HistoryOrder("PE1", "SELL", 65, Decimal("20.00"), "open", CLOCK, "confirmed"),
              HistoryOrder("PE1", "BUY", 65, Decimal("10.00"), "exit", CLOCK + HOUR, "unconfirmed"),
              HistoryOrder("PE1", "BUY", 65, Decimal("12.00"), "open", CLOCK + 2 * HOUR, "confirmed")]
    t = adjustment_history(orders, {"PE1": Decimal("11.00")}, adjustments_max=None).totals
    assert (t.open_pnl, t.pnl, t.premium_left) == (None, None, None)
    assert (t.open_reason, t.premium_reason) == ("pending", "pending")


def test_exits_apply_before_opens_inside_one_batch():
    """The batch's add (listed first) does not change the average its exit books at: (20 - 10) x 65."""
    t1 = CLOCK + HOUR
    orders = [HistoryOrder("PE1", "SELL", 65, Decimal("20.00"), "open", CLOCK),
              HistoryOrder("PE1", "SELL", 65, Decimal("30.00"), "add", t1),
              HistoryOrder("PE1", "BUY", 65, Decimal("10.00"), "exit", t1)]
    h = adjustment_history(orders, {"PE1": Decimal("10.00")}, adjustments_max=None)
    assert h.rows[1].booked == Decimal("650.00")


@pytest.mark.parametrize("placed_at", [None, "2026-10-28T10:00:00+05:30"])
def test_placed_at_must_be_a_datetime(placed_at):
    with pytest.raises(ValueError, match="placed_at"):
        HistoryOrder("A", "BUY", 65, Decimal("1.00"), "open", placed_at)  # type: ignore[arg-type]


def test_mixed_naive_and_aware_times_are_refused():
    orders = [HistoryOrder("A", "BUY", 65, Decimal("1.00"), "open", CLOCK),
              HistoryOrder("A", "SELL", 65, Decimal("1.00"), "exit", CLOCK.replace(tzinfo=None) + HOUR)]
    with pytest.raises(ValueError, match="naive"):
        adjustment_history(orders, {}, adjustments_max=None)


@pytest.mark.parametrize("price", [None, Decimal("0"), Decimal("-1.00")])
def test_a_live_price_none_or_not_above_zero_is_refused(price):
    with pytest.raises(ValueError, match="live_prices"):
        adjustment_history(seeded_orders(), {"PE22700": price}, adjustments_max=None)  # type: ignore[dict-item]
