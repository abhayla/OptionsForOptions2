"""#380-3: recovery actions on a partly executed or blocked strategy (ADR-136, ADR-137, Q223, Q238/#389).

Real input: the GC-3L round trip of 2026-10-19 (``orders-/positions-2026-10-19-roundtrip.json``, strategy 9). The
Iron Condor partial states are DERIVED from that real order row (same keys, values changed per case: symbol, side,
status, filled, tag), as the brief asks; the Iron Condor itself is ADR-136's own example (NIFTY 1 lot = 65; buys
22800 PE and 23600 CE fill, sell 23000 PE fills, sell 23400 CE rejected).
"""
from __future__ import annotations

import copy
import datetime
import json
from decimal import Decimal as D
from pathlib import Path

import pytest
from execution_inputs import EXPIRY, LOT, all_true_context, condor_legs
from ofo.engine import Action
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.execution.recovery import (
    TERMINAL_ORDER_STATUSES,
    MarginAnswer,
    RecoveryAction,
    RecoveryLeg,
    Refusal,
    Scope,
    ZerodhaOrder,
    ZerodhaRead,
    close_filled_legs,
    close_via_basket,
    missing_legs,
    offers,
    place_missing_legs,
    recovery_gate,
    use_zerodha_numbers,
)
from ofo.execution.safety import CheckCode

REPLIES = Path(__file__).resolve().parents[1] / "fixtures" / "kite_replies"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
NOW = datetime.datetime(2026, 10, 19, 11, 0, tzinfo=IST)
BUY, SELL = Action.BUY, Action.SELL
# The catalogue symbols of the Iron Condor legs at EXPIRY (tests/fixtures/instruments/instruments_slice.csv).
SYMBOLS = ("NIFTY26O0622800PE", "NIFTY26O0623000PE", "NIFTY26O0623400CE", "NIFTY26O0623600CE")
LOTS = dict.fromkeys(SYMBOLS, LOT)
ENOUGH = MarginAnswer(D("150000.00"), D("48210.75"))
STRATEGY = 9


def _rows(name: str) -> list[dict]:
    return json.loads((REPLIES / name).read_text(encoding="utf-8"))["data"]


REAL_ROW = _rows("orders-2026-10-19-roundtrip.json")[0]
REAL_CONTRACT = REAL_ROW["tradingsymbol"]  # the real 2026-10-19 contract, read from the reply
WING = "NIFTY26O0622900PE"


def row(symbol: str, side: str, status: str, filled: int, tag: str | None,  # noqa: PLR0913 - one per field
        quantity: int = LOT) -> ZerodhaOrder:
    """A derived reply row: the real 2026-10-19 row with the case's values, read back through the same fields."""
    r = copy.deepcopy(REAL_ROW)
    r.update(tradingsymbol=symbol, transaction_type=side, status=status, filled_quantity=filled, quantity=quantity,
             pending_quantity=quantity - filled, tag=tag)
    return from_kite(r)


def from_kite(r: dict) -> ZerodhaOrder:
    return ZerodhaOrder(r["tradingsymbol"], Action(r["transaction_type"]), r["status"], r["quantity"],
                        r["filled_quantity"], r["tag"])


def condor_plan(quantity: int = LOT) -> ExecutionPlan:
    return ExecutionPlan(str(STRATEGY), tuple(PlannedLeg(f"L{i}", s, leg) for i, (s, leg)
                                              in enumerate(zip(SYMBOLS, condor_legs(quantity), strict=True))))


def adr136_rows(fourth: str = "REJECTED") -> list[ZerodhaOrder]:
    return [row(SYMBOLS[0], "BUY", "COMPLETE", LOT, "OFS9V1L0"), row(SYMBOLS[3], "BUY", "COMPLETE", LOT, "OFS9V1L3"),
            row(SYMBOLS[1], "SELL", "COMPLETE", LOT, "OFS9V1L1"),
            row(SYMBOLS[2], "SELL", fourth, 0, "OFS9V1L2")]


HELD = {SYMBOLS[0]: LOT, SYMBOLS[1]: -LOT, SYMBOLS[3]: LOT}


def read(orders: list[ZerodhaOrder] | None, net: dict | None = None, at: datetime.datetime = NOW) -> ZerodhaRead:
    return ZerodhaRead(None if orders is None else tuple(orders), HELD if net is None else net, at)


