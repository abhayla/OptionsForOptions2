"""W-066 round 2 (Tier A review 2026-10-09): no outcome template has an open slot.

Round 1 gave several outcome templates the open `Recorded` slot (any one token) and one the untyped
`LegacyRecorded`, so the template was closed but its slots were not. These tests refuse a free token in each slot and
enumerate the outcome templates FROM THE CATALOGUE (not a hand list) so a template switched back to an open slot fails.
"""

from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from ofo.errors import explanations as ex
from ofo.errors.explanations import EXPLANATIONS, render_explanation
from ofo.engine.legs import Action, Instrument

#: Template id prefixes of every text the outcome API renders (outcome, legs, data labels, summary, scenario, table).
OUTCOME_PREFIXES = ("outcome_", "leg_label_", "data_label_", "label_", "summary_", "scenario_", "cell_", "table_")
#: ALLOW-list of the closed slot types an outcome template may use. Anything else (Quoted, UserText, Recorded,
#: LegacyRecorded, Values, str, or a type added later) turns the detection test red until it is reviewed and listed here.
CLOSED_SLOT_TYPES = frozenset({
    ex.Rupees, ex.Points, ex.SignedAmount, ex.Amount, ex.HourMinute, ex.ClockSeconds, ex.UnderlyingName,
    ex.InstrumentRef, ex.LevelRegions, ex.LegRef, ex.LegRefs, ex.HealthWord, ex.ExpiryDate, ex.CellText,
    ex.Explained, ex.ScenarioViewLabel, ex.ColumnLabel, ex.HealthLabel,
})


def _outcome_templates() -> dict[str, ex.ExplanationTemplate]:
    return {tid: t for tid, t in ex.EXPLANATIONS.items() if tid.startswith(OUTCOME_PREFIXES)}


def test_the_catalogue_enumeration_finds_the_outcome_templates() -> None:
    found = _outcome_templates()
    assert len(found) >= 60
    for must in ("cell_text", "leg_label_symbol", "outcome_problem_leg", "summary_lose_unlimited",
                 "scenario_estimated_unavailable", "outcome_why_other_underlying"):
        assert must in found


def _slots_outside_the_allow_list() -> dict[str, list[str]]:
    bad = {tid: [n for n, st in t.slots.items() if st not in CLOSED_SLOT_TYPES] for tid, t in _outcome_templates().items()}
    return {tid: names for tid, names in bad.items() if names}


def test_no_outcome_template_has_an_open_slot() -> None:
    assert _slots_outside_the_allow_list() == {}


@pytest.mark.parametrize("open_type", [ex.Quoted, ex.UserText, ex.Recorded, ex.LegacyRecorded, ex.Values, str])
def test_a_real_template_switched_to_any_open_slot_type_turns_the_check_red(monkeypatch, open_type) -> None:
    """M17: mutate a REAL catalogue entry (`outcome_why_other_underlying.underlying`) and run the real check."""
    import dataclasses
    real = EXPLANATIONS["outcome_why_other_underlying"]
    mutated = dataclasses.replace(real, slots={**real.slots, "underlying": open_type})
    monkeypatch.setattr(ex, "EXPLANATIONS", {**EXPLANATIONS, "outcome_why_other_underlying": mutated})
    with pytest.raises(AssertionError):
        test_no_outcome_template_has_an_open_slot()
    assert _slots_outside_the_allow_list() == {"outcome_why_other_underlying": ["underlying"]}


@pytest.mark.parametrize("value", [Decimal("-0"), Decimal(0) * -1, Decimal("-0.0"), Decimal("0E-10") * -1])
def test_negative_zero_prints_without_a_minus_sign(value: Decimal) -> None:
    assert str(render_explanation("cell_number", value=value)).lstrip("0.") == ""
    assert not str(render_explanation("cell_number", value=value)).startswith("-")
    assert not str(render_explanation("cell_percent", value=value)).startswith("-")
    assert not str(render_explanation("cell_percent_signed", value=value)).startswith("-")


def test_negative_zero_literals() -> None:
    assert str(render_explanation("cell_number", value=Decimal("-0"))) == "0"
    assert str(render_explanation("cell_number", value=Decimal(0) * -1)) == "0"
    assert str(render_explanation("cell_number", value=Decimal("-0.0000"))) == "0.0000"
    assert str(render_explanation("cell_percent", value=Decimal("-0.0"))) == "0.0%"
    assert str(render_explanation("cell_percent_signed", value=Decimal("-0"))) == "+0%"


