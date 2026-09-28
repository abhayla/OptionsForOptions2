"""AC-1..AC-5: Builder activity history, undo and restore over the golden Iron Condor.

Spec: spec/requirements/REQ-070.md; legs from spec/business-rules/scenario-calculations.md Sec 6
(tests/engine/test_golden_iron_condor.py).
"""
from __future__ import annotations

import datetime
from dataclasses import FrozenInstanceError
from decimal import Decimal as D

import pytest

from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.metrics import strategy_metrics
from ofo.engine.strategy import Strategy
from ofo.strategy.builder_history import (
    LABEL_ADD_LEG,
    LABEL_ALTERNATIVE,
    LABEL_EXPIRY,
    LABEL_ORIGINAL,
    LABEL_QUANTITY,
    LABEL_REMOVE_LEG,
    LABEL_RESTORE,
    LABEL_STRIKE,
    LABEL_UNDO,
    BuilderHistoryError,
    BuilderSession,
)

EXPIRY = datetime.date(2026, 10, 27)
QTY = 75

LEG1 = Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, QTY, D("42.50"), D("38.20"))
LEG2 = Leg(Action.SELL, Instrument.PE, D("23000"), EXPIRY, QTY, D("86.00"), D("72.50"))
LEG3 = Leg(Action.SELL, Instrument.CE, D("23400"), EXPIRY, QTY, D("91.50"), D("78.00"))
LEG4 = Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, QTY, D("44.00"), D("39.50"))
CONDOR_LEGS = (LEG1, LEG2, LEG3, LEG4)


def make_session() -> BuilderSession:
    return BuilderSession(CONDOR_LEGS)


def test_ac1_alternative_setup_replaces_config_and_keeps_previous_as_history():
    """AC-1: choosing an alternative setup replaces the configuration and keeps the previous one."""
    session = make_session()
    alternative = (LEG1, LEG2)  # a simpler two-leg alternative
    session.choose_alternative(alternative)

    assert session.current == alternative
    labels = [e.label for e in session.history_entries()]
    assert labels == [LABEL_ORIGINAL, LABEL_ALTERNATIVE]
    # the entry keeps the PREVIOUS (four-leg) configuration, not the new one.
    assert session.history_entries()[-1].legs == CONDOR_LEGS


def test_ac2_meaningful_changes_create_exactly_one_labelled_entry_each():
    """AC-2: add/remove leg, strike, quantity, expiry each create exactly one labelled entry."""
    session = make_session()

    session.change_strike(0, D("22750"))
    session.change_quantity(1, 150)
    session.change_expiry(2, datetime.date(2026, 11, 3))
    session.remove_leg(3)
    new_leg = Leg(Action.BUY, Instrument.CE, D("23700"), EXPIRY, QTY, D("30.00"))
    session.add_leg(new_leg)

    labels = [e.label for e in session.history_entries()]
    assert labels == [
        LABEL_ORIGINAL,
        LABEL_STRIKE,
        LABEL_QUANTITY,
        LABEL_EXPIRY,
        LABEL_REMOVE_LEG,
        LABEL_ADD_LEG,
    ]
    assert session.current[0].strike == D("22750")
    assert session.current[1].quantity == 150


def test_ac2_material_change_moves_engine_metrics_concretely():
    """AC-2: the concrete 'material risk/payoff change' rule - strategy_metrics moves on a strike edit."""
    before = strategy_metrics(Strategy(legs=CONDOR_LEGS))
    session = make_session()
    session.change_strike(0, D("22750"))
    after = strategy_metrics(Strategy(legs=session.current))

    assert (after.max_profit, after.max_loss, after.breakevens) != (
        before.max_profit,
        before.max_loss,
        before.breakevens,
    )


def test_ac2_cosmetic_changes_create_no_entries():
    """AC-2: reordering legs, renaming and toggling display create no history entries."""
    session = make_session()
    before_metrics = strategy_metrics(Strategy(legs=session.current))

    session.reorder_legs([3, 2, 1, 0])
    session.rename("My Iron Condor")
    session.toggle_display("collapsed")

    assert [e.label for e in session.history_entries()] == [LABEL_ORIGINAL]
    assert session.current == (LEG4, LEG3, LEG2, LEG1)
    assert session.display_name == "My Iron Condor"
    assert session.display_flags["collapsed"] is True
    after_metrics = strategy_metrics(Strategy(legs=session.current))
    assert (after_metrics.max_profit, after_metrics.max_loss, after_metrics.breakevens) == (
        before_metrics.max_profit,
        before_metrics.max_loss,
        before_metrics.breakevens,
    )


def test_ac2_setting_the_same_value_creates_no_entry():
    session = make_session()
    session.change_strike(0, LEG1.strike)
    session.change_quantity(0, LEG1.quantity)
    session.change_expiry(0, LEG1.expiry)
    assert [e.label for e in session.history_entries()] == [LABEL_ORIGINAL]


def test_ac3_restore_preserves_current_configuration_first():
    """AC-3: restore saves the current configuration first, then restores; the restore is itself recorded."""
    session = make_session()
    original_seq = session.history_entries()[0].seq

    session.change_strike(0, D("22750"))
    session.reorder_legs([1, 0, 2, 3])  # cosmetic drift, never logged - must still be preserved on restore
    drifted_current = session.current

    restored = session.restore(original_seq)

    assert restored.legs == CONDOR_LEGS
    assert session.current == CONDOR_LEGS
    labels = [e.label for e in session.history_entries()]
    assert labels == [LABEL_ORIGINAL, LABEL_STRIKE, LABEL_RESTORE]
    # the entry created by restore preserved the drifted current configuration, not the pre-drift one.
    assert session.history_entries()[-1].legs == drifted_current


