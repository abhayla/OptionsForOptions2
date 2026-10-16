"""ADR-095 / ADR-080 (3) / REQ-056 AC-7: the strategy-level tolerance split pro rata into per-leg protected limits.

Spec basis: ADR-095 "each leg gets the share of it that its planned value (planned premium x quantity) has of the sum
of all legs' planned values"; ADR-080 (3) "price protection splits the user's strategy-level tolerance into per-leg
limits". Real input: the 12:08:52 IST quotes of 2026-10-16 for the four NIFTY 19 Oct 2026 iron-condor legs
(``tests/fixtures/kite_quotes/iron-condor-2026-10-16.json``, copied from the recorded ``quote NIFTY 2026-10-19``
reply), lot 65, tick 0.05.
"""
from __future__ import annotations

import json
import random
from decimal import Decimal as D
from decimal import localcontext
from pathlib import Path

import pytest
from ofo.engine import Action
from ofo.engine.executable_price import Depth, depth_from_quote, round_to_tick
from ofo.engine.price_protection import PlannedLeg, protected_limits

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/kite_quotes/iron-condor-2026-10-16.json"
TICK = D("0.05")
NO_DEPTH = Depth(bids=(), asks=())
ON_TICK_IN_FIVE = 4  # property cases: 4 in 5 planned prices on the tick, the rest any paisa


@pytest.fixture(scope="module")
def real() -> dict:
    return json.loads(FIXTURE.read_text(), parse_float=D)


def _real_legs(real: dict) -> list[PlannedLeg]:
    return [PlannedLeg(Action(leg["side"]), leg["quantity"], leg["last_price"], depth_from_quote(leg))
            for leg in real["legs"]]


def _leg(side: Action, quantity: int, price: str) -> PlannedLeg:
    return PlannedLeg(side, quantity, D(price), NO_DEPTH)


def test_core_real_iron_condor_tolerance_300(real):
    """Core, hand-computed. Planned value 65 x (29.80 + 58.15 + 40.55 + 16.25) = 9,408.75.
    BUY 22800PE: allowance 300 x 29.80 / 9408.75 = 0.9501..., 29.80 + 0.9501 = 30.7501 -> floor 30.75 (61.75 rupees).
    SELL 22950PE: 1.8541..., 58.15 - 1.8541 = 56.2958 -> ceil 56.30 (120.25). SELL 23250CE: 1.2929...,
    40.55 - 1.2929 = 39.2570 -> ceil 39.30 (81.25). BUY 23400CE: 0.5181..., 16.7681 -> floor 16.75 (32.50).
    Total 295.75 <= 300; every leg's depth today fills 65 inside its protected limit."""
    assert real["tick"] == TICK and [leg["quantity"] for leg in real["legs"]] == [65] * 4
    result = protected_limits(_real_legs(real), D("300"), TICK)
    sides = [leg.side for leg in result.legs]
    assert sides == [Action.BUY, Action.SELL, Action.SELL, Action.BUY]
    assert [leg.planned_price for leg in result.legs] == [D("29.8"), D("58.15"), D("40.55"), D("16.25")]
    assert [leg.limit for leg in result.legs] == [D("30.75"), D("56.30"), D("39.30"), D("16.75")]
    assert [leg.adverse for leg in result.legs] == [D("61.75"), D("120.25"), D("81.25"), D("32.50")]
    assert result.total_adverse == D("295.75") <= D("300")
    # shares: the pro-rata rupees rounded down to the paisa, e.g. 300 x 1937.00 / 9408.75 = 61.7616... for the BUY PE
    assert [leg.share for leg in result.legs] == [D("61.76"), D("120.51"), D("84.04"), D("33.67")]
    assert sum(leg.share for leg in result.legs) <= D("300")
    # today's depth: best ask 29.75 / bid 58.60 / bid 40.50 / ask 16.30 cover 65 on every leg
    assert [leg.executable_limit for leg in result.legs] == [D("29.75"), D("58.60"), D("40.50"), D("16.30")]
    assert [leg.fills_within for leg in result.legs] == [True] * 4


def test_fills_within_false_when_depth_is_worse_than_the_protected_limit(real):
    """A 1-paisa tolerance on the real legs (limits = planned prices): BUY 22800PE 29.80 vs ask 29.75 fills; SELL
    22950PE 58.15 vs bid 58.60 fills; SELL 23250CE 40.55 vs bid 40.50 does not; BUY 23400CE 16.25 vs ask 16.30 does
    not. A leg with no depth never fills."""
    result = protected_limits(_real_legs(real), D("0.01"), TICK)
    assert [leg.limit for leg in result.legs] == [D("29.80"), D("58.15"), D("40.55"), D("16.25")]
    assert [leg.fills_within for leg in result.legs] == [True, True, False, False]
    empty = protected_limits([_leg(Action.BUY, 65, "10")], D("100"), TICK)
    assert empty.legs[0].fills_within is False and empty.legs[0].executable_limit is None


