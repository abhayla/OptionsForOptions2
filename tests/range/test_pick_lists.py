"""AC-3/AC-5/AC-6/AC-7 tests: expected-market-range pick lists (REQ-026).

Fixture: tests/fixtures/instruments/instruments_slice.csv (the same real Zerodha instrument-list
slice used by tests/instruments/test_catalogue.py, captured 2026-09-29).

Hand-computed expected values (measured directly from the fixture with a throwaway script, NOT
derived from running this module's own code):

    NIFTY  2026-09-29: option strikes 15000..34500 (min=15000, max=34500)
    NIFTY  2026-10-06: option strikes 20800..25800 (min=20800, max=25800)
    SENSEX 2026-10-01: option strikes 68000..83100 (min=68000, max=83100)
    SENSEX 2026-10-08: option strikes 68000..82700 (min=68000, max=82700)

Caps (ADR-042 defaults): NIFTY 3,000 points, SENSEX 9,000 points, measured from the current level.

NIFTY current = 23,237 (chosen: not a multiple of 100, inside every NIFTY expiry's strike range).
    2026-09-29: lower bound = max(15000, 23237-3000=20237) = 20237 (cap binds; strikes go
        further). 23237-20237 = 3000 = exactly 30 steps of 100 -> 31 values, last = 20237.
        upper bound = min(34500, 23237+3000=26237) = 26237 (cap binds). 31 values, last = 26237.
    2026-10-06: lower bound = max(20800, 20237) = 20800 (STRIKE binds — strikes run out before the
        cap). 23237-20800 = 2437; last step with value >= 20800 is step 24 (2400) -> 20837 (step 25
        = 2500 -> 20737 < 20800, excluded). 25 values, last = 20837.
        upper bound = min(25800, 26237) = 25800 (STRIKE binds). 25800-23237 = 2563; last step with
        value <= 25800 is step 25 (2500) -> 25737 (step 26 = 2600 -> 25837 > 25800, excluded).
        26 values, last = 25737.

SENSEX current = 81,422 (not a multiple of 100, inside every SENSEX expiry's strike range).
    2026-10-01: lower bound = max(68000, 81422-9000=72422) = 72422 (cap binds). 81422-72422 = 9000
        = exactly 90 steps -> 91 values, last = 72422.
        upper bound = min(83100, 81422+9000=90422) = 83100 (STRIKE binds — furthest strike is
        inside the cap). 83100-81422 = 1678; last step <= 1678 is step 16 (1600) -> 83022 (step 17
        = 1700 -> 83122 > 83100, excluded). 17 values, last = 83022.
    2026-10-08: lower bound = max(68000, 72422) = 72422 (cap binds, same as above). 91 values.
        upper bound = min(82700, 90422) = 82700 (STRIKE binds). 82700-81422 = 1278; last step <=
        1278 is step 12 (1200) -> 82622 (step 13 = 1300 -> 82722 > 82700, excluded). 13 values,
        last = 82622.

NIFTY current-on-a-round-hundred case: current = 23,200 (2026-09-29 expiry). Same bound
computation, first value is still exactly the current level (23200), second value 23100 (not
double-counted).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.instruments.catalogue import Catalogue
from ofo.instruments.parser import parse_instruments_csv
from ofo.range.pick_lists import (
    ExpectedRange,
    RangeCaps,
    build_pick_list,
    choose_range,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "instruments" / "instruments_slice.csv"

NIFTY_NEAR_EXPIRY = date(2026, 9, 29)
NIFTY_FAR_EXPIRY = date(2026, 10, 6)
SENSEX_NEAR_EXPIRY = date(2026, 10, 1)
SENSEX_FAR_EXPIRY = date(2026, 10, 8)

NIFTY_CURRENT = Decimal("23237")
NIFTY_CURRENT_ROUND = Decimal("23200")
SENSEX_CURRENT = Decimal("81422")


@pytest.fixture()
def catalogue() -> Catalogue:
    contracts = parse_instruments_csv(FIXTURE)
    cat = Catalogue()
    cat.load(contracts)
    return cat


@pytest.fixture()
def caps() -> RangeCaps:
    return RangeCaps.defaults()


# --- Core proof: NIFTY, real current level, real expiry from the merged catalogue ---


def test_core_nifty_lower_list_capped_by_admin_setting(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-5 (core proof): NIFTY 2026-09-29 lower list is capped at current-3000 (strikes extend
    further, to 15000, so the Admin cap is the binding limiter, not the instrument master)."""
    lower = build_pick_list(catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT, caps, direction="lower")
    assert lower[0] == NIFTY_CURRENT
    assert lower[1] == NIFTY_CURRENT - Decimal("100")
    assert lower[-1] == Decimal("20237")
    assert len(lower) == 31
    assert lower == sorted(lower, reverse=True)


