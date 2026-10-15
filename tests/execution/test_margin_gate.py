"""W-081 (REQ-055 AC-1/3/4): the margin gate before the Kite basket is built.

Core: against the real 2026-10-15 basket-margin reply for the 4-leg NIFTY iron condor (final.total 68498.85,
initial.total 296332.8), available Rs 68,498.85 builds the basket and Rs 68,498.84 blocks it, the message showing
available vs required. Expected figures come from that recorded Zerodha reply, never from running the gate.
"""
from __future__ import annotations

import dataclasses
import inspect
import json
import pathlib
from decimal import Decimal

import pytest

from ofo.execution import margin_gate
from ofo.execution.margin_gate import MarginReplyError, MarginVerdict, check_margin, required_from_basket_reply

REPLY_FILE = (pathlib.Path(__file__).resolve().parents[2]
              / "docs/research/kite-proof-2026-10-07/rest-2026-10-15/margins_basket.json")


@pytest.fixture(scope="module")
def reply_data() -> dict:
    with REPLY_FILE.open(encoding="utf-8") as handle:
        recorded = json.load(handle, parse_float=Decimal)
    assert recorded["reply"]["status"] == "success"
    return recorded["reply"]["data"]


def test_fixture_is_the_real_condor_reply(reply_data: dict) -> None:
    """The recorded figures the core test rests on (read from the file, written down here from the file)."""
    assert reply_data["final"]["total"] == Decimal("68498.85")
    assert reply_data["initial"]["total"] == Decimal("296332.8")


def test_ac1_available_equal_to_final_total_builds_the_basket(reply_data: dict) -> None:
    """AC-1 (core): available Rs 68,498.85 equals the required final.total, so the basket is built."""
    required = required_from_basket_reply(reply_data)
    assert required == Decimal("68498.85")
    verdict = check_margin(Decimal("68498.85"), required)
    assert verdict.allowed is True
    assert verdict.message is None
    assert (verdict.available, verdict.required) == (Decimal("68498.85"), Decimal("68498.85"))


def test_ac4_one_paisa_short_blocks_with_both_amounts(reply_data: dict) -> None:
    """AC-4 (core): available Rs 68,498.84 is one paisa short, so no basket; the message shows both amounts."""
    verdict = check_margin(Decimal("68498.84"), required_from_basket_reply(reply_data))
    assert verdict.allowed is False
    assert verdict.message is not None
    assert verdict.message.what_happened == (
        "Zerodha says this strategy needs ₹68,498.85 of margin; ₹68,498.84 is available in your account.")
    assert verdict.message.what_is_blocked == "Building the Zerodha basket for this strategy."
    assert verdict.message.code == "MARGIN_201"


def test_ac4_the_message_offers_quantity_review_and_add_funds(reply_data: dict) -> None:
    """AC-4: the next step offers a quantity change, a review, or adding funds."""
    verdict = check_margin(Decimal("1000"), required_from_basket_reply(reply_data))
    assert verdict.message is not None
    assert verdict.message.next_action == (
        "Reduce the quantity, review the strategy, or add funds in Zerodha, then check again.")


def test_ac4_indian_grouping_for_large_amounts(reply_data: dict) -> None:
    """AC-4: the amounts use the engine's rupee formatter (lakh grouping): initial.total is Rs 2,96,332.80."""
    verdict = check_margin(Decimal("1"), reply_data["initial"]["total"])
    assert verdict.message is not None
    assert "₹2,96,332.80" in verdict.message.what_happened
    assert "₹1.00" in verdict.message.what_happened


def test_ac1_final_total_is_required_not_initial_total(reply_data: dict) -> None:
    """AC-1 (decision by role): the hedged basket needs final.total (68498.85), not initial.total (296332.8)."""
    assert required_from_basket_reply(reply_data) != Decimal("296332.8")
    assert check_margin(Decimal("68498.85"), required_from_basket_reply(reply_data)).allowed is True


def test_ac1_sub_paisa_amounts_never_round_in_the_users_favour() -> None:
    """AC-1: required 100.001 with available 100.00 is blocked and the message does not show two equal amounts."""
    verdict = check_margin(Decimal("100.00"), Decimal("100.001"))
    assert verdict.allowed is False
    assert verdict.message is not None
    assert "needs ₹100.01 of margin; ₹100.00 is available" in verdict.message.what_happened
    short = check_margin(Decimal("100.009"), Decimal("100.01"))
    assert short.allowed is False and short.message is not None
    assert "needs ₹100.01 of margin; ₹100.00 is available" in short.message.what_happened


@pytest.mark.parametrize("bad", [68498.85, "68498.85", 68498, True, Decimal("NaN"), Decimal("Infinity")])
def test_ac1_money_must_be_exact_finite_decimal(bad: object) -> None:
    """AC-1: a float, string, int, bool, NaN or infinity amount raises; it never compares."""
    with pytest.raises((TypeError, ValueError)):
        check_margin(bad, Decimal("1"))  # type: ignore[arg-type]
    with pytest.raises((TypeError, ValueError)):
        check_margin(Decimal("1"), bad)  # type: ignore[arg-type]