def test_eighty_percent_of_value_gets_eighty_percent_of_tolerance():
    """Checklist 4 (kills the equal-split mutation): values 80 and 20 of 100 -> shares exactly 80 and 20 of 100."""
    result = protected_limits([_leg(Action.BUY, 1, "80"), _leg(Action.SELL, 1, "20")], D("100"), TICK)
    assert [leg.share for leg in result.legs] == [D("80"), D("20")]
    assert [leg.limit for leg in result.legs] == [D("160"), D("0.05")]  # SELL 20 - 20 = 0 -> clamped to one tick
    assert result.total_adverse == D("80") + D("19.95")


def test_share_uses_unsigned_value_for_mixed_sides():
    """Checklist 6/7 (kills the signed-value mutation): a credit strategy's SELL legs count as positive value, so a
    signed sum (BUY - SELL) can never shrink or flip the shares."""
    legs = [_leg(Action.SELL, 75, "100"), _leg(Action.BUY, 75, "50"), _leg(Action.SELL, 75, "30"),
            _leg(Action.BUY, 75, "20")]
    result = protected_limits(legs, D("200"), TICK)
    assert [leg.share for leg in result.legs] == [D("100"), D("50"), D("30"), D("20")]
    # per unit: 100/75 = 1.333 -> SELL 98.6667 ceil 98.70; 0.6667 -> BUY 50.6667 floor 50.65;
    # 0.4 -> SELL 29.60; 0.2667 -> BUY 20.2667 floor 20.25
    assert [leg.limit for leg in result.legs] == [D("98.70"), D("50.65"), D("29.60"), D("20.25")]


def test_single_leg_gets_the_whole_tolerance():
    result = protected_limits([_leg(Action.BUY, 65, "100")], D("300"), TICK)
    # 300 / 65 = 4.615... -> 104.615 floor 104.60, 4.60 x 65 = 299.00
    assert result.legs[0].share == D("300") and result.legs[0].limit == D("104.60")
    assert result.total_adverse == D("299.00")


@pytest.mark.parametrize("side, planned, expected", [
    (Action.BUY, "10.00", "10.10"),  # 10 + 0.13 = 10.13 -> floor 10.10, never 10.15
    (Action.SELL, "10.00", "9.90"),  # 10 - 0.13 = 9.87 -> ceil 9.90, never 9.85
])
def test_rounding_toward_the_user(side, planned, expected):
    """Checklist 2 (kills the rounding-away mutation): allowance 13 rupees / 100 units = 0.13 per unit."""
    result = protected_limits([_leg(side, 100, planned)], D("13"), TICK)
    assert result.legs[0].limit == D(expected) and result.legs[0].adverse == D("10.00")


def test_one_paisa_tolerance_leaves_no_room(real):
    """Checklist 3: every leg's limit is its planned price rounded toward the user."""
    legs = [*_real_legs(real), _leg(Action.BUY, 65, "12.37"), _leg(Action.SELL, 65, "12.37")]
    result = protected_limits(legs, D("0.01"), TICK)
    for leg in result.legs:
        assert leg.limit == round_to_tick(leg.planned_price, TICK, leg.side)
    assert [leg.limit for leg in result.legs][-2:] == [D("12.35"), D("12.40")]


def test_sell_limit_clamped_at_one_tick():
    """Checklist 5: a SELL at 0.10 with 50 rupees of room on 65 units would go negative; it stops at 0.05."""
    result = protected_limits([_leg(Action.SELL, 65, "0.10")], D("50"), TICK)
    assert result.legs[0].limit == TICK and result.legs[0].adverse == D("3.25")


def test_zero_tolerance_is_allowed_and_gives_no_room():
    result = protected_limits([_leg(Action.BUY, 65, "29.80"), _leg(Action.SELL, 65, "58.15")], D("0"), TICK)
    assert [leg.limit for leg in result.legs] == [D("29.80"), D("58.15")] and result.total_adverse == 0


