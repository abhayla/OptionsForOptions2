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
import re
from decimal import Decimal

import pytest

from ofo.execution import margin_gate
from ofo.execution.margin_gate import MarginReplyError, MarginVerdict, check_margin, required_from_basket_reply

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPLY_FILE = ROOT / "docs/research/kite-proof-2026-10-07/rest-2026-10-15/margins_basket.json"
EXIT_FILE = ROOT / "tests/fixtures/kite_margins/basket-2026-10-16-exit-sell-held.json"
BUY_CE_FILE = ROOT / "tests/fixtures/kite_margins/basket-2026-10-16-buy-ce-otm-bump0.json"
STRANGLE_FILE = ROOT / "tests/fixtures/kite_margins/basket-2026-10-16-long-strangle-bump5.json"


@dataclasses.dataclass(frozen=True)
class Leg:
    """One request order, the fields the gate reads (what ofo_app's BasketOrder carries)."""

    exchange: str
    tradingsymbol: str
    transaction_type: str
    quantity: int
    price: Decimal


CE, PE = "NIFTY26SEP23150CE", "NIFTY26SEP23150PE"  # catalogue symbols (the synthetic replies below name them)
FUT, BFO_PE = "NIFTY26SEPFUT", "SENSEX26O0173900PE"


def _legs(request: list[dict]) -> list[Leg]:
    return [Leg(r["exchange"], r["tradingsymbol"], r["transaction_type"], r["quantity"], Decimal(str(r["price"])))
            for r in request]


with REPLY_FILE.open(encoding="utf-8") as _handle:
    CONDOR = _legs(json.load(_handle, parse_float=Decimal)["request"])  # the 4 legs sent on 2026-10-15


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
    required = required_from_basket_reply(reply_data, CONDOR)
    assert required == Decimal("68498.85")
    verdict = check_margin(Decimal("68498.85"), required)
    assert verdict.allowed is True
    assert verdict.message is None
    assert (verdict.available, verdict.required) == (Decimal("68498.85"), Decimal("68498.85"))


def test_ac4_one_paisa_short_blocks_with_both_amounts(reply_data: dict) -> None:
    """AC-4 (core): available Rs 68,498.84 is one paisa short, so no basket; the message shows both amounts."""
    verdict = check_margin(Decimal("68498.84"), required_from_basket_reply(reply_data, CONDOR))
    assert verdict.allowed is False
    assert verdict.message is not None
    assert verdict.message.what_happened == (
        "Zerodha says this strategy needs ₹68,498.85 of margin; ₹68,498.84 is available in your account.")
    assert verdict.message.what_is_blocked == "Building the Zerodha basket for this strategy."
    assert verdict.message.code == "MARGIN_201"


def test_ac4_the_message_offers_quantity_review_and_add_funds(reply_data: dict) -> None:
    """AC-4: the next step offers a quantity change, a review, or adding funds."""
    verdict = check_margin(Decimal("1000"), required_from_basket_reply(reply_data, CONDOR))
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
    assert required_from_basket_reply(reply_data, CONDOR) != Decimal("296332.8")
    assert check_margin(Decimal("68498.85"), required_from_basket_reply(reply_data, CONDOR)).allowed is True


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


@pytest.mark.parametrize("required", [Decimal("1e12") + 1, Decimal("1e30"), Decimal("1e100"), Decimal("1E+999999")])
def test_ac1_an_absurd_required_margin_blocks_with_a_message_never_raises(required: Decimal) -> None:
    """AC-1 (round 3 M2): a required margin too large to round to the paisa or to show blocks the basket with the
    could-not-confirm message; no InvalidOperation or ValueError escapes."""
    verdict = check_margin(Decimal("68498.85"), required)
    assert verdict.allowed is False
    assert verdict.message is not None
    assert verdict.message.what_happened == (
        "We could not confirm your available margin with Zerodha. Execution is paused.")


