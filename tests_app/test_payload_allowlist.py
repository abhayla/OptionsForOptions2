"""W-017 (REQ-063 AC-5): the audit payload allowlist for the broker-reply event types, on the REAL Kite replies.

Lives in tests_app/ because tests/ may not import ofo_app (tests/test_no_app_imports.py).

Core: the redacted replies of 2026-10-16 (``tests/fixtures/kite_replies/``, two samples each: 122104 and 151006),
wrapped as the payload of their event type and passed through ``ofo_app.audit_allowlist.filter_payload``, keep exactly
the declared field set, and a planted credential / identity field is dropped.

The expected sets below are typed by hand from the fixtures (not computed from the module), so a field added to or
removed from the module changes a set and fails here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ofo.audit.catalogue import EventType
from ofo_app import audit_allowlist
from ofo_app.audit_allowlist import PayloadShapeError, UndeclaredEventType, filter_payload

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "kite_replies"
SAMPLES = ("122104", "151006")

ORDER_FIELDS = {
    "order_id", "exchange_order_id", "parent_order_id", "status", "order_timestamp",
    "exchange_timestamp", "exchange", "tradingsymbol", "instrument_token", "order_type", "transaction_type",
    "product", "quantity", "disclosed_quantity", "price", "trigger_price", "average_price", "filled_quantity",
    "pending_quantity", "cancelled_quantity", "tag",
}
TRADE_FIELDS = {
    "trade_id", "order_id", "exchange_order_id", "instrument_token", "tradingsymbol", "exchange",
    "transaction_type", "product", "quantity", "average_price", "order_timestamp", "fill_timestamp",
    "exchange_timestamp",
}
#: What the real order reply carries and the allowlist must NOT keep.
ORDER_DROPPED = {
    "placed_by", "account_id", "guid", "meta", "meta_raw", "tags", "status_message", "status_message_raw", "variety",
    "validity", "validity_ttl", "modified", "auction_number", "market_protection", "exchange_update_timestamp",
}
PLANTED = {
    "access_token": "SECRET-VALUE-1", "api_key": "key", "enctoken": "enc", "placed_by": "AB1234",
    "account_id": "AB1234",
    "user_name": "A Trader", "user_id": "AB1234", "email": "a@b.example", "public_token": "pt",
}

TYPES = (
    (EventType.BROKER_RESPONSE_RECORDED, "orders", ORDER_FIELDS),
    (EventType.EXECUTION_RECORDED, "trades", TRADE_FIELDS),
)


def _records(kind: str, sample: str) -> list[dict]:
    data = json.loads((FIXTURES / f"{kind}-{sample}.json").read_text(encoding="utf-8"))["data"]
    return list(data)


def _all(kind: str) -> list[tuple[str, dict]]:
    return [(sample, record) for sample in SAMPLES for record in _records(kind, sample)]


@pytest.mark.parametrize("event_type, kind, expected", TYPES, ids=[t[1] for t in TYPES])
def test_each_real_reply_keeps_exactly_the_declared_fields(event_type: EventType, kind: str, expected: set) -> None:
    records = _all(kind)
    assert len(records) >= 2  # both samples contribute
    for sample, record in records:
        kept = filter_payload(event_type, record)
        assert set(kept) == expected, (sample, set(kept) ^ expected)
        for name in expected:  # values are carried unchanged
            assert kept[name] == record[name]


def test_real_order_fields_that_identify_the_client_are_dropped() -> None:
    for _, record in _all("orders"):
        assert set(record) >= {"placed_by", "account_id"}  # the fixtures do carry them (redacted to XX0000)
        kept = filter_payload(EventType.BROKER_RESPONSE_RECORDED, record)
        assert not (ORDER_DROPPED & set(kept))
    assert {k for _, r in _all("orders") for k in r} >= ORDER_DROPPED


@pytest.mark.parametrize("event_type, kind, expected", TYPES, ids=[t[1] for t in TYPES])
def test_a_planted_credential_or_identity_field_is_dropped_at_top_level(event_type, kind, expected) -> None:
    record = {**_records(kind, "122104")[0], **PLANTED}
    kept = filter_payload(event_type, record)
    assert set(kept) == expected
    assert not (set(PLANTED) & set(kept))


@pytest.mark.parametrize("event_type, kind, expected", TYPES, ids=[t[1] for t in TYPES])
def test_a_planted_field_nested_in_an_undeclared_key_is_dropped(event_type, kind, expected) -> None:
    record = {**_records(kind, "151006")[0], "meta": {"access_token": "SECRET-VALUE-1", **PLANTED}, "tags": [PLANTED]}
    kept = filter_payload(event_type, record)
    assert set(kept) == expected
    assert "SECRET-VALUE-1" not in json.dumps(kept, default=str)


@pytest.mark.parametrize("event_type, kind, expected", TYPES, ids=[t[1] for t in TYPES])
def test_a_mapping_in_a_declared_scalar_field_is_refused(event_type, kind, expected) -> None:
    record = _records(kind, "122104")[0]
    for field in sorted(expected):
        with pytest.raises(PayloadShapeError):
            filter_payload(event_type, {**record, field: {"access_token": "SECRET-VALUE-1"}})
    with pytest.raises(PayloadShapeError):
        filter_payload(event_type, {**record, "tradingsymbol": [{"access_token": "SECRET-VALUE-1"}]})


@pytest.mark.parametrize("event_type", [EventType.ZERODHA_SESSION_AUTHENTICATED, EventType.ZERODHA_SESSION_EXPIRED])
def test_session_types_stay_undeclared_and_refused(event_type: EventType) -> None:
    assert not audit_allowlist.is_declared(event_type)
    with pytest.raises(UndeclaredEventType):
        filter_payload(event_type, {"user_id": "AB1234"})
    assert "unproven for type session: no real Kite login reply recorded (GC-3 captures one)" in (
        audit_allowlist.__doc__ or ""
    )


def test_exactly_eleven_types_are_declared_and_the_others_still_refuse() -> None:
    declared = {e for e in EventType if audit_allowlist.is_declared(e)}
    assert {e.value for e in declared} >= {t[0].value for t in TYPES}
    assert len(declared) == 11
    assert EventType.RECONCILIATION_RECORDED not in declared
    for event_type in set(EventType) - declared:
        with pytest.raises(UndeclaredEventType):
            filter_payload(event_type, {})


def test_no_declared_field_name_is_a_credential_or_identity_name() -> None:
    """A tripwire on the declarations themselves (the allowlist, not this list, is the guard): none of the three
    broker-reply types may ever declare a name of the credential / identity kind."""
    forbidden_words = ("token_secret", "access_token", "api_key", "enctoken", "placed_by", "account_id", "user_name",
                       "email", "password", "secret", "public_token", "refresh_token", "user_id")
    for event_type, _, _ in TYPES:
        for name in audit_allowlist.ALLOWLIST[event_type]:
            assert name not in forbidden_words, (event_type, name)


def test_the_database_text_follows_the_python_allowlist() -> None:
    """allowlist_spec() (the source the migrations embed) lists the two types with the same field sets."""
    spec = audit_allowlist.allowlist_spec()
    for event_type, _, expected in TYPES:
        assert set(spec[event_type.value]) == expected
        assert set(spec[event_type.value].values()) == {"scalar"}


# The domain's real reconcile payload shapes (backend/ofo/reconciliation/resolution.py _resolve and the mismatch loop,
# grouping.py GroupingSession.start), typed by hand from those lines.
DOMAIN_RECONCILE_PAYLOADS = (
    {  # resolution.py: manual resolution
        "strategy_id": "S-1", "resolution": "accept_broker", "reason": "checked", "before_broker": [["NIFTY", 1]],
        "before_platform": [["NIFTY", 2]], "after_platform": [["NIFTY", 1]], "still_blocked": False, "exited": False,
    },
    {  # resolution.py: mismatch
        "kind": "quantity", "strategy_ids": ["S-1"], "broker_state": [["NIFTY", 1]], "platform_state": [["NIFTY", 2]],
        "difference": [["NIFTY", -1]], "next_action": "resolve",
    },
    {  # grouping.py: suggest
        "action": "suggest", "groups": [{"id": "g1", "legs": ["NIFTY:NRML"], "resembles": "none"}],
        "unresolved": [], "hidden": [],
    },
)


@pytest.mark.parametrize("payload", DOMAIN_RECONCILE_PAYLOADS, ids=["resolution", "mismatch", "grouping"])
def test_reconciliation_recorded_stays_undeclared_and_refuses_the_domain_payloads(payload) -> None:
    assert not audit_allowlist.is_declared(EventType.RECONCILIATION_RECORDED)
    with pytest.raises(UndeclaredEventType):
        filter_payload(EventType.RECONCILIATION_RECORDED, payload)


@pytest.mark.parametrize("event_type", sorted(audit_allowlist.ALLOWLIST, key=lambda e: e.value), ids=lambda e: e.value)
def test_a_payload_keeping_no_declared_field_is_refused_never_stored_empty(event_type: EventType) -> None:
    with pytest.raises(PayloadShapeError):
        filter_payload(event_type, {"not_a_declared_field": 1, "another": "x"})
    assert filter_payload(event_type, {}) == {}  # an empty payload was and stays allowed
    assert filter_payload(event_type, None) == {}


def test_free_text_status_message_is_not_kept_on_a_real_order() -> None:
    for _, record in _all("orders"):
        assert "status_message" in record
        assert "status_message" not in filter_payload(EventType.BROKER_RESPONSE_RECORDED, record)