def scope(blocked: bool = False, lots: dict | None = None) -> Scope:
    return Scope(STRATEGY, 1, LOTS if lots is None else lots, NOW, blocked)


def place(r: ZerodhaRead, margin: MarginAnswer = ENOUGH, plan: ExecutionPlan | None = None, blocked: bool = False):
    return place_missing_legs(plan or condor_plan(), r, margin, scope(blocked))


def close(r: ZerodhaRead, blocked: bool = False):
    return close_filled_legs(condor_plan(), r, scope(blocked))


def offered(r: ZerodhaRead, margin: MarginAnswer = ENOUGH, blocked: bool = False):
    return offers(condor_plan(), r, margin, scope(blocked))


# ---- 1. Place missing legs -----------------------------------------------------------------------------------------

def test_place_missing_legs_builds_only_the_rejected_sell_and_its_worst_case() -> None:
    """ADR-136 (1)/(4): one basket with only SELL 23400 CE 65 (planned 65 - filled 0); worst case after = the planned
    Iron Condor's max loss, by hand: credit 86.00 + 91.50 - 42.50 - 44.00 = 91.00 per unit, width 200 ->
    (200 - 91) x 65 = 7085.00."""
    out = place(read(adr136_rows()))
    assert out.refusal is None
    assert out.legs == (RecoveryLeg("L2", SYMBOLS[2], SELL, LOT),)
    assert abs(out.worst_case_after) == D("7085.00")


def test_place_missing_two_lot_part_fill_places_planned_minus_filled() -> None:
    """ADR-136 (1): quantity = planned minus filled in whole lots: 2 lots planned, 1 lot of the sell filled -> 65."""
    rows = [row(SYMBOLS[0], "BUY", "COMPLETE", 2 * LOT, "OFS9V1L0", 2 * LOT),
            row(SYMBOLS[3], "BUY", "COMPLETE", 2 * LOT, "OFS9V1L3", 2 * LOT),
            row(SYMBOLS[1], "SELL", "COMPLETE", 2 * LOT, "OFS9V1L1", 2 * LOT),
            row(SYMBOLS[2], "SELL", "CANCELLED", LOT, "OFS9V1L2", 2 * LOT)]
    out = place(read(rows), plan=condor_plan(2 * LOT))
    assert out.legs == (RecoveryLeg("L2", SYMBOLS[2], SELL, LOT),)


@pytest.mark.parametrize("tag", [None, "OFS9V2L2", "OFS77V1L0", "MANUAL"])
def test_place_missing_refused_while_any_order_is_open_on_that_contract(tag: str | None) -> None:
    """ADR-136 (1)/(2): no open order on that contract at Zerodha with or without our tag -> never a second order."""
    rows = [*adr136_rows(), row(SYMBOLS[2], "SELL", "OPEN", 0, tag)]
    out = place(read(rows))
    assert (out.refusal, out.contracts, out.legs) == (Refusal.ORDER_OPEN, (SYMBOLS[2],), ())


@pytest.mark.parametrize("status", ["OPEN", "TRIGGER PENDING", "AMO REQ RECEIVED", "VALIDATION PENDING",
                                    "PUT ORDER REQ RECEIVED", "MODIFY PENDING", "a status Kite adds tomorrow", ""])
def test_any_status_outside_the_three_terminal_ones_counts_as_open(status: str) -> None:
    """Allow-list (finding guard-as-forbidden-list): only COMPLETE / CANCELLED / REJECTED settle an order."""
    assert frozenset({"COMPLETE", "CANCELLED", "REJECTED"}) == TERMINAL_ORDER_STATUSES
    assert place(read(adr136_rows(fourth=status))).refusal is Refusal.ORDER_OPEN


def test_open_order_on_a_filled_contract_does_not_block_placing_a_different_missing_leg() -> None:
    """The open-order guard is per contract to be traded: an exit order open on 23000 PE does not stop 23400 CE."""
    out = place(read([*adr136_rows(), row(SYMBOLS[1], "BUY", "OPEN", 0, None)]))
    assert out.legs == (RecoveryLeg("L2", SYMBOLS[2], SELL, LOT),)


