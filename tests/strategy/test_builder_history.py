"""AC-1..AC-5: Builder activity history, undo and restore over the golden Iron Condor.

Spec: spec/requirements/REQ-070.md; legs from spec/business-rules/scenario-calculations.md Sec 6
(tests/engine/test_golden_iron_condor.py).

Fix round (2026-09-29, independent verifier): entries store the configuration AFTER the event their label
names, not before - a 'User modified strike' entry holds the STRUCK configuration. restore()/undo() jump
straight to a past entry's stored legs and record that jump as its own new entry.
"""
from __future__ import annotations

import datetime
from dataclasses import FrozenInstanceError, fields
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
    """AC-1: choosing an alternative setup replaces the configuration; the entry it creates holds the NEW
    (alternative) configuration - fix round: a label names the state its own entry holds, and the previous
    configuration is preserved because it is already entry 1, 'Original suggested setup'."""
    session = make_session()
    alternative = (LEG1, LEG2)  # a simpler two-leg alternative
    session.choose_alternative(alternative)

    assert session.current == alternative
    labels = [e.label for e in session.history()]
    assert labels == [LABEL_ORIGINAL, LABEL_ALTERNATIVE]
    assert session.history()[0].legs == CONDOR_LEGS  # the previous setup, preserved as entry 1
    assert session.history()[-1].legs == alternative  # 'Setup changed to alternative' holds the alternative


def test_ac1_alternative_identical_to_current_creates_no_entry():
    """Fix round item 2: choosing an alternative identical to the current configuration is a no-op."""
    session = make_session()
    session.choose_alternative(CONDOR_LEGS)
    assert [e.label for e in session.history()] == [LABEL_ORIGINAL]
    assert session.current == CONDOR_LEGS


def test_ac2_alternative_in_reversed_order_creates_no_entry():
    """Small fix round item 1: builder_history.py:247 compared legs as an ordered tuple, so a reversed-order
    'alternative' with the SAME legs recorded a spurious entry - leg order is cosmetic everywhere (AC-2)."""
    session = make_session()
    session.choose_alternative(tuple(reversed(CONDOR_LEGS)))
    assert [e.label for e in session.history()] == [LABEL_ORIGINAL]
    assert session.current == CONDOR_LEGS  # current is untouched, not silently reordered either


def test_ac2_genuinely_different_alternative_still_records():
    """Small fix round item 1: the order-insensitive comparison must not swallow a real change."""
    session = make_session()
    different = (LEG1, LEG2, LEG3)  # same order prefix, genuinely fewer legs
    session.choose_alternative(different)
    assert [e.label for e in session.history()] == [LABEL_ORIGINAL, LABEL_ALTERNATIVE]
    assert session.current == different

    session2 = make_session()
    reordered_but_different = (LEG4, LEG3, LEG2, Leg(Action.BUY, Instrument.PE, D("22700"), EXPIRY, QTY, D("30.00")))
    session2.choose_alternative(reordered_but_different)
    assert [e.label for e in session2.history()] == [LABEL_ORIGINAL, LABEL_ALTERNATIVE]
    assert session2.current == reordered_but_different


def test_ac2_meaningful_changes_create_exactly_one_labelled_entry_each():
    """AC-2: add/remove leg, strike, quantity, expiry each create exactly one labelled entry, holding the
    RESULTING configuration - fix round: the label names the state its own entry stores."""
    session = make_session()

    session.change_strike(0, D("22750"))
    session.change_quantity(1, 150)
    session.change_expiry(2, datetime.date(2026, 11, 3))
    session.remove_leg(3)
    new_leg = Leg(Action.BUY, Instrument.CE, D("23700"), EXPIRY, QTY, D("30.00"))
    session.add_leg(new_leg)

    entries = session.history()
    labels = [e.label for e in entries]
    assert labels == [
        LABEL_ORIGINAL,
        LABEL_STRIKE,
        LABEL_QUANTITY,
        LABEL_EXPIRY,
        LABEL_REMOVE_LEG,
        LABEL_ADD_LEG,
    ]
    # the entry named 'User modified strike' holds the STRUCK strike, not the pre-change 22800.
    assert entries[1].legs[0].strike == D("22750")
    assert entries[0].legs[0].strike == D("22800")  # 'Original suggested setup' unchanged
    # the entry named 'User changed quantity' holds the changed quantity.
    assert entries[2].legs[1].quantity == 150
    assert session.current[0].strike == D("22750")
    assert session.current[1].quantity == 150
    assert session.current == entries[-1].legs  # current always mirrors the last entry after a meaningful change


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

    assert [e.label for e in session.history()] == [LABEL_ORIGINAL]
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
    assert [e.label for e in session.history()] == [LABEL_ORIGINAL]


