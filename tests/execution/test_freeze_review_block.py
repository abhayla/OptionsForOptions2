"""AC-4 (REQ-054, ADR-081): on the order review a leg whose units are not below the contract's stored freeze limit is
blocked with the reason and the limit; a leg with no stored limit carries the warning; nothing is split.

Values: NIFTY26O1923550CE (token 47185) has freeze limit 3511 on NSE's 15 Oct 2026 file and lot 65 (F-36, real row).
3511 = 54 x 65 + 1, so 54 lots = 3,510 units is the largest allowed order and 55 lots = 3,575 units is blocked.
Tests marked synthetic use lot 1 so that units == limit is reachable (a real lot of 65 never lands on 3,511)."""
from __future__ import annotations

import datetime
import pathlib

import pytest
from plan_inputs import CE, SELL, FakeMargin, leg

from ofo.errors.templates import display_text
from ofo.execution.freeze import STALE_AFTER_DAYS, StoredFreeze, freeze_check, largest_allowed_units
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.execution.review import execution_review

SYMBOL = "NIFTY26O1923550CE"
EXPIRY = datetime.date(2026, 10, 19)
TODAY = datetime.date(2026, 10, 16)
REAL = StoredFreeze(limit=3511, lot=65, file_date=datetime.date(2026, 10, 15))


def plan_of(units: int, symbol: str = SYMBOL) -> ExecutionPlan:
    lg = leg(SELL, CE, "23550", qty=units, expiry=EXPIRY)
    return ExecutionPlan("S-1", (PlannedLeg("leg-1", symbol, lg),))


def review(units: int, limits):
    return execution_review(plan_of(units), FakeMargin({}), freeze_limits=limits, today=TODAY)


def test_core_55_lots_blocked_54_lots_passes() -> None:
    """AC-4 core: 3,575 units (55 lots) is blocked, 3,510 units (54 lots) passes, on the real limit 3511."""
    blocked = review(55 * 65, {SYMBOL: REAL})
    assert blocked.can_execute is False
    [finding] = blocked.blocked
    assert (finding.leg_ref, finding.contract) == ("leg-1", SYMBOL)
    text = display_text(finding.message)
    assert "3575 units (55 lots)" in text
    assert "3511 units" in text
    assert "3510 units (54 lots)" in text
    assert blocked.warnings == ()
    ok = review(54 * 65, {SYMBOL: REAL})
    assert ok.can_execute is True and ok.blocked == () and ok.warnings == ()


def test_largest_allowed_is_limit_minus_one_rounded_to_lots() -> None:
    """AC-4: F-36 arithmetic by hand: 3511 - 1 = 3510 = 54 x 65; BANKNIFTY 1441 -> 1440 = 48 x 30."""
    assert largest_allowed_units(REAL) == 3510
    assert largest_allowed_units(StoredFreeze(1441, 30, datetime.date(2026, 10, 15))) == 1440
    # synthetic: a limit that IS a lot multiple (3510 = 54 x 65): an order of 3,510 is not below it, so 53 lots is the top
    assert largest_allowed_units(StoredFreeze(3510, 65, datetime.date(2026, 10, 15))) == 3445


def test_boundary_units_equal_to_limit_is_blocked_synthetic() -> None:
    """AC-4 (synthetic, lot 1): limit 100 -> 99 passes, 100 blocks, 101 blocks. Kills `<` mutated to `<=`."""
    stored = StoredFreeze(limit=100, lot=1, file_date=datetime.date(2026, 10, 15))
    assert freeze_check(plan_of(99), {SYMBOL: stored}, today=TODAY).blocks == ()
    assert len(freeze_check(plan_of(100), {SYMBOL: stored}, today=TODAY).blocks) == 1
    assert len(freeze_check(plan_of(101), {SYMBOL: stored}, today=TODAY).blocks) == 1


def test_missing_limit_warns_and_never_blocks_or_passes_silently() -> None:
    """AC-4: no stored limit (none given, an empty map, or only another contract's limit) -> the warning, no block."""
    for limits in (None, {}, {"OTHERCONTRACT": REAL}):
        r = review(55 * 65, limits)
        assert r.can_execute is True and r.blocked == ()
        [w] = r.warnings
        assert w.contract == SYMBOL
        assert "Zerodha may reject a large order" in display_text(w.message)


def test_limits_are_matched_by_the_plan_contract_symbol_not_by_position() -> None:
    """AC-4: a limit stored for another symbol never applies to this leg."""
    other = {"OTHERCONTRACT": StoredFreeze(100, 1, datetime.date(2026, 10, 15))}
    assert freeze_check(plan_of(5000), other, today=TODAY).blocks == ()


def test_four_part_messages_and_codes() -> None:
    """AC-4 (REQ-065, ADR-086): both messages carry the four parts; the block says what it blocks."""
    blocked = review(55 * 65, {SYMBOL: REAL}).blocked[0].message
    warn = review(55 * 65, None).warnings[0].message
    for m in (blocked, warn):
        assert m.what_happened and m.impact and m.what_is_blocked and m.next_action
    assert blocked.code == "STRATEGY_VALIDATION_501" and warn.code == "STRATEGY_VALIDATION_502"
    assert "Reduce this leg to 54 lots or fewer" in blocked.next_action