def test_ac1_a_huge_balance_still_covers_a_normal_requirement() -> None:
    """AC-1 (round 3 M2): the cap on shown amounts does not block a balance that covers the requirement."""
    assert check_margin(Decimal("1e30"), Decimal("68498.85")).allowed is True


def test_ac1_a_caller_cannot_forge_an_allowed_verdict() -> None:
    """AC-1: MarginVerdict cannot be built outside check_margin (caller-supplied-verdict-trusted); there is no mint
    token to borrow (round 2: the old ``_MINT`` let any importer build one)."""
    assert not hasattr(margin_gate, "_MINT")
    with pytest.raises(TypeError):
        MarginVerdict(Decimal("1"), Decimal("9"))  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        MarginVerdict(Decimal("1"), Decimal("9"), _mint=object())  # type: ignore[call-arg]
    with pytest.raises(TypeError):  # `allowed` and `message` are not inputs
        MarginVerdict(Decimal("1"), Decimal("9"), allowed=True, message=None)  # type: ignore[call-arg]


def test_ac1_replace_cannot_copy_a_verdict() -> None:
    """AC-1 (round 2): a verdict is not a dataclass, so ``dataclasses.replace`` raises for every field, including the
    amounts (round 1 let ``replace(blocked, available=big)`` make an allowed verdict); it cannot be edited either."""
    blocked = check_margin(Decimal("68498.84"), Decimal("68498.85"))
    for changes in ({"allowed": True}, {"message": None}, {"available": Decimal("99999999")}, {}):
        with pytest.raises(TypeError):
            dataclasses.replace(blocked, **changes)
    with pytest.raises(AttributeError):
        blocked.allowed = True  # type: ignore[misc]
    assert blocked.allowed is False and blocked.message is not None


def test_ac3_zerodhas_figure_alone_decides(reply_data: dict) -> None:
    """AC-3: the gate takes only Zerodha's two figures (no platform estimate parameter) and says Zerodha's figure."""
    # #338: closes_held is a bool the basket builder computes; still no platform estimate parameter
    assert list(inspect.signature(check_margin).parameters) == ["available", "required", "closes_held"]
    verdict = check_margin(Decimal("10"), required_from_basket_reply(reply_data, CONDOR))
    assert verdict.message is not None and verdict.message.what_happened.startswith("Zerodha says")


@pytest.mark.parametrize("data", [
    {}, {"final": {}}, {"final": None}, {"final": {"total": None}}, {"final": {"total": 68498.85}},
    {"final": {"total": "68498.85"}}, {"final": {"total": Decimal("NaN")}},
    {"final": {"total": True}}, {"initial": {"total": Decimal("5")}},
])
def test_ac1_a_reply_without_a_decimal_final_total_is_an_error(data: object) -> None:
    """AC-1: missing final, missing total, a float/str/bool/NaN/negative total -> MarginReplyError (fail closed)."""
    with pytest.raises(MarginReplyError):
        required_from_basket_reply(data, CONDOR)  # type: ignore[arg-type]


# --- ADR-094: the BUY premium above Kite's own figure, up to the limit price --------------------------------------

@pytest.fixture(scope="module")
def strangle() -> tuple[dict, list[Leg]]:
    """The real 2026-10-16 long-strangle reply (bump=5: both BUY limits 5.00 above live) and its request."""
    with STRANGLE_FILE.open(encoding="utf-8") as handle:
        recorded = json.load(handle, parse_float=Decimal)
    return recorded["reply"]["data"], _legs(recorded["request"])


def _reply(*legs: tuple[str, str, object], total: object = Decimal("100")) -> dict:
    """A minimal reply: (tradingsymbol, exchange, option_premium) per order; a None premium leaves the key out."""
    rows = [{"tradingsymbol": s, "exchange": e, **({} if p is None else {"option_premium": p})} for s, e, p in legs]
    return {"final": {"total": total}, "orders": rows}


def _leg(symbol: str, side: str, quantity: int = 65, price: str = "10", exchange: str = "NFO") -> Leg:
    return Leg(exchange, symbol, side, quantity, Decimal(price))


