"""REQ-060 AC-2 as refined by ADR-083: an expired leg is a settlement event, not a mismatch (W-085).

Core proof: a SENSEX calendar holding a leg that expired on 2026-10-15 and a later-expiry leg. After the close the
expired leg is closed at an injected settlement price with a timeline entry, reconciliation against Zerodha positions
that no longer show it reports no mismatch, and the strategy continues with the far leg. A single-expiry strategy
whose every leg expired becomes Exited through a recorded transition.

Real contracts: the SENSEX 2026-10-15 option rows come from the recorded catalogue
``tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv`` and the far leg is the real SENSEX future of
2026-10-29 from ``tests/fixtures/instruments/instruments_slice.csv`` (no later-expiry SENSEX OPTION row exists in any
recorded fixture; the slice holds only 10-15 and the 10-29 future). The settlement source is injected: it is
UNPROVEN against the exchange's real settlement price (ADR-083 consequences), so these tests prove the platform's
reaction, not the source.

Hand-computed expectations (units 20 = one SENSEX lot; engine formula position_pnl, SELL = (entry - value) x qty):
- short 72600 CE, entry 210.50, settled at 150.00: (210.50 - 150.00) x 20 = 1210.00
- short 72600 PE, entry 180.00, settled at 0.00:   (180.00 - 0.00) x 20 = 3600.00
"""
from __future__ import annotations

import csv
import datetime
import pathlib
from decimal import Decimal as D

import pytest

from ofo.engine import Action, Instrument
from ofo.reconciliation.compare import MismatchKind, compare
from ofo.reconciliation.settlement import SettlementError, settle_expired_legs
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.versions import ExecutionResult, OutcomeKind, ResultStatus, StrategyRecord, VersionError
from ofo.timeline.catalogue import EntryType
from ofo.timeline.log import Timeline

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
EXPIRY_DAY = datetime.date(2026, 10, 15)
FAR_EXPIRY = datetime.date(2026, 10, 29)
AFTER_CLOSE = datetime.datetime(2026, 10, 15, 16, 0, tzinfo=IST)
ENTERED = datetime.datetime(2026, 10, 12, 10, 0, tzinfo=IST)
NOW_CLOCK = datetime.datetime(2026, 10, 16, 9, 0, tzinfo=IST)


def clock() -> datetime.datetime:
    return NOW_CLOCK