def test_blocked_review_is_not_executable_and_slicing_is_left_as_it_was() -> None:
    """AC-4: ADR-081 'never split' - a blocked leg makes the review not executable. The existing entry sequence
    (REQ-058, unchanged by this item) still shows 3,575 units as slices of the 1,755 default; reported, not edited."""
    r = review(55 * 65, {SYMBOL: REAL})
    assert r.can_execute is False
    assert [ln.quantity for ln in r.sequence] == [1755, 1755, 65]


def test_stored_freeze_refuses_non_positive_and_bool() -> None:
    """AC-4: the stored limit and lot are positive integers; bool and 0 are refused."""
    d = datetime.date(2026, 10, 15)
    for limit, lot in ((0, 65), (-1, 65), (3511, 0), (True, 65), (3511, True), (3511.0, 65)):
        with pytest.raises(ValueError):
            StoredFreeze(limit, lot, d)


def test_review_still_needs_an_execution_plan() -> None:
    """AC-4: freeze_check never accepts a hand-built plan substitute."""
    with pytest.raises(ValueError):
        freeze_check("plan", {}, today=TODAY)  # type: ignore[arg-type]


def test_freeze_limits_is_a_required_argument() -> None:
    """AC-4 (fail closed): execution_review cannot be called without freeze_limits; omission is a TypeError, not a
    silent pass. None is the explicit 'no limits known' and warns."""
    with pytest.raises(TypeError):
        execution_review(plan_of(54 * 65), FakeMargin({}))  # type: ignore[call-arg]
    assert execution_review(plan_of(54 * 65), FakeMargin({}), freeze_limits=None, today=TODAY).warnings


def test_units_that_are_not_a_lot_multiple_are_refused() -> None:
    """AC-4: 3,576 units against lot 65 is not a whole number of lots: refused, never floored to 55 lots."""
    with pytest.raises(ValueError, match="whole number of lots"):
        freeze_check(plan_of(3576), {SYMBOL: REAL}, today=TODAY)


def _adapter_inputs():
    """Real fixture rows -> parsed file -> catalogue join -> stored limits keyed by InstrumentId (what the store holds)."""
    from decimal import Decimal

    from ofo.instruments.catalogue import Catalogue
    from ofo.instruments.freeze_file import match_to_catalogue, parse_freeze_file
    from ofo.instruments.parser import zerodha_listed

    path = pathlib.Path(__file__).parent.parent / "fixtures" / "exchange" / "NSE_FO_contract_15102026_sample.csv"
    parsed = parse_freeze_file(path, nse_name="NSE_FO_contract_15102026.csv.gz")
    listed = zerodha_listed(
        instrument_token=47185 * 256 + 9, exchange_token=47185, tradingsymbol=SYMBOL, name="NIFTY", expiry=EXPIRY,
        strike=Decimal("23550"), tick_size=Decimal("0.05"), lot_size=65, instrument_type="CE", segment="NFO-OPT",
        exchange="NFO", seen_on=datetime.date(2026, 10, 15))
    catalogue = Catalogue()
    catalogue.load([listed])
    join = match_to_catalogue(parsed, catalogue)
    return catalogue, {m.instrument_id: (m.freeze_limit, parsed.file_date) for m in join.matched}


def test_store_to_adapter_to_review_on_real_rows() -> None:
    """AC-4 core, no hand-built dict: stored limit of token 47185 (3511, 2026-10-15) -> adapter (lot 65 from the
    catalogue) -> review: 55 lots blocked, 54 lots passes."""
    from ofo.execution.freeze import freeze_limits_for_plan

    catalogue, stored = _adapter_inputs()
    assert stored and list(stored.values()) == [(3511, datetime.date(2026, 10, 15))]
    for units, allowed in ((55 * 65, False), (54 * 65, True)):
        plan = plan_of(units)
        limits = freeze_limits_for_plan(plan, catalogue, stored)
        assert limits == {SYMBOL: StoredFreeze(3511, 65, datetime.date(2026, 10, 15))}
        assert execution_review(plan, FakeMargin({}), freeze_limits=limits, today=TODAY).can_execute is allowed


def test_adapter_gives_no_entry_for_an_unknown_or_unstored_symbol() -> None:
    """AC-4: a symbol the catalogue does not hold, or holds with no stored limit, gets no entry, so the review warns."""
    from ofo.execution.freeze import freeze_limits_for_plan

    catalogue, stored = _adapter_inputs()
    assert freeze_limits_for_plan(plan_of(65, "OTHERCONTRACT"), catalogue, stored) == {}
    assert freeze_limits_for_plan(plan_of(65), catalogue, {}) == {}
    r = execution_review(plan_of(55 * 65, "OTHERCONTRACT"), FakeMargin({}),
                         freeze_limits=freeze_limits_for_plan(plan_of(65, "OTHERCONTRACT"), catalogue, stored), today=TODAY)
    assert r.can_execute and len(r.warnings) == 1


