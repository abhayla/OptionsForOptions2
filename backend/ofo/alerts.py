"""The alert kinds: which conditions ask the user for a decision (ADR-330 (3), (3b), (4)).

Stdlib only. An ACTIONABLE kind is a record that stays open (Active) until the user answers; an INFORMATIONAL kind is a
History line that is never counted. The one writer is ``ofo_app.actionable_alerts``; the words live in the catalogue
(``ofo.errors.explanations``: ``alert_fired_at``, ``alert_no_longer_true_since``, label table ``alert_answer``).
Nothing here exits a position: an alert only informs and asks (ADR-003).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ofo.adjustment import stop_lines as sl

EXIT: Final = "exit"
CONTINUE: Final = "continue"
ADD_LEGS: Final = "add_legs"
CONFIRM_NEW_SHAPE: Final = "confirm_new_shape"
CLOSED_BY_SYSTEM: Final = "closed_by_system"
NOTED: Final = "noted"
#: every value of the answer column (migration 0054 CHECK; a test compares the two)
ANSWERS: Final = (EXIT, CONTINUE, ADD_LEGS, CONFIRM_NEW_SHAPE, CLOSED_BY_SYSTEM, NOTED)
#: the answers a USER may give; the other two are written by the system only
USER_ANSWERS: Final = (EXIT, CONTINUE, ADD_LEGS, CONFIRM_NEW_SHAPE)


@dataclass(frozen=True)
class AlertKind:
    code: str
    actionable: bool
    answers: tuple[str, ...]  # the answers the user may give (empty for an informational kind)
    wording_id: str  # the catalogue id of the kind's "Fired at" line


_FIRED = "alert_fired_at"
_ASK = (EXIT, CONTINUE)
KINDS: Final = {k.code: k for k in (
    AlertKind("plan_loss_stop", True, _ASK, _FIRED),
    AlertKind("plan_profit_target", True, _ASK, _FIRED),
    AlertKind("plan_rupee_loss", True, _ASK, _FIRED),
    AlertKind("plan_rupee_profit", True, _ASK, _FIRED),
    AlertKind("plan_time_exit", True, _ASK, _FIRED),
    AlertKind("adjustment_rule", True, _ASK, _FIRED),
    AlertKind("side_closed", True, (ADD_LEGS, CONFIRM_NEW_SHAPE), _FIRED),
    AlertKind("stop_fired", False, (), _FIRED),
    AlertKind("settled", False, (), _FIRED),
    AlertKind("orders_placed", False, (), _FIRED),
    AlertKind("stop_saved", False, (), _FIRED),
)}

#: the plan's loss stops: "% of max loss", "% of margin" and the 2x-credit line (``stop_lines``);
#: its profit target: "% of max profit" (T-07). Every other trigger is an adjustment rule.
_PLAN_LOSS_STOP: Final = frozenset({sl.TRIGGER_MAX_LOSS, sl.TRIGGER_MARGIN, sl.CREDIT_RULE})
_PLAN_PROFIT_TARGET: Final = frozenset({"T-07"})


def kind_of(trigger_id: str | None) -> str:
    """The kind of the condition a trigger id (or stop rule id) stands for; unknown or absent -> adjustment_rule."""
    if trigger_id in _PLAN_LOSS_STOP:
        return "plan_loss_stop"
    if trigger_id in _PLAN_PROFIT_TARGET:
        return "plan_profit_target"
    if trigger_id == sl.TRIGGER_TIME_EXIT:
        return "plan_time_exit"
    return "adjustment_rule"


def is_actionable(kind: str) -> bool:
    return kind in KINDS and KINDS[kind].actionable


def allowed_answers(kind: str) -> tuple[str, ...]:
    """The answers a user may give for ``kind``; an unknown kind allows none (fail closed)."""
    found = KINDS.get(kind)
    return found.answers if found is not None else ()