def _catalogue_rows(path: pathlib.Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [row for row in csv.DictReader(handle) if row["name"] == "SENSEX"]


def _real_contract(rows: list[dict], kind: str, strike: str | None, expiry: datetime.date) -> tuple:
    """The contract of a real catalogue row; refuses to build one the recorded catalogue does not hold."""
    for row in rows:
        if row["instrument_type"] == kind and row["expiry"] == expiry.isoformat() and (
                kind == "FUT" or D(row["strike"]) == D(strike)):
            assert int(row["lot_size"]) == 20  # one SENSEX lot, as the catalogue says
            return ("SENSEX", Instrument[kind], None if kind == "FUT" else D(strike), expiry)
    raise AssertionError(f"no real SENSEX {kind} {strike} {expiry} in the recorded catalogue")


_OPTION_ROWS = _catalogue_rows(FIXTURES / "kite_ws" / "instruments-2026-10-08-subscribed.csv")
_SLICE_ROWS = _catalogue_rows(FIXTURES / "instruments" / "instruments_slice.csv")
SHORT_CE = _real_contract(_OPTION_ROWS, "CE", "72600", EXPIRY_DAY)
SHORT_PE = _real_contract(_OPTION_ROWS, "PE", "72600", EXPIRY_DAY)
FAR_FUT = _real_contract(_SLICE_ROWS, "FUT", None, FAR_EXPIRY)
ENTRY_PRICES = {SHORT_CE: D("210.50"), SHORT_PE: D("180.00"), FAR_FUT: D("72500.00")}
SETTLEMENT = {SHORT_CE: D("150.00"), SHORT_PE: D("0.00")}


def source_of(prices):
    return lambda contract: prices.get(contract)


def _active(legs) -> StrategyRecord:
    record = StrategyRecord(StrategyDefinition("SENSEX", tuple(legs)), at=ENTERED, clock=clock)
    version = record.propose_execution(at=ENTERED + datetime.timedelta(minutes=1))
    record.confirm(version.number, at=ENTERED + datetime.timedelta(minutes=2))
    record.apply_result(ExecutionResult(
        1, ResultStatus.COMPLETE, version.intended_position, ENTERED + datetime.timedelta(minutes=3), "exec-1"))
    assert record.active_version is not None and not record.reconciliation_required
    return record


def calendar() -> StrategyRecord:
    """Short 72600 CE expiring 2026-10-15 plus the long 2026-10-29 future (the far leg)."""
    return _active((
        DefinitionLeg(Action.SELL, Instrument.CE, D("72600"), EXPIRY_DAY, 20),
        DefinitionLeg(Action.BUY, Instrument.FUT, None, FAR_EXPIRY, 20),
    ))


def straddle() -> StrategyRecord:
    """Single-expiry strategy: short 72600 CE and PE, both expiring 2026-10-15."""
    return _active((
        DefinitionLeg(Action.SELL, Instrument.CE, D("72600"), EXPIRY_DAY, 20),
        DefinitionLeg(Action.SELL, Instrument.PE, D("72600"), EXPIRY_DAY, 20),
    ))


def settle(record, prices=SETTLEMENT, *, now=AFTER_CLOSE, entry_prices=ENTRY_PRICES, timeline=None):
    return settle_expired_legs(record, now, source_of(prices), entry_prices, timeline=timeline)


def recon(broker, **strategies):
    return compare(broker, strategies, None, at=AFTER_CLOSE, clock=clock)


# ---- the core ----------------------------------------------------------------------------------------------------

def test_core_calendar_expired_leg_settles_far_leg_continues_reconciliation_clean():
    record, timeline = calendar(), Timeline("CAL-1", clock=clock)

    result = settle(record, timeline=timeline)

    assert [leg.contract for leg in result.settled] == [SHORT_CE]
    assert result.settled[0].settlement_price == D("150.00")
    assert result.settled[0].units == -20
    assert result.settled[0].realized_pnl == D("1210.00")
    assert result.awaiting == () and not result.exited
    # The platform's books: only the far leg is left, the strategy is alive and not blocked.
    assert record.active_version.intended_position.as_dict() == {FAR_FUT: 20}
    assert not record.exited and not record.reconciliation_required and record.awaiting_settlement == frozenset()
    # One timeline entry names contract, settlement price, quantity and realized P&L.
    (entry,) = timeline.entries
    assert entry.kind is EntryType.EXIT and entry.at == AFTER_CLOSE
    detail = dict(entry.content)
    assert detail["event"] == "leg_settled" and detail["settlement_price"] == "150.00"
    assert detail["units"] == -20 and detail["realized_pnl"] == "1210.00" and "72600" in detail["contract"]
    # Zerodha no longer shows the expired leg: no mismatch of any kind.
    report = recon({FAR_FUT: 20}, CAL=record)
    assert report.mismatches == () and report.blocked_strategy_ids == frozenset()


def test_core_single_expiry_strategy_with_every_leg_expired_becomes_exited_by_recorded_transition():
    record, timeline = straddle(), Timeline("STR-1", clock=clock)

    result = settle(record, timeline=timeline)

    assert {leg.contract for leg in result.settled} == {SHORT_CE, SHORT_PE} and result.exited
    assert sorted(leg.realized_pnl for leg in result.settled) == [D("1210.00"), D("3600.00")]
    assert record.exited and not record.reconciliation_required
    last = record.outcomes[-1]  # the recorded transition, not an inference from an empty position
    assert last.kind is OutcomeKind.EXITED and last.at == AFTER_CLOSE and last.actual.lines == ()
    assert [e.kind for e in timeline.entries] == [EntryType.EXIT, EntryType.EXIT, EntryType.COMPLETION]
    assert dict(timeline.entries[-1].content)["event"] == "all_legs_settled"
    assert recon({}, STR=record).mismatches == ()


# ---- reconciliation kinds ---------------------------------------------------------------------------------------

def test_unsettled_expired_leg_absent_at_zerodha_is_awaiting_settlement_not_blocking():
    record = calendar()
    result = settle(record, prices={})  # no settlement price yet

    assert result.settled == () and result.awaiting == (SHORT_CE,)
    assert record.awaiting_settlement == frozenset({SHORT_CE})
    assert record.active_version.intended_position.as_dict() == {SHORT_CE: -20, FAR_FUT: 20}  # left open
    report = recon({FAR_FUT: 20}, CAL=record)
    (m,) = report.mismatches
    assert m.kind is MismatchKind.AWAITING_SETTLEMENT and m.difference == ((SHORT_CE, 20),) and not m.blocks
    assert report.blocked_strategy_ids == frozenset()


def test_awaiting_flag_does_not_hide_a_missing_far_leg_or_a_wrong_quantity():
    record = calendar()
    settle(record, prices={})
    # Broker shows neither leg: the expired one is only noted, the far leg is still a real, blocking mismatch.
    by_kind = {x.kind: x for x in recon({}, CAL=record).mismatches}
    assert set(by_kind) == {MismatchKind.AWAITING_SETTLEMENT, MismatchKind.MISSING_PLATFORM_POSITION}
    m = by_kind[MismatchKind.MISSING_PLATFORM_POSITION]
    assert m.strategy_ids == ("CAL",) and m.difference == ((FAR_FUT, -20),)
    # The expired leg is still at Zerodha but at a different size: an ordinary quantity mismatch, blocking.
    kinds = {x.kind: x for x in recon({SHORT_CE: -10, FAR_FUT: 20}, CAL=record).mismatches}
    assert kinds[MismatchKind.QUANTITY_MISMATCH].strategy_ids == ("CAL",)


def test_expired_leg_still_at_zerodha_after_settlement_is_shown_not_blocking():
    record = calendar()
    settle(record)
    report = recon({SHORT_CE: -20, FAR_FUT: 20}, CAL=record)
    (m,) = report.mismatches
    assert m.kind is MismatchKind.EXPIRED_STILL_AT_BROKER and m.difference == ((SHORT_CE, -20),)
    assert not m.blocks and report.blocked_strategy_ids == frozenset()


def test_settled_leg_suppression_is_only_for_settled_contracts():
    record = calendar()
    settle(record)
    stray = ("SENSEX", Instrument.CE, D("72700"), EXPIRY_DAY)  # an expired contract the platform never settled
    (m,) = recon({stray: -20, FAR_FUT: 20}, CAL=record).mismatches
    assert m.kind is MismatchKind.UNEXPECTED_BROKER_POSITION


# ---- no guessed price -------------------------------------------------------------------------------------------

def test_missing_settlement_price_leaves_leg_open_and_never_defaults_one():
    record, timeline = calendar(), Timeline("CAL-2", clock=clock)
    result = settle(record, prices={}, timeline=timeline)
    assert result.settled == () and timeline.entries == () and not result.exited
    assert record.outcomes[-1].kind is OutcomeKind.ACTIVATED  # nothing recorded as settled, nothing closed
    # A later run with the price available settles it and clears the awaiting flag.
    again = settle(record, timeline=timeline)
    assert [leg.contract for leg in again.settled] == [SHORT_CE] and record.awaiting_settlement == frozenset()


def test_missing_entry_price_leaves_leg_open_no_guessed_pnl():
    record = calendar()
    result = settle(record, entry_prices={FAR_FUT: D("72500.00")})
    assert result.settled == () and result.awaiting == (SHORT_CE,)
    assert record.active_version.intended_position.as_dict() == {SHORT_CE: -20, FAR_FUT: 20}


@pytest.mark.parametrize("bad", [150.0, "150", D("-1"), D("NaN"), D("150.123"), True])
def test_a_source_answer_that_is_not_a_valid_price_is_refused(bad):
    record = calendar()
    with pytest.raises(SettlementError):
        settle(record, prices={SHORT_CE: bad})
    assert record.active_version.intended_position.as_dict() == {SHORT_CE: -20, FAR_FUT: 20}


# ---- when a leg counts as expired -------------------------------------------------------------------------------

def test_expiry_day_before_the_close_and_a_later_expiry_are_not_settled():
    record = calendar()
    before_close = datetime.datetime(2026, 10, 15, 15, 31, tzinfo=IST)  # F-33: SENSEX traded to 15:39 on expiry
    assert settle(record, now=before_close).settled == ()
    assert settle(record, now=datetime.datetime(2026, 10, 15, 15, 38, tzinfo=IST)).settled == ()
    day_before = datetime.datetime(2026, 10, 14, 16, 0, tzinfo=IST)
    assert settle(record, now=day_before).settled == ()
    assert record.awaiting_settlement == frozenset()  # not yet expired, so not "awaiting" either
    # The far leg (2026-10-29) is never settled on 2026-10-15, whatever the source says.
    assert settle(record, prices={FAR_FUT: D("72700.00")}).settled == ()


def test_a_leg_whose_expiry_was_an_earlier_day_settles_at_any_time_of_day():
    record = calendar()
    next_morning = datetime.datetime(2026, 10, 16, 8, 0, tzinfo=IST)
    assert [leg.contract for leg in settle(record, now=next_morning).settled] == [SHORT_CE]


def test_a_blocked_strategy_is_refused_not_silently_settled():
    record = calendar()
    record.observe_broker_position(
        record.actual_position.__class__.of({FAR_FUT: 20}), at=ENTERED + datetime.timedelta(hours=1), reference="obs")
    assert record.reconciliation_required
    with pytest.raises(VersionError):
        settle(record)
    assert SHORT_CE in record.active_version.intended_position.as_dict()


def test_an_exited_strategy_is_left_alone_and_a_second_run_settles_nothing():
    record = straddle()
    settle(record)
    again = settle(record)
    assert again.settled == () and again.awaiting == () and not again.exited


def test_a_second_holder_of_the_expired_contract_keeps_the_mismatch_blocking():
    """Awaiting is only for contracts held by strategies that await it: with another holder the broker's single
    net number cannot be explained, so both strategies stay blocked (ordinary AC-7 rule)."""
    waiting, other = calendar(), straddle()  # both hold the short 72600 CE of 2026-10-15
    settle(waiting, prices={})
    assert waiting.awaiting_settlement == frozenset({SHORT_CE}) and other.awaiting_settlement == frozenset()
    report = recon({FAR_FUT: 20, SHORT_PE: -20}, WAIT=waiting, OTHER=other)
    (m,) = report.mismatches
    assert m.kind is MismatchKind.MISSING_PLATFORM_POSITION and m.strategy_ids == ("OTHER", "WAIT")
    assert report.blocked_strategy_ids == frozenset({"OTHER", "WAIT"})


def test_a_settled_contract_a_proposal_wants_again_is_not_treated_as_a_stale_listing():
    settled_one = calendar()
    settle(settled_one)
    proposer = _active((DefinitionLeg(Action.BUY, Instrument.FUT, None, FAR_EXPIRY, 20),))
    proposer.edit(
        StrategyDefinition("SENSEX", (
            DefinitionLeg(Action.BUY, Instrument.FUT, None, FAR_EXPIRY, 20),
            DefinitionLeg(Action.SELL, Instrument.CE, D("72600"), EXPIRY_DAY, 20),
        )), at=ENTERED + datetime.timedelta(hours=2))
    report = recon({FAR_FUT: 40, SHORT_CE: -20}, DONE=settled_one, PROP=proposer)
    ce = [m for m in report.mismatches if m.difference and m.difference[0][0] == SHORT_CE]
    assert ce and all(m.kind is not MismatchKind.EXPIRED_STILL_AT_BROKER for m in ce)
    assert ce[0].strategy_ids == ("PROP",)


# ---- round 2: external changes, atomicity, quantity ------------------------------------------------------------

def test_external_change_on_an_awaiting_leg_is_a_blocking_external_modification_not_a_note():
    """The user squared off the expiring short in Kite before any run: AC-4/AC-6 still block (as on main)."""
    record = calendar()
    settle(record, prices={})
    report = compare({FAR_FUT: 20}, {"CAL": record}, None, at=AFTER_CLOSE, clock=clock, external={SHORT_CE: 20})
    (m,) = report.mismatches
    assert m.kind is MismatchKind.EXTERNAL_MODIFICATION and m.strategy_ids == ("CAL",)
    assert report.blocked_strategy_ids == frozenset({"CAL"})


def test_external_change_on_a_settled_contract_is_not_the_stale_listing_note():
    record = calendar()
    settle(record)
    report = compare({SHORT_CE: -20, FAR_FUT: 20}, {"CAL": record}, None, at=AFTER_CLOSE, clock=clock,
                     external={SHORT_CE: -20})
    (m,) = report.mismatches
    assert m.kind is MismatchKind.UNEXPECTED_BROKER_POSITION  # what main reports for the same input


def test_settle_refuses_a_leg_with_an_unexplained_external_change_and_changes_nothing():
    record, timeline = calendar(), Timeline("CAL-3", clock=clock)
    with pytest.raises(SettlementError, match="external change"):
        settle_expired_legs(record, AFTER_CLOSE, source_of(SETTLEMENT), ENTRY_PRICES, timeline=timeline,
                            external_changes={SHORT_CE: 20})
    assert record.active_version.intended_position.as_dict() == {SHORT_CE: -20, FAR_FUT: 20}
    assert timeline.entries == () and record.settled_contracts == frozenset()
    # An external change on a contract that is not expiring does not stop the expired leg settling.
    ok = settle_expired_legs(record, AFTER_CLOSE, source_of(SETTLEMENT), ENTRY_PRICES, external_changes={FAR_FUT: 5})
    assert [leg.contract for leg in ok.settled] == [SHORT_CE]


def test_settlement_is_atomic_a_failing_timeline_write_changes_nothing():
    record, timeline = calendar(), Timeline("CAL-4", clock=clock)
    timeline.append(EntryType.CREATED, at=AFTER_CLOSE + datetime.timedelta(hours=1), actor="system")
    with pytest.raises(ValueError, match="chronological"):
        settle(record, timeline=timeline)  # the new entry would predate the last one: the write fails
    assert record.active_version.intended_position.as_dict() == {SHORT_CE: -20, FAR_FUT: 20}
    assert record.settled_contracts == frozenset() and len(timeline.entries) == 1
    assert len(record.outcomes) == 1  # only the original activation


class _FailingTimeline(Timeline):
    """A timeline whose real append raises OSError (storage failure) once armed."""

    __slots__ = ()

    def append(self, *args, **kwargs):
        if _FailingTimeline.armed:
            raise OSError("disk full")
        return super().append(*args, **kwargs)

    armed = False


def test_a_failing_real_timeline_append_leaves_the_record_unchanged():
    record = calendar()
    timeline = _FailingTimeline("CAL-5", clock=clock)
    # The dry run uses a plain Timeline copy, so only the REAL append can fail here.
    _FailingTimeline.armed = True
    try:
        with pytest.raises(OSError):
            settle(record, timeline=timeline)
    finally:
        _FailingTimeline.armed = False
    assert record.active_version.intended_position.as_dict() == {SHORT_CE: -20, FAR_FUT: 20}
    assert record.settled_contracts == frozenset() and len(record.outcomes) == 1 and timeline.entries == ()
    assert [leg.contract for leg in settle(record, timeline=timeline).settled] == [SHORT_CE]  # retry works


def test_verifier_case_expired_leg_plus_standalone_both_gone_at_zerodha_blocks_nothing_then_settles():
    """AC-2 round 3: SELL 72600 CE x20 in a calendar AND a recorded standalone CE x10 (short); after the close
    Zerodha drops both and shows only the far future. ADR-083: no blocking mismatch, never SIDE_MISMATCH."""
    record = calendar()
    settle(record, prices={})
    standalone = {SHORT_CE: -10}
    report = compare({FAR_FUT: 20}, {"CAL": record}, standalone, at=AFTER_CLOSE, clock=clock)
    (m,) = report.mismatches
    assert m.kind is MismatchKind.AWAITING_SETTLEMENT and not m.blocks and m.difference == ((SHORT_CE, 30),)
    assert report.blocked_strategy_ids == frozenset() and not record.reconciliation_required
    # The price arrives: the strategy is not blocked, so settlement works, and the picture stays clean.
    assert [leg.contract for leg in settle(record).settled] == [SHORT_CE]
    after = compare({FAR_FUT: 20}, {"CAL": record}, standalone, at=AFTER_CLOSE, clock=clock)
    assert all(x.kind is not MismatchKind.SIDE_MISMATCH and not x.blocks for x in after.mismatches)


def test_a_standalone_alone_on_an_expired_contract_is_not_standalone_changed_but_a_live_one_still_is():
    alone_expired = {SHORT_CE: -10}
    (m,) = compare({}, {}, alone_expired, at=AFTER_CLOSE, clock=clock).mismatches
    assert m.kind is MismatchKind.AWAITING_SETTLEMENT and not m.blocks
    before_close = datetime.datetime(2026, 10, 15, 15, 0, tzinfo=IST)
    (m,) = compare({}, {}, alone_expired, at=before_close, clock=clock).mismatches
    assert m.kind is MismatchKind.STANDALONE_CHANGED  # not yet expired: as before


def test_standalone_on_an_expired_contract_still_at_zerodha_at_another_quantity_still_mismatches():
    record = calendar()
    settle(record, prices={})
    ms = compare({SHORT_CE: -5, FAR_FUT: 20}, {"CAL": record}, {SHORT_CE: -10}, at=AFTER_CLOSE, clock=clock).mismatches
    assert any(x.blocks for x in ms)  # a quantity left at Zerodha that expiry should have removed: still blocks


def test_expired_leg_listed_at_a_different_quantity_is_not_the_harmless_note():
    record = calendar()
    settle(record)
    (m,) = recon({SHORT_CE: -10, FAR_FUT: 20}, CAL=record).mismatches
    assert m.kind is MismatchKind.UNEXPECTED_BROKER_POSITION and m.kind is not MismatchKind.EXPIRED_STILL_AT_BROKER