def test_margin_short_refuses_and_offers_only_close_and_kite() -> None:
    """ADR-136 (3) / REQ-055 AC-4: short margin -> no basket; only Close filled legs (plus keep = do nothing, and the
    Kite link) are offered."""
    short = MarginAnswer(D("40000.00"), D("48210.75"))
    assert place(read(adr136_rows()), short).refusal is Refusal.MARGIN_SHORT
    assert offered(read(adr136_rows()), short) == (
        RecoveryAction.CHECK_WITH_ZERODHA, RecoveryAction.CLOSE_FILLED_LEGS, RecoveryAction.MANAGE_ON_KITE)
    assert offered(read(adr136_rows())) == (
        RecoveryAction.CHECK_WITH_ZERODHA, RecoveryAction.PLACE_MISSING_LEGS, RecoveryAction.CLOSE_FILLED_LEGS,
        RecoveryAction.MANAGE_ON_KITE)


@pytest.mark.parametrize("margin", [MarginAnswer(None, D("1")), MarginAnswer(D("1"), None), MarginAnswer(None, None)])
def test_margin_not_read_refuses(margin: MarginAnswer) -> None:
    """Fail closed: Zerodha's margin unread -> nothing built."""
    assert place(read(adr136_rows()), margin).refusal is Refusal.MARGIN_UNKNOWN


def test_margin_equal_to_available_builds_and_a_negative_required_counts_as_zero() -> None:
    """Exactly enough builds; a negative required (Kite's reply for a reducing basket) is counted as 0."""
    assert place(read(adr136_rows()), MarginAnswer(D("48210.75"), D("48210.75"))).refusal is None
    assert place(read(adr136_rows()), MarginAnswer(D("0"), D("-1200.00"))).refusal is None


def test_a_sell_is_never_placed_beyond_what_its_protective_buy_filled() -> None:
    """ADR-117 (2)(b): buy 23600 CE AND sell 23400 CE both rejected -> only the buy is placed; the sell waits."""
    rows = [row(SYMBOLS[0], "BUY", "COMPLETE", LOT, "OFS9V1L0"), row(SYMBOLS[3], "BUY", "REJECTED", 0, "OFS9V1L3"),
            row(SYMBOLS[1], "SELL", "COMPLETE", LOT, "OFS9V1L1"), row(SYMBOLS[2], "SELL", "REJECTED", 0, "OFS9V1L2")]
    assert place(read(rows)).legs == (RecoveryLeg("L3", SYMBOLS[3], BUY, LOT),)


def test_a_sell_whose_protection_is_used_by_another_filled_sell_is_not_placed() -> None:
    """ADR-117 (2)(b): the one filled 22800 PE buy already covers the filled 23000 PE sell -> nothing to place."""
    plan = ExecutionPlan("9", (PlannedLeg("L0", SYMBOLS[0], condor_legs()[0]),
                               PlannedLeg("L1", SYMBOLS[1], condor_legs()[1]),
                               PlannedLeg("L2", WING, condor_legs()[1].__class__(
                                   SELL, condor_legs()[1].instrument, D("22900"), EXPIRY, LOT, D("60.00")))))
    rows = [row(SYMBOLS[0], "BUY", "COMPLETE", LOT, "OFS9V1L0"), row(SYMBOLS[1], "SELL", "COMPLETE", LOT, "OFS9V1L1"),
            row(WING, "SELL", "REJECTED", 0, "OFS9V1L2")]
    out = place_missing_legs(plan, read(rows), ENOUGH, scope(lots={**LOTS, WING: LOT}))
    assert out.refusal is Refusal.NOTHING_TO_PLACE


def test_place_missing_refused_while_reconciliation_block_is_up() -> None:
    """ADR-136 (1) / ADR-120 (2): never while a reconciliation block is up; then ADR-137's two actions are offered."""
    assert place(read(adr136_rows()), blocked=True).refusal is Refusal.BLOCKED
    assert offered(read(adr136_rows()), blocked=True) == (
        RecoveryAction.USE_ZERODHA_NUMBERS, RecoveryAction.CLOSE_VIA_BASKET, RecoveryAction.MANAGE_ON_KITE)


