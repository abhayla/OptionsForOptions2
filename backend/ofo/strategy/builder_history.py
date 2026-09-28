"""Builder activity history: labelled, append-only entries over a Builder session's leg configuration.

Spec: spec/requirements/REQ-070.md AC-1..AC-5; ADR-019 (Q134-Q139: an alternative setup keeps the previous one,
history is automatic with no manual version management, restore preserves the current configuration first,
history stays reachable after execution but is not shown by default); T2 #84 (a meaningful change is add/remove
leg, strike, quantity, expiry or a material risk/payoff change; small UI interactions create no history, and
Undo is offered right after a meaningful change); ADR-007/Q214 (Undo's ~5s window is a UI concern - this module
only offers "undo of the last meaningful change", with no timer).

**Entry semantics (fix round, verifier finding 2026-09-29 "label/content mismatch"):** each :class:`HistoryEntry`
stores the configuration that exists AFTER the event its label names - entry 1 ``'Original suggested setup'``
stores the initial configuration; a ``'User modified strike'`` entry stores the STRUCK configuration, not the
one before it. ``current`` always equals the last entry's legs immediately after any meaningful change, a
restore or an undo; only a cosmetic change (:meth:`reorder_legs`, :meth:`rename`, :meth:`toggle_display`) can
make ``current`` briefly differ from the last entry, and it creates no entry of its own (AC-2). :meth:`restore`
and :meth:`undo` each jump ``current`` straight to a past entry's stored legs and record that jump as its own
new entry holding the same (destination) legs - "the current [i.e. about-to-be-replaced] configuration is
preserved first" because it is already the previous entry in this append-only log by construction.

Concrete "material risk/payoff change" rule (AC-2): ``ofo.engine.metrics.strategy_metrics`` computes
``max_profit``, ``max_loss`` and ``breakevens`` purely as a function of each leg's action, instrument, strike,
quantity and expiry (``scenario-calculations.md`` Sec 3) - leg ORDER never appears in that computation. So every
mutator that can change those fields (:meth:`BuilderSession.add_leg`, :meth:`remove_leg`, :meth:`change_strike`,
:meth:`change_quantity`, :meth:`change_expiry`, :meth:`choose_alternative`) is exactly the set of operations that
CAN move the strategy's metrics, and is treated as meaningful. Every mutator that only touches order or display
metadata (:meth:`reorder_legs`, :meth:`rename`, :meth:`toggle_display`) never touches those fields, so it
provably cannot change the metrics, and is treated as cosmetic. ``tests/strategy/test_builder_history.py``
(AC-2) proves this on the golden Iron Condor by calling ``strategy_metrics`` directly before and after each kind
of change.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, replace
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, Sequence

from ofo.engine.legs import Leg

#: The seven change labels named in W-016 / REQ-070 AC-2, plus the two recording restore and undo (AC-3, AC-4).
LABEL_ORIGINAL = "Original suggested setup"
LABEL_STRIKE = "User modified strike"
LABEL_QUANTITY = "User changed quantity"
LABEL_ADD_LEG = "User added leg"
LABEL_REMOVE_LEG = "User removed leg"
LABEL_EXPIRY = "User changed expiry"
LABEL_ALTERNATIVE = "Setup changed to alternative"
LABEL_RESTORE = "User restored an earlier configuration"
LABEL_UNDO = "User undid the last change"

#: Hard cap on legs in one Builder session and on how far an expiry edit may move a leg, so a malformed or
#: runaway edit fails closed instead of silently accepted (builder-common.md input-domain checklist).
MAX_LEGS = 12
MAX_EXPIRY_SHIFT_DAYS = 3650


class BuilderHistoryError(ValueError):
    """A history/undo/restore/edit operation on a :class:`BuilderSession` was refused."""


@dataclass(frozen=True)
class HistoryEntry:
    """One immutable, labelled snapshot of the configuration AFTER the event ``label`` names (AC-2 negative:
    entries are immutable; fix round: the entry's ``legs`` is the POST-change state, never the pre-change one)."""

    seq: int
    label: str
    legs: tuple[Leg, ...]


@dataclass(frozen=True)
class DefaultView:
    """AC-5: the Builder's default output - the current configuration only, never any history data."""

    legs: tuple[Leg, ...]
    display_name: str
    display_flags: Mapping[str, bool]


def _leg_key(leg: Leg) -> tuple:
    return (leg.action, leg.instrument, leg.strike, leg.expiry)


def _leg_sort_key(leg: Leg) -> tuple:
    """A total order over every field of a leg, safe to sort (never compares None to a Decimal)."""
    return (
        leg.action.value,
        leg.instrument.value,
        leg.strike is None,
        leg.strike if leg.strike is not None else Decimal(0),
        leg.quantity,
        leg.expiry,
        leg.entry_price,
        leg.ltp is None,
        leg.ltp if leg.ltp is not None else Decimal(0),
    )


def _same_configuration(a: Sequence[Leg], b: Sequence[Leg]) -> bool:
    """Fix round item 1: compare configurations order-insensitively (leg order is cosmetic everywhere)."""
    a, b = tuple(a), tuple(b)
    return len(a) == len(b) and sorted(a, key=_leg_sort_key) == sorted(b, key=_leg_sort_key)


def _check_legs(legs: Sequence[Leg]) -> tuple[Leg, ...]:
    """Shared validation for any full leg set: type, non-empty, no duplicate logical leg, within the leg cap."""
    checked = tuple(legs)
    if not checked:
        raise BuilderHistoryError("a configuration needs at least one leg")
    if len(checked) > MAX_LEGS:
        raise BuilderHistoryError(f"a configuration cannot have more than {MAX_LEGS} legs, got {len(checked)}")
    for leg in checked:
        if not isinstance(leg, Leg):
            raise BuilderHistoryError(f"every leg must be a Leg, got {leg!r}")
    keys = [_leg_key(leg) for leg in checked]
    if len(set(keys)) != len(keys):
        raise BuilderHistoryError("a configuration cannot hold two identical legs (same action/instrument/strike/expiry)")
    return checked


class BuilderSession:
    """The Builder's current leg configuration plus its append-only activity history.

    :meth:`default_view` is the "default table output" (AC-5): the current legs and display metadata only,
    never the history. Call :meth:`history` explicitly to see the log; it survives :meth:`mark_executed`, after
    which every edit method is refused (ADR-019: changes after execution become versions, W-012's job) while
    the history stays fully readable.
    """

    def __init__(self, initial_legs: Sequence[Leg], *, display_name: str = "Untitled strategy") -> None:
        self._legs = _check_legs(initial_legs)
        self._history: list[HistoryEntry] = []
        self._seq = 0
        self._undo_target: int | None = None
        self._executed = False
        self._display_name = display_name
        self._display_flags: dict = {}
        self._append(LABEL_ORIGINAL, self._legs)

    # -- accessors -----------------------------------------------------------------------------------------
    @property
    def current(self) -> tuple[Leg, ...]:
        """The current configuration only."""
        return self._legs

    @property
    def display_name(self) -> str:
        """Fix round item 3: read-only - changed only through :meth:`rename`, which refuses after execution."""
        return self._display_name

    @property
    def display_flags(self) -> Mapping[str, bool]:
        """Fix round item 3: a read-only view - changed only through :meth:`toggle_display`."""
        return MappingProxyType(self._display_flags)

    def default_view(self) -> DefaultView:
        """AC-5: the default output - current legs and display metadata, no history field of any kind."""
        return DefaultView(
            legs=self._legs, display_name=self._display_name, display_flags=dict(self._display_flags)
        )

    def history(self) -> tuple[HistoryEntry, ...]:
        """Explicit accessor for the full labelled history (AC-5); persists across :meth:`mark_executed`."""
        return tuple(self._history)

    @property
    def is_executed(self) -> bool:
        return self._executed

    def mark_executed(self) -> None:
        """Record that this strategy has been executed. History stays intact and readable (AC-5)."""
        self._executed = True

    # -- internal plumbing -----------------------------------------------------------------------------------
    def _check_not_executed(self) -> None:
        if self._executed:
            raise BuilderHistoryError(
                "this Builder session has been executed; it is read-only - changes now become new versions "
                "(ADR-019, see W-012), the activity history remains readable"
            )

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _append(self, label: str, legs: tuple[Leg, ...]) -> HistoryEntry:
        entry = HistoryEntry(seq=self._next_seq(), label=label, legs=legs)
        self._history.append(entry)
        return entry

    def _entry_by_seq(self, seq: int) -> HistoryEntry:
        for entry in self._history:
            if entry.seq == seq:
                return entry
        raise BuilderHistoryError(f"no history entry with seq {seq!r}")

    def _leg_at(self, index: int) -> Leg:
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(self._legs):
            raise BuilderHistoryError(f"leg index {index!r} is out of range for {len(self._legs)} leg(s)")
        return self._legs[index]

    def _check_no_duplicate_with_others(self, new_leg: Leg, skip_index: int) -> None:
        """AC-2 fix round: every edit, not just add_leg, must refuse creating a duplicate leg."""
        others = self._legs[:skip_index] + self._legs[skip_index + 1 :]
        if any(_leg_key(existing) == _leg_key(new_leg) for existing in others):
            raise BuilderHistoryError("this edit would create a duplicate leg (same action/instrument/strike/expiry)")

    def _record_meaningful(self, label: str, new_legs: tuple[Leg, ...]) -> None:
        """Append the entry holding the POST-change state and update current to match (fix round semantics)."""
        entry = self._append(label, new_legs)
        self._legs = new_legs
        self._undo_target = entry.seq

    # -- meaningful changes (AC-2): each leaves exactly one labelled entry holding the RESULTING configuration --
    def add_leg(self, new_leg: Leg) -> None:
        """AC-2: adding a leg is always meaningful."""
        self._check_not_executed()
        if not isinstance(new_leg, Leg):
            raise BuilderHistoryError(f"new_leg must be a Leg, got {new_leg!r}")
        candidate = self._legs + (new_leg,)
        _check_legs(candidate)  # cap + duplicate check against the leg being added
        self._record_meaningful(LABEL_ADD_LEG, candidate)

    def remove_leg(self, index: int) -> None:
        """AC-2: removing a leg is always meaningful; refuses to empty the configuration."""
        self._check_not_executed()
        self._leg_at(index)
        if len(self._legs) == 1:
            raise BuilderHistoryError("cannot remove the last leg of a configuration")
        candidate = self._legs[:index] + self._legs[index + 1 :]
        self._record_meaningful(LABEL_REMOVE_LEG, candidate)

    def change_strike(self, index: int, new_strike: Decimal) -> None:
        """AC-2: a strike change is meaningful; setting the same value is a no-op (no entry)."""
        self._check_not_executed()
        old_leg = self._leg_at(index)
        if old_leg.strike is None:
            raise BuilderHistoryError("a futures leg has no strike to change")
        new_leg = replace(old_leg, strike=new_strike)  # Leg.__post_init__ validates new_strike
        if new_leg.strike == old_leg.strike:
            return
        self._check_no_duplicate_with_others(new_leg, index)
        candidate = self._legs[:index] + (new_leg,) + self._legs[index + 1 :]
        self._record_meaningful(LABEL_STRIKE, candidate)

    def change_quantity(self, index: int, new_quantity: int) -> None:
        """AC-2: a quantity change is meaningful; setting the same value is a no-op (no entry)."""
        self._check_not_executed()
        old_leg = self._leg_at(index)
        new_leg = replace(old_leg, quantity=new_quantity)  # validates positive int
        if new_leg.quantity == old_leg.quantity:
            return
        self._check_no_duplicate_with_others(new_leg, index)
        candidate = self._legs[:index] + (new_leg,) + self._legs[index + 1 :]
        self._record_meaningful(LABEL_QUANTITY, candidate)

    def change_expiry(self, index: int, new_expiry: datetime.date) -> None:
        """AC-2: an expiry change is meaningful; setting the same value is a no-op (no entry)."""
        self._check_not_executed()
        old_leg = self._leg_at(index)
        if isinstance(new_expiry, datetime.datetime) or not isinstance(new_expiry, datetime.date):
            raise BuilderHistoryError(f"new_expiry must be a timezone-naive datetime.date, got {new_expiry!r}")
        shift = abs((new_expiry - old_leg.expiry).days)
        if shift > MAX_EXPIRY_SHIFT_DAYS:
            raise BuilderHistoryError(f"expiry shift of {shift} days from {old_leg.expiry} is not a plausible edit")
        new_leg = replace(old_leg, expiry=new_expiry)
        if new_leg.expiry == old_leg.expiry:
            return
        self._check_no_duplicate_with_others(new_leg, index)
        candidate = self._legs[:index] + (new_leg,) + self._legs[index + 1 :]
        self._record_meaningful(LABEL_EXPIRY, candidate)

    def choose_alternative(self, new_legs: Sequence[Leg]) -> None:
        """AC-1: choosing an alternative setup replaces the configuration and keeps the previous one.

        Fix round item 2: choosing an alternative identical to the current configuration is a no-op.
        """
        self._check_not_executed()
        checked = _check_legs(new_legs)
        if _same_configuration(checked, self._legs):
            return
        self._record_meaningful(LABEL_ALTERNATIVE, checked)

    # -- cosmetic changes (AC-2): no history entry, ever ------------------------------------------------------
    def reorder_legs(self, new_order: Sequence[int]) -> None:
        """Reordering legs never changes strategy_metrics (order-independent), so it is cosmetic (AC-2)."""
        self._check_not_executed()
        order = tuple(new_order)
        if sorted(order) != list(range(len(self._legs))):
            raise BuilderHistoryError(f"new_order must be a permutation of 0..{len(self._legs) - 1}, got {order!r}")
        self._legs = tuple(self._legs[i] for i in order)

    def rename(self, new_name: str) -> None:
        """Renaming the session's display label touches no leg field, so it is cosmetic (AC-2)."""
        self._check_not_executed()
        if not isinstance(new_name, str) or not new_name.strip():
            raise BuilderHistoryError(f"new_name must be a non-empty string, got {new_name!r}")
        self._display_name = new_name

    def toggle_display(self, flag_name: str) -> None:
        """Toggling a display-only flag (e.g. 'collapsed') touches no leg field, so it is cosmetic (AC-2)."""
        self._check_not_executed()
        if not isinstance(flag_name, str) or not flag_name:
            raise BuilderHistoryError(f"flag_name must be a non-empty string, got {flag_name!r}")
        self._display_flags[flag_name] = not self._display_flags.get(flag_name, False)

    # -- restore and undo (AC-3, AC-4) -------------------------------------------------------------------------
    def restore(self, seq: int) -> HistoryEntry:
        """AC-3: jump straight to an earlier entry's configuration; the jump is itself recorded.

        The configuration being replaced is "preserved first" by construction: it is already the previous
        entry in this append-only log (every meaningful change, restore and undo always leaves ``current``
        equal to the last entry it appends).
        """
        self._check_not_executed()
        if isinstance(seq, bool) or not isinstance(seq, int):
            raise BuilderHistoryError(f"seq must be a plain int (not bool/float), got {seq!r}")
        target = self._entry_by_seq(seq)
        entry = self._append(LABEL_RESTORE, target.legs)
        self._legs = entry.legs
        self._undo_target = None
        return entry

    def undo(self) -> HistoryEntry:
        """AC-4: revert exactly the last meaningful change - jump to the entry BEFORE it, recorded as its own
        entry. Refuses once that window has closed (used already, or superseded by a later meaningful change)."""
        self._check_not_executed()
        if self._undo_target is None:
            raise BuilderHistoryError("nothing to undo: no meaningful change is pending, or it was already undone")
        target_index = next(i for i, e in enumerate(self._history) if e.seq == self._undo_target)
        previous_legs = self._history[target_index - 1].legs
        entry = self._append(LABEL_UNDO, previous_legs)
        self._legs = entry.legs
        self._undo_target = None
        return entry