def test_ac1_required_margin_cannot_be_negative() -> None:
    """AC-1: a negative required margin raises (Zerodha never needs less than nothing)."""
    with pytest.raises(ValueError):
        check_margin(Decimal("1"), Decimal("-1"))


def test_ac4_a_negative_balance_always_blocks_and_shows_its_sign() -> None:
    """AC-4 (round 2 item 3): Zerodha's own signed equity.net is compared and shown, never clamped to zero; even
    a required margin of 0 is not met by a negative balance."""
    verdict = check_margin(Decimal("-120.5"), Decimal("68498.85"))
    assert verdict.allowed is False and verdict.available == Decimal("-120.5")
    assert verdict.message is not None
    assert verdict.message.what_happened == (
        "Zerodha says this strategy needs ₹68,498.85 of margin; -₹120.50 is available in your account.")
    assert check_margin(Decimal("-0.01"), Decimal("0")).allowed is False
    assert check_margin(Decimal("0"), Decimal("0")).allowed is True


@pytest.mark.parametrize("available,required", [(None, Decimal("1")), (Decimal("1"), None), (None, None)])
def test_ac1_an_unknown_amount_blocks_the_basket(available: Decimal | None, required: Decimal | None) -> None:
    """AC-1: funds or required margin not confirmed with Zerodha -> no basket (fail closed)."""
    verdict = check_margin(available, required)
    assert verdict.allowed is False
    assert verdict.message is not None
    assert verdict.message.what_happened == (
        "We could not confirm your available margin with Zerodha. Execution is paused.")


def test_ac1_a_caller_cannot_forge_an_allowed_verdict() -> None:
    """AC-1: MarginVerdict cannot be built outside check_margin (caller-supplied-verdict-trusted)."""
    with pytest.raises(TypeError):
        MarginVerdict(Decimal("1"), Decimal("9"))  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        MarginVerdict(Decimal("1"), Decimal("9"), _mint=object())  # type: ignore[arg-type]
    with pytest.raises(TypeError):  # `allowed` and `message` are not inputs
        MarginVerdict(Decimal("1"), Decimal("9"), allowed=True, message=None)  # type: ignore[call-arg]
    with pytest.raises(TypeError):  # even a holder of the mint cannot pass them
        MarginVerdict(Decimal("1"), Decimal("9"), margin_gate._MINT, True)  # type: ignore[call-arg]


def test_ac1_replace_cannot_forge_an_allowed_verdict() -> None:
    """AC-1 (round 2 item 1): dataclasses.replace cannot set `allowed` or drop the message; copying with other
    amounts re-derives both from available >= required."""
    blocked = check_margin(Decimal("68498.84"), Decimal("68498.85"))
    with pytest.raises(TypeError):
        dataclasses.replace(blocked, allowed=True, message=None)
    with pytest.raises(TypeError):
        dataclasses.replace(blocked, message=None)
    with pytest.raises(TypeError):
        dataclasses.replace(blocked, allowed=True)
    still_blocked = dataclasses.replace(blocked, available=Decimal("1"))
    assert still_blocked.allowed is False and still_blocked.message is not None
    now_allowed = dataclasses.replace(blocked, available=Decimal("68498.85"))
    assert now_allowed.allowed is True and now_allowed.message is None  # derived from the amounts, not asserted
    with pytest.raises(dataclasses.FrozenInstanceError):
        blocked.allowed = True  # type: ignore[misc]


def test_ac3_zerodhas_figure_alone_decides(reply_data: dict) -> None:
    """AC-3: the gate takes only Zerodha's two figures (no platform estimate parameter) and says Zerodha's figure."""
    assert list(inspect.signature(check_margin).parameters) == ["available", "required"]
    verdict = check_margin(Decimal("10"), required_from_basket_reply(reply_data))
    assert verdict.message is not None and verdict.message.what_happened.startswith("Zerodha says")


@pytest.mark.parametrize("data", [
    {}, {"final": {}}, {"final": None}, {"final": {"total": None}}, {"final": {"total": 68498.85}},
    {"final": {"total": "68498.85"}}, {"final": {"total": Decimal("NaN")}}, {"final": {"total": Decimal("-5")}},
    {"final": {"total": True}}, {"initial": {"total": Decimal("5")}},
])
def test_ac1_a_reply_without_a_decimal_final_total_is_an_error(data: object) -> None:
    """AC-1: missing final, missing total, a float/str/bool/NaN/negative total -> MarginReplyError (fail closed)."""
    with pytest.raises(MarginReplyError):
        required_from_basket_reply(data)  # type: ignore[arg-type]


def test_module_has_no_float_money() -> None:
    """AC-1: the gate module never converts money through float."""
    source = inspect.getsource(margin_gate)
    assert "float(" not in source
