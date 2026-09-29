"""REQ-038 AC-1: the strategy definition and the live market state are separate, immutable objects."""
from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal as D

import pytest

from ofo.engine import Action, Instrument, Leg, Strategy
from ofo.strategy.definition import DefinitionError, DefinitionLeg, StrategyDefinition
from ofo.strategy.live_state import DataHealth, Greeks, LegQuote, LiveState, LiveStateError

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
EXPIRY = datetime.date(2026, 10, 27)
GOLDEN = Strategy((
    Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, 75, D("42.50"), D("38.20")),
    Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, 75, D("86.00"), D("72.50")),
    Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, 75, D("91.50"), D("78.00")),
    Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, 75, D("44.00"), D("39.50")),
))
DEFINITION = StrategyDefinition.from_engine(
    "NIFTY", GOLDEN, rules_ref="exit-rules-1", risk_limits={"max_loss": D("8175")},
    preferences={"expiry_style": "weekly"},
)
MARKET_FIELDS = {"spot", "futures", "ltp", "bid", "ask", "volume", "oi", "oi_change", "iv", "greeks", "pnl",
                 "margin", "charges", "distances", "trigger_state", "as_of", "data_health", "entry_price"}


def live(spot: str, pnl: str) -> LiveState:
    return LiveState(
        as_of=datetime.datetime(2026, 10, 1, 10, 0, tzinfo=IST), data_health=DataHealth.AVAILABLE,
        spot=D(spot), futures=D("23260.40"),
        leg_quotes=(LegQuote(0, ltp=D("38.20"), bid=D("38.10"), ask=D("38.30"), volume=1200, oi=50000,
                             oi_change=-300, iv=D("14.2"),
                             greeks=Greeks(D("-0.21"), D("0.0004"), D("-5.1"), D("9.8"))),),
        pnl=D(pnl), margin=D("48210.55"), charges=D("212.40"),
        distances=(("to_upper_breakeven", D("291")), ("to_lower_breakeven", D("-291"))),
        trigger_state=(("exit-rules-1:max_loss", False),),
    )


def test_definition_holds_every_user_decision_and_no_market_data():
    """AC-1: the definition carries underlying, expiries, legs, strikes, sides, quantities, rules, risk limits and
    preferences; the golden condor's entry prices and LTPs are dropped, and no definition field is market data."""
    assert DEFINITION.underlying == "NIFTY" and DEFINITION.expiries == (EXPIRY,)
    assert [(l.action, l.instrument, l.strike, l.quantity) for l in DEFINITION.legs] == [
        (Action.BUY, Instrument.PE, D("22800"), 75), (Action.SELL, Instrument.PE, D("23000"), 75),
        (Action.SELL, Instrument.CE, D("23400"), 75), (Action.BUY, Instrument.CE, D("23600"), 75)]
    assert DEFINITION.rules_ref == "exit-rules-1"
    assert DEFINITION.risk_limits == (("max_loss", D("8175")),)
    assert DEFINITION.preferences == (("expiry_style", "weekly"),)
    definition_fields = {f.name for f in dataclasses.fields(StrategyDefinition)} | {
        f.name for f in dataclasses.fields(DefinitionLeg)}
    assert definition_fields.isdisjoint(MARKET_FIELDS)
    with pytest.raises(TypeError):
        DefinitionLeg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, 75, ltp=D("38.20"))
    with pytest.raises(TypeError):
        StrategyDefinition("NIFTY", DEFINITION.legs, spot=D("23200"))


def test_live_state_holds_market_data_and_no_definition():
    """AC-1: live state carries spot, futures, LTP, bid/ask, volume, OI, OI change, IV, Greeks, P&L, margin,
    charges, distances, trigger state, timestamp and data health, and nothing of the definition."""
    state = live("23200", "1365.00")
    quote = state.leg_quotes[0]
    assert (state.spot, state.futures, quote.ltp, quote.bid, quote.ask) == (
        D("23200"), D("23260.40"), D("38.20"), D("38.10"), D("38.30"))
    assert (quote.volume, quote.oi, quote.oi_change, quote.iv, quote.greeks.delta) == (1200, 50000, -300, D("14.2"), D("-0.21"))
    assert (state.pnl, state.margin, state.charges, state.data_health) == (D("1365.00"), D("48210.55"), D("212.40"), DataHealth.AVAILABLE)
    assert state.distances[1] == ("to_lower_breakeven", D("-291")) and state.trigger_state == (("exit-rules-1:max_loss", False),)
    live_fields = {f.name for f in dataclasses.fields(LiveState)}
    definition_fields = {f.name for f in dataclasses.fields(StrategyDefinition)}
    assert live_fields.isdisjoint(definition_fields)
    assert not any(isinstance(getattr(state, name), StrategyDefinition) for name in live_fields)