def test_adapter_takes_the_lot_from_the_catalogue_not_the_caller() -> None:
    """AC-4: the adapter has no lot parameter; with the catalogue's lot 65 a 3,575-unit leg is 55 lots in the message."""
    from ofo.execution.freeze import freeze_limits_for_plan

    catalogue, stored = _adapter_inputs()
    limits = freeze_limits_for_plan(plan_of(55 * 65), catalogue, stored)
    assert limits[SYMBOL].lot == 65


def test_two_catalogue_entries_for_one_symbol_give_no_entry_so_the_review_warns() -> None:
    """AC-4: a Zerodha symbol carried by two catalogue contracts is ambiguous (F-03): no limit entry, the warning.
    Kills `len(entries) != 1` mutated to `not entries`."""
    import dataclasses
    from decimal import Decimal

    from ofo.execution.freeze import freeze_limits_for_plan
    from ofo.instruments.catalogue import Catalogue
    from ofo.instruments.parser import zerodha_listed

    def listed(token: int):
        return zerodha_listed(
            instrument_token=token * 256 + 9, exchange_token=token, tradingsymbol=SYMBOL, name="NIFTY", expiry=EXPIRY,
            strike=Decimal("23550"), tick_size=Decimal("0.05"), lot_size=65, instrument_type="CE", segment="NFO-OPT",
            exchange="NFO", seen_on=datetime.date(2026, 10, 15))

    catalogue = Catalogue()
    catalogue.load([listed(47185), listed(47999)])
    assert len(catalogue.entries_for_broker_symbol("zerodha", SYMBOL)) == 2
    stored = {e.id: (3511, datetime.date(2026, 10, 15)) for e in catalogue.all_entries()}
    limits = freeze_limits_for_plan(plan_of(55 * 65), catalogue, stored)
    assert limits == {}
    r = execution_review(plan_of(55 * 65), FakeMargin({}), freeze_limits=limits, today=TODAY)
    assert r.can_execute and len(r.warnings) == 1 and dataclasses.is_dataclass(r)


FILE_DATE = datetime.date(2026, 10, 15)
STALE_TEXT = ("The freeze limit for NIFTY26O1923550CE was last read from the exchange file of 15 Oct 2026, "
              "9 days ago. It may have changed; Zerodha may reject a large order.")


def test_core_8_days_old_no_warning_9_days_old_warns_real_limit() -> None:
    """Issue 257 core: NIFTY 3511 / lot 65 / file 2026-10-15: review on 2026-10-23 (8 days) no warning, 2026-10-24
    (9 days) warns; the 55-lot leg is blocked in both (the stale limit is still applied). Kills `>` to `>=`."""
    assert STALE_AFTER_DAYS == 8
    for day, stale in ((datetime.date(2026, 10, 23), False), (datetime.date(2026, 10, 24), True)):
        r = execution_review(plan_of(55 * 65), FakeMargin({}), freeze_limits={SYMBOL: REAL}, today=day)
        assert r.can_execute is False and len(r.blocked) == 1
        assert len(r.warnings) == (1 if stale else 0)
        fresh = execution_review(plan_of(54 * 65), FakeMargin({}), freeze_limits={SYMBOL: REAL}, today=day)
        assert fresh.can_execute is True and len(fresh.warnings) == (1 if stale else 0)
        if stale:
            [w] = r.warnings
            assert (w.leg_ref, w.contract) == ("leg-1", SYMBOL)
            assert display_text(w.message).startswith(STALE_TEXT)
            assert w.message.what_happened == STALE_TEXT


def test_stale_message_has_four_parts_and_its_own_code() -> None:
    day = datetime.date(2026, 10, 24)
    m = freeze_check(plan_of(54 * 65), {SYMBOL: REAL}, today=day).warnings[0].message
    assert m.what_happened and m.impact and m.what_is_blocked and m.next_action
    assert m.code == "STRATEGY_VALIDATION_503"
    assert "should" not in display_text(m).lower()


def test_no_stored_limit_gives_only_the_unknown_warning_no_stale_warning() -> None:
    for limits in (None, {}):
        [w] = freeze_check(plan_of(54 * 65), limits, today=datetime.date(2027, 1, 1)).warnings
        assert w.message.code == "STRATEGY_VALIDATION_502"


def test_future_file_date_gives_no_stale_warning_and_no_crash() -> None:
    future = StoredFreeze(3511, 65, datetime.date(2026, 10, 20))
    r = freeze_check(plan_of(55 * 65), {SYMBOL: future}, today=TODAY)
    assert r.warnings == () and len(r.blocks) == 1


def test_today_is_a_required_keyword() -> None:
    with pytest.raises(TypeError):
        freeze_check(plan_of(54 * 65), {SYMBOL: REAL})  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        execution_review(plan_of(54 * 65), FakeMargin({}), freeze_limits=None)  # type: ignore[call-arg]