def test_adr094_core_real_long_strangle_reply_adds_the_premium_above_kites_figure(strangle) -> None:
    """Core (ADR-094): final.total 6409; CE 65 x 45.55 = 2960.75 vs option_premium 2697.5 (+263.25); PE 65 x 63.15 =
    4104.75 vs 3711.5 (+393.25) -> 6409 + 263.25 + 393.25 = 7065.50. Figures read from the recorded file."""
    data, orders = strangle
    assert data["final"]["total"] == Decimal("6409")
    assert [o["option_premium"] for o in data["orders"]] == [Decimal("2697.5"), Decimal("3711.5")]
    assert [(o.quantity, o.price) for o in orders] == [(65, Decimal("45.55")), (65, Decimal("63.15"))]
    assert required_from_basket_reply(data, orders) == Decimal("7065.50")


def test_adr094_the_1033_case_two_buy_legs_5_above_live() -> None:
    """ADR-094 real case: Kite 2,073.50, two BUY legs each Rs 325.00 above Kite's premium -> 2,723.50."""
    data = _reply((CE, "NFO", Decimal("975")), (PE, "NFO", Decimal("975")),
                  total=Decimal("2073.50"))
    orders = [_leg(CE, "BUY", price="20"), _leg(PE, "BUY", price="20")]  # 65 x 20
    assert required_from_basket_reply(data, orders) == Decimal("2723.50")


def test_adr094_sell_legs_add_nothing_even_with_odd_premiums() -> None:
    """Checklist 1: a SELL leg whose option_premium is negative, or larger than qty x price, adds 0."""
    data = _reply((CE, "NFO", Decimal("-5")), (PE, "NFO", Decimal("99999")))
    orders = [_leg(CE, "SELL"), _leg(PE, "SELL")]
    assert required_from_basket_reply(data, orders) == Decimal("100")


def test_adr094_a_buy_leg_with_premium_above_qty_x_price_adds_zero_never_a_credit() -> None:
    """Checklist 2: qty x price (650) < option_premium (900) -> +0, so the result is not below final.total."""
    data = _reply((CE, "NFO", Decimal("900")))
    assert required_from_basket_reply(data, [_leg(CE, "BUY")]) == Decimal("100")
    equal = _reply((CE, "NFO", Decimal("650")))
    assert required_from_basket_reply(equal, [_leg(CE, "BUY")]) == Decimal("100")


@pytest.mark.parametrize("premium", [None, 12.5, "650", True, Decimal("-1"), Decimal("NaN"), Decimal("Infinity")])
def test_adr094_a_buy_leg_with_an_unusable_option_premium_blocks(premium: object) -> None:
    """Checklist 3: missing / float / str / bool / negative / NaN / infinite option_premium -> MarginReplyError."""
    with pytest.raises(MarginReplyError):
        required_from_basket_reply(_reply((CE, "NFO", premium)), [_leg(CE, "BUY")])


def test_adr094_an_int_option_premium_is_exact() -> None:
    """Kite prints whole numbers without a point: 650 x 1 vs premium int 600 -> +50."""
    data = _reply((CE, "NFO", 600))
    assert required_from_basket_reply(data, [_leg(CE, "BUY", quantity=1, price="650")]) == Decimal("150")


def test_adr094_a_sell_legs_bad_premium_is_not_read() -> None:
    """A SELL leg adds nothing, so its premium is not looked at (Kite sends 0 there)."""
    data = _reply((CE, "NFO", None))
    assert required_from_basket_reply(data, [_leg(CE, "SELL")]) == Decimal("100")


