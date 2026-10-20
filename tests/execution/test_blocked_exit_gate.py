"""#380-3, ADR-137 (3): the ONE narrow blocked-exit rule inside ``check_pre_execution`` (``safety._blocked_exit_allowed``).

A reconciliation-blocked strategy refuses every action, except an EXIT basket whose every order (a) is the opposite side
of what Zerodha shows NOW for that contract, (b) is at most Zerodha's absolute net there, (c) has no open order on that
contract, and (d) is all buy-backs, or all sells once Zerodha shows no short (REQ-058 Q238, two baskets). Every other
check of the gate still runs. Expected values come from the rule's text and the held condor (65 units per leg: BUY 22800
PE, SELL 23000 PE, SELL 23400 CE, BUY 23600 CE), never from running the code.
"""
from __future__ import annotations

import dataclasses
import datetime

import pytest
from ofo.engine import Action, Leg, Strategy
from ofo.execution import CheckCode, ExecutionAction
from ofo.execution.context import ZerodhaNow, product_key
from ofo.timeutil import MAX_READ_AGE

from tests.execution.execution_inputs import AS_OF, LOT, all_true_context, check, condor_legs

BLOCKED = frozenset({"S-1"})
HELD = condor_legs()  # stored: BUY 22800 PE, SELL 23000 PE, SELL 23400 CE, BUY 23600 CE, 65 each
LONG_PE, SHORT_PE, SHORT_CE, LONG_CE = HELD
KEYS = [product_key(leg) for leg in HELD]
ZERODHA_MATCHES = {KEYS[0]: LOT, KEYS[1]: -LOT, KEYS[2]: -LOT, KEYS[3]: LOT}
READ_AT = AS_OF + datetime.timedelta(seconds=2)  # the route clock after both replies


def _order(leg: Leg, side: Action, units: int = LOT) -> Leg:
    return dataclasses.replace(leg, action=side, quantity=units)


BUY_BACKS = Strategy((_order(SHORT_PE, Action.BUY), _order(SHORT_CE, Action.BUY)))  # step 1
SELLS = Strategy((_order(LONG_PE, Action.SELL), _order(LONG_CE, Action.SELL)))  # step 2


def _now(net=None, open_orders=frozenset(), read_at=READ_AT) -> ZerodhaNow:
    return ZerodhaNow(dict(ZERODHA_MATCHES if net is None else net), frozenset(open_orders), read_at)


def _ctx(now: ZerodhaNow | None, active=HELD, **overrides):
    return all_true_context(**({"action": ExecutionAction.EXIT, "active_legs": active,
                                "reconciliation_blocked_strategy_ids": BLOCKED, "zerodha_now": now} | overrides))


def _codes(strategy, ctx, catalogue, eligibility) -> set:
    return set(check(strategy, ctx, catalogue, eligibility).failed_codes)


def test_all_four_conditions_held_passes_while_blocked(catalogue, eligibility):
    """ADR-137 (3): step 1 (buy back both shorts, 65 each, nothing open, read at the click) passes the blocked check."""
    result = check(BUY_BACKS, _ctx(_now()), catalogue, eligibility)
    assert result.blocked is False
    assert CheckCode.RECONCILIATION_MISMATCH in result.passed


def test_without_a_read_at_the_click_the_block_stands(catalogue, eligibility):
    """ADR-120 (2): no Zerodha read in the context -> blocked exactly as before the rule."""
    assert _codes(BUY_BACKS, _ctx(None), catalogue, eligibility) == {CheckCode.RECONCILIATION_MISMATCH}


def test_a_wrong_side_order_is_refused(catalogue, eligibility):
    """(a): the store says short 23400 CE, Zerodha shows LONG 65 there now: a BUY would enlarge the long -> blocked."""
    net = ZERODHA_MATCHES | {KEYS[2]: LOT}
    buy_ce = Strategy((_order(SHORT_CE, Action.BUY),))
    assert _codes(buy_ce, _ctx(_now(net)), catalogue, eligibility) == {CheckCode.RECONCILIATION_MISMATCH}


def test_an_order_on_a_contract_zerodha_shows_flat_is_refused(catalogue, eligibility):
    """(a): Zerodha flat on 23400 CE -> a buy-back there would OPEN a long -> blocked."""
    net = ZERODHA_MATCHES | {KEYS[2]: 0}
    buy_ce = Strategy((_order(SHORT_CE, Action.BUY),))
    assert _codes(buy_ce, _ctx(_now(net)), catalogue, eligibility) == {CheckCode.RECONCILIATION_MISMATCH}


def test_more_units_than_zerodha_holds_is_refused(catalogue, eligibility):
    """(b): the store says short 130, Zerodha shows short 65: buying back 130 would open a 65 long -> blocked."""
    active = (LONG_PE, SHORT_PE, _order(SHORT_CE, Action.SELL, 2 * LOT), LONG_CE)
    buy_130 = Strategy((_order(SHORT_CE, Action.BUY, 2 * LOT),))
    assert _codes(buy_130, _ctx(_now(), active=active), catalogue, eligibility) == {CheckCode.RECONCILIATION_MISMATCH}
    buy_65 = Strategy((_order(SHORT_CE, Action.BUY, LOT),))
    assert check(buy_65, _ctx(_now(), active=active), catalogue, eligibility).blocked is False  # exactly the net