def test_ac3_restore_jumps_to_the_target_entrys_configuration_and_is_recorded():
    """AC-3: restore jumps straight to an earlier entry's configuration; the jump is itself recorded. The
    configuration being replaced was already preserved as the entry immediately before the restore entry."""
    session = make_session()
    original_seq = session.history()[0].seq

    session.change_strike(0, D("22750"))
    changed = session.current

    restored = session.restore(original_seq)

    assert restored.legs == CONDOR_LEGS
    assert session.current == CONDOR_LEGS
    labels = [e.label for e in session.history()]
    assert labels == [LABEL_ORIGINAL, LABEL_STRIKE, LABEL_RESTORE]
    # the changed configuration, about to be replaced, is preserved as the entry right before the restore.
    assert session.history()[-2].legs == changed
    assert session.history()[-1].legs == CONDOR_LEGS  # 'User restored...' holds the restored configuration


def test_ac3_restore_unknown_entry_is_refused():
    session = make_session()
    with pytest.raises(BuilderHistoryError):
        session.restore(9999)


def test_red_restore_requires_a_plain_int_seq():
    """Small fix round item 2: restore(True)/restore(1.0) were wrongly accepted as entry 1 (bool/float alias)."""
    session = make_session()
    with pytest.raises(BuilderHistoryError):
        session.restore(True)  # isinstance(True, int) is True in Python - must be explicitly rejected
    with pytest.raises(BuilderHistoryError):
        session.restore(1.0)  # 1.0 == 1 - must be explicitly rejected too
    # a genuine plain int still works.
    assert session.restore(session.history()[0].seq).legs == CONDOR_LEGS


def test_ac4_undo_reverts_exactly_the_last_meaningful_change_and_is_recorded():
    """AC-4: undo reverts the last meaningful change - jumps to the entry BEFORE it - and is itself recorded."""
    session = make_session()
    session.change_strike(0, D("22750"))
    changed = session.current

    undone = session.undo()

    assert undone.legs == CONDOR_LEGS
    assert session.current == CONDOR_LEGS
    labels = [e.label for e in session.history()]
    assert labels == [LABEL_ORIGINAL, LABEL_STRIKE, LABEL_UNDO]
    assert session.history()[-2].legs == changed  # the struck state, preserved right before the undo entry
    assert session.history()[-1].legs == CONDOR_LEGS  # 'User undid...' holds the reverted-to configuration


def test_ac4_undo_window_closes_after_a_second_meaningful_change():
    """AC-4: a second meaningful change replaces the undo target - undo only reverts the LAST one."""
    session = make_session()
    session.change_strike(0, D("22750"))
    after_strike = session.current
    session.change_quantity(1, 150)  # replaces the undo target

    undone = session.undo()

    assert undone.legs == after_strike  # the state right before the quantity change
    assert session.current[0].strike == D("22750")  # the strike change is not undone
    assert session.current[1].quantity == QTY  # the quantity change IS undone


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


def test_ac5_history_persists_after_execution_and_edits_are_refused():
    """AC-5: history survives mark_executed(). Fix round item 4: after execution the session is read-only."""
    session = make_session()
    session.change_strike(0, D("22750"))
    session.mark_executed()

    assert session.is_executed is True
    labels = [e.label for e in session.history()]
    assert labels == [LABEL_ORIGINAL, LABEL_STRIKE]
    assert session.current[0].strike == D("22750")

    with pytest.raises(BuilderHistoryError):
        session.change_quantity(0, 150)
    with pytest.raises(BuilderHistoryError):
        session.add_leg(Leg(Action.BUY, Instrument.CE, D("23700"), EXPIRY, QTY, D("30.00")))
    with pytest.raises(BuilderHistoryError):
        session.reorder_legs([1, 0, 2, 3])
    with pytest.raises(BuilderHistoryError):
        session.restore(session.history()[0].seq)
    with pytest.raises(BuilderHistoryError):
        session.undo()
    # history stays fully readable after every refused edit.
    assert [e.label for e in session.history()] == [LABEL_ORIGINAL, LABEL_STRIKE]