def test_not_whole_lots_refused() -> None:
    """F&O fills come in whole lots (ADR-135); a fill that is not one is not guessed at."""
    rows = adr136_rows()
    rows[2] = row(SYMBOLS[1], "SELL", "COMPLETE", 30, "OFS9V1L1")
    assert place(read(rows)).refusal is Refusal.NOT_WHOLE_LOTS


# ---- answer states of Zerodha's reads (standing item (d)) ----------------------------------------------------------

def test_answer_state_failed_refuses_every_action() -> None:
    """failed: the order read failed -> every action refused, only Check with Zerodha offered."""
    r = read(None)
    assert place(r).refusal is Refusal.READ_FAILED
    assert close(r).refusal is Refusal.READ_FAILED
    assert offered(r) == (RecoveryAction.CHECK_WITH_ZERODHA,)
    assert close(read(adr136_rows(), net=None) if False else ZerodhaRead(tuple(adr136_rows()), None, NOW)).refusal \
        is Refusal.READ_FAILED


@pytest.mark.parametrize("at", [NOW - datetime.timedelta(seconds=61), NOW + datetime.timedelta(seconds=6)])
def test_answer_state_stale_or_future_read_refuses(at: datetime.datetime) -> None:
    """ambiguous time: older than 60 s or stamped > 5 s ahead (``ofo.orders.model`` limits) -> refused."""
    assert place(read(adr136_rows(), at=at)).refusal is Refusal.READ_STALE
    assert close(read(adr136_rows(), at=at)).refusal is Refusal.READ_STALE


def test_answer_state_empty_book_and_tags_not_found_are_not_partial() -> None:
    """empty / not found: no row carries the plan's tags -> nothing filled -> not a partial state, nothing built."""
    assert place(read([])).refusal is Refusal.NOT_PARTIAL
    real_other = [from_kite(r) for r in _rows("orders-151006.json")]  # strategy 1's real rows, not strategy 9's
    assert place(read(real_other)).refusal is Refusal.NOT_PARTIAL
    assert offered(read([])) == (RecoveryAction.CHECK_WITH_ZERODHA,)


def test_answer_state_ambiguous_tag_twice_refuses() -> None:
    """ambiguous: one of our tags on two rows -> refused, never summed."""
    rows = [*adr136_rows(), row(SYMBOLS[0], "BUY", "COMPLETE", LOT, "OFS9V1L0")]
    assert place(read(rows)).refusal is Refusal.AMBIGUOUS
    assert close(read(rows)).refusal is Refusal.AMBIGUOUS


def test_answer_state_absent_contract_is_missing_and_stated_real_round_trip_is_not_partial() -> None:
    """absent: no row for 23400 CE at all -> it is missing (Not sent). stated: the REAL 2026-10-19 plan 1 filled
    65 of 65 -> complete, not partial."""
    assert place(read(adr136_rows()[:3])).legs == (RecoveryLeg("L2", SYMBOLS[2], SELL, LOT),)
    real = [from_kite(r) for r in _rows("orders-2026-10-19-roundtrip.json")]
    plan = ExecutionPlan("9", (PlannedLeg("L0", REAL_CONTRACT, condor_legs()[3]),))
    out = place_missing_legs(plan, read(real, net={}), ENOUGH, scope(lots={REAL_CONTRACT: LOT}))
    assert out.refusal is Refusal.NOT_PARTIAL


# ---- 2. Close filled legs: two baskets, shorts first ---------------------------------------------------------------

def test_close_filled_legs_basket_one_is_the_buy_back_only() -> None:
    """Q238 / ADR-136 example: buy back 23000 PE first; the longs are not in basket 1."""
    out = close(read(adr136_rows()))
    assert (out.step, out.legs) == (1, (RecoveryLeg("L1", SYMBOLS[1], BUY, LOT),))


def test_close_basket_two_only_after_zerodha_shows_the_short_bought_back() -> None:
    """Basket 2 (sell the longs) is decided from Zerodha's fresh net, never from a caller's word."""
    after_check = {SYMBOLS[0]: LOT, SYMBOLS[1]: 0, SYMBOLS[3]: LOT}
    out = close(read(adr136_rows(), net=after_check))
    assert (out.step, out.legs) == (2, (RecoveryLeg("L0", SYMBOLS[0], SELL, LOT),
                                        RecoveryLeg("L3", SYMBOLS[3], SELL, LOT)))