@pytest.mark.parametrize("template, slots", [
    ("cell_text", {"value": "₹8,245.25"}),                       # the reproduced M2a: money passed as text
    ("cell_text", {"value": "you-should-buy"}),
    ("cell_text", {"value": "Open"}),
    ("summary_lose_unlimited", {"index": "you-should-exit"}),
    ("summary_make_unlimited", {"index": "best-trade"}),
    ("summary_start_regions", {"index": "guaranteed", "regions": ((None, Decimal(1)),)}),
    ("summary_start_regions", {"index": "NIFTY", "regions": ()}),
    ("summary_start_regions", {"index": "NIFTY", "regions": ((None, None),)}),
    ("summary_start_regions", {"index": "NIFTY", "regions": ((Decimal(2), Decimal(1)),)}),
    ("summary_start_regions", {"index": "NIFTY", "regions": ((None, "22,400"),)}),
    ("summary_start_regions", {"index": "NIFTY", "regions": "below 22,400"}),
    ("summary_start_touch", {"level": "22300"}),
    ("scenario_caption_left", {"underlying": "best-trade"}),
    ("scenario_estimated_unavailable", {"legs": "Buy now, this is the best trade"}),
    ("scenario_estimated_unavailable", {"legs": "NSE_FO:44624, buy-now"}),
    ("leg_label_symbol", {"symbol": "buy-now", "label": None}),
    ("outcome_problem_leg", {"leg": "you-should-exit", "why": None}),
    ("outcome_spot_missing", {"underlying": "best-trade"}),
    ("outcome_spot_unusable", {"underlying": "NIFTY", "health": "all-is-well"}),
    ("outcome_why_other_underlying", {"contract_on": "buy-now", "underlying": "NIFTY"}),
    ("outcome_forward_error", {"expiry": "tomorrow-for-sure", "why": None}),
    ("leg_label_quote_unusable", {"health": "great-quote"}),
])
def test_a_free_token_is_refused_in_every_formerly_open_slot(template: str, slots: dict) -> None:
    if "why" in slots:
        slots = {**slots, "why": render_explanation("outcome_why_expired")}
    if "label" in slots:
        slots = {**slots, "label": render_explanation("leg_label_no_quote")}
    with pytest.raises((TypeError, ValueError)):
        render_explanation(template, **slots)


def test_scenario_estimated_unavailable_takes_a_closed_list_of_legs() -> None:
    ok = render_explanation("scenario_estimated_unavailable", legs=("NIFTY2610822800CE", "NSE_FO:44632"))
    assert str(ok) == ("Estimated Now is unavailable: no implied volatility for NIFTY2610822800CE, NSE_FO:44632")
    for bad in ((), ("a b",), ("buy-now",), "NIFTY2610822800CE", ("NIFTY2610822800CE", "Buy now")):
        with pytest.raises((TypeError, ValueError)):
            render_explanation("scenario_estimated_unavailable", legs=bad)


def test_closed_slots_still_take_their_real_values() -> None:
    assert str(render_explanation("cell_text", value=Action.BUY)) == "BUY"
    assert str(render_explanation("cell_text", value=Instrument.CE)) == "CE"
    assert str(render_explanation("cell_text", value=datetime.date(2026, 10, 29))) == "2026-10-29"
    assert str(render_explanation("cell_text", value=3)) == "3"
    assert "SENSEX" in render_explanation("summary_lose_unlimited", index="SENSEX")
    assert str(render_explanation("leg_label_symbol", symbol="SENSEX26OCTFUT",
                                  label=render_explanation("leg_label_no_quote"))) == "SENSEX26OCTFUT: no live quote"
    assert str(render_explanation("outcome_forward_error", expiry=datetime.date(2026, 10, 29),
                                  why=render_explanation("outcome_why_forward"))).startswith("forward for 2026-10-29: ")


@pytest.mark.parametrize("value, text", [
    (Decimal("1E+3"), "1000"), (Decimal("1E+2"), "100"), (Decimal("1.50"), "1.50"), (Decimal("-0.0000001"), "-0.0000001"),
    (Decimal("0E-10"), "0.0000000000"), (7, "7"),
])
def test_cell_number_and_percent_print_plain_notation(value: object, text: str) -> None:
    assert str(render_explanation("cell_number", value=value)) == text
    assert str(render_explanation("cell_percent", value=value)) == text + "%"


@pytest.mark.parametrize("value, text", [(Decimal("1E+2"), "+100"), (Decimal("1E+3"), "+1000"),
                                          (Decimal("-1E+2"), "-100"), (Decimal("16.7"), "+16.7")])
def test_signed_amount_prints_plain_notation(value: Decimal, text: str) -> None:
    assert str(render_explanation("cell_percent_signed", value=value)) == text + "%"


def test_problem_leg_and_margin_wording() -> None:
    line = str(render_explanation("outcome_problem_leg", leg="NSE_FO:44624", why=render_explanation("outcome_why_expired")))
    assert line == "Instrument NSE_FO:44624 cannot be used: expired"
    assert "::" not in line and ": :" not in line
    margin = str(render_explanation("outcome_margin_pending"))
    assert margin == "Margin from Zerodha is not shown yet; it needs your Kite login."
    assert "item" not in margin and "W-0" not in margin


def test_the_table_builds_its_money_and_text_cells_through_closed_slots() -> None:
    """M2a: a money cell rendered as `cell_text(format_rupees(v))` must be refused (the mutation turns this red)."""
    from ofo.engine.display import format_rupees
    with pytest.raises((TypeError, ValueError)):
        render_explanation("cell_text", value=format_rupees(Decimal("8245.25")))


def test_level_regions_read_as_a_list() -> None:
    d = Decimal
    one = lambda r: str(render_explanation("summary_start_regions", index="NIFTY", regions=r))  # noqa: E731
    assert one(((None, d("22400")),)) == "If NIFTY ends below 22,400 at expiry."
    assert one(((d("22400"), None),)) == "If NIFTY ends above 22,400 at expiry."
    assert one(((None, d("22326.85")), (d("22873.15"), None))) == (
        "If NIFTY ends below 22,326.85 or above 22,873.15 at expiry.")
    assert one(((None, d("1")), (d("2"), d("3")), (d("4"), None))) == (
        "If NIFTY ends below 1, between 2 and 3 or above 4 at expiry.")
    assert str(render_explanation("summary_start_touch", level=d("22300"))) == (
        "At every level except exactly 22,300 at expiry.")
