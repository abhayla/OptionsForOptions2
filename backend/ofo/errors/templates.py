"""MessageTemplate catalogue + `render()`: the ONLY way to build a `UserFacingError` (W-024 round 3).

Core: user-facing error text comes only from this fixed, reviewed catalogue with typed slots, so the
ADR-003 wording check runs over a finite set in CI (`tests/errors/test_error_catalogue.py`), never
over arbitrary runtime strings.

Each template's four parts are plain strings with `{slot_name}` placeholders (`str.format` syntax);
`render` fills them from typed, validated slot values (`ofo.errors.slots`) and returns a
`UserFacingError`. No caller ever supplies free text for a part — only slot values.

No real personal data in any template text below: no names, no account numbers, no PAN-shaped
identifiers.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from ofo.errors.classes import ErrorClass
from ofo.errors.model import UserFacingError, _build, _claim_render_token
from ofo.instruments.catalogue import SUPPORTED_UNDERLYINGS

from ofo.errors.gate_slots import (
    Clock, ContractSymbol, DataHealthState, DataInputName, Date, ExecutionStatusName, LegContract, LegRef, OrderRef,
    RiskRows, Rupees, Strikes, Symbol, UnitsByContract, VersionStateName, VersionStates, WorstCase,
)
from ofo.errors.slots import Code, Count, ExternalText, Instrument, Int, Money, SlotType, Time, Underlying

_PART_NAMES: tuple[str, ...] = ("what_happened", "impact", "what_is_blocked", "next_action")


@dataclass(frozen=True)
class MessageTemplate:
    """One reviewed message: four part templates (`str.format` placeholders) plus the typed slots
    that fill them. `external_text_slot`, if set, names a slot (type `ExternalText`) shown verbatim
    in its own labelled field — never referenced inside `what_happened`/`impact`/`what_is_blocked`/
    `next_action`, so it can never be scanned as, or merged into, our own wording."""

    id: str
    error_class: ErrorClass
    code: str
    what_happened: str
    impact: str
    what_is_blocked: str
    next_action: str
    slots: Mapping[str, type[SlotType]] = field(default_factory=dict)
    external_text_slot: str | None = None

    def __post_init__(self) -> None:
        # Read-only slot map: a template's slot types cannot be swapped after it is defined.
        object.__setattr__(self, "slots", MappingProxyType(dict(self.slots)))


_TEMPLATES: tuple[MessageTemplate, ...] = (
    MessageTemplate(
        id="user_input_lot_size",
        error_class=ErrorClass.USER_INPUT,
        code="USER_INPUT_001",
        what_happened="The lot size you entered ({entered}) is not a positive whole number.",
        impact="The strategy cannot be priced or saved with this quantity.",
        what_is_blocked="Saving and pricing of this strategy.",
        next_action="Enter a lot size of 1 or more and try again.",
        slots={"entered": Int},
    ),
    MessageTemplate(
        id="strategy_validation_duplicate_leg",
        error_class=ErrorClass.STRATEGY_VALIDATION,
        code="STRATEGY_VALIDATION_001",
        what_happened="This strategy has two {instrument} legs on the same strike and expiry in the same direction.",
        impact="The payoff and margin shown would not match what the exchange allows.",
        what_is_blocked="Saving this strategy version.",
        next_action="Remove or change one of the duplicate legs, then save again.",
        slots={"instrument": Instrument},
    ),
    MessageTemplate(
        id="market_data_stale",
        error_class=ErrorClass.MARKET_DATA,
        code="MARKET_DATA_001",
        what_happened="No option chain data has arrived for {symbol} in the last {minutes} minutes.",
        impact="Prices and Greeks on screen are stale and may not match the live market.",
        what_is_blocked="New order preparation for this instrument.",
        next_action="Wait for the data feed to reconnect, or refresh the page in a few minutes.",
        slots={"symbol": Underlying, "minutes": Count},
    ),
    MessageTemplate(
        id="broker_authentication_session_expired",
        error_class=ErrorClass.BROKER_AUTHENTICATION,
        code="BROKER_AUTHENTICATION_001",
        what_happened="Your Zerodha session expired at {expired_at}.",
        impact="Orders, positions and margin cannot be read or sent to Zerodha right now.",
        what_is_blocked="Order preparation, submission and live position tracking.",
        next_action="Log in to Zerodha again from the account page to reconnect.",
        slots={"expired_at": Time},
    ),
    MessageTemplate(
        id="broker_eligibility_fo_segment",
        error_class=ErrorClass.BROKER_ELIGIBILITY,
        code="BROKER_ELIGIBILITY_001",
        what_happened="Your Zerodha account is not enabled for F&O segment trading.",
        impact="Options and futures orders placed here cannot be accepted by Zerodha.",
        what_is_blocked="Order submission for this strategy.",
        next_action="Enable the F&O segment in your Zerodha account, then retry.",
        slots={},
    ),
    MessageTemplate(
        id="margin_insufficient",
        error_class=ErrorClass.MARGIN,
        code="MARGIN_001",
        what_happened="Margin available {available} is below the {required} this strategy needs.",
        impact="Zerodha would reject this order for insufficient margin.",
        what_is_blocked="Execution of this strategy.",
        next_action="Add funds in Zerodha or reduce the quantity, then retry.",
        slots={"available": Money, "required": Money},
    ),
    MessageTemplate(
        id="order_rejection_leg",
        error_class=ErrorClass.ORDER_REJECTION,
        code="ORDER_REJECTION_001",
        # Round 3: the paraphrased broker reason ("price outside the circuit limit") is replaced by
        # the real Zerodha message, quoted verbatim in its own labelled field (external_text_slot
        # below) — never paraphrased or merged into this sentence.
        what_happened="Zerodha rejected one leg of this order.",
        impact="This leg was not placed, so the strategy is only partly submitted.",
        what_is_blocked="Further legs of this order until this one is resolved.",
        next_action="Review Zerodha's message below and resubmit this leg.",
        slots={},
        external_text_slot="broker_message",
    ),
    MessageTemplate(
        id="partial_execution_legs",
        error_class=ErrorClass.PARTIAL_EXECUTION,
        code="PARTIAL_EXECUTION_001",
        what_happened="{filled} of {total} legs filled; the remaining legs are still open at Zerodha.",
        impact="The strategy's current position does not match its intended shape yet.",
        what_is_blocked="Automatic adjustments and rule evaluation for this strategy.",
        next_action="Check the open legs in Zerodha and cancel or complete them manually.",
        slots={"filled": Count, "total": Count},
    ),
    MessageTemplate(
        id="reconciliation_mismatch_lots",
        error_class=ErrorClass.RECONCILIATION_MISMATCH,
        code="RECONCILIATION_MISMATCH_001",
        what_happened="Zerodha shows {broker_lots} lots on this leg; this platform's record shows {platform_lots} lots.",
        impact="P&L, Greeks and rule checks for this strategy cannot be trusted until this is resolved.",
        what_is_blocked="New orders and automatic rule triggers for this strategy.",
        next_action="Review the mismatch on the reconciliation screen and confirm which figure is correct.",
        slots={"broker_lots": Count, "platform_lots": Count},
    ),
    MessageTemplate(
        id="notification_delivery_failed",
        error_class=ErrorClass.NOTIFICATION,
        code="NOTIFICATION_001",
        what_happened="The WhatsApp alert for this rule trigger could not be delivered.",
        impact="You may not have seen that this rule was triggered.",
        what_is_blocked="Further WhatsApp alerts on this channel until delivery succeeds again.",
        next_action="Check the alert on this page directly, and confirm your WhatsApp number is correct.",
        slots={},
    ),
    MessageTemplate(
        id="entitlement_access_trial_ended",
        error_class=ErrorClass.ENTITLEMENT_ACCESS,
        code="ENTITLEMENT_ACCESS_001",
        what_happened="Your trial period for this feature ended on {ended_at}.",
        impact="This feature's screens and actions are read-only.",
        what_is_blocked="Creating or editing strategies that use this feature.",
        next_action="Upgrade your plan on the billing page to regain access.",
        slots={"ended_at": Time},
    ),
    MessageTemplate(
        id="internal_system_save_failed",
        error_class=ErrorClass.INTERNAL_SYSTEM,
        code="INTERNAL_SYSTEM_001",
        what_happened="An unexpected server error occurred while saving this strategy (reference {reference}).",
        impact="Your latest changes to this strategy were not saved.",
        what_is_blocked="Saving this strategy until the issue is resolved.",
        next_action="Try again in a few minutes; contact support if this keeps happening.",
        slots={"reference": Code},
    ),
)


# --- Round 9 (issue #30): the execution safety gate (REQ-059) and the disconnect status (REQ-049 AC-5) -----------
# Each `what_happened` keeps the sentence the gate showed before round 9 (W-014's reviewed reason text), except the
# expired-leg message, which uses the brief's wording; the other three parts are new and await the owner's read
# (tests/errors/template_pins.json, docs/process/w024-templates-for-owner.md).

_EXEC = "Execution of this strategy."
_RECONNECT = "Reconnect your Zerodha account from the account page, then try again."
_NO_ALTERNATIVE = " No nearby listed strike is available to offer."
_ALTERNATIVES = " Strikes you could consider instead: {strikes}. Your strategy has not been changed."
_PICK_OR_REMOVE = "Pick one of the strikes shown for this leg yourself, or remove the leg, then check again."
_REPLACE_OR_REMOVE = "Replace or remove this leg, then check again."
_NOT_TRADABLE = "This leg cannot be sent to Zerodha as it stands."
_PRO_IMPACT = "This action is not available on your current plan."
_PRO_BLOCKED = "This entry or adjustment."
_PRO_NEXT = "Upgrade to Pro to continue, or exit or reduce the strategy instead."


def _gate(id: str, error_class: ErrorClass, number: int, what: str, impact: str, blocked: str, next_: str,
          slots: Mapping[str, type[SlotType]] | None = None) -> MessageTemplate:
    return MessageTemplate(
        id=id, error_class=error_class, code=f"{error_class.name}_{number:03d}", what_happened=what, impact=impact,
        what_is_blocked=blocked, next_action=next_, slots=dict(slots or {}),
    )


def _contract_pair(id: str, error_class: ErrorClass, number: int, problem: str) -> tuple[MessageTemplate, ...]:
    """A contract problem in its two forms: no alternative strike to offer, and one or two offered (never applied)."""
    return (
        _gate(id, error_class, number, "{leg} " + problem + _NO_ALTERNATIVE, _NOT_TRADABLE, _EXEC,
              _REPLACE_OR_REMOVE, {"leg": LegRef}),
        _gate(id + "_alternatives", error_class, number + 1, "{leg} " + problem + _ALTERNATIVES, _NOT_TRADABLE, _EXEC,
              _PICK_OR_REMOVE, {"leg": LegRef, "strikes": Strikes}),
    )


_SUPPORTED = ", ".join(SUPPORTED_UNDERLYINGS)
_UI, _SV, _MD = ErrorClass.USER_INPUT, ErrorClass.STRATEGY_VALIDATION, ErrorClass.MARKET_DATA
_BA, _BE, _MG = ErrorClass.BROKER_AUTHENTICATION, ErrorClass.BROKER_ELIGIBILITY, ErrorClass.MARGIN
_EA, _RM, _IS = ErrorClass.ENTITLEMENT_ACCESS, ErrorClass.RECONCILIATION_MISMATCH, ErrorClass.INTERNAL_SYSTEM
_PE = ErrorClass.PARTIAL_EXECUTION
_PARTIAL_BLOCKED = "Completing, retrying or closing this strategy."

_GATE_TEMPLATES: tuple[MessageTemplate, ...] = (
    _gate("gate_underlying_unsupported", _UI, 101,
          "{symbol} is not supported. Supported underlyings: " + _SUPPORTED + ".",
          "None of this strategy's contracts can be checked or traded on this platform.", _EXEC,
          "Build the strategy on a supported underlying.", {"symbol": Symbol}),
    _gate("gate_lot_size_unconfirmed", _UI, 102, "{leg}: the lot size for this expiry could not be confirmed.",
          "The quantity of this leg cannot be checked against the exchange lot size.", _EXEC,
          "Refresh the instrument list, then check again.", {"leg": LegRef}),
    _gate("gate_quantity_not_lots", _UI, 103,
          "{leg}: quantity {quantity} is not a whole number of lots. The {underlying} lot size for this expiry is "
          "{lot} (for example {lot} or {two_lots}).",
          "The exchange accepts orders only in whole lots.", _EXEC,
          "Change this leg's quantity to a whole number of lots, then check again.",
          {"leg": LegRef, "quantity": Count, "underlying": Underlying, "lot": Count, "two_lots": Count}),
    _gate("gate_version_not_executable", _SV, 101,
          "This version of the strategy is {state}. This action executes only a version that is {allowed}.",
          "The orders would not match the strategy version this action is meant for.",
          "This action on this strategy version.", "Open the version this action applies to, then try again.",
          {"state": VersionStateName, "allowed": VersionStates}),
    _gate("gate_rules_unconfirmed", _SV, 102,
          "We could not confirm that this strategy's rules are valid. Review them to continue.",
          "Monitoring could act on rules that have not been checked.", _EXEC,
          "Open the strategy's rules and save them again."),
    _gate("gate_rules_invalid", _SV, 103, "This strategy's rules are not valid. Review them to continue.",
          "Monitoring cannot act on rules that are not valid.", _EXEC,
          "Correct the rules marked as not valid, then save the strategy."),
    _gate("gate_dependencies_unconfirmed", _SV, 104,
          "We could not confirm that the orders this execution depends on are in place.",
          "Orders could be placed without the orders they rely on.", _EXEC,
          "Check the strategy's open orders, then try again."),
    _gate("gate_dependencies_unsatisfied", _SV, 105,
          "An order this execution depends on is not in place yet (for example a protective leg).",
          "Orders could be placed without the order they rely on.", _EXEC,
          "Place the order this execution depends on first, then try again."),
    _gate("gate_duplicate_leg", _SV, 106,
          "{leg} is the same contract as leg {other}. The legs have not been combined; edit the strategy to keep "
          "one or combine them yourself.",
          "Two legs on one contract would be sent as separate orders.", _EXEC,
          "Edit the strategy so each contract appears in one leg only.", {"leg": LegRef, "other": Count}),
    _gate("gate_exit_unverified", _SV, 107,
          "We could not compare this exit with the strategy's open positions. Execution is blocked and no order "
          "has been submitted.",
          "An exit could open a position instead of closing one.", "This exit.",
          "Refresh the strategy's positions from Zerodha, then try the exit again."),
    _gate("gate_exit_adds_position", _SV, 108,
          "This exit includes an order that would open or add to a position instead of closing one. An exit can "
          "only close or reduce positions this strategy holds.",
          "Sending it would add risk instead of removing it.", "This exit.",
          "Remove the order that opens or adds to a position, then try the exit again."),
    _gate("gate_market_unconfirmed", _MD, 101,
          "We could not confirm that the market is open. Execution is paused until it is confirmed.",
          "No order can be placed while the market's status is unknown.", _EXEC,
          "Try again once the market status is shown."),
    _gate("gate_market_closed", _MD, 102, "The market is closed. Orders can be placed once it opens.",
          "No order can be placed while the market is closed.", _EXEC,
          "Return during market hours and execute again."),
    _gate("gate_data_unhealthy", _MD, 103,
          "Market data needed for execution ({data_input}) {state}. Execution is paused until it is current.",
          "Prices, margin and checks could rest on data that does not match the market.", _EXEC,
          "Wait for the data to update, then try again.", {"data_input": DataInputName, "state": DataHealthState}),
    _gate("gate_expiry_passed", _MD, 104, "Leg {leg} ({contract}) expired on {date}.",
          "This strategy cannot be executed as planned.", "Execute", "Replace or remove this leg.",
          {"leg": Count, "contract": LegContract, "date": Date}),
    _gate("gate_contract_ambiguous", _MD, 105, "{leg} matches more than one contract in the instrument list.",
          _NOT_TRADABLE, _EXEC, "Refresh the instrument list, then check again.", {"leg": LegRef}),
    *_contract_pair("gate_contract_not_found", _MD, 106, "does not exist in Zerodha's instrument list."),
    *_contract_pair("gate_contract_no_zerodha_record", _MD, 108,
                    "has no Zerodha instrument record, so it cannot be traded at Zerodha."),
    *_contract_pair("gate_contract_not_listed", _MD, 110, "is no longer listed by Zerodha."),
    *_contract_pair("gate_contract_unconfirmed", _BE, 101,
                    "has not been confirmed as available on Zerodha yet. Refresh availability to continue."),
    *_contract_pair("gate_contract_unavailable", _BE, 103,
                    "is currently unavailable on Zerodha. Zerodha isn't accepting fresh orders for this contract "
                    "right now."),
    _gate("gate_broker_unconfirmed", _BA, 101, "We could not confirm your Zerodha connection. Reconnect to continue.",
          "Orders cannot be sent to Zerodha.", _EXEC, _RECONNECT),
    _gate("gate_broker_not_connected", _BA, 102, "Your Zerodha account is not connected. Connect it to continue.",
          "Orders cannot be sent to Zerodha.", _EXEC, "Connect your Zerodha account from the account page."),
    _gate("gate_session_unconfirmed", _BA, 103, "We could not confirm your Zerodha session. Reconnect to continue.",
          "Orders cannot be sent to Zerodha.", _EXEC, _RECONNECT),
    _gate("gate_session_expired", _BA, 104, "Your Zerodha session has expired. Reconnect to continue.",
          "Orders cannot be sent to Zerodha.", _EXEC, _RECONNECT),
    _gate("gate_margin_unconfirmed", _MG, 101,
          "We could not confirm your available margin with Zerodha. Execution is paused.",
          "The orders could be rejected for insufficient margin.", _EXEC,
          "Check your margin in Zerodha, then try again."),
    _gate("gate_margin_insufficient", _MG, 102,
          "Available margin {available} is less than the estimated {required} this strategy needs. Zerodha's figure "
          "is final. No order has been submitted.",
          "Zerodha would reject these orders for insufficient margin.", _EXEC,
          "Add funds in Zerodha or reduce the quantity, then try again.",
          {"available": Rupees, "required": Rupees}),
    _gate("gate_entitlement_unconfirmed", _EA, 101,
          "We could not confirm your plan. New entries and adjustments that add or change positions need Pro.",
          "This action cannot run until your plan is confirmed.", _PRO_BLOCKED,
          "Reload the page to confirm your plan, or exit or reduce the strategy instead."),
    _gate("gate_entitlement_pro", _EA, 102,
          "New entries and adjustments that add or change positions need Pro. Exiting, or closing or reducing legs "
          "of an active strategy, stays available on every plan.",
          _PRO_IMPACT, _PRO_BLOCKED, _PRO_NEXT),
    _gate("gate_entitlement_worse_worst_case", _EA, 103,
          "This adjustment makes the strategy's worst case at expiry larger (option premiums excluded): from "
          "{before} to {after}. Adjustments that add risk need Pro. Exiting, or closing or reducing legs without a "
          "larger worst case, stays available on every plan.",
          _PRO_IMPACT, _PRO_BLOCKED, _PRO_NEXT, {"before": WorstCase, "after": WorstCase}),
    _gate("gate_entitlement_futures_entry_unknown", _EA, 104,
          "Entry price of a futures leg is not known yet — adjustment needs Pro until it is.",
          _PRO_IMPACT, _PRO_BLOCKED, _PRO_NEXT),
    _gate("gate_entitlement_multi_expiry", _EA, 105,
          "This strategy has legs on more than one expiry. Without Pro it can be exited, reduced by the same share "
          "on every leg, or have only its sold options closed; other adjustments may add risk and need Pro.",
          _PRO_IMPACT, _PRO_BLOCKED, _PRO_NEXT),
    _gate("gate_reconciliation_unknown", _RM, 101,
          "Reconciliation status unknown. Execution is blocked until your Zerodha positions have been reconciled.",
          "The platform cannot tell whether its record matches your Zerodha positions.", _EXEC,
          "Run reconciliation for your account, then try again."),
    _gate("gate_reconciliation_mismatch", _RM, 102,
          "Your Zerodha positions for this strategy do not match what we recorded. Resolve the mismatch to "
          "continue.",
          "P&L, checks and new orders for this strategy would rest on the wrong positions.", _EXEC,
          "Open the reconciliation screen and resolve the mismatch."),
    _gate("gate_active_legs_unverified", _RM, 103,
          "This strategy's open positions could not be verified against its stored active version. Execution is "
          "blocked and no order has been submitted.",
          "Orders could be prepared from positions this strategy does not hold.", _EXEC,
          "Reload the strategy so its positions are read again, then try again."),
    _gate("gate_strategy_mismatch", _RM, 104,
          "This check was prepared for a different strategy. Execution is blocked; reopen the strategy to continue.",
          "The checks shown do not belong to this strategy.", _EXEC, "Reopen this strategy and check again."),
    _gate("gate_internal_error", _IS, 101,
          "An internal error stopped the safety checks. Execution is blocked and no order has been submitted.",
          "The platform could not finish checking this strategy before execution.", _EXEC,
          "Try again in a few minutes; contact support if this keeps happening."),
    # Strategy template catalogue (ofo.strategy.loader): the user sees this; the developer detail stays on the error.
    _gate("strategy_catalogue_unreadable", _IS, 102, "The strategy template list could not be read.",
          "Strategy templates cannot be offered right now.", "Choosing a strategy from a template.",
          "Build the strategy leg by leg for now; contact support if this keeps happening."),
    _gate("strategy_catalogue_invalid", _IS, 103,
          "The strategy template list has {count} problem(s) and could not be loaded.",
          "Strategy templates cannot be offered right now.", "Choosing a strategy from a template.",
          "Build the strategy leg by leg for now; contact support if this keeps happening.", {"count": Count}),
    # Partial execution (ofo.execution.partial, REQ-058): each what-happened keeps the sentence shown before round 9,
    # minus any raw exception text (logged instead).
    _gate("partial_reread_failed", _PE, 101,
          "We could not re-read your Zerodha positions and orders. No order has been prepared.",
          "The platform does not know this strategy's current state at Zerodha.", _PARTIAL_BLOCKED,
          "Try again in a moment; check the positions in Zerodha if this keeps happening."),
    _gate("partial_nothing_prepared", _PE, 102, "Nothing prepared.", "No order is waiting for your confirmation.",
          _PARTIAL_BLOCKED, "Check the strategy's state, then choose again."),
    _gate("partial_status_not_partial", _PE, 103, "Nothing prepared: the strategy is {status}.",
          "Completing, retrying or closing applies only to a partly executed strategy.", _PARTIAL_BLOCKED,
          "Check the strategy's state, then choose again.", {"status": ExecutionStatusName}),
    _gate("partial_waiting", _PE, 104,
          "Another preparation for this strategy is waiting for your confirmation. Confirm or discard it first. "
          "No order has been prepared.",
          "Only one set of orders can wait for your confirmation at a time.", "A new preparation for this strategy.",
          "Confirm or discard the waiting orders, then choose again."),
    _gate("partial_in_flight", _PE, 105,
          "Orders for this strategy are in flight and Zerodha has not confirmed them yet. No order has been "
          "prepared; check again once they are confirmed.",
          "New orders now could duplicate the ones Zerodha is still handling.", _PARTIAL_BLOCKED,
          "Wait for Zerodha to confirm the open orders, then check again."),
    _gate("partial_needs_fresh_read", _PE, 106,
          "You chose Close Partial Strategy. Completing or retrying needs a fresh read of your Zerodha positions "
          "taken after that choice. No order has been prepared.",
          "Orders based on the earlier read could add to positions you chose to close.", "Completing or retrying.",
          "Refresh the strategy's positions from Zerodha, then choose again."),
    _gate("partial_gate_blocked", _PE, 107, "The safety checks blocked this. No order has been prepared.",
          "The orders cannot be sent until every safety check passes.", _PARTIAL_BLOCKED,
          "Read the safety check results shown with this, resolve them, then try again."),
    _gate("partial_ready", _PE, 108, "{count} order(s) ready for your confirmation.",
          "Nothing is sent to Zerodha until you confirm.", "Sending these orders until you confirm them.",
          "Review the orders, then confirm or discard them.", {"count": Count}),
    _gate("partial_margin_reread_failed", _PE, 109,
          "We could not re-read your available margin. No order has been prepared.",
          "The orders could be rejected for insufficient margin.", _PARTIAL_BLOCKED,
          "Try again in a moment; check your margin in Zerodha if this keeps happening."),
    _gate("partial_already_complete", _PE, 110,
          "Zerodha now shows every leg filled. The strategy is complete; nothing was prepared.",
          "No further order is needed for this strategy.", "Completing or retrying this strategy.",
          "Review the filled strategy on its page."),
    _gate("partial_review_manually", _PE, 111,
          "Review the filled and failed legs below. No order has been prepared.",
          "The strategy stays partly executed until you choose an action.", "Automatic completion of this strategy.",
          "Choose Complete Strategy, Retry Failed Leg or Close Partial Strategy when ready."),
    _gate("partial_no_price", _PE, 112,
          "Zerodha did not give a current price for every filled leg. No order has been prepared.",
          "Exit orders cannot be priced without a current price.", "Closing this strategy.",
          "Try again once Zerodha shows a price for every filled leg."),
    _gate("partial_exits_in_flight", _PE, 113,
          "Exit orders for every filled leg are already in flight. No order has been prepared.",
          "More exit orders could close more than the strategy holds.", "Closing this strategy.",
          "Wait for Zerodha to confirm the open exit orders, then check again."),
    # REQ-049 AC-5's exact sentence is the what-happened part (owner-cited); the other three are new.
    _gate("marketdata_disconnected", _MD, 120,
          "Live market data disconnected. Last updated: {time}. Live strategy monitoring is paused.",
          "Prices on screen may not match the live market, and rules are not checked while data is missing.",
          "Rule monitoring for this strategy.", "Wait for the feed to reconnect; monitoring resumes on its own.",
          {"time": Clock}),
)


# Broker sink refusals (ofo.execution.send_guard, REQ-036): raised before anything is sent; each keeps the meaning of
# the message the sink raised before round 9 and adds the other three parts (pending owner read).
_SEND_IMPACT = "No order was sent to Zerodha."
_SEND_BLOCKED = "Sending these orders to Zerodha."
_SEND_REPREPARE = "Prepare the orders again from the strategy's current version, then confirm them."
_SEND_SUPPORT = "Try again in a few minutes; contact support if this keeps happening."
_VERSION_NOTE = "The orders would not match the version of the strategy this action is meant for."
_WRONG_SIDE = " A wrong side could add to a position instead of completing or closing it."

_SEND_TEMPLATES: tuple[MessageTemplate, ...] = (
    _gate("send_request_not_from_sink", _IS, 201, "A broker request was built outside the broker sink.",
          _SEND_IMPACT, _SEND_BLOCKED, _SEND_SUPPORT),
    _gate("send_version_not_live", _SV, 201,
          "Version v{version} is neither the active nor the pending version of this strategy.",
          _SEND_IMPACT + " " + _VERSION_NOTE, _SEND_BLOCKED, _SEND_REPREPARE, {"version": Count}),
    _gate("send_choice_unknown", _IS, 202, "The chosen action sends no orders.", _SEND_IMPACT, _SEND_BLOCKED,
          "Choose Complete Strategy, Retry Failed Leg or Close Partial Strategy, then try again."),
    _gate("send_order_wrong_version", _SV, 202, "An order does not belong to this strategy version.",
          _SEND_IMPACT + " " + _VERSION_NOTE, _SEND_BLOCKED, _SEND_REPREPARE),
    _gate("send_contract_not_a_leg", _SV, 203, "An order names a contract that is not a leg of version v{version}.",
          _SEND_IMPACT, _SEND_BLOCKED, _SEND_REPREPARE, {"version": Count}),
    _gate("send_side_not_allowed", _SV, 204, "An order's side is not the side this action sends for that leg.",
          _SEND_IMPACT + _WRONG_SIDE, _SEND_BLOCKED, _SEND_REPREPARE),
    _gate("send_quantity_exceeds", _SV, 205,
          "{units} units in an order exceed what the strategy allows ({room} units remain for that contract).",
          _SEND_IMPACT + " A larger quantity could take the position past the strategy's plan.", _SEND_BLOCKED,
          _SEND_REPREPARE, {"units": Count, "room": Count}),
    _gate("send_catalogue_not_one", _MD, 201,
          "The instrument catalogue has {count} instruments for a leg of this strategy; exactly one is needed.",
          _SEND_IMPACT + " No trading symbol can be chosen for that leg.", _SEND_BLOCKED,
          "Refresh the instrument list, then prepare the orders again.", {"count": Count}),
    _gate("send_no_zerodha_record", _MD, 202,
          "A leg has no Zerodha instrument record, so no trading symbol can be derived for it.",
          _SEND_IMPACT + " No symbol is guessed.", _SEND_BLOCKED,
          "Refresh the instrument list, then replace or remove this leg."),
    _gate("send_catalogue_missing", _IS, 203,
          "The broker sink needs the instrument catalogue to derive trading symbols.",
          _SEND_IMPACT, _SEND_BLOCKED, _SEND_SUPPORT),
    _gate("send_order_other_strategy", _SV, 206, "An order does not belong to this strategy.",
          _SEND_IMPACT, _SEND_BLOCKED, _SEND_REPREPARE),
    _gate("send_version_unreadable", _SV, 207, "An order names a strategy version that cannot be read.",
          _SEND_IMPACT + " " + _VERSION_NOTE, _SEND_BLOCKED, _SEND_REPREPARE),
    _gate("send_leg_not_in_version", _SV, 208, "An order names a leg that is not part of version v{version}.",
          _SEND_IMPACT, _SEND_BLOCKED, _SEND_REPREPARE, {"version": Count}),
    _gate("send_symbol_mismatch", _SV, 209, "An order's contract is not the catalogue symbol of its leg.",
          _SEND_IMPACT + " The symbol is always taken from the catalogue, never from the order.", _SEND_BLOCKED,
          _SEND_REPREPARE),
    _gate("send_side_not_leg_side", _SV, 210, "An order's side is not the side of its leg.",
          _SEND_IMPACT + _WRONG_SIDE, _SEND_BLOCKED, _SEND_REPREPARE),
    _gate("send_client_tag_missing", _IS, 204, "The platform's client tag is missing from an order.",
          _SEND_IMPACT, _SEND_BLOCKED, _SEND_SUPPORT),
    _gate("send_request_not_resolved", _IS, 205,
          "The broker sink did not resolve this request, or it was already sent.",
          _SEND_IMPACT + " Each request is sent once at most.", _SEND_BLOCKED,
          "Check the strategy's orders in Zerodha before preparing anything again."),
)


# Reconciliation mismatches (ofo.reconciliation.compare, REQ-060 AC-3): one template per MismatchKind. Each
# `next_action` is the exact sentence the comparison recorded before round 9 (the audit record keeps it); the other
# three parts are new (pending owner read).
_REC_IMPACT = "P&L, Greeks and rule checks for this strategy cannot be trusted until this is resolved."
_REC_BLOCKED = "New orders and automatic rule triggers for the strategies this mismatch names."
_REC_NONE_BLOCKED = "Nothing: no strategy is blocked by this mismatch."
_REC_RECONCILE = (
    "Reconcile this strategy: adopt the broker position, prepare a closing or restoring order, or mark as requiring "
    "attention."
)
_REC_SLOT = {"contracts": Count}

_RECONCILIATION_TEMPLATES: tuple[MessageTemplate, ...] = (
    _gate("recon_missing_platform_position", _RM, 201,
          "Zerodha shows none of the position this strategy holds on {contracts} contract(s).",
          _REC_IMPACT, _REC_BLOCKED,
          "Reconcile this strategy: adopt the broker position, prepare a closing or restoring order, mark as "
          "requiring attention, or (if the broker is flat) mark the strategy exited.", _REC_SLOT),
    _gate("recon_unexpected_broker_position", _RM, 202,
          "Zerodha shows a position on {contracts} contract(s) that no strategy or recorded standalone position holds.",
          "The platform's record does not include this position.", _REC_NONE_BLOCKED,
          "Choose how to group it: add to an existing strategy, create a new strategy, or leave it standalone. "
          "No strategy is blocked.", _REC_SLOT),
    _gate("recon_quantity_mismatch", _RM, 203,
          "Zerodha's quantity on {contracts} contract(s) differs from the platform's record for this strategy.",
          _REC_IMPACT, _REC_BLOCKED, _REC_RECONCILE, _REC_SLOT),
    _gate("recon_strike_mismatch", _RM, 204,
          "Zerodha shows this strategy's quantity on a different strike from the one recorded ({contracts} "
          "contract(s) involved).", _REC_IMPACT, _REC_BLOCKED, _REC_RECONCILE, _REC_SLOT),
    _gate("recon_side_mismatch", _RM, 205,
          "Zerodha shows the opposite side (buy or sell) from the platform's record on {contracts} contract(s).",
          _REC_IMPACT, _REC_BLOCKED, _REC_RECONCILE, _REC_SLOT),
    _gate("recon_expiry_mismatch", _RM, 206,
          "Zerodha shows this strategy's quantity on a different expiry from the one recorded ({contracts} "
          "contract(s) involved).", _REC_IMPACT, _REC_BLOCKED, _REC_RECONCILE, _REC_SLOT),
    _gate("recon_external_modification", _RM, 207,
          "A change on {contracts} contract(s) was made outside the platform; no platform order or fill explains it.",
          _REC_IMPACT, _REC_BLOCKED,
          "Review the change made outside the platform, then reconcile: adopt the broker position, prepare a "
          "closing or restoring order, or mark as requiring attention.", _REC_SLOT),
    _gate("recon_partial_execution", _RM, 208,
          "This strategy is partly executed on {contracts} contract(s): Zerodha shows part of the planned quantity.",
          _REC_IMPACT, _REC_BLOCKED,
          "Partially executed: Complete Strategy, Retry Failed Leg, Review Manually or Close Partial Strategy.",
          _REC_SLOT),
    _gate("recon_standalone_changed", _RM, 209,
          "A recorded standalone position changed on {contracts} contract(s).",
          "The recorded standalone quantity no longer matches Zerodha.", _REC_NONE_BLOCKED,
          "Review the standalone position and update its recorded quantity. No strategy is blocked.", _REC_SLOT),
)


# Round 9 part 4: Strategy Guard refusals (ofo.strategy.guard) and the partial-execution flow's remaining texts
# (slicing refusals, a stale read, broker-versus-platform mismatches). All pending owner read.
_GUARD_NO_SEND = "No order was sent to Zerodha."
_GUARD_BLOCKED = "Sending these orders to Zerodha until you acknowledge the change."
_SLICE_NEXT = "Check the strategy's filled quantities and the contract in Zerodha, then choose again."
_MISMATCH_BLOCKED = "Completing, retrying or closing this strategy."
_MISMATCH_NEXT = "Check the order or position in Zerodha, then refresh this strategy from Zerodha and choose again."
_PORDER = {"order": OrderRef}
_PCONTRACT = {"contract": ContractSymbol}

_PART4_TEMPLATES: tuple[MessageTemplate, ...] = (
    _gate("guard_risk_profile_changed", _SV, 301, "This action changes your strategy's risk profile",
          "The strategy's maximum profit, maximum loss, breakevens, premium, margin or position would differ from "
          "what it is now.", _GUARD_BLOCKED,
          "Read the before and after figures shown with this, then acknowledge the change or discard the action."),
    _gate("guard_not_checked", _SV, 302,
          "Strategy Guard has not checked this exact action for this strategy and version.",
          _GUARD_NO_SEND, "Sending these orders to Zerodha.", "Check the action again, then confirm it."),
    _gate("guard_acknowledgement_required", _SV, 303,
          "This action changes your strategy's risk profile: {rows}.", _GUARD_NO_SEND, _GUARD_BLOCKED,
          "Read the before and after figures, acknowledge the change, then confirm again.", {"rows": RiskRows}),
    _gate("partial_ready_risk_changed", _PE, 114,
          "This action changes your strategy's risk profile. {count} order(s) ready for your confirmation.",
          "Nothing is sent to Zerodha until you acknowledge the change and confirm.",
          "Sending these orders until you acknowledge the change and confirm them.",
          "Read the before and after figures, then acknowledge the change and confirm the orders, or discard them.",
          {"count": Count}),
    _gate("partial_slice_not_whole_lots", _PE, 115,
          "Nothing prepared: {units} units of {contract} is not a whole number of lots of {lot}.",
          "Zerodha accepts orders only in whole lots.", _PARTIAL_BLOCKED, _SLICE_NEXT,
          {"units": Count, "contract": ContractSymbol, "lot": Count}),
    _gate("partial_slice_freeze_below_lot", _PE, 116,
          "Nothing prepared: the freeze quantity for {contract} is below one lot of {lot}.",
          "Orders for this contract cannot be split into whole lots within the freeze quantity.",
          _PARTIAL_BLOCKED, _SLICE_NEXT, {"contract": ContractSymbol, "lot": Count}),
    _gate("partial_slice_too_many_orders", _PE, 117,
          "Nothing prepared: {units} units of {contract} at a freeze of {freeze} would need more than {limit} orders.",
          "The orders for this contract exceed the number this platform prepares at once.",
          _PARTIAL_BLOCKED, _SLICE_NEXT,
          {"units": Count, "contract": ContractSymbol, "freeze": Count, "limit": Count}),
    _gate("partial_slice_no_lot_size", _PE, 118,
          "Nothing prepared: the instrument list has {count} instruments with the symbol {contract}, so its lot "
          "size is unknown.", "Order sizes cannot be checked against the exchange lot size.", _PARTIAL_BLOCKED,
          "Refresh the instrument list, then choose again.", {"count": Count, "contract": ContractSymbol}),
    _gate("partial_slice_freeze_unusable", _PE, 120,
          "Nothing prepared: the freeze quantity for {contract} is not a positive integer.",
          "Orders for this contract cannot be split without a usable freeze quantity.",
          _PARTIAL_BLOCKED, _SLICE_NEXT, {"contract": ContractSymbol}),
    _gate("partial_read_stale", _PE, 119,
          "Nothing prepared: the stale broker read could not be used; it became too old while the orders were "
          "being prepared.", "Orders based on an old read could add to positions that have since changed.",
          _PARTIAL_BLOCKED, "Refresh the strategy's positions from Zerodha, then choose again."),
    _gate("partial_mismatch_unknown_order", _RM, 301,
          "Zerodha shows order {order} that the platform has no record of.",
          "This strategy's positions may include orders the platform did not place.", _MISMATCH_BLOCKED,
          _MISMATCH_NEXT, _PORDER),
    _gate("partial_mismatch_other_strategy", _RM, 302, "Order {order} belongs to another strategy.",
          "The platform cannot count this order toward this strategy.", _MISMATCH_BLOCKED, _MISMATCH_NEXT, _PORDER),
    _gate("partial_mismatch_order_unmatched", _RM, 303,
          "Order {order} could not be matched with this strategy's record.",
          "The platform cannot confirm this order's state.", _MISMATCH_BLOCKED, _MISMATCH_NEXT, _PORDER),
    _gate("partial_mismatch_order_missing", _RM, 304,
          "Order {order} is not in Zerodha's order list {seconds}s after it was sent.",
          "The platform cannot tell whether this order was placed.", _MISMATCH_BLOCKED, _MISMATCH_NEXT,
          {"order": OrderRef, "seconds": Count}),
    _gate("partial_mismatch_outside_plan", _RM, 305,
          "{contract}: Zerodha shows a position outside this strategy's plan.",
          "The strategy's position does not match its plan.", _MISMATCH_BLOCKED, _MISMATCH_NEXT, _PCONTRACT),
    _gate("partial_mismatch_quantity", _RM, 306,
          "{contract}: Zerodha shows {units} units; the plan allows 0 to {limit}.",
          "The strategy's position does not match its plan.", _MISMATCH_BLOCKED, _MISMATCH_NEXT,
          {"contract": ContractSymbol, "units": Int, "limit": Int}),
    _gate("partial_mismatch_fills_differ", _RM, 307,
          "The fills the platform confirmed ({ledger}) differ from the positions Zerodha shows ({broker}).",
          "The strategy's position cannot be trusted until the difference is explained.", _MISMATCH_BLOCKED,
          _MISMATCH_NEXT, {"ledger": UnitsByContract, "broker": UnitsByContract}),
    _gate("partial_mismatch_unresolved", _RM, 308, "This strategy has an unresolved reconciliation mismatch.",
          "The strategy's position cannot be trusted until it is reconciled.", _MISMATCH_BLOCKED,
          "Reconcile this strategy first, then choose again."),
)

# --- Round 9 part 6: the API boundary (backend/ofo_app/errors.py). Any exception that is not `UserFacing` shows the
# first; a request the API cannot read, or an address it does not serve, shows the other two. The exception's own
# text is logged with the reference, never shown. New: awaiting the owner's read.
_BOUNDARY_TEMPLATES: tuple[MessageTemplate, ...] = (
    _gate("internal_system_request_failed", _IS, 2,
          "An unexpected server error stopped this request (reference {reference}).",
          "The action you asked for was not completed.", "This request, until the issue is resolved.",
          "Try again in a few minutes; contact support with the reference if this keeps happening.",
          {"reference": Code}),
    _gate("user_input_request_invalid", _UI, 2,
          "Some of the values sent with this request are missing or not in the expected form.",
          "The request was not carried out.", "This request, until its values are corrected.",
          "Check the values you entered and try again."),
    _gate("user_input_request_not_available", _UI, 3,
          "The page or action you asked for is not available here.",
          "Nothing was changed.", "This request.",
          "Go back to the previous page and choose again."),
    # Fix round (review MINOR): a 401 is a sign-in problem, a 503 a service that is down for now, not a 500.
    _gate("entitlement_access_sign_in_required", _EA, 2,
          "You are not signed in, or your sign-in has ended.",
          "Your account's strategies and actions cannot be shown or changed.", "This request, until you sign in.",
          "Sign in again, then repeat the action."),
    _gate("internal_system_service_unavailable", _IS, 3,
          "This service is not available at the moment.",
          "The action you asked for was not carried out.", "This request, while the service is unavailable.",
          "Wait a few minutes and try again."),
)

_TEMPLATES = (_TEMPLATES + _GATE_TEMPLATES + _SEND_TEMPLATES + _RECONCILIATION_TEMPLATES + _PART4_TEMPLATES
              + _BOUNDARY_TEMPLATES)


#: Read-only public view of the catalogue (for the CI scan and for callers listing templates).
#: `render()` never reads it: it works from its own snapshot taken below, so neither adding a key
#: (refused: a mappingproxy has no __setitem__) nor forcing new text into a template object (with
#: `object.__setattr__`) changes what a user is shown.
CATALOGUE: Mapping[str, MessageTemplate] = MappingProxyType({t.id: t for t in _TEMPLATES})


def _make_render(token: object) -> Callable[..., UserFacingError]:
    """Snapshot the catalogue into immutable tuples and return `render`, which holds that snapshot,
    the token and the checks in its closure (none of them is a module attribute a caller can swap)."""
    snapshot: dict[str, tuple[ErrorClass, str, tuple[str, ...], tuple[tuple[str, type[SlotType]], ...], str | None]]
    snapshot = {
        t.id: (
            t.error_class,
            t.code,
            tuple(str(getattr(t, name)) for name in _PART_NAMES),
            tuple(t.slots.items()),
            t.external_text_slot,
        )
        for t in _TEMPLATES
    }
    build = _build

    def render(template_id: str, **slots: object) -> UserFacingError:
        """The only way to build a `UserFacingError`: fill `template_id`'s typed slots.

        Fails closed on: an unknown template id; a missing or extra slot; a slot value of the wrong
        type or outside its closed set/range; and (in the builder, round 6) FINISHED text that is
        blank, duplicated, has non-Latin/confusable characters, or contains ADR-003/Q226/Q230 wording.
        """
        if template_id not in snapshot:
            raise ValueError(f"unknown template id {template_id!r}")
        error_class, code, part_texts, slot_types, external_slot = snapshot[template_id]

        expected = {name for name, _ in slot_types}
        if external_slot is not None:
            expected.add(external_slot)
        missing = expected - set(slots)
        if missing:
            raise ValueError(f"template {template_id!r} missing slot(s): {sorted(missing)}")
        extra = set(slots) - expected
        if extra:
            raise ValueError(f"template {template_id!r} got unexpected slot(s): {sorted(extra)}")

        formatted: dict[str, str] = {}
        for name, slot_type in slot_types:
            value = slots[name]
            slot_type.validate(value)
            text = slot_type.format(value)
            if type(text) is not str:
                raise TypeError(f"slot {name!r} formatter returned {type(text).__name__}, not str")
            formatted[name] = text

        parts = {name: text.format(**formatted) for name, text in zip(_PART_NAMES, part_texts)}

        # Zerodha's or the user's own words go to the builder as the ExternalText itself; the
        # builder validates it and shows it quoted with its label (Q226).
        external = None if external_slot is None else slots[external_slot]

        # The four-part, Latin-letter and ADR-003/Q226/Q230 wording checks run INSIDE the builder
        # (round 6, Q230), on the FINISHED text, so a slot value or formatter that combines with
        # fixed template text into advice wording is refused there, whatever route reached it.
        return build(token, error_class=error_class, code=code, external=external, **parts)

    return render


render = _make_render(_claim_render_token())
del _make_render


def display_text(message: UserFacingError) -> str:
    """The text a user is shown for `message`: all four REQ-065 AC-2 parts, one per line, plus Zerodha's or the
    user's own words in their labelled field when present. Built only from a `render()` result."""
    if type(message) is not UserFacingError:
        raise TypeError(f"display_text needs a UserFacingError from render(), got {type(message).__name__}")
    lines = [
        message.what_happened,
        message.impact,
        "Blocked: " + message.what_is_blocked,
        "Next step: " + message.next_action,
    ]
    if message.external_text is not None:
        lines.append(message.external_text)
    return "\n".join(lines)
