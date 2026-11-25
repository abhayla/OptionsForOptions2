"""Modular doors Phase 6 (PLAN 5.6, B2): ``exit_legs`` closes exactly the net, opposite side, per contract, sorted by
the contract text. The ORACLE below is today's body copied verbatim; the function under test must equal it for the
four ``LegToPrice`` fields, element by element (no database, no network). Written first: it is green on today's code
and must stay green when ``exit_legs`` reads ``ofo.tracking.closing.open_legs_to_close``.

New contract (Tier A minor): ``exit_legs`` reads ``open_legs_to_close``, which accepts only plain ints, so a Decimal,
bool or float net raises TypeError (the old body accepted them). Unreachable today: the only caller ``held_units``
always passes plain int (execution_plan_store.py:374, order_book_store.py:78-79); it fails closed before any pricing.

Spec basis: ADR-105 (an exit closes exactly the net, opposite side); ADR-281 (the real path is frozen except
maintenance); ADR-016 to ADR-019.
"""
from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal as D

import pytest
from ofo.engine import Action
from ofo_app import execute_plan as ep


def _oracle(held: Mapping[str, int], instrument_of):
    return [ep.LegToPrice(instrument_of(contract), Action.SELL if net > 0 else Action.BUY, abs(net), None)
            for contract, net in sorted(held.items()) if net != 0]


def _of(contract: str):
    return ("id", contract)


CONDOR = {"NFO-OPT:47169": -65, "NFO-OPT:47177": 65, "NFO-OPT:47152": -65, "NFO-OPT:47138": 65}
CASES = {
    "string order trap: 10 sorts before 9": {"NFO-OPT:9": 65, "NFO-OPT:10": -130, "NFO-OPT:100": 25},
    "zero nets are left out": {"NFO-OPT:1": 0, "NFO-OPT:2": 50, "NFO-OPT:3": 0, "NFO-OPT:4": -75},
    "all zero": {"NFO-OPT:1": 0, "NFO-OPT:2": 0},
    "empty": {},
    "a single short": {"NFO-OPT:47169": -65},
    "a single long": {"NFO-OPT:47169": 65},
    "4-leg condor": CONDOR,
    "4-leg condor, reversed insertion": dict(reversed(list(CONDOR.items()))),
    "4-leg condor with a zero net": {**CONDOR, "NFO-OPT:47138": 0},
    "mixed sizes": {"NSE_FO:2": -1, "NSE_FO:11": 1, "NSE_FO:1": 1300, "BSE_FO:5": -20},
}


@pytest.mark.parametrize("name", list(CASES))
def test_exit_legs_equals_the_oracle_field_by_field(name: str) -> None:
    held = CASES[name]
    new, old = ep.exit_legs(held, _of), _oracle(held, _of)
    assert len(new) == len(old)
    for got, want in zip(new, old, strict=True):
        assert got.instrument_id == want.instrument_id
        assert got.action is want.action
        assert got.quantity == want.quantity
        assert got.planned_entry is None and want.planned_entry is None
    assert new == old


def test_the_string_order_trap_is_pinned_not_numeric() -> None:
    """'NFO-OPT:10' < 'NFO-OPT:100' < 'NFO-OPT:9' as text; a numeric sort would put 9 first."""
    legs = ep.exit_legs(CASES["string order trap: 10 sorts before 9"], _of)
    assert [leg.instrument_id[1] for leg in legs] == ["NFO-OPT:10", "NFO-OPT:100", "NFO-OPT:9"]
    assert [(leg.action, leg.quantity) for leg in legs] == [(Action.BUY, 130), (Action.SELL, 25), (Action.SELL, 65)]


def test_a_single_short_is_closed_by_a_buy_of_the_whole_quantity() -> None:
    (leg,) = ep.exit_legs({"NFO-OPT:47169": -65}, _of)
    assert (leg.action, leg.quantity, leg.planned_entry) == (Action.BUY, 65, None)


@pytest.mark.parametrize("bad", [D("65"), True, 65.0], ids=["decimal", "bool", "float"])
def test_a_net_that_is_not_a_plain_int_is_refused_before_pricing(bad) -> None:
    with pytest.raises(TypeError):
        ep.exit_legs({"NFO-OPT:1": bad}, _of)


def test_a_zero_decimal_next_to_a_valid_int_leg_is_refused() -> None:
    with pytest.raises(TypeError):
        ep.exit_legs({"NFO-OPT:1": D("0"), "NFO-OPT:2": 65}, _of)