def test_units_are_summed_per_contract(catalogue, eligibility):
    """(b): two 65 buy-backs of one contract Zerodha shows short 65 add to 130 -> blocked by the rule (and the
    duplicate-leg check)."""
    twice = Strategy((_order(SHORT_CE, Action.BUY), _order(SHORT_CE, Action.BUY)))
    assert CheckCode.RECONCILIATION_MISMATCH in _codes(twice, _ctx(_now()), catalogue, eligibility)


def test_an_open_order_on_the_contract_is_refused(catalogue, eligibility):
    """(c): any open order at Zerodha on 23000 PE (whatever its tag) -> blocked."""
    now = _now(open_orders={KEYS[1]})
    assert _codes(BUY_BACKS, _ctx(now), catalogue, eligibility) == {CheckCode.RECONCILIATION_MISMATCH}


def test_an_open_order_on_another_contract_does_not_refuse(catalogue, eligibility):
    """(c) names the order's own contract: an open order on 23600 CE does not stop buying back the shorts."""
    assert check(BUY_BACKS, _ctx(_now(open_orders={KEYS[3]})), catalogue, eligibility).blocked is False


def test_a_mixed_basket_is_refused(catalogue, eligibility):
    """(d): buy-backs and sells in one basket -> blocked (two baskets, shorts first)."""
    mixed = Strategy(BUY_BACKS.legs + SELLS.legs)
    assert _codes(mixed, _ctx(_now()), catalogue, eligibility) == {CheckCode.RECONCILIATION_MISMATCH}


def test_sells_while_a_short_is_open_are_refused_and_pass_once_flat(catalogue, eligibility):
    """(d): step 2 (sell the longs) while Zerodha still shows a short -> blocked; once both shorts read 0 -> passes."""
    assert _codes(SELLS, _ctx(_now()), catalogue, eligibility) == {CheckCode.RECONCILIATION_MISMATCH}
    flat_shorts = ZERODHA_MATCHES | {KEYS[1]: 0, KEYS[2]: 0}
    assert check(SELLS, _ctx(_now(flat_shorts)), catalogue, eligibility).blocked is False


def test_a_contract_the_read_does_not_carry_is_refused(catalogue, eligibility):
    """Standing item (c): an unresolved contract (absent from the read) fails closed."""
    net = {k: v for k, v in ZERODHA_MATCHES.items() if k != KEYS[2]}
    assert _codes(BUY_BACKS, _ctx(_now(net)), catalogue, eligibility) == {CheckCode.RECONCILIATION_MISMATCH}


@pytest.mark.parametrize("read_at, allowed", [
    (AS_OF - datetime.timedelta(seconds=1), False),  # taken before the click
    (AS_OF, True),
    (AS_OF + MAX_READ_AGE, True),
    (AS_OF + MAX_READ_AGE + datetime.timedelta(seconds=1), False),  # held too long
], ids=["before-click", "at-click", "at-limit", "too-old"])
def test_the_read_must_be_taken_at_the_click(read_at, allowed, catalogue, eligibility):
    """Finding freshness-judged-on-request-start-clock: the read's own time, at or after the click, within the limit."""
    result = check(BUY_BACKS, _ctx(_now(read_at=read_at)), catalogue, eligibility)
    assert result.blocked is (not allowed)


@pytest.mark.parametrize("action", [ExecutionAction.NEW_ENTRY, ExecutionAction.ADJUSTMENT])
def test_only_an_exit_uses_the_rule(action, catalogue, eligibility):
    """The rule is for EXIT baskets only: an entry or adjustment on a blocked strategy stays blocked."""
    assert CheckCode.RECONCILIATION_MISMATCH in _codes(BUY_BACKS, _ctx(_now(), action=action), catalogue, eligibility)


def test_every_other_gate_still_applies(catalogue, eligibility):
    """ADR-119: the allowed basket outside market hours is refused by the market-hours check, not let through."""
    assert _codes(BUY_BACKS, _ctx(_now(), market_open=False), catalogue, eligibility) == {CheckCode.MARKET_CLOSED}


def test_the_stored_reduce_only_check_still_applies(catalogue, eligibility):
    """The blocked rule never replaces the exit check: Zerodha short 130 but the store holds 65 -> a 130 buy-back is
    still refused as adding a position."""
    net = ZERODHA_MATCHES | {KEYS[2]: -2 * LOT}
    buy_130 = Strategy((_order(SHORT_CE, Action.BUY, 2 * LOT),))
    assert _codes(buy_130, _ctx(_now(net)), catalogue, eligibility) == {CheckCode.EXIT_NOT_REDUCE_ONLY}


@pytest.mark.parametrize("kwargs", [
    {"net": {("k",): 1.5}},
    {"net": {("k",): True}},
    {"net": [1]},
    {"open_orders": {("k",)}},
    {"read_at": datetime.datetime(2026, 9, 29, 10, 0)},  # naive
])
def test_zerodha_now_refuses_bad_shapes(kwargs):
    """Fail closed on construction: units are integers, open orders a frozenset of keys, the time timezone-aware."""
    base = {"net": {}, "open_orders": frozenset(), "read_at": READ_AT} | kwargs
    with pytest.raises(ValueError):
        ZerodhaNow(**base)


def test_a_forged_read_object_is_refused():
    """Finding caller-supplied-verdict-trusted: only a ZerodhaNow is accepted in the context."""
    class Fake:
        net, open_orders, read_at = dict(ZERODHA_MATCHES), frozenset(), READ_AT

    with pytest.raises(ValueError):
        _ctx(Fake())
