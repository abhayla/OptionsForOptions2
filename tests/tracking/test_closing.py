"""Phase 4 (modular doors, PLAN-phases-3-8 5.4.2): the shared closing step, ``ofo.tracking.closing``.

``open_legs_to_close(net, only)``: one close per non-zero net, on the opposite side, for the whole open quantity, in the
order of ``only`` (or of ``net``). A key of ``only`` with net 0 or absent is left out (a quantity-0 order is never
built). No sorting, no float. No database: stdlib only.
"""
from __future__ import annotations

import pytest
from ofo.tracking.closing import Close, open_legs_to_close


def test_empty_net_closes_nothing():
    assert open_legs_to_close({}) == []
    assert open_legs_to_close({}, only=[1, 2]) == []


def test_zero_nets_close_nothing():
    assert open_legs_to_close({1: 0, 2: 0}) == []


def test_a_long_is_closed_by_a_sell_and_a_short_by_a_buy_for_the_whole_quantity():
    assert open_legs_to_close({10: 65, 20: -130}) == [Close(10, "SELL", 65), Close(20, "BUY", 130)]


def test_the_order_of_net_is_kept_and_nothing_is_sorted():
    assert [c.key for c in open_legs_to_close({30: 1, 10: -1, 20: 2})] == [30, 10, 20]
    assert [c.key for c in open_legs_to_close({"NFO-OPT:10": 1, "NFO-OPT:9": 1})] == ["NFO-OPT:10", "NFO-OPT:9"]


def test_only_sets_the_order_and_the_subset():
    net = {10: 65, 20: -65, 30: 65, 40: -65}
    assert [c.key for c in open_legs_to_close(net, only=[30, 10])] == [30, 10]
    assert open_legs_to_close(net, only=[20]) == [Close(20, "BUY", 65)]


def test_a_key_of_only_that_is_flat_or_absent_is_left_out():
    net = {10: 65, 20: 0}
    assert open_legs_to_close(net, only=[20, 99, 10]) == [Close(10, "SELL", 65)]


def test_a_repeated_key_of_only_closes_once():
    assert open_legs_to_close({10: 65}, only=[10, 10]) == [Close(10, "SELL", 65)]


def test_only_none_means_every_open_leg_and_an_empty_only_means_none():
    assert [c.key for c in open_legs_to_close({10: 1, 20: -1}, only=None)] == [10, 20]
    assert open_legs_to_close({10: 1, 20: -1}, only=[]) == []


def test_the_input_is_not_changed():
    net = {10: 65, 20: -65}
    only = [20, 10]
    open_legs_to_close(net, only)
    assert net == {10: 65, 20: -65} and only == [20, 10]


@pytest.mark.parametrize("bad", [65.0, 0.5, True, "65"])
def test_a_quantity_that_is_not_a_whole_number_is_refused_never_rounded(bad):
    with pytest.raises(TypeError):
        open_legs_to_close({10: bad})


def test_a_close_carries_whole_numbers_only():
    [close] = open_legs_to_close({10: -65})
    assert isinstance(close.quantity, int) and not isinstance(close.quantity, bool)