def test_red_display_fields_are_read_only_only_through_their_methods():
    """Small fix round item 3: display_name/display_flags could be assigned directly, bypassing rename()/
    toggle_display() (which already refuse after execution) - make the attributes read-only always."""
    session = make_session()
    with pytest.raises(AttributeError):
        session.display_name = "hacked"  # type: ignore[misc]
    with pytest.raises(TypeError):
        session.display_flags["collapsed"] = True  # type: ignore[index]

    session.rename("Renamed via the proper method")
    session.mark_executed()
    with pytest.raises(AttributeError):
        session.display_name = "hacked again"  # type: ignore[misc]
    with pytest.raises(BuilderHistoryError):
        session.rename("also refused after execution")
    assert session.display_name == "Renamed via the proper method"


def test_ac5_default_view_carries_no_history_data():
    """AC-5: the default output (default_view) is the current configuration only - never history."""
    session = make_session()
    session.change_strike(0, D("22750"))

    view = session.default_view()
    field_names = {f.name for f in fields(view)}
    assert field_names == {"legs", "display_name", "display_flags"}
    assert "history" not in field_names and "entries" not in field_names and "label" not in field_names
    assert view.legs == session.current
    assert view.display_name == session.display_name


def test_red_history_entries_are_immutable():
    session = make_session()
    entry = session.history()[0]
    with pytest.raises(FrozenInstanceError):
        entry.label = "tampered"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        entry.legs = ()  # type: ignore[misc]


def test_red_history_accessor_returns_a_copy_not_the_live_list():
    """A raw state change that bypasses the proper method must not affect the session (input-domain checklist)."""
    session = make_session()
    entries = session.history()
    entries_mutable = list(entries)
    entries_mutable.append("not a real entry")
    assert [e.label for e in session.history()] == [LABEL_ORIGINAL]


def test_red_duplicate_leg_is_rejected_on_add():
    session = make_session()
    with pytest.raises(BuilderHistoryError):
        session.add_leg(LEG1)  # identical action/instrument/strike/expiry already present


def test_red_duplicate_leg_is_rejected_on_every_edit():
    """Fix round item 3: change_strike and change_expiry must refuse creating a duplicate leg too.

    The duplicate key is (action, instrument, strike, expiry) - quantity is not part of it (a builder should be
    free to size the same option twice with different lot counts is still refused as a *duplicate leg*, so a
    quantity-only edit can never itself produce a same-key collision; strike and expiry can).
    """
    twin_strike_a = Leg(Action.BUY, Instrument.PE, D("22800"), EXPIRY, QTY, D("42.50"))
    twin_strike_b = Leg(Action.BUY, Instrument.PE, D("22700"), EXPIRY, QTY, D("42.50"))
    session = BuilderSession((twin_strike_a, twin_strike_b))
    with pytest.raises(BuilderHistoryError):
        session.change_strike(1, D("22800"))  # would make twin_strike_b identical to twin_strike_a

    twin_expiry_a = Leg(Action.BUY, Instrument.CE, D("23700"), EXPIRY, QTY, D("10.00"))
    twin_expiry_b = Leg(Action.BUY, Instrument.CE, D("23700"), datetime.date(2026, 11, 3), QTY, D("10.00"))
    session2 = BuilderSession((twin_expiry_a, twin_expiry_b))
    with pytest.raises(BuilderHistoryError):
        session2.change_expiry(1, EXPIRY)  # would make twin_expiry_b identical to twin_expiry_a


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
    """AC-2: appending 1,000 entries one at a time must not re-validate the whole history: the calls made by 1,000
    appends are twice those of 500 (work is counted, not timed)."""
    from work_count import assert_linear

    sessions = []

    def appends(n: int):
        session = BuilderSession((LEG1, LEG2))
        sessions.append(session)

        def work() -> None:
            for i in range(n):
                session.change_quantity(0, QTY + (i % 50) + 1)
        return work

    assert_linear(appends, 500)
    assert [len(s.history()) for s in sessions] == [501, 1001]  # original + 500 / 1000 meaningful changes