def test_ac3_restore_unknown_entry_is_refused():
    session = make_session()
    with pytest.raises(BuilderHistoryError):
        session.restore(9999)


def test_ac4_undo_reverts_exactly_the_last_meaningful_change_and_is_recorded():
    """AC-4: undo reverts the last meaningful change and is itself recorded."""
    session = make_session()
    session.change_strike(0, D("22750"))
    changed = session.current

    undone = session.undo()

    assert undone.legs == CONDOR_LEGS
    assert session.current == CONDOR_LEGS
    labels = [e.label for e in session.history_entries()]
    assert labels == [LABEL_ORIGINAL, LABEL_STRIKE, LABEL_UNDO]
    assert session.history_entries()[-1].legs == changed


def test_ac4_undo_window_closes_after_a_second_meaningful_change():
    """AC-4: a second meaningful change replaces the undo target - undo only reverts the LAST one."""
    session = make_session()
    session.change_strike(0, D("22750"))
    session.change_quantity(1, 150)  # replaces the undo target

    undone = session.undo()

    assert undone.legs[0].strike == D("22750")  # the state right before the quantity change
    assert undone.legs[1].quantity == QTY
    assert session.current[1].quantity == QTY
    assert session.current[0].strike == D("22750")  # the strike change is not undone


def test_ac4_undo_with_nothing_to_undo_is_refused():
    session = make_session()
    with pytest.raises(BuilderHistoryError):
        session.undo()


def test_ac4_undo_twice_in_a_row_is_refused():
    session = make_session()
    session.change_strike(0, D("22750"))
    session.undo()
    with pytest.raises(BuilderHistoryError):
        session.undo()


def test_ac5_history_persists_after_execution_and_is_not_the_default_output():
    """AC-5: history survives mark_executed(); current (default output) never includes it."""
    session = make_session()
    session.change_strike(0, D("22750"))
    assert isinstance(session.current, tuple)
    assert not hasattr(session.current, "label")  # the default output is just legs, not history entries

    session.mark_executed()

    assert session.is_executed is True
    labels = [e.label for e in session.history_entries()]
    assert labels == [LABEL_ORIGINAL, LABEL_STRIKE]
    assert session.current[0].strike == D("22750")


def test_red_history_entries_are_immutable():
    session = make_session()
    entry = session.history_entries()[0]
    with pytest.raises(FrozenInstanceError):
        entry.label = "tampered"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        entry.legs = ()  # type: ignore[misc]


def test_red_history_accessor_returns_a_copy_not_the_live_list():
    """A raw state change that bypasses the proper method must not affect the session (input-domain checklist)."""
    session = make_session()
    entries = session.history_entries()
    entries_mutable = list(entries)
    entries_mutable.append("not a real entry")
    assert [e.label for e in session.history_entries()] == [LABEL_ORIGINAL]


def test_red_duplicate_leg_is_rejected():
    session = make_session()
    with pytest.raises(BuilderHistoryError):
        session.add_leg(LEG1)  # identical action/instrument/strike/expiry already present


def test_red_leg_cap_is_enforced():
    session = BuilderSession((LEG1,))
    for i in range(11):
        session.add_leg(
            Leg(Action.BUY, Instrument.CE, D(24000 + i * 100), EXPIRY, QTY, D("10.00"))
        )
    with pytest.raises(BuilderHistoryError):
        session.add_leg(Leg(Action.BUY, Instrument.CE, D("30000"), EXPIRY, QTY, D("10.00")))


def test_red_cannot_remove_the_last_leg():
    session = BuilderSession((LEG1,))
    with pytest.raises(BuilderHistoryError):
        session.remove_leg(0)


def test_red_index_out_of_range_is_refused():
    session = make_session()
    with pytest.raises(BuilderHistoryError):
        session.change_strike(99, D("22750"))
    with pytest.raises(BuilderHistoryError):
        session.remove_leg(-1)


def test_red_absurd_expiry_shift_is_refused():
    session = make_session()
    with pytest.raises(BuilderHistoryError):
        session.change_expiry(0, datetime.date(2050, 1, 1))


def test_red_naive_datetime_expiry_is_refused():
    session = make_session()
    with pytest.raises(BuilderHistoryError):
        session.change_expiry(0, datetime.datetime(2026, 11, 3))


def test_red_futures_leg_has_no_strike_to_change():
    fut_leg = Leg(Action.BUY, Instrument.FUT, None, EXPIRY, QTY, D("23000.00"))
    session = BuilderSession((fut_leg, LEG1))
    with pytest.raises(BuilderHistoryError):
        session.change_strike(0, D("23100"))


def test_one_by_one_append_of_1000_meaningful_changes_stays_fast():
    """Input-domain checklist: appending 1,000 entries one at a time must not re-validate the whole history."""
    import time

    session = BuilderSession((LEG1, LEG2))
    start = time.perf_counter()
    for i in range(1000):
        session.change_quantity(0, QTY + (i % 50) + 1)
    elapsed = time.perf_counter() - start

    assert len(session.history_entries()) == 1001  # original + 1000 meaningful changes
    assert elapsed < 2.0, f"1000 appends took {elapsed:.2f}s - looks like O(n) or worse per append"
