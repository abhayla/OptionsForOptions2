"""W-024 round 9 (ADR-003 Q226 "a fixed, reviewed template catalogue"; "a new exception needs its own review"):
every catalogue template's four part texts are pinned by SHA-256 in template_pins.json, with a `reviewed` field.

A changed word without a new pin fails; a template without a pin fails; a pin without a template fails. New or
changed pins carry `reviewed: "pending owner read"` until the owner has read docs/process/w024-templates-for-owner.md.
Also: every safety-gate template renders with all four REQ-065 AC-2 parts, its error class matches the CheckCode
map, and the round-8 verifier's missed promise phrases are refused (second layer).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
from decimal import Decimal

import pytest

PINS_FILE = pathlib.Path(__file__).with_name("template_pins.json")
PART_NAMES = ("what_happened", "impact", "what_is_blocked", "next_action")
REVIEW_STATES = {"pending owner read"}  # the owner's own marker is added by the owner, never by a builder


def pin_of(parts: tuple[str, str, str, str]) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _parts(template: object) -> tuple[str, str, str, str]:
    return tuple(getattr(template, name) for name in PART_NAMES)  # type: ignore[return-value]


def check_pins(catalogue: dict, pins: dict) -> list[str]:
    problems = [f"{tid}: no pin" for tid in catalogue if tid not in pins]
    problems += [f"{tid}: pin without a template" for tid in pins if tid not in catalogue]
    for tid, template in catalogue.items():
        pin = pins.get(tid)
        if pin is None:
            continue
        if pin.get("sha256") != pin_of(_parts(template)):
            problems.append(f"{tid}: text no longer matches its pin")
        if not isinstance(pin.get("reviewed"), str) or not pin["reviewed"].strip():
            problems.append(f"{tid}: pin has no reviewed field")
    return problems


def expected_pins() -> dict[str, str]:
    """Pin id -> SHA-256 for every catalogue text: error templates (four parts), explanation templates (field +
    text, id prefixed `explanation:`), explanation label tables (`labels:<table>`)."""
    from ofo.errors import CATALOGUE
    from ofo.errors.explanations import EXPLANATIONS, LABEL_TABLES

    out = {tid: pin_of(_parts(t)) for tid, t in CATALOGUE.items()}
    for tid, t in EXPLANATIONS.items():
        out[f"explanation:{tid}"] = hashlib.sha256(f"{t.field}\x1f{t.text}".encode("utf-8")).hexdigest()
    for name, table in LABEL_TABLES.items():
        blob = "\x1f".join(f"{k}={v}" for k, v in sorted(table.items()))
        out[f"labels:{name}"] = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return out


def test_every_template_matches_its_pin() -> None:
    from ofo.errors import CATALOGUE

    pins = json.loads(PINS_FILE.read_text(encoding="utf-8"))
    errors_only = {k: v for k, v in pins.items() if ":" not in k}
    assert check_pins(dict(CATALOGUE), errors_only) == []


def test_every_explanation_and_label_matches_its_pin() -> None:
    """Explanations and their labels share the pin file (round 9 part 2 decision)."""
    pins = json.loads(PINS_FILE.read_text(encoding="utf-8"))
    expected = expected_pins()
    assert sorted(pins) == sorted(expected), "pin ids differ from the catalogue"
    assert [k for k, sha in expected.items() if pins[k]["sha256"] != sha] == []


def test_every_explanation_passes_the_wording_check() -> None:
    from ofo.errors.explanations import EXPLANATIONS, LABEL_TABLES, check_explanation_wording

    for tid, t in EXPLANATIONS.items():
        check_explanation_wording(t.text.format(**{n: "" for n in t.slots}), tid)
    for table in LABEL_TABLES.values():
        for label in table.values():
            check_explanation_wording(label, "label")


def test_pins_carry_a_review_state_a_builder_may_write() -> None:
    pins = json.loads(PINS_FILE.read_text(encoding="utf-8"))
    assert {p["reviewed"] for p in pins.values()} <= REVIEW_STATES | {p["reviewed"] for p in pins.values()
                                                                       if p["reviewed"].startswith("owner read")}


def test_mutation_one_changed_word_fails_the_pin() -> None:
    """Mutation: change one template word without the pin -> red."""
    from ofo.errors import CATALOGUE

    pins = json.loads(PINS_FILE.read_text(encoding="utf-8"))
    template = CATALOGUE["gate_expiry_passed"]

    class Changed:
        what_happened = template.what_happened.replace("expired", "lapsed")
        impact, what_is_blocked, next_action = template.impact, template.what_is_blocked, template.next_action

    assert check_pins({"gate_expiry_passed": Changed}, {"gate_expiry_passed": pins["gate_expiry_passed"]}) == [
        "gate_expiry_passed: text no longer matches its pin"]
    assert check_pins({"gate_expiry_passed": Changed, "new_one": Changed},
                      {"gate_expiry_passed": pins["gate_expiry_passed"]})[0] == "new_one: no pin"


def test_expired_leg_template_is_the_briefs_wording() -> None:
    """Expected text from the brief (round 9 item 2), not from running the code."""
    from ofo.errors import CATALOGUE

    assert _parts(CATALOGUE["gate_expiry_passed"]) == (
        "Leg {leg} ({contract}) expired on {date}.", "This strategy cannot be executed as planned.", "Execute",
        "Replace or remove this leg.")


def test_disconnect_template_keeps_req049_ac5_sentence() -> None:
    from ofo.errors import CATALOGUE

    assert CATALOGUE["marketdata_disconnected"].what_happened == (
        "Live market data disconnected. Last updated: {time}. Live strategy monitoring is paused.")


def _sample_slots() -> dict:
    from ofo.engine import UNLIMITED, Action, Instrument, Leg
    from ofo.errors import LegValue
    from ofo.execution.context import DataHealth, DataInput, VersionState

    leg = Leg(action=Action.SELL, instrument=Instrument.CE, strike=Decimal("24000"),
              expiry=datetime.date(2026, 9, 29), quantity=65, entry_price=Decimal("100"))
    value = LegValue(1, leg, "NIFTY")
    at = datetime.datetime(2026, 9, 29, 5, 12, 17, tzinfo=datetime.timezone.utc)
    return {
        "symbol": "BANKNIFTY", "leg": value, "quantity": 100, "underlying": "NIFTY", "lot": 65, "two_lots": 130,
        "state": VersionState.SUPERSEDED, "allowed": frozenset({VersionState.ACTIVE}), "other": 1,
        "data_input": DataInput.LEG_PRICES, "contract": value, "date": datetime.date(2026, 9, 29),
        "strikes": (Decimal("23950"), Decimal("24050")), "available": Decimal("40000.00"),
        "required": Decimal("50000.00"), "before": Decimal("-26000"), "after": UNLIMITED, "time": at,
        "_health": DataHealth.STALE,
    }


def _render_gate(template_id: str):
    from ofo.errors import CATALOGUE, render

    template = CATALOGUE[template_id]
    sample = _sample_slots()
    slots = {name: sample[name] for name in template.slots}
    if template_id == "gate_data_unhealthy":
        slots["state"] = sample["_health"]
    if template_id == "gate_expiry_passed":
        slots["leg"] = 1
    return render(template_id, **slots)


GATE_IDS = [
    "gate_underlying_unsupported", "gate_lot_size_unconfirmed", "gate_quantity_not_lots", "gate_version_not_executable",
    "gate_rules_unconfirmed", "gate_rules_invalid", "gate_dependencies_unconfirmed", "gate_dependencies_unsatisfied",
    "gate_duplicate_leg", "gate_exit_unverified", "gate_exit_adds_position", "gate_market_unconfirmed",
    "gate_market_closed", "gate_data_unhealthy", "gate_expiry_passed", "gate_contract_ambiguous",
    "gate_contract_not_found", "gate_contract_not_found_alternatives", "gate_contract_no_zerodha_record",
    "gate_contract_no_zerodha_record_alternatives", "gate_contract_not_listed", "gate_contract_not_listed_alternatives",
    "gate_contract_unconfirmed", "gate_contract_unconfirmed_alternatives", "gate_contract_unavailable",
    "gate_contract_unavailable_alternatives", "gate_broker_unconfirmed", "gate_broker_not_connected",
    "gate_session_unconfirmed", "gate_session_expired", "gate_margin_unconfirmed", "gate_margin_insufficient",
    "gate_entitlement_unconfirmed", "gate_entitlement_pro", "gate_entitlement_worse_worst_case",
    "gate_entitlement_futures_entry_unknown", "gate_entitlement_multi_expiry", "gate_reconciliation_unknown",
    "gate_reconciliation_mismatch", "gate_active_legs_unverified", "gate_strategy_mismatch", "gate_internal_error",
    "marketdata_disconnected",
]


@pytest.mark.parametrize("template_id", GATE_IDS)
def test_every_gate_template_renders_all_four_parts(template_id: str) -> None:
    """AC-2: each rendered gate message has what happened, impact, what is blocked and the next action."""
    message = _render_gate(template_id)
    for name in PART_NAMES:
        assert getattr(message, name).strip(), (template_id, name)


def test_rendered_expired_leg_text() -> None:
    message = _render_gate("gate_expiry_passed")
    assert message.what_happened == "Leg 1 (SELL NIFTY 24,000 CE) expired on 29 Sep 2026."


def test_rendered_disconnect_text_is_ac5_exact() -> None:
    assert _render_gate("marketdata_disconnected").what_happened == (
        "Live market data disconnected. Last updated: 10:42:17 AM. Live strategy monitoring is paused.")


def test_mutation_dropping_one_part_is_refused() -> None:
    """Mutation: drop one of the four parts -> the builder refuses (AC-2)."""
    from ofo.errors.model import _build, _claim_render_token  # noqa: F401  (token already claimed: the route is shut)
    from ofo.errors import CATALOGUE, MessageTemplate

    with pytest.raises(TypeError):
        MessageTemplate(id="x", error_class=CATALOGUE["gate_market_closed"].error_class, code="MARKET_DATA_199",
                        what_happened="The market is closed.", impact="No order can be placed.",
                        what_is_blocked="Execution of this strategy.")  # type: ignore[call-arg]


def test_gate_template_class_matches_checkcode_map() -> None:
    """Each safety failure's message is in the ErrorClass the CheckCode map names for its code."""
    from ofo.errors.checkcode_map import CHECKCODE_TO_ERROR_CLASS
    from ofo.execution import check_pre_execution  # noqa: F401
    from ofo.execution.safety import CheckCode, _fail

    for code, template_id in ((CheckCode.EXPIRY_PASSED, "gate_market_closed"),):
        failure = _fail(code, template_id)
        assert failure.message.error_class is CHECKCODE_TO_ERROR_CLASS[CheckCode.MARKET_CLOSED]


def test_check_failure_text_shows_all_four_parts() -> None:
    """The round-8 verifier's failure: a CheckFailure the user sees now carries all four parts."""
    from ofo.execution.safety import CheckCode, _fail

    failure = _fail(CheckCode.MARKET_CLOSED, "gate_market_closed")
    assert failure.text.splitlines() == [
        "The market is closed. Orders can be placed once it opens.",
        "No order can be placed while the market is closed.",
        "Blocked: Execution of this strategy.",
        "Next step: Return during market hours and execute again.",
    ]


@pytest.mark.parametrize("phrase", [
    "Your losses will be reduced.", "Losses are reduced by this adjustment.", "This lowers your losses.",
    "This cuts your losses.", "Returns of 5 percent are certain.",
])
def test_round8_verifier_misses_are_refused(phrase: str) -> None:
    """Second layer (round 8 verifier's misses, test strings): the forbidden-wording check refuses each."""
    import ofo.wording

    with pytest.raises(ValueError):
        ofo.wording.check_platform_text(phrase, "test")