@pytest.mark.parametrize("legs, tolerance, match", [
    ([_leg(Action.BUY, 65, "10")], D("-0.01"), "tolerance"),
    ([_leg(Action.BUY, 65, "10")], 300, "tolerance"),
    ([_leg(Action.BUY, 65, "10")], 300.0, "tolerance"),
    ([_leg(Action.BUY, 65, "10")], D("NaN"), "tolerance"),
    ([], D("300"), "non-empty"),
    ([PlannedLeg(Action.BUY, 0, D("10"), NO_DEPTH)], D("300"), "quantity"),
    ([PlannedLeg(Action.BUY, -65, D("10"), NO_DEPTH)], D("300"), "quantity"),
    ([PlannedLeg(Action.BUY, 65, D("0"), NO_DEPTH)], D("300"), "planned_price"),
    ([PlannedLeg(Action.SELL, 65, D("-1"), NO_DEPTH)], D("300"), "planned_price"),
    ([PlannedLeg(Action.BUY, 65, 10.0, NO_DEPTH)], D("300"), "planned_price"),  # type: ignore[arg-type]
    ([PlannedLeg("BUY", 65, D("10"), NO_DEPTH)], D("300"), "side"),  # type: ignore[arg-type]
    ([PlannedLeg(Action.BUY, 65, D("10"), None)], D("300"), "depth"),  # type: ignore[arg-type]
])
def test_refuses_bad_input(legs, tolerance, match):
    with pytest.raises(ValueError, match=match):
        protected_limits(legs, tolerance, TICK)


def test_raw_limit_within_a_sub_tick_step_of_the_tick_still_rounds_toward_the_user():
    """The raw BUY limit lands within 1e-8 of the 1.05 tick and must still give 1.00. BUY 3,000,001 at 1.00 plus a SELL
    of 1 at 0.05: total value 3,000,001.05; share 150000.04 x 3000001 / 3000001.05 = 150000.0375 -> 150000.03;
    allowance 0.0499999933... -> raw 1.0499999933 (6.7e-9 under 1.05) -> floor 1.00. Cutting that raw price away
    from the user at the sub-tick step (ceil to 1.05000000) would hand the leg a tick it has no share for."""
    legs = [_leg(Action.BUY, 3_000_001, "1.00"), _leg(Action.SELL, 1, "0.05")]
    result = protected_limits(legs, D("150000.04"), TICK)
    assert result.legs[0].share == D("150000.03")
    assert result.legs[0].limit == D("1.00") and result.legs[0].adverse == 0
    assert result.legs[1].limit == TICK  # the SELL's share 0.00 leaves it at its planned 0.05


@pytest.mark.parametrize("planned, tick", [
    (10, D("0.05")), (True, D("0.05")), (D("10"), 1), (D("10"), True),
])
def test_price_and_tick_must_be_decimal_not_int_or_bool(planned, tick):
    with pytest.raises(ValueError, match="int, bool and float are refused"):
        protected_limits([PlannedLeg(Action.BUY, 65, planned, NO_DEPTH)], D("300"), tick)


def test_buy_below_one_tick_is_refused_not_loosened():
    """A BUY planned at 0.03 cannot have a limit of at least one tick inside a 0.01-rupee share: refused."""
    with pytest.raises(ValueError, match="one tick"):
        protected_limits([_leg(Action.BUY, 1, "0.03")], D("0.01"), TICK)


def test_property_adverse_never_exceeds_tolerance_and_limits_are_tightest_within_share():
    """Checklist 1, 2,000 random strategies of 1-4 legs, mixed sides, on- and off-tick prices."""
    rng = random.Random(95)  # noqa: S311 - a seeded, reproducible case generator, not security
    for _ in range(2000):
        legs = []
        for _ in range(rng.randint(1, 4)):
            side = rng.choice([Action.BUY, Action.SELL])
            quantity = rng.choice([rng.randint(1, 2000), 65 * rng.randint(1, 20)])
            on_tick = rng.randint(1, 5) <= ON_TICK_IN_FIVE
            price = D(rng.randint(1, 20000)) * TICK if on_tick else D(rng.randint(5, 100000)) / 100
            legs.append(_leg(side, quantity, str(price)))
        tolerance = D(rng.randint(0, 500000)) / 100
        result = protected_limits(legs, tolerance, TICK)
        total_value = sum(leg.planned_price * leg.quantity for leg in legs)
        assert result.total_adverse <= tolerance
        assert sum(leg.share for leg in result.legs) <= tolerance
        for leg in result.legs:
            with localcontext() as ctx:
                ctx.prec = 90
                exact_share = tolerance * leg.planned_price * leg.quantity / total_value
            assert leg.share <= exact_share and exact_share - leg.share < D("0.01")
            assert leg.limit > 0 and leg.limit % TICK == 0
            assert leg.adverse <= leg.share
            # tightest: one tick looser would exceed the share (unless the SELL clamp set the limit)
            looser = leg.limit + TICK if leg.side is Action.BUY else leg.limit - TICK
            looser_adverse = (looser - leg.planned_price if leg.side is Action.BUY
                              else leg.planned_price - looser) * leg.quantity
            if not (leg.side is Action.SELL and leg.limit == TICK):
                assert looser_adverse > leg.share
