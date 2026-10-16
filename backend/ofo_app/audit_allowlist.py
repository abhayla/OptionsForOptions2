"""Per-event-type payload field ALLOWLIST for the audit store (REQ-063 AC-5).

Spec basis: REQ-063 AC-5 "Audit and other stored payloads use a per-event-type field ALLOWLIST (each event type
declares the fields it may carry; anything else is dropped before storage), never a list of forbidden key names";
W-052 (declare only the nine non-broker types; broker, order, execution, reconciliation, session and identity types
stay undeclared until W-017, which needs real Kite responses); W-017 (declares the three broker-reply types below from
the real replies of 2026-10-16, ``tests/fixtures/kite_replies/``).

Rules:
- A field not declared for its event type is DROPPED before the hash is computed, so the hash covers exactly the
  stored form. This applies at every depth: a field declared as a nested mapping keeps only its declared sub-fields.
- An event type with no entry is REFUSED (:class:`UndeclaredEventType`): fail closed, nothing is written.
- A declared scalar field holding a mapping is refused (it could smuggle undeclared keys past the filter).

Declared types and their fields (where the fields come from):

- ``entitlement_changed``: action, client_id, platform_user_id, import_id, before, after. ``before``/``after`` are
  qualifying-list snapshots (``ofo.admin.qualifying_store.QualifyingEntry.snapshot``: client_id, list_status,
  verification_status, verified_at, platform_user_id, entitlement_status, added_by, added_at), as written by
  ``ofo.admin.qualifying.QualifyingListService._audit`` for its "entitlement_status" action.
- ``direct_customer_eligibility_granted`` / ``direct_customer_eligibility_revoked``: action, client_id,
  platform_user_id, import_id, reason, before, after (the same snapshot; the qualifying list is the direct-customer
  eligibility source, REQ-020).
- ``admin_change_recorded``: action, reason, client_id, import_id, before, after (snapshot), and
  dropped_instrument_tokens, dropped_tradingsymbols (``ofo.instruments.catalogue.Catalogue.update(force=True)``).
- ``trial_started`` / ``trial_expired``: platform_user_id, starts_at, ends_at, reason (the 7-day trial from
  registration, ADR-023 Q88; ends early on a used Zerodha account, ADR-039). No trial domain code exists yet, so
  these are the minimal identity and dates.
- ``referral_reward_granted``: platform_user_id, referred_platform_user_id, reward_period, starts_at, ends_at,
  reason (REQ-021; no referral domain code exists yet).
- ``subscription_started`` / ``subscription_expired``: platform_user_id, plan, price (exact Decimal, ADR-008),
  starts_at, ends_at, reason (no payment instrument or gateway data: payments sit behind an adapter, ADR-012/ADR-029).

- ``broker_response_recorded`` (W-017): one Kite ORDER record of ``GET /orders``, flat (not the ``data`` list):
  order_id, exchange_order_id, parent_order_id, status, status_message, order_timestamp, exchange_timestamp, exchange,
  tradingsymbol, instrument_token, order_type, transaction_type, product, quantity, disclosed_quantity, price,
  trigger_price, average_price, filled_quantity, pending_quantity, cancelled_quantity, tag. Each is present in all
  three real order records and explains a decision (what was asked, what filled, why not). DROPPED on purpose:
  ``placed_by`` and ``account_id`` (the client id), ``guid``, ``meta``/``meta_raw``/``tags``/``status_message_raw``
  (free-form broker text and maps the reply does not promise to keep credential-free), and housekeeping
  (variety, validity, validity_ttl, modified, auction_number, market_protection, exchange_update_timestamp).
  ``exchange_token`` is not in the order reply (only ``instrument_token``), so it is not declared.
- ``execution_recorded`` (W-017): one Kite TRADE record of ``GET /trades``, flat: trade_id, order_id,
  exchange_order_id, instrument_token, tradingsymbol, exchange, transaction_type, product, quantity, average_price,
  order_timestamp, fill_timestamp, exchange_timestamp (all fields of the real trade record; it carries no identity).
- ``reconciliation_recorded`` (W-017): one Kite POSITION record (an element of ``data.net`` or ``data.day`` of
  ``GET /portfolio/positions``), flat, one event per position: tradingsymbol, exchange, instrument_token, product,
  quantity, average_price, last_price, close_price, pnl, m2m, unrealised, realised, buy_quantity, buy_price,
  sell_quantity, sell_price. The ``day``/``net`` lists are not declared (a list of mappings cannot pass the scalar
  filter). UNPROVEN: the domain's own reconcile-result payloads (``ofo.reconciliation.resolution`` kind /
  strategy_ids / broker_state ..., ``grouping`` groups) have no real recorded reply; their keys are not declared here,
  so a store write of them keeps nothing until a later item declares them.
- unproven for type session: no real Kite login reply recorded (GC-3 captures one). ``zerodha_session_authenticated``
  and ``zerodha_session_expired`` stay undeclared and refused.

Every other ``ofo.audit.catalogue.EventType`` member (21 of 33) is undeclared and refused.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Union

from ofo.audit.catalogue import EventType

#: A field whose value is a scalar (str, int, bool, None, Decimal, aware datetime) or a list of scalars.
SCALAR = "scalar"

FieldSpec = Union[str, Mapping[str, Any]]

#: ``QualifyingEntry.snapshot()`` keys (ofo/admin/qualifying_store.py).
QUALIFYING_SNAPSHOT: Mapping[str, FieldSpec] = MappingProxyType(
    {
        "client_id": SCALAR,
        "list_status": SCALAR,
        "verification_status": SCALAR,
        "verified_at": SCALAR,
        "platform_user_id": SCALAR,
        "entitlement_status": SCALAR,
        "added_by": SCALAR,
        "added_at": SCALAR,
    }
)


def _fields(*scalars: str, **nested: Mapping[str, FieldSpec]) -> Mapping[str, FieldSpec]:
    spec: dict[str, FieldSpec] = {name: SCALAR for name in scalars}
    spec.update(nested)
    return MappingProxyType(spec)


_ELIGIBILITY = _fields(
    "action", "client_id", "platform_user_id", "import_id", "reason",
    before=QUALIFYING_SNAPSHOT, after=QUALIFYING_SNAPSHOT,
)
_TRIAL = _fields("platform_user_id", "starts_at", "ends_at", "reason")
_SUBSCRIPTION = _fields("platform_user_id", "plan", "price", "starts_at", "ends_at", "reason")

_BROKER_ORDER = _fields(
    "order_id", "exchange_order_id", "parent_order_id", "status", "status_message", "order_timestamp",
    "exchange_timestamp", "exchange", "tradingsymbol", "instrument_token", "order_type", "transaction_type",
    "product", "quantity", "disclosed_quantity", "price", "trigger_price", "average_price", "filled_quantity",
    "pending_quantity", "cancelled_quantity", "tag",
)
_BROKER_TRADE = _fields(
    "trade_id", "order_id", "exchange_order_id", "instrument_token", "tradingsymbol", "exchange",
    "transaction_type", "product", "quantity", "average_price", "order_timestamp", "fill_timestamp",
    "exchange_timestamp",
)
_BROKER_POSITION = _fields(
    "tradingsymbol", "exchange", "instrument_token", "product", "quantity", "average_price", "last_price",
    "close_price", "pnl", "m2m", "unrealised", "realised", "buy_quantity", "buy_price", "sell_quantity",
    "sell_price",
)

ALLOWLIST: Mapping[EventType, Mapping[str, FieldSpec]] = MappingProxyType(
    {
        EventType.ENTITLEMENT_CHANGED: _fields(
            "action", "client_id", "platform_user_id", "import_id",
            before=QUALIFYING_SNAPSHOT, after=QUALIFYING_SNAPSHOT,
        ),
        EventType.TRIAL_STARTED: _TRIAL,
        EventType.TRIAL_EXPIRED: _TRIAL,
        EventType.DIRECT_CUSTOMER_ELIGIBILITY_GRANTED: _ELIGIBILITY,
        EventType.DIRECT_CUSTOMER_ELIGIBILITY_REVOKED: _ELIGIBILITY,
        EventType.REFERRAL_REWARD_GRANTED: _fields(
            "platform_user_id", "referred_platform_user_id", "reward_period", "starts_at", "ends_at", "reason"
        ),
        EventType.SUBSCRIPTION_STARTED: _SUBSCRIPTION,
        EventType.SUBSCRIPTION_EXPIRED: _SUBSCRIPTION,
        EventType.BROKER_RESPONSE_RECORDED: _BROKER_ORDER,
        EventType.EXECUTION_RECORDED: _BROKER_TRADE,
        EventType.RECONCILIATION_RECORDED: _BROKER_POSITION,
        EventType.ADMIN_CHANGE_RECORDED: _fields(
            "action", "reason", "client_id", "import_id", "dropped_instrument_tokens", "dropped_tradingsymbols",
            before=QUALIFYING_SNAPSHOT, after=QUALIFYING_SNAPSHOT,
        ),
    }
)


class UndeclaredEventType(ValueError):
    """The event type has no payload field allowlist, so it is refused (fail closed)."""


class PayloadShapeError(ValueError):
    """A payload value has a shape the allowlist cannot filter (e.g. a mapping in a scalar field)."""


def is_declared(event_type: EventType) -> bool:
    return event_type in ALLOWLIST


def _filter(value: Mapping[str, Any], spec: Mapping[str, FieldSpec], path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PayloadShapeError(f"{path} must be a mapping, got {type(value).__name__}")
    kept: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or key not in spec:
            continue  # undeclared: dropped before storage (REQ-063 AC-5)
        field_spec = spec[key]
        if field_spec == SCALAR:
            _require_no_mapping(item, f"{path}.{key}")
            kept[key] = list(item) if isinstance(item, tuple) else item
        elif item is None:
            kept[key] = None
        else:
            kept[key] = _filter(item, field_spec, f"{path}.{key}")  # type: ignore[arg-type]
    return kept


def _require_no_mapping(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        raise PayloadShapeError(f"{path} is declared as a scalar field but holds a mapping")
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _require_no_mapping(item, f"{path}[{index}]")


def _spec_json(spec: Mapping[str, FieldSpec]) -> dict[str, Any]:
    return {name: (SCALAR if field == SCALAR else _spec_json(field)) for name, field in spec.items()}  # type: ignore[arg-type]


def allowlist_spec() -> dict[str, Any]:
    """The allowlist as plain JSON: ``{event_type: {field: "scalar" | {sub_field: "scalar"}}}``.

    The single source the database copy is generated from (migration 0002 embeds it in
    ``public.ofo_audit_payload_allowlist()``; a head test asserts the two are equal).
    """
    return {event_type.value: _spec_json(spec) for event_type, spec in ALLOWLIST.items()}


def filter_payload(event_type: EventType, payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a new payload holding only the fields declared for ``event_type``.

    Raises :class:`UndeclaredEventType` for a type with no entry and :class:`PayloadShapeError` for a shape the
    filter cannot vouch for.
    """
    if not isinstance(event_type, EventType):
        raise UndeclaredEventType(f"not an audit event type: {event_type!r}")
    spec = ALLOWLIST.get(event_type)
    if spec is None:
        raise UndeclaredEventType(
            f"{event_type.value}: no payload field allowlist is declared, so it cannot be stored (REQ-063 AC-5; "
            "session and identity events wait for a real recorded reply, W-017 declared only the broker-reply types)"
        )
    return _filter(payload if payload is not None else {}, spec, "payload")