def test_market_movement_never_changes_the_definition():
    """AC-1: many live states at different spots leave the definition equal, hash-equal and unmodifiable."""
    before, before_hash = dataclasses.replace(DEFINITION), hash(DEFINITION)
    states = [live(str(23000 + 10 * i), str(-100 * i)) for i in range(50)]
    assert len({s.spot for s in states}) == 50
    assert DEFINITION == before and hash(DEFINITION) == before_hash
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFINITION.legs = ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFINITION.legs[0].strike = D("22700")
    with pytest.raises(dataclasses.FrozenInstanceError):
        states[0].spot = D("1")


def test_definition_rejects_invalid_input():
    """AC-1 red: unknown underlying, two legs on one contract, absurd sizes, misspelled names, float money."""
    leg = DEFINITION.legs[0]
    cases = [
        lambda: StrategyDefinition("BANKNIFTY", DEFINITION.legs),
        lambda: StrategyDefinition("NIFTY", (leg, leg)),
        lambda: StrategyDefinition("NIFTY", (leg, dataclasses.replace(leg, action=Action.SELL))),
        lambda: StrategyDefinition("NIFTY", ()),
        lambda: StrategyDefinition("NIFTY", tuple(dataclasses.replace(leg, strike=D(20000 + 50 * i)) for i in range(21))),
        lambda: dataclasses.replace(leg, quantity=10**7),
        lambda: dataclasses.replace(leg, quantity=True),
        lambda: dataclasses.replace(leg, strike=D(22800.1)),
        lambda: dataclasses.replace(leg, expiry=datetime.datetime(2026, 10, 27, 15, 30)),
        lambda: StrategyDefinition("NIFTY", DEFINITION.legs, risk_limits={"Max Loss": D("1")}),
        lambda: StrategyDefinition("NIFTY", DEFINITION.legs, risk_limits={"max_loss": 8175.0}),
        lambda: StrategyDefinition("NIFTY", DEFINITION.legs, risk_limits=(("max_loss", D("1")), ("max_loss", D("2")))),
        lambda: StrategyDefinition("NIFTY", DEFINITION.legs, preferences={"style": ""}),
        lambda: StrategyDefinition("NIFTY", DEFINITION.legs, rules_ref="  "),
    ]
    for index, case in enumerate(cases):
        with pytest.raises(DefinitionError):
            case()
            pytest.fail(f"case {index} was accepted")


def test_live_state_rejects_invalid_input():
    """AC-1 red: naive timestamp, bid above ask, duplicate leg quote, float price, negative volume, bad names."""
    ok = live("23200", "0")
    cases = [
        lambda: dataclasses.replace(ok, as_of=datetime.datetime(2026, 10, 1, 10, 0)),
        lambda: LegQuote(0, bid=D("39"), ask=D("38")),
        lambda: dataclasses.replace(ok, leg_quotes=(LegQuote(0), LegQuote(0))),
        lambda: dataclasses.replace(ok, spot=D(23200.1)),
        lambda: LegQuote(0, volume=-1),
        lambda: LegQuote(0, oi=10**13),
        lambda: LegQuote(20),
        lambda: dataclasses.replace(ok, pnl=1365.0),
        lambda: dataclasses.replace(ok, distances=(("to_be", D("1")), ("to_be", D("2")))),
        lambda: dataclasses.replace(ok, trigger_state=(("rule", "yes"),)),
        lambda: dataclasses.replace(ok, data_health="available"),
    ]
    for index, case in enumerate(cases):
        with pytest.raises(LiveStateError):
            case()
            pytest.fail(f"case {index} was accepted")
