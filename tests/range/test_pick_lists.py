"""AC-3/AC-5/AC-6/AC-7 tests: expected-market-range pick lists (REQ-026).

Fixture: tests/fixtures/instruments/instruments_slice.csv (the same real Zerodha instrument-list
slice used by tests/instruments/test_catalogue.py, captured 2026-09-29).

Fix round 1 (verifier finding): the current level is usually not on the 100-point grid (e.g.
23,237 or 81,422); values must be SNAPPED to real listed strikes, not just offset from the current
level, or the list offers values that are not tradable strikes. When the furthest listed strike
binds the list, it must be reached exactly, even if it is not itself a 100-multiple.

Hand-computed expected values below come from an independent reference script that reads the CSV
fixture directly (NOT this module) and reimplements the algorithm from the REQ-026 note/AC-5 text:
snap to the current level's 100-multiple grid, skip any 100-multiple the catalogue does not list
for that expiry, stop at whichever of (Admin cap, furthest listed strike) binds first, and append
the furthest listed strike as a final value when it is the binding bound and off-grid.

    NIFTY  2026-09-29 (current 23,237, cap 3,000): far-OTM strikes are SPARSE in this real slice —
        20,300..20,700 (100-multiples) are simply not listed (only 19,500 and 20,800 exist in that
        gap) — so the cap-bound lower list (bound 20,237) actually stops at the last REAL strike
        reachable before the gap, 20,800: [23237, 23200, 23100, ..., 20800] (26 values).
        Upper (cap-bound, bound 26,237, dense listing): [23237, 23300, ..., 26200] (31 values).
    NIFTY  2026-10-06 (current 23,237, cap 3,000): strikes 20,800..25,800, dense, strike-bound both
        directions. Lower ends exactly at 20,800 (26 values) — the verifier's second failing case
        (old code stopped at 20,837). Upper ends exactly at 25,800 (27 values).
    SENSEX 2026-10-01 (current 81,422, cap 9,000): strikes 68,000..83,100, fully dense (gap 100).
        Lower is cap-bound (bound 72,422): [81422, 81400, 81300, ...] (91 values, last 72,500) —
        the verifier's first failing case (old code gave the non-strike 81,322/81,222). Upper is
        strike-bound, ends exactly at 83,100 (18 values).
    SENSEX 2026-10-08 (current 81,422, cap 9,000): strikes 68,000..82,700, dense. Lower: same as
        above (91 values, last 72,500). Upper strike-bound, ends exactly at 82,700 (14 values).
    NIFTY  2026-09-29, current ON a 100-multiple (23,200): first value is 23,200 once, second step
        is 23,100 (not duplicated); lower list is one shorter than the 23,237 case (25 values,
        still ending at 20,800); upper list is unaffected by the round current (31 values, ending
        26,200, same shape as the 23,237 case since upper direction's grid start differs only by
        which side of 23,200 it falls).

These were verified against the module with a throwaway script during development (not against
this file's own expectations — the script independently re-parses the CSV; see build round 2 notes)
and are asserted here as fixed hand-computed numbers.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ofo.instruments.catalogue import Catalogue
from ofo.instruments.models import Contract
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


def _synthetic_catalogue_with_offgrid_furthest_strike() -> Catalogue:
    """A hand-built catalogue whose furthest listed strike below the current level is NOT a
    100-multiple (20,850) — no such case exists in the real fixture (every real furthest strike
    happens to land on a round hundred), so this scenario is exercised with a small synthetic
    contract set, the same pattern used by the existing instruments test suite for a
    single-strike expiry."""
    expiry = date(2026, 11, 3)
    strikes = [Decimal(v) for v in (20850, 20900, 20950, 21000, 21050, 21100, 21150, 21200)]
    contracts = [
        Contract(
            instrument_token=90000 + i,
            exchange_token=9000 + i,
            tradingsymbol=f"NIFTY26NOV{int(strike)}CE",
            name="NIFTY",
            expiry=expiry,
            strike=strike,
            tick_size=Decimal("0.05"),
            lot_size=65,
            instrument_type="CE",
            segment="NFO-OPT",
            exchange="NFO",
        )
        for i, strike in enumerate(strikes)
    ]
    cat = Catalogue()
    cat.load(contracts)
    return cat, expiry


# --- Core proof: NIFTY, real current level, real expiry from the merged catalogue ---


def test_core_nifty_lower_list_snapped_to_real_strikes(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-5 (core proof, fix round 1): NIFTY 2026-09-29 lower list values are snapped to the
    current level's 100-grid and stop at the last REAL strike before the sparse far-OTM gap."""
    lower = build_pick_list(catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT, caps, direction="lower")
    assert lower[0] == NIFTY_CURRENT
    assert lower[1] == Decimal("23200")
    assert lower[-1] == Decimal("20800")
    assert len(lower) == 26
    assert lower == sorted(lower, reverse=True)


