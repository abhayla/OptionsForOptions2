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

from dataclasses import dataclass, field

from .classes import ErrorClass
from .model import UserFacingError
from .slots import Code, ExternalText, Instrument, Int, Money, SlotType, Time

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
    slots: dict[str, type[SlotType]] = field(default_factory=dict)
    external_text_slot: str | None = None


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
        slots={"symbol": Code, "minutes": Int},
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
        slots={"filled": Int, "total": Int},
    ),
    MessageTemplate(
        id="reconciliation_mismatch_lots",
        error_class=ErrorClass.RECONCILIATION_MISMATCH,
        code="RECONCILIATION_MISMATCH_001",
        what_happened="Zerodha shows {broker_lots} lots on this leg; this platform's record shows {platform_lots} lots.",
        impact="P&L, Greeks and rule checks for this strategy cannot be trusted until this is resolved.",
        what_is_blocked="New orders and automatic rule triggers for this strategy.",
        next_action="Review the mismatch on the reconciliation screen and confirm which figure is correct.",
        slots={"broker_lots": Int, "platform_lots": Int},
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

CATALOGUE: dict[str, MessageTemplate] = {t.id: t for t in _TEMPLATES}


def render(template_id: str, **slots: object) -> UserFacingError:
    """The only public way to build a `UserFacingError`: fill `template_id`'s typed slots.

    Fails closed: unknown `template_id`; a missing or extra slot name; a slot value of the wrong
    type (a `str` where `Money` is expected, a `float` anywhere, an untyped/naive value, ...).
    """
    template = CATALOGUE.get(template_id)
    if template is None:
        raise ValueError(f"unknown template id {template_id!r}")

    expected_names = set(template.slots)
    if template.external_text_slot is not None:
        expected_names.add(template.external_text_slot)
    provided_names = set(slots)

    missing = expected_names - provided_names
    if missing:
        raise ValueError(f"template {template_id!r} missing slot(s): {sorted(missing)}")
    extra = provided_names - expected_names
    if extra:
        raise ValueError(f"template {template_id!r} got unexpected slot(s): {sorted(extra)}")

    formatted: dict[str, str] = {}
    for name, slot_type in template.slots.items():
        value = slots[name]
        slot_type.validate(value)
        formatted[name] = slot_type.format(value)

    parts = {part_name: getattr(template, part_name).format(**formatted) for part_name in _PART_NAMES}

    external_text: str | None = None
    if template.external_text_slot is not None:
        value = slots[template.external_text_slot]
        ExternalText.validate(value)
        external_text = ExternalText.format(value)

    return UserFacingError._build(
        error_class=template.error_class,
        code=template.code,
        external_text=external_text,
        **parts,
    )