def test_core_nifty_upper_list_capped_by_admin_setting(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-5 (core proof): NIFTY 2026-09-29 upper list mirrors the lower list upward."""
    upper = build_pick_list(catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT, caps, direction="upper")
    assert upper[0] == NIFTY_CURRENT
    assert upper[1] == NIFTY_CURRENT + Decimal("100")
    assert upper[-1] == Decimal("26237")
    assert len(upper) == 31


def test_core_nifty_lower_value_above_current_is_refused(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-6/AC-5 (core proof): a lower value above the current level is refused — it is simply not
    an offered pick-list value, so choose_range rejects it."""
    with pytest.raises(ValueError, match="not an offered lower"):
        choose_range(
            catalogue,
            "NIFTY",
            NIFTY_NEAR_EXPIRY,
            NIFTY_CURRENT,
            caps,
            lower_choice=NIFTY_CURRENT + Decimal("100"),
            upper_choice=NIFTY_CURRENT,
        )


# --- AC-5: strike-bound vs cap-bound, both directions, both indices ---


def test_nifty_far_expiry_strike_bound_limits_both_directions(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-5: NIFTY 2026-10-06 strikes (20800..25800) run out before the 3,000-point cap in both
    directions, so the FURTHEST LISTED STRIKE binds, not the Admin cap."""
    lower = build_pick_list(catalogue, "NIFTY", NIFTY_FAR_EXPIRY, NIFTY_CURRENT, caps, direction="lower")
    upper = build_pick_list(catalogue, "NIFTY", NIFTY_FAR_EXPIRY, NIFTY_CURRENT, caps, direction="upper")
    assert lower[-1] == Decimal("20837")
    assert len(lower) == 25
    assert upper[-1] == Decimal("25737")
    assert len(upper) == 26


def test_sensex_near_expiry_upper_is_strike_bound_lower_is_cap_bound(
    catalogue: Catalogue, caps: RangeCaps
) -> None:
    """AC-5: SENSEX 2026-10-01 — lower list is cap-bound (strikes extend past the 9,000-point cap
    to 68000), upper list is strike-bound (furthest strike 83100 is inside the cap of 90422)."""
    lower = build_pick_list(catalogue, "SENSEX", SENSEX_NEAR_EXPIRY, SENSEX_CURRENT, caps, direction="lower")
    upper = build_pick_list(catalogue, "SENSEX", SENSEX_NEAR_EXPIRY, SENSEX_CURRENT, caps, direction="upper")
    assert lower[0] == SENSEX_CURRENT
    assert lower[-1] == Decimal("72422")
    assert len(lower) == 91
    assert upper[0] == SENSEX_CURRENT
    assert upper[-1] == Decimal("83022")
    assert len(upper) == 17


def test_sensex_far_expiry_both_bounds_hold(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-5: SENSEX 2026-10-08 — same cap-bound lower list as the near expiry; strike-bound upper
    list with a different furthest strike (82700 vs 83100)."""
    lower = build_pick_list(catalogue, "SENSEX", SENSEX_FAR_EXPIRY, SENSEX_CURRENT, caps, direction="lower")
    upper = build_pick_list(catalogue, "SENSEX", SENSEX_FAR_EXPIRY, SENSEX_CURRENT, caps, direction="upper")
    assert lower[-1] == Decimal("72422")
    assert len(lower) == 91
    assert upper[-1] == Decimal("82622")
    assert len(upper) == 13


# --- AC-3: both lists start at the current level; current-on-a-round-hundred case ---


def test_current_level_on_a_round_hundred_is_still_the_first_value_once(
    catalogue: Catalogue, caps: RangeCaps
) -> None:
    """AC-3: when the current level happens to be a multiple of 100, it is still the first list
    value exactly once (not skipped, not duplicated by the first 100-point step)."""
    lower = build_pick_list(
        catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT_ROUND, caps, direction="lower"
    )
    upper = build_pick_list(
        catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT_ROUND, caps, direction="upper"
    )
    assert lower[0] == NIFTY_CURRENT_ROUND
    assert lower[1] == Decimal("23100")
    assert lower.count(NIFTY_CURRENT_ROUND) == 1
    assert upper[0] == NIFTY_CURRENT_ROUND
    assert upper[1] == Decimal("23300")


def test_platform_never_prefills_an_assumed_range(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-3: the pick lists are pure functions of (current level, expiry, caps) — no default lower
    or upper value is baked in; both lists start exactly at current_level regardless of index."""
    lower = build_pick_list(catalogue, "SENSEX", SENSEX_NEAR_EXPIRY, SENSEX_CURRENT, caps, direction="lower")
    upper = build_pick_list(catalogue, "SENSEX", SENSEX_NEAR_EXPIRY, SENSEX_CURRENT, caps, direction="upper")
    assert lower[0] == upper[0] == SENSEX_CURRENT


# --- AC-6: lower never above current, upper never below current ---


def test_lower_list_never_exceeds_current_level(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-6: every value in the lower list is <= current_level."""
    lower = build_pick_list(catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT, caps, direction="lower")
    assert max(lower) == NIFTY_CURRENT
    assert all(v <= NIFTY_CURRENT for v in lower)


def test_upper_list_never_below_current_level(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-6: every value in the upper list is >= current_level."""
    upper = build_pick_list(catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT, caps, direction="upper")
    assert min(upper) == NIFTY_CURRENT
    assert all(v >= NIFTY_CURRENT for v in upper)


def test_upper_value_below_current_is_refused(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-6 negative case: an upper choice below the current level is refused."""
    with pytest.raises(ValueError, match="not an offered upper"):
        choose_range(
            catalogue,
            "NIFTY",
            NIFTY_NEAR_EXPIRY,
            NIFTY_CURRENT,
            caps,
            lower_choice=NIFTY_CURRENT,
            upper_choice=NIFTY_CURRENT - Decimal("100"),
        )


# --- AC-7: the range is an input, never a prediction ---


def test_expected_range_is_labelled_user_input(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-7: a validly chosen range is returned labelled 'user input', never a prediction."""
    chosen = choose_range(
        catalogue,
        "NIFTY",
        NIFTY_NEAR_EXPIRY,
        NIFTY_CURRENT,
        caps,
        lower_choice=Decimal("23037"),
        upper_choice=Decimal("23437"),
    )
    assert chosen.label == "user input"
    assert chosen.lower == Decimal("23037")
    assert chosen.upper == Decimal("23437")


def test_expected_range_is_immutable(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-7: the range object cannot be mutated after creation (frozen dataclass)."""
    chosen = choose_range(
        catalogue,
        "NIFTY",
        NIFTY_NEAR_EXPIRY,
        NIFTY_CURRENT,
        caps,
        lower_choice=NIFTY_CURRENT,
        upper_choice=NIFTY_CURRENT,
    )
    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError, a subclass of AttributeError
        chosen.lower = Decimal("0")  # type: ignore[misc]


def test_expected_range_rejects_a_non_user_input_label() -> None:
    """AC-7 negative case: constructing the range with any other label is refused — it must never
    be presented as a prediction."""
    with pytest.raises(ValueError, match="never a prediction"):
        ExpectedRange(
            name="NIFTY",
            expiry=NIFTY_NEAR_EXPIRY,
            lower=Decimal("23000"),
            upper=Decimal("23500"),
            label="predicted range",
        )


def test_expected_range_rejects_lower_above_upper() -> None:
    """Consistency guard: lower must never exceed upper, whatever produced the two values."""
    with pytest.raises(ValueError):
        ExpectedRange(
            name="NIFTY",
            expiry=NIFTY_NEAR_EXPIRY,
            lower=Decimal("23500"),
            upper=Decimal("23000"),
        )


# --- Input-domain checklist: typed values, float, unknown expiry ---


def test_typed_value_not_on_the_pick_list_is_refused(catalogue: Catalogue, caps: RangeCaps) -> None:
    """Input is by pick list only (AC-5): a typed value that is not a 100-point step away from the
    current level is refused even though it lies within the range."""
    with pytest.raises(ValueError, match="not an offered lower"):
        choose_range(
            catalogue,
            "NIFTY",
            NIFTY_NEAR_EXPIRY,
            NIFTY_CURRENT,
            caps,
            lower_choice=Decimal("23150"),  # 87 away from current, not a 100-point step
            upper_choice=NIFTY_CURRENT,
        )


def test_float_current_level_is_refused(catalogue: Catalogue, caps: RangeCaps) -> None:
    """Money/levels are Decimal end to end; a float current level fails closed."""
    with pytest.raises(ValueError, match="Decimal"):
        build_pick_list(catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, 23237.0, caps, direction="lower")  # type: ignore[arg-type]


def test_float_choice_is_refused(catalogue: Catalogue, caps: RangeCaps) -> None:
    """A float pick-list choice fails closed, never silently coerced."""
    with pytest.raises(ValueError, match="Decimal"):
        choose_range(
            catalogue,
            "NIFTY",
            NIFTY_NEAR_EXPIRY,
            NIFTY_CURRENT,
            caps,
            lower_choice=23237.0,  # type: ignore[arg-type]
            upper_choice=NIFTY_CURRENT,
        )


def test_unknown_expiry_is_refused(catalogue: Catalogue, caps: RangeCaps) -> None:
    """An expiry with no listed option contracts (unknown or not yet listed) fails closed."""
    with pytest.raises(ValueError, match="no option contracts found"):
        build_pick_list(catalogue, "NIFTY", date(2099, 1, 1), NIFTY_CURRENT, caps, direction="lower")


def test_unknown_underlying_is_refused(catalogue: Catalogue, caps: RangeCaps) -> None:
    """An underlying with no configured Admin cap fails closed rather than defaulting."""
    with pytest.raises(ValueError, match="no configured range cap"):
        build_pick_list(catalogue, "BANKNIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT, caps, direction="lower")


def test_invalid_direction_is_refused(catalogue: Catalogue, caps: RangeCaps) -> None:
    """Only 'lower' and 'upper' are valid directions — fail closed on anything else."""
    with pytest.raises(ValueError, match="direction"):
        build_pick_list(catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT, caps, direction="sideways")


# --- Mutation-style tests: a broken cap or strike limit must turn these red ---


def test_mutation_cap_must_bind_even_though_strikes_extend_further(
    catalogue: Catalogue, caps: RangeCaps
) -> None:
    """Mutation-style (discriminates a dropped cap): NIFTY 2026-09-29 strikes extend to 15000, a
    full 8,237 points below current — far past the 3,000-point cap. If the cap term were dropped
    from build_pick_list, the lower list would run all the way to 15000 (83 values) instead of
    stopping at 20237 (31 values). This test's exact length/last-value assertions go red under
    that mutation."""
    options_min_strike = Decimal("15000")
    lower = build_pick_list(catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT, caps, direction="lower")
    assert lower[-1] != options_min_strike
    assert lower[-1] == Decimal("20237")
    assert len(lower) == 31
    # Precondition proving the cap is genuinely the binding constraint here (not a fluke):
    assert NIFTY_CURRENT - caps.for_index("NIFTY") > options_min_strike


def test_mutation_strike_limit_must_bind_even_though_cap_allows_more(
    catalogue: Catalogue, caps: RangeCaps
) -> None:
    """Mutation-style (discriminates a dropped strike limit): NIFTY 2026-10-06 strikes stop at
    20800, well inside the 3,000-point cap floor of 20237. If the furthest-listed-strike term were
    dropped, the lower list would extend to 20237 (31 values) instead of stopping at 20837 (25
    values). This test's exact length/last-value assertions go red under that mutation."""
    cap_floor = NIFTY_CURRENT - caps.for_index("NIFTY")
    lower = build_pick_list(catalogue, "NIFTY", NIFTY_FAR_EXPIRY, NIFTY_CURRENT, caps, direction="lower")
    assert lower[-1] != cap_floor
    assert lower[-1] == Decimal("20837")
    assert len(lower) == 25
    # Precondition proving the strike limit is genuinely the binding constraint here:
    assert Decimal("20800") > cap_floor


def test_mutation_lower_choice_above_current_must_never_be_constructible(
    catalogue: Catalogue, caps: RangeCaps
) -> None:
    """Mutation-style (discriminates a broken AC-6 guard): if choose_range ever allowed
    lower > current (e.g. a membership check against the wrong list, or a list that included
    current+100), this ExpectedRange with lower > upper would be constructed silently. Instead the
    ValueError from ExpectedRange.__post_init__'s consistency guard — or, earlier, the pick-list
    membership check — must fire first."""
    with pytest.raises(ValueError):
        choose_range(
            catalogue,
            "NIFTY",
            NIFTY_NEAR_EXPIRY,
            NIFTY_CURRENT,
            caps,
            lower_choice=NIFTY_CURRENT + Decimal("500"),
            upper_choice=NIFTY_CURRENT,
        )