def test_core_nifty_upper_list_snapped_to_real_strikes(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-5 (core proof): NIFTY 2026-09-29 upper list mirrors the lower list upward (dense listing,
    no gaps in this direction)."""
    upper = build_pick_list(catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT, caps, direction="upper")
    assert upper[0] == NIFTY_CURRENT
    assert upper[1] == Decimal("23300")
    assert upper[-1] == Decimal("26200")
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


# --- Verifier's two failing cases, reproduced exactly ---


def test_verifier_case_sensex_81422_lower_list_is_on_the_strike_grid(
    catalogue: Catalogue, caps: RangeCaps
) -> None:
    """AC-5 (verifier finding): SENSEX current 81,422 must give 81422, 81400, 81300, ... — real
    listed strikes — never the old code's off-grid 81,322/81,222."""
    lower = build_pick_list(catalogue, "SENSEX", SENSEX_NEAR_EXPIRY, SENSEX_CURRENT, caps, direction="lower")
    assert lower[0] == Decimal("81422")
    assert lower[1] == Decimal("81400")
    assert lower[2] == Decimal("81300")
    assert Decimal("81322") not in lower
    assert Decimal("81222") not in lower
    assert lower[-1] == Decimal("72500")
    assert len(lower) == 91


def test_verifier_case_nifty_far_expiry_lower_list_ends_at_furthest_strike(
    catalogue: Catalogue, caps: RangeCaps
) -> None:
    """AC-5 (verifier finding): NIFTY 2026-10-06 lower list must end exactly at the furthest
    listed strike, 20,800 — never the old code's overshoot-by-formula value of 20,837."""
    lower = build_pick_list(catalogue, "NIFTY", NIFTY_FAR_EXPIRY, NIFTY_CURRENT, caps, direction="lower")
    assert lower[-1] == Decimal("20800")
    assert Decimal("20837") not in lower
    assert len(lower) == 26


# --- AC-5: strike-bound vs cap-bound, both directions, both indices ---


def test_nifty_far_expiry_strike_bound_limits_both_directions(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-5: NIFTY 2026-10-06 strikes (20800..25800) run out before the 3,000-point cap in both
    directions, so the FURTHEST LISTED STRIKE binds, and the list reaches it exactly."""
    lower = build_pick_list(catalogue, "NIFTY", NIFTY_FAR_EXPIRY, NIFTY_CURRENT, caps, direction="lower")
    upper = build_pick_list(catalogue, "NIFTY", NIFTY_FAR_EXPIRY, NIFTY_CURRENT, caps, direction="upper")
    assert lower[-1] == Decimal("20800")
    assert len(lower) == 26
    assert upper[-1] == Decimal("25800")
    assert len(upper) == 27


def test_sensex_near_expiry_upper_is_strike_bound_lower_is_cap_bound(
    catalogue: Catalogue, caps: RangeCaps
) -> None:
    """AC-5: SENSEX 2026-10-01 — lower list is cap-bound (dense strikes extend past the 9,000-point
    cap), upper list is strike-bound and reaches the furthest strike, 83,100, exactly."""
    lower = build_pick_list(catalogue, "SENSEX", SENSEX_NEAR_EXPIRY, SENSEX_CURRENT, caps, direction="lower")
    upper = build_pick_list(catalogue, "SENSEX", SENSEX_NEAR_EXPIRY, SENSEX_CURRENT, caps, direction="upper")
    assert lower[0] == SENSEX_CURRENT
    assert lower[-1] == Decimal("72500")
    assert len(lower) == 91
    assert upper[0] == SENSEX_CURRENT
    assert upper[-1] == Decimal("83100")
    assert len(upper) == 18


def test_sensex_far_expiry_both_bounds_hold(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-5: SENSEX 2026-10-08 — same cap-bound lower list as the near expiry; strike-bound upper
    list reaching a different furthest strike (82,700 vs 83,100), exactly."""
    lower = build_pick_list(catalogue, "SENSEX", SENSEX_FAR_EXPIRY, SENSEX_CURRENT, caps, direction="lower")
    upper = build_pick_list(catalogue, "SENSEX", SENSEX_FAR_EXPIRY, SENSEX_CURRENT, caps, direction="upper")
    assert lower[-1] == Decimal("72500")
    assert len(lower) == 91
    assert upper[-1] == Decimal("82700")
    assert len(upper) == 14


# --- AC-5 fix round 1: a furthest listed strike that is NOT a 100-multiple must still be reached ---


def test_furthest_strike_not_a_100_multiple_is_still_the_final_value() -> None:
    """AC-5 (fix round 1 rule): when the binding bound is the furthest listed strike and that
    strike is off the 100-grid (20,850), it is appended as the final list value regardless, so the
    list genuinely reaches it, per the REQ-026 note ("every value is a real strike") combined with
    AC-5's "runs ... to the furthest listed strike"."""
    cat, expiry = _synthetic_catalogue_with_offgrid_furthest_strike()
    caps = RangeCaps({"NIFTY": Decimal("1000")})
    current = Decimal("21237")
    lower = build_pick_list(cat, "NIFTY", expiry, current, caps, direction="lower")
    # current-cap floor = 20237; furthest listed strike = 20850 > 20237, so the strike binds.
    assert lower == [
        Decimal("21237"),
        Decimal("21200"),
        Decimal("21100"),
        Decimal("21000"),
        Decimal("20900"),
        Decimal("20850"),  # off-grid final value — the furthest real strike, not a 100-multiple
    ]
    assert lower[-1] == Decimal("20850")


# --- AC-3: both lists start at the current level; current-on-a-round-hundred case ---


def test_current_level_on_a_round_hundred_is_still_the_first_value_once(
    catalogue: Catalogue, caps: RangeCaps
) -> None:
    """AC-3: when the current level happens to be a multiple of 100, it is still the first list
    value exactly once (not skipped, not duplicated by the first grid step)."""
    lower = build_pick_list(
        catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT_ROUND, caps, direction="lower"
    )
    upper = build_pick_list(
        catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT_ROUND, caps, direction="upper"
    )
    assert lower[0] == NIFTY_CURRENT_ROUND
    assert lower[1] == Decimal("23100")
    assert lower.count(NIFTY_CURRENT_ROUND) == 1
    assert lower[-1] == Decimal("20800")
    assert len(lower) == 25
    assert upper[0] == NIFTY_CURRENT_ROUND
    assert upper[1] == Decimal("23300")
    assert upper.count(NIFTY_CURRENT_ROUND) == 1
    assert len(upper) == 31


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
        lower_choice=Decimal("23100"),
        upper_choice=Decimal("23300"),
    )
    assert chosen.label == "user input"
    assert chosen.lower == Decimal("23100")
    assert chosen.upper == Decimal("23300")


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
    """Input is by pick list only (AC-5): a typed value that is not offered (not a real strike on
    the current level's grid) is refused even though it lies within the range."""
    with pytest.raises(ValueError, match="not an offered lower"):
        choose_range(
            catalogue,
            "NIFTY",
            NIFTY_NEAR_EXPIRY,
            NIFTY_CURRENT,
            caps,
            lower_choice=Decimal("23150"),  # not a value this list offers
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


def test_every_value_after_the_first_is_a_listed_strike(catalogue: Catalogue, caps: RangeCaps) -> None:
    """AC-5 (fix round 1 rule): assert over the real fixture, both indices, both directions, that
    every pick-list value after the first is a strike the catalogue actually lists for that
    expiry (the first value is the current level itself, which need not be a strike)."""
    cases = [
        ("NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT),
        ("NIFTY", NIFTY_FAR_EXPIRY, NIFTY_CURRENT),
        ("SENSEX", SENSEX_NEAR_EXPIRY, SENSEX_CURRENT),
        ("SENSEX", SENSEX_FAR_EXPIRY, SENSEX_CURRENT),
    ]
    for name, expiry, current in cases:
        listed = {
            c.strike
            for c in catalogue.contracts_for(name, expiry, instrument_types=frozenset({"CE", "PE"}))
        }
        for direction in ("lower", "upper"):
            values = build_pick_list(catalogue, name, expiry, current, caps, direction=direction)
            for v in values[1:]:
                assert v in listed, f"{name} {expiry} {direction}: {v} is not a listed strike"


# --- Mutation-style tests: a broken cap, strike limit, or snap must turn these red ---


def test_mutation_cap_must_bind_even_though_strikes_extend_further(
    catalogue: Catalogue, caps: RangeCaps
) -> None:
    """Mutation-style (discriminates a dropped cap): NIFTY 2026-09-29 dense strikes extend well
    past the 3,000-point cap floor of 20,237 (down toward 15,000). If the cap term were dropped
    from build_pick_list, the lower list would run much further than 20,800. This test's exact
    length/last-value assertions go red under that mutation."""
    lower = build_pick_list(catalogue, "NIFTY", NIFTY_NEAR_EXPIRY, NIFTY_CURRENT, caps, direction="lower")
    assert lower[-1] == Decimal("20800")
    assert len(lower) == 26
    # Precondition: the cap floor (20237) is below the actual last value (20800), proving the cap
    # is genuinely constraining here relative to what dense listing would otherwise allow further out.
    assert NIFTY_CURRENT - caps.for_index("NIFTY") < Decimal("20800")


def test_mutation_strike_limit_must_bind_even_though_cap_allows_more(
    catalogue: Catalogue, caps: RangeCaps
) -> None:
    """Mutation-style (discriminates a dropped strike limit): NIFTY 2026-10-06 strikes stop at
    20,800, well inside the 3,000-point cap floor of 20,237. If the furthest-listed-strike term
    were dropped, the lower list would extend past 20,800 toward 20,237. This test's exact
    length/last-value assertions go red under that mutation."""
    cap_floor = NIFTY_CURRENT - caps.for_index("NIFTY")
    lower = build_pick_list(catalogue, "NIFTY", NIFTY_FAR_EXPIRY, NIFTY_CURRENT, caps, direction="lower")
    assert lower[-1] != cap_floor
    assert lower[-1] == Decimal("20800")
    assert len(lower) == 26
    # Precondition proving the strike limit is genuinely the binding constraint here:
    assert Decimal("20800") > cap_floor


def test_mutation_snap_must_land_on_real_strikes_not_raw_offsets(
    catalogue: Catalogue, caps: RangeCaps
) -> None:
    """Mutation-style (discriminates a dropped snap): SENSEX current 81,422 is off-grid; without
    snapping to 100-multiples, an offset-from-current scheme would produce 81,322 and 81,222,
    neither of which is a listed strike. The snapped list must never contain them."""
    lower = build_pick_list(catalogue, "SENSEX", SENSEX_NEAR_EXPIRY, SENSEX_CURRENT, caps, direction="lower")
    assert Decimal("81322") not in lower
    assert Decimal("81222") not in lower
    assert lower[1] == Decimal("81400")


def test_mutation_final_furthest_strike_value_must_be_present(
    catalogue: Catalogue, caps: RangeCaps
) -> None:
    """Mutation-style (discriminates a dropped final-value append): NIFTY 2026-10-06 upper list is
    strike-bound at 25,800. If the "append the furthest strike as the final value" step were
    dropped, the natural grid stepping alone must still reach it here (25,800 is a 100-multiple)
    — so this test also covers the off-grid case via the synthetic-catalogue test above; here it
    additionally pins the real-fixture strike-bound endpoint so any regression that removes the
    bound entirely (reverting to plain cap-based stepping) is caught by the mismatch with the cap
    floor 26,237."""
    upper = build_pick_list(catalogue, "NIFTY", NIFTY_FAR_EXPIRY, NIFTY_CURRENT, caps, direction="upper")
    assert upper[-1] == Decimal("25800")
    assert upper[-1] != NIFTY_CURRENT + caps.for_index("NIFTY")


def test_mutation_offgrid_final_value_must_be_appended() -> None:
    """Mutation-style (discriminates a dropped final-value append, off-grid case): using the
    synthetic catalogue whose furthest listed strike (20,850) is NOT a 100-multiple, if the
    "append the furthest strike as the final value" step were dropped, the list would stop at the
    last on-grid value (20,900) and never reach 20,850. This test's exact final-value assertion
    goes red under that mutation."""
    cat, expiry = _synthetic_catalogue_with_offgrid_furthest_strike()
    caps = RangeCaps({"NIFTY": Decimal("1000")})
    lower = build_pick_list(cat, "NIFTY", expiry, Decimal("21237"), caps, direction="lower")
    assert lower[-1] == Decimal("20850")
    assert lower[-1] != Decimal("20900")


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