def test_adr094_count_or_identity_mismatch_between_request_and_reply_blocks() -> None:
    """Checklist 4: fewer / more reply orders, swapped orders, a different exchange -> MarginReplyError."""
    two = _reply((CE, "NFO", Decimal("0")), (PE, "NFO", Decimal("0")))
    ce, pe = _leg(CE, "BUY"), _leg(PE, "BUY")
    assert required_from_basket_reply(two, [ce, pe]) == Decimal("100") + 2 * Decimal("650")
    for orders in ([ce], [ce, pe, ce], [pe, ce], [_leg(CE, "BUY", exchange="BFO"), pe]):
        with pytest.raises(MarginReplyError):
            required_from_basket_reply(two, orders)
    with pytest.raises(MarginReplyError):
        required_from_basket_reply({"final": {"total": Decimal("1")}}, [ce])  # no orders list at all
    with pytest.raises(MarginReplyError):
        required_from_basket_reply({"final": {"total": Decimal("1")}, "orders": ["x"]}, [ce])  # a row that is no object


def test_adr094_futures_buy_adds_nothing_and_a_bfo_option_is_counted() -> None:
    """Checklist 5: a NIFTY future BUY adds 0 (even with no option_premium); a SENSEX (BFO) option BUY is counted."""
    fut = _reply((FUT, "NFO", None))
    assert required_from_basket_reply(fut, [_leg(FUT, "BUY")]) == Decimal("100")
    sensex = _reply((BFO_PE, "BFO", Decimal("100")))
    order = _leg(BFO_PE, "BUY", quantity=20, price="12.5", exchange="BFO")
    assert required_from_basket_reply(sensex, [order]) == Decimal("100") + Decimal("150")


@pytest.mark.parametrize("quantity,price", [(0, "10"), (-65, "10"), (True, "10"), (65, "0"), (65, "-1"), (65, "NaN"),
                                            (65, "Infinity")])
def test_adr094_a_buy_leg_with_a_bad_quantity_or_price_blocks(quantity: object, price: str) -> None:
    """Quantity must be an int > 0 and the limit price an exact Decimal > 0, else the reply cannot be used."""
    data = _reply((CE, "NFO", Decimal("0")))
    with pytest.raises(MarginReplyError):
        required_from_basket_reply(data, [Leg("NFO", CE, "BUY", quantity, Decimal(price))])  # type: ignore[arg-type]
    with pytest.raises(MarginReplyError):
        required_from_basket_reply(data, [Leg("NFO", CE, "BUY", 65, 10.5)])  # type: ignore[arg-type]


# --- #321: a basket that closes held positions (Kite's final.total is negative) ------------------------------------

def test_321_core_real_exit_reply_needs_zero_margin_and_is_allowed() -> None:
    """Core: the real 2026-10-16 15:06 SELL 65 of a held NIFTY CE reply has final.total -214.5 -> required 0."""
    with EXIT_FILE.open(encoding="utf-8") as handle:
        recorded = json.load(handle, parse_float=Decimal)
    data = recorded["reply"]["data"]
    assert data["final"]["total"] == Decimal("-214.5")
    required = required_from_basket_reply(data, _legs(recorded["request"]))
    assert required == Decimal(0)
    assert check_margin(Decimal(0), required).allowed is True
    assert check_margin(Decimal("1000"), required).allowed is True


def test_321_a_negative_total_is_never_a_credit_toward_a_buy_legs_top_up() -> None:
    """Mixed basket: BUY new leg (top-up 650-0=650) + SELL a held one, total -214.5 -> 0 + 650, not 435.5."""
    data = _reply((CE, "NFO", Decimal("0")), (PE, "NFO", Decimal("0")), total=Decimal("-214.5"))
    orders = [_leg(CE, "BUY"), _leg(PE, "SELL")]
    assert required_from_basket_reply(data, orders) == Decimal("650")


@pytest.mark.parametrize("total", [Decimal("-0.01"), Decimal("-1E+6"), Decimal(-5), -5])
def test_321_any_finite_negative_total_is_zero_required(total: object) -> None:
    assert required_from_basket_reply(_reply((CE, "NFO", None), total=total), [_leg(CE, "SELL")]) == Decimal(0)


@pytest.mark.parametrize("total", [Decimal("-Infinity"), Decimal("Infinity"), Decimal("NaN"), Decimal("-NaN"), None,
                                   -214.5])
