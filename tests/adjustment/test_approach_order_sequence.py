"""IC e2e paper contract, Stage B3 (design decisions 5, 15): A-11 obeys the roll debit limit, and every basket that
closes and opens (a roll, A-11) lists each buy-back before any sell, so a placed basket never sells before it buys."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal as D

import pytest
from ofo.adjustment import liquidity
from ofo.adjustment.approaches import Trade, _ordered, build_approach
from test_approaches import CFG, inputs, load

OVER = liquidity.Limits(debit_state=liquidity.SET, debit=liquidity.DebitLimit(D("1")))
ROOMY = liquidity.Limits(debit_state=liquidity.SET, debit=liquidity.DebitLimit(D("1000000")))
UNREADABLE = liquidity.Limits(debit_state=liquidity.UNREADABLE)


def adj02():
    return inputs(load("ADJ-02"))


def cheap_sells():
    """ADJ-02 with the contracts A-11 SELLS priced at Rs 0.05: the recentre then costs money (a debit)."""
    position, chain, spot = adj02()
    sold = {t.tradingsymbol for t in build_approach(position, chain, spot, "A-11", CFG).trades if t.action == "SELL"}
    tiny = [replace(r, ltp=D("0.05"), bid=D("0.05"), ask=D("0.05")) if r.tradingsymbol in sold else r for r in chain]
    return position, tiny, spot


def test_a11_debit_above_the_limit_is_refused_with_its_reason():
    position, chain, spot = cheap_sells()
    free = build_approach(position, chain, spot, "A-11", CFG)
    assert free.refusal is None and free.trades  # without limits it builds
    built = build_approach(position, chain, spot, "A-11", CFG, limits=OVER)
    debit = -sum(((1 if t.action == "SELL" else -1) * t.price * t.quantity for t in free.trades), D(0))
    assert debit > D("1"), debit  # the roll really is a debit here, so the refusal is the limit's
    assert built.refusal is not None and built.trades == () and built.after == ()
    assert built.refusal == ("This roll costs ₹23,055.50 net, which is more than the ₹1 your playbook "
                             "allows for one roll.")


def test_a11_within_the_limit_still_builds_the_same_trades():
    position, chain, spot = cheap_sells()
    free = build_approach(position, chain, spot, "A-11", CFG)
    roomy = build_approach(position, chain, spot, "A-11", CFG, limits=ROOMY)
    assert roomy.refusal is None and roomy.trades == free.trades


def test_a11_unreadable_limit_fails_closed():
    position, chain, spot = cheap_sells()
    built = build_approach(position, chain, spot, "A-11", CFG, limits=UNREADABLE)
    assert built.refusal is not None and built.trades == ()


@pytest.mark.parametrize("approach", ["A-01", "A-05", "A-02", "A-04", "A-06", "A-11"])
def test_every_buy_back_comes_before_any_sell(approach):
    position, chain, spot = adj02()
    built = build_approach(position, chain, spot, approach, CFG)
    assert built.refusal is None and built.trades, (approach, built.refusal)
    actions = [t.action for t in built.trades]
    assert "BUY" in actions and "SELL" in actions
    assert actions == sorted(actions, key=lambda a: a != "BUY"), actions  # every BUY first
    closes = [i for i, t in enumerate(built.trades) if t.action == "BUY"]
    assert closes == list(range(len(closes)))


def test_ordered_puts_a_sell_first_basket_in_buy_first_order():
    sell = Trade("SELL", "CE", D("23600"), None, 1, 75, D("10"), "X1")
    buy = Trade("BUY", "CE", D("23500"), None, 1, 75, D("20"), "X2")
    assert [t.action for t in _ordered([sell, buy])] == ["BUY", "SELL"]
    assert [t.action for t in _ordered([buy, sell])] == ["BUY", "SELL"]
