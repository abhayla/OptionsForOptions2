"""W-078 / REQ-059 AC-3 (ADR-080): tick rounding toward the user and the depth-based executable limit.

Spec basis: ADR-080 "BUY rounds down, SELL rounds up - so the price sent is never worse than the price the user
accepted"; "when the 5 levels cannot fill the quantity, the review says so". Real input: the 15:10 replies
``quote_CE.json`` / ``quote_PE.json`` (NIFTY 23,550 CE and 21,900 PE, 19 Oct 2026 expiry), lot 65, tick 0.05.
"""
from __future__ import annotations

import json
from decimal import Decimal as D
from pathlib import Path

import pytest

from ofo.engine import Action
from ofo.engine.executable_price import (
    depth_from_quote, executable_limit, leg_slippage, round_to_tick, total_slippage,
)

REAL = Path(__file__).resolve().parents[2] / "docs/research/kite-proof-2026-10-07/rest-2026-10-15-order"
LOT, TICK = 65, D("0.05")


def _quote(name: str) -> dict:
    data = json.loads((REAL / name).read_text(), parse_float=D)["data"]
    (quote,) = data.values()
    return quote


@pytest.fixture(scope="module")
def ce() -> dict:
    return _quote("quote_CE.json")


@pytest.fixture(scope="module")
def pe() -> dict:
    return _quote("quote_PE.json")


def test_core_real_ce_buy_one_lot_limit_4_00_slippage_3_25(ce):
    """Core: BUY 1 lot of the real CE: executable limit 4.00 (best ask, 65 available), Rs 3.25 over the LTP 3.95."""
    r = executable_limit(depth_from_quote(ce), Action.BUY, LOT, TICK, ce["last_price"])
    assert (r.fillable, r.limit) == (True, D("4.00"))
    assert r.walked_cost == D("260.00") and r.planned_cost == D("256.75") and r.slippage == D("3.25")


def test_core_real_ce_buy_two_lots_limit_4_05_slippage_9_75(ce):
    """Core: 2 lots need the second level: limit 4.05, walked 65@4.00 + 65@4.05 = 523.25 vs 513.50 at the LTP."""
    r = executable_limit(depth_from_quote(ce), Action.BUY, 2 * LOT, TICK, ce["last_price"])
    assert r.limit == D("4.05") and r.walked_cost == D("523.25") and r.planned_cost == D("513.50")
    assert r.slippage == D("9.75")


def test_core_buy_limit_3_975_is_sent_as_3_95_and_sell_as_4_00():
    assert round_to_tick(D("3.975"), TICK, Action.BUY) == D("3.95")
    assert round_to_tick(D("3.975"), TICK, Action.SELL) == D("4.00")
    assert round_to_tick(D("4.00"), TICK, Action.BUY) == D("4.00") == round_to_tick(D("4.00"), TICK, Action.SELL)


@pytest.mark.parametrize("price, tick", [(D("0"), TICK), (D("-1"), TICK), (D("4"), D("0")), (D("4"), D("-0.05"))])
def test_round_to_tick_refuses_non_positive(price, tick):
    with pytest.raises(ValueError):
        round_to_tick(price, tick, Action.BUY)


def test_floats_are_refused_everywhere(ce):
    with pytest.raises(ValueError):
        round_to_tick(3.975, TICK, Action.BUY)
    with pytest.raises(ValueError):
        round_to_tick(D("3.975"), 0.05, Action.BUY)
    with pytest.raises(ValueError):
        executable_limit(depth_from_quote(ce), Action.BUY, LOT, TICK, 3.95)
    with pytest.raises(ValueError):
        depth_from_quote({"depth": {"buy": [{"price": 3.95, "quantity": 1}], "sell": []}})


def test_buy_walks_ask_side_sell_walks_bid_side_real_pe(pe):
    """BUY on the PE: ask side from 4.60 (limit 4.60); SELL: bid side from 4.55 (limit 4.55). Wrong side differs."""
    depth = depth_from_quote(pe)
    buy = executable_limit(depth, Action.BUY, LOT, TICK, pe["last_price"])
    sell = executable_limit(depth, Action.SELL, LOT, TICK, pe["last_price"])
    assert buy.limit == D("4.60") and sell.limit == D("4.55")
    assert buy.slippage == D("3.25")      # 65 * (4.60 - 4.55)
    assert sell.slippage == D("0.00")     # SELL planned - walked = 65*4.55 - 65*4.55


def test_sell_slippage_is_positive_when_worse(ce):
    """SELL 1 lot of the real CE at the bid 3.95 vs a planned price of 4.00: planned minus walked = +3.25."""
    r = executable_limit(depth_from_quote(ce), Action.SELL, LOT, TICK, D("4.00"))
    assert r.limit == D("3.95") and r.slippage == D("3.25")


def test_sell_two_lots_in_deep_bid_uses_first_level_only(ce):
    r = executable_limit(depth_from_quote(ce), Action.SELL, 2 * LOT, TICK, D("3.95"))
    assert r.limit == D("3.95") and r.slippage == D("0.00")


def test_five_levels_short_of_quantity_is_not_fillable_and_invents_no_limit(ce):
    """Asks total 65+12545+12480+7800+8515 = 41,405: one unit more than that has no limit, never one beyond level 5."""
    depth = depth_from_quote(ce)
    ok = executable_limit(depth, Action.BUY, 41405, TICK, ce["last_price"])
    assert ok.fillable and ok.limit == D("4.20")
    short = executable_limit(depth, Action.BUY, 41406, TICK, ce["last_price"])
    assert (short.fillable, short.limit, short.walked_cost, short.slippage) == (False, None, None, None)


def test_limit_is_the_worst_level_not_the_first(ce):
    r = executable_limit(depth_from_quote(ce), Action.BUY, 2 * LOT, TICK, ce["last_price"])
    assert r.limit != D("4.00")


def test_off_tick_level_price_is_rounded_toward_the_user_not_the_walked_cost():
    """A level at 4.07 (off the 0.05 tick) sends BUY at 4.05 (down) but the walked cost uses the level's own price."""
    depth = {"buy": [], "sell": [{"price": D("4.07"), "quantity": 100, "orders": 1}]}
    r = executable_limit(depth_from_quote({"depth": depth}), Action.BUY, 50, TICK, D("4.00"))
    assert r.limit == D("4.05") and r.walked_cost == D("203.50")


def test_per_leg_and_total_slippage_sum_and_unfillable_leg_has_none(ce, pe):
    one = executable_limit(depth_from_quote(ce), Action.BUY, LOT, TICK, ce["last_price"])
    two = executable_limit(depth_from_quote(pe), Action.SELL, LOT, TICK, pe["last_price"])
    assert leg_slippage(one) == D("3.25")
    assert total_slippage([one, two]) == D("3.25")
    short = executable_limit(depth_from_quote(ce), Action.BUY, 10**6, TICK, ce["last_price"])
    assert total_slippage([one, short]) is None  # a total that hides an unfillable leg would understate the cost


def test_quantity_must_be_positive_int(ce):
    for bad in (0, -65, True, 1.5):
        with pytest.raises(ValueError):
            executable_limit(depth_from_quote(ce), Action.BUY, bad, TICK, ce["last_price"])