def test_321_a_non_finite_or_non_number_total_still_blocks(total: object) -> None:
    with pytest.raises(MarginReplyError):
        required_from_basket_reply(_reply((CE, "NFO", None), total=total), [_leg(CE, "SELL")])


def test_321_negative_available_funds_still_block_a_closing_basket() -> None:
    assert check_margin(Decimal("-1"), Decimal(0)).allowed is False


def test_adr094_the_result_is_never_below_the_final_total(strangle) -> None:
    data, orders = strangle
    assert required_from_basket_reply(data, orders) >= data["final"]["total"]


def test_module_has_no_float_money() -> None:
    """AC-1: the gate module never converts money through float."""
    source = inspect.getsource(margin_gate)
    assert "float(" not in source


# --- ADR-099 / ADR-101: Kite money is rounded half-up to the paisa where it is parsed -----------------------------

def _recorded_decimals(node: object) -> object:
    """Rebuild a recorded reply (the recorder stored numbers as strings) the way `parse_float=Decimal` gives them."""
    if isinstance(node, dict):
        return {k: _recorded_decimals(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_recorded_decimals(v) for v in node]
    if isinstance(node, str) and re.fullmatch(r"-?\d+(\.\d+)?", node):
        return Decimal(node)
    return node


def test_099_core_real_rest_basket_reply_is_exact_to_the_paisa() -> None:
    """Real reply ofo-kite-ticks/2026-10-16/rest/rest-122852.json (one NIFTY call BUY, 65 @ 31.9): final.total
    "2073.5", option_premium "2073.5"; 65 x 31.9 = 2073.50, so the top-up is 0 and the figure is 2073.50."""
    recorded = json.loads(BUY_CE_FILE.read_text(encoding="utf-8"))
    assert recorded["reply"]["data"]["final"]["total"] == "2073.5"  # the raw recorded value
    data = _recorded_decimals(recorded["reply"]["data"])
    required = required_from_basket_reply(data, _legs(recorded["request"]))  # type: ignore[arg-type]
    assert required == Decimal("2073.50") and required.as_tuple() == Decimal("2073.50").as_tuple()  # to the paisa


def test_099_float_tail_above_the_available_figure_is_not_a_shortfall() -> None:
    """The live case (issue 297): Zerodha needs 68498.85000000001, 68498.85 is available -> allowed."""
    required = required_from_basket_reply(_reply(total=Decimal("68498.85000000001")), [])
    assert required == Decimal("68498.85")
    verdict = check_margin(Decimal("68498.85"), required)
    assert verdict.allowed is True and verdict.message is None


def test_099_the_attack_one_paisa_short_stays_blocked() -> None:
    required = required_from_basket_reply(_reply(total=Decimal("68498.86")), [])
    verdict = check_margin(Decimal("68498.85"), required)
    assert verdict.allowed is False and verdict.message is not None
    assert "needs ₹68,498.86 of margin; ₹68,498.85 is available" in verdict.message.what_happened


def test_099_a_float_tail_on_a_buy_legs_premium_uses_the_paisa() -> None:
    """option_premium 1124.2499999999998 reads 1124.25; 65 x 20 = 1300 -> top-up 175.75 on a total of 100 = 275.75."""
    data = _reply((CE, "NFO", Decimal("1124.2499999999998")), total=Decimal("100"))
    assert required_from_basket_reply(data, [_leg(CE, "BUY", price="20")]) == Decimal("275.75")


def test_099_a_negative_total_is_still_zero_after_rounding() -> None:
    assert required_from_basket_reply(_reply(total=Decimal("-214.5")), []) == Decimal("0")


# --- #338: a basket that only closes held positions and needs 0 passes whatever the balance -------------------------
from ofo.execution.margin_gate import reduces_held_only  # noqa: E402


@pytest.mark.parametrize("available", [Decimal("-120.50"), Decimal("-0.01"), Decimal("0"), Decimal("671.50")])
def test_338_closing_basket_needing_zero_passes_on_any_balance(available: Decimal) -> None:
    """REQ-055 AC-1 (#338, B4 d funds negative / zero / positive): closes_held and required 0 -> allowed, no message."""
    verdict = check_margin(available, Decimal("0"), closes_held=True)
    assert (verdict.allowed, verdict.message) == (True, None)


def test_338_closing_basket_with_a_positive_required_is_checked_as_today() -> None:
    """REQ-055 AC-1 (#338 attack 2): Zerodha states a positive figure for a closing basket -> -120.50 < 0.01 blocks."""
    assert check_margin(Decimal("-120.50"), Decimal("0.01"), closes_held=True).allowed is False
    assert check_margin(Decimal("354.25"), Decimal("354.25"), closes_held=True).allowed is True


def test_338_unknown_figures_block_even_for_a_closing_basket() -> None:
    """REQ-055 AC-1 (#338, B4 d missing): an unknown balance or required figure is never a pass."""
    assert check_margin(None, Decimal("0"), closes_held=True).allowed is False
    assert check_margin(Decimal("-1"), None, closes_held=True).allowed is False


@pytest.mark.parametrize("flag", [1, "yes", None, object()])
def test_338_closes_held_must_be_exactly_a_bool(flag: object) -> None:
    """REQ-055 AC-1 (#338): a truthy non-bool is refused, never read as 'closes held'."""
    with pytest.raises(TypeError):
        check_margin(Decimal("-1"), Decimal("0"), closes_held=flag)  # type: ignore[arg-type]


HC, HP = "NFO:12080386", "NFO:12080387"  # held contracts (instrument ids)
REDUCING = [
    ([(HC, "SELL", 65)], {HC: 65}),             # close a long
    ([(HC, "SELL", 30)], {HC: 65}),             # partial exit
    ([(HC, "BUY", 65)], {HC: -65}),             # buy-back of a short
    ([(HC, "SELL", 30), (HC, "SELL", 35)], {HC: 65}),  # two orders summing to the held units
    ([(HC, "SELL", 65), (HP, "BUY", 75)], {HC: 65, HP: -75}),
]
NOT_REDUCING = [
    ([], {HC: 65}),                             # empty basket
    ([(HC, "SELL", 65)], {}),                   # nothing held
    ([(HC, "SELL", 65)], {HC: -65}),            # adds to a short
    ([(HC, "BUY", 65)], {HC: 65}),              # adds to a long
    ([(HC, "SELL", 66)], {HC: 65}),             # more than held
    ([(HC, "SELL", 40), (HC, "SELL", 40)], {HC: 65}),  # together more than held
    ([(HC, "SELL", 30), (HC, "BUY", 30)], {HC: 65}),   # both sides of one contract
    ([(HC, "SELL", 65), (HP, "SELL", 75)], {HC: 65}),  # mixed: the second leg opens
    ([(HC, "sell", 65)], {HC: 65}),             # side not exactly SELL
    ([(HC, "SELL", 0)], {HC: 65}),              # zero units
    ([(HC, "SELL", True)], {HC: 65}),           # a bool is not units
    ([(HC, "SELL", 65)], {HC: 0}),              # held 0
    ([(HC, "SELL", 65)], {HC: 65.0}),           # held not an int
    ([(HC, "SELL", 65)], {HC: True}),           # held a bool
]


@pytest.mark.parametrize(("orders", "held"), REDUCING)
def test_338_reduce_only_allowed_shapes(orders, held) -> None:
    """REQ-055 AC-1 (#338): exit, partial exit, buy-back and split closes are reduce-only."""
    assert reduces_held_only(orders, held) is True


@pytest.mark.parametrize(("orders", "held"), NOT_REDUCING)
def test_338_every_other_shape_is_not_reduce_only(orders, held) -> None:
    """REQ-055 AC-1 (#338 attack 1, allow-list): any shape outside the allowed one is False."""
    assert reduces_held_only(orders, held) is False