def test_close_never_sells_longs_while_the_buy_back_is_still_open() -> None:
    """The basket-1 buy-back is still open at Zerodha: no second buy-back and no step 2."""
    out = close(read([*adr136_rows(), row(SYMBOLS[1], "BUY", "OPEN", 0, "OFS9V2L1")]))
    assert (out.refusal, out.contracts, out.legs) == (Refusal.ORDER_OPEN, (SYMBOLS[1],), ())


def test_close_refused_while_one_of_our_entry_orders_is_open_and_change_price_link_offered() -> None:
    """Q223: an entry order still placed -> the user cancels it on Kite first; the Change price on Kite link shows."""
    r = read(adr136_rows(fourth="OPEN"))
    out = close(r)
    assert (out.refusal, out.contracts) == (Refusal.ENTRY_ORDER_OPEN, (SYMBOLS[2],))
    assert RecoveryAction.CHANGE_PRICE_ON_KITE in offered(r)
    assert RecoveryAction.CHANGE_PRICE_ON_KITE not in offered(read(adr136_rows()))


def test_close_never_exceeds_what_our_entry_filled() -> None:
    """Outside lots stay outside: Zerodha shows 130 short on 23000 PE, our entry filled 65 -> buy back 65."""
    out = close(read(adr136_rows(), net={**HELD, SYMBOLS[1]: -2 * LOT}))
    assert out.legs == (RecoveryLeg("L1", SYMBOLS[1], BUY, LOT),)


# ---- 3. Use Zerodha's numbers for this contract --------------------------------------------------------------------

def _positions_net(name: str) -> dict[str, int]:
    data = json.loads((REPLIES / name).read_text(encoding="utf-8"))["data"]["net"]
    return {r["tradingsymbol"]: r["quantity"] for r in data}


def test_use_zerodha_numbers_on_the_real_flat_round_trip_places_nothing() -> None:
    """ADR-137 (2) / ADR-116: the REAL 2026-10-19 reply shows 24000 CE flat; strategy 9 expected 65 -> holds 0;
    no order is built."""
    real = ZerodhaRead(tuple(from_kite(r) for r in _rows("orders-2026-10-19-roundtrip.json")),
                       _positions_net("positions-2026-10-19-roundtrip.json"), NOW)
    out = use_zerodha_numbers(REAL_CONTRACT, real, holders={"9": LOT}, now=NOW, blocked=True)
    assert (out.refusal, out.legs, dict(out.units_after)) == (None, (), {"9": 0})


def test_use_zerodha_numbers_adr137_example_and_matches_again() -> None:
    """ADR-137 example: expects 130, Zerodha 65, no open order -> 65. ADR-123: two holders matching again -> kept."""
    r = ZerodhaRead((), {REAL_CONTRACT: LOT}, NOW)
    assert dict(use_zerodha_numbers(REAL_CONTRACT, r, holders={"9": 2 * LOT}, now=NOW,
                                    blocked=True).units_after) == {"9": LOT}
    both = ZerodhaRead((), {REAL_CONTRACT: 2 * LOT}, NOW)
    assert dict(use_zerodha_numbers(REAL_CONTRACT, both, holders={"9": LOT, "10": LOT}, now=NOW,
                                    blocked=True).units_after) == {"9": LOT, "10": LOT}


def test_use_zerodha_numbers_refusals() -> None:
    """Refused with an open order (any tag), a stale read, a failed read, several holders it cannot split, or no
    block."""
    c = REAL_CONTRACT
    open_row = ZerodhaRead((row(c, "BUY", "OPEN", 0, None),), {c: LOT}, NOW)
    assert use_zerodha_numbers(c, open_row, holders={"9": 2 * LOT}, now=NOW, blocked=True).refusal is Refusal.ORDER_OPEN
    stale = ZerodhaRead((), {c: LOT}, NOW - datetime.timedelta(minutes=5))
    assert use_zerodha_numbers(c, stale, holders={"9": 2 * LOT}, now=NOW, blocked=True).refusal is Refusal.READ_STALE
    assert use_zerodha_numbers(c, ZerodhaRead((), None, NOW), holders={"9": 1}, now=NOW,
                               blocked=True).refusal is Refusal.READ_FAILED
    assert use_zerodha_numbers(c, ZerodhaRead(None, {}, NOW), holders={"9": 1}, now=NOW,
                               blocked=True).refusal is Refusal.READ_FAILED
    split = ZerodhaRead((), {c: LOT}, NOW)
    assert use_zerodha_numbers(c, split, holders={"9": LOT, "10": LOT}, now=NOW,
                               blocked=True).refusal is Refusal.AMBIGUOUS
    assert use_zerodha_numbers(c, split, holders={"9": 2 * LOT}, now=NOW, blocked=False).refusal is Refusal.NOT_BLOCKED


# ---- 4. Close via a basket (blocked contract) ----------------------------------------------------------------------

def test_close_via_basket_exits_what_zerodha_holds_shorts_first() -> None:
    """ADR-137 (3): the blocked strategy's exit, shorts first; refused when not blocked."""
    out = close_via_basket(condor_plan(), read(adr136_rows()), now=NOW, blocked=True)
    assert (out.step, out.legs) == (1, (RecoveryLeg("L1", SYMBOLS[1], BUY, LOT),))
    assert close_via_basket(condor_plan(), read(adr136_rows()), now=NOW, blocked=False).refusal is Refusal.NOT_BLOCKED


# ---- 5. The shared gate: market hours (ADR-119) applies to every recovery basket -----------------------------------

def test_recovery_basket_goes_through_the_shared_gate_market_closed(catalogue, eligibility) -> None:
    """ADR-136 (1) "inside 09:15-15:30 IST per ADR-119": the missing-legs basket passes ``check_pre_execution``;
    market closed -> blocked with MARKET_CLOSED; open -> that check passes."""
    out = missing_legs(condor_plan(), read(adr136_rows()), scope())
    legs = [condor_legs()[2]]
    assert [leg.contract for leg in out.legs] == [SYMBOLS[2]]
    closed = recovery_gate(legs, all_true_context(market_open=False), catalogue, eligibility, strategy_id="S-1")
    assert CheckCode.MARKET_CLOSED in closed.failed_codes
    opened = recovery_gate(legs, all_true_context(), catalogue, eligibility, strategy_id="S-1")
    assert CheckCode.MARKET_CLOSED not in opened.failed_codes


# ---- 6. Route wiring (#380-3 item 1): a recovery basket is a NEW plan number -------------------------------------

def test_second_place_press_never_re_places_what_the_first_basket_filled() -> None:
    """Threat "a second order for an open leg" across presses: Place missing legs went out as plan 2 (OFS9V2L0) and
    filled; plan 1's sell is still REJECTED. Counting only plan 1 would build SELL 65 again (double short). Dies if
    ``_fills`` reads one plan version only."""
    rows = [*adr136_rows(), row(SYMBOLS[2], "SELL", "COMPLETE", LOT, "OFS9V2L0")]
    out = place(read(rows))
    assert (out.refusal, out.legs) == (Refusal.NOT_PARTIAL, ())


def test_place_missing_refused_once_a_later_plan_started_closing() -> None:
    """Close filled legs step 1 (OFS9V2L0 BUY 23000 PE) completed: the strategy is being closed, never completed."""
    rows = [*adr136_rows(), row(SYMBOLS[1], "BUY", "COMPLETE", LOT, "OFS9V2L0")]
    out = place(read(rows, net={SYMBOLS[0]: LOT, SYMBOLS[3]: LOT}))
    assert (out.refusal, out.contracts, out.legs) == (Refusal.CLOSING, (SYMBOLS[1],), ())


def test_base_plan_tag_on_the_other_side_is_still_ambiguous() -> None:
    rows = [*adr136_rows(), row(SYMBOLS[0], "SELL", "COMPLETE", LOT, "OFS9V1L9")]
    assert place(read(rows)).refusal is Refusal.AMBIGUOUS


def test_an_older_plan_is_not_read() -> None:
    """Scope plan 1 ignores plan 0 tags (none exist in practice); a stray older fill never counts as this entry's."""
    rows = [*adr136_rows(), row(SYMBOLS[2], "SELL", "COMPLETE", LOT, "OFS9V0L2")]
    out = place(read(rows))
    assert out.legs == (RecoveryLeg("L2", SYMBOLS[2], SELL, LOT),)
