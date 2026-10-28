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
    ex.WholeRupees, ex.SignedWholeRupees, ex.WholePoints, ex.SignedPercent,  # REQ-152/153: Decimal-only, closed
    ex.OiCount,  # GC-UI D-B16 (REQ-083 AC-5): an OI count, int >= 0 only, never a bool; compact Indian form
    ex.SignedPaisa,  # REQ-109 AC-2 (GC-UI D-B48): per-leg paper P&L to the paisa; Decimal-only via Rupees.validate
    ex.Explained, ex.ScenarioViewLabel, ex.ColumnLabel, ex.HealthLabel, ex.ExceptLevels,
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
    ("summary_start_touch", {"levels": "22300"}),
    ("summary_start_touch", {"levels": ("22300",)}),
    ("summary_start_touch", {"levels": ()}),
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
    assert str(render_explanation("summary_start_touch", levels=(d("22300"),))) == (
        "At every level except exactly 22,300 at expiry.")


def _regions_text(r) -> str:
    return str(render_explanation("summary_start_regions", index="NIFTY", regions=r))


def test_level_regions_accept_a_point_part() -> None:
    d = Decimal
    assert _regions_text(((d("22400"), d("22400")),)) == "If NIFTY ends at 22,400 at expiry."
    assert _regions_text(((None, d("1")), (d("2"), d("2")), (d("3"), None))) == (
        "If NIFTY ends below 1, at 2 or above 3 at expiry.")


@pytest.mark.parametrize("regions", [
    ((Decimal(5), Decimal(10)), (Decimal(1), Decimal(3))),
    ((Decimal(1), Decimal(10)), (Decimal(5), Decimal(20))),
    ((Decimal(1), Decimal(3)), (Decimal(1), Decimal(3))),
    ((Decimal(1), Decimal(3)), (Decimal(3), Decimal(5))),
    ((Decimal(1), Decimal(3)), (None, Decimal(5))),
    ((Decimal(1), None), (Decimal(5), Decimal(9))),
    ((None, Decimal("2.24E+4")),),
    ((Decimal("1E+2"), Decimal("3E+2")),),
], ids=["unordered", "overlap", "duplicate", "touching", "open-lower-not-first", "open-upper-not-last", "exponent", "exponent-lower"])
def test_level_regions_refuse_a_malformed_list(regions) -> None:
    with pytest.raises((TypeError, ValueError)):
        _regions_text(regions)


# --- W-066 round 7 (issue #172): a region may carry the exact zero points that split its loss ("except" levels) -------

def test_ac7_a_region_with_except_levels_reads_except_exactly() -> None:
    """AC-7: the except part follows its own region; one, two and three levels; touch form for a loss everywhere."""
    d = Decimal
    assert _regions_text(((d("22000"), d("22800"), (d("22400"),)),)) == (
        "If NIFTY ends between 22,000 and 22,800 (except exactly 22,400) at expiry.")
    assert _regions_text(((None, d("22800"), (d("22200"), d("22400"))),)) == (
        "If NIFTY ends below 22,800 (except exactly 22,200 and 22,400) at expiry.")
    assert _regions_text(((d("22000"), None, (d("22100"), d("22300"), d("22500"))),)) == (
        "If NIFTY ends above 22,000 (except exactly 22,100, 22,300 and 22,500) at expiry.")
    assert _regions_text(((None, d("1")), (d("2"), d("5"), (d("3"),)), (d("6"), None))) == (
        "If NIFTY ends below 1, between 2 and 5 (except exactly 3) or above 6 at expiry.")
    assert str(render_explanation("summary_start_touch", levels=(d("22200"), d("22600")))) == (
        "At every level except exactly 22,200 and 22,600 at expiry.")


_ALLOWED_REGION_SHAPES = {2, 3}


@pytest.mark.parametrize("regions", [
    ((Decimal(1), Decimal(5), ()),),                                   # an empty except tuple
    ((Decimal(1), Decimal(5), (Decimal(1),)),),                        # on the lower edge
    ((Decimal(1), Decimal(5), (Decimal(5),)),),                        # on the upper edge
    ((Decimal(1), Decimal(5), (Decimal(7),)),),                        # outside the region
    ((None, Decimal(5), (Decimal(6),)),),                              # outside an open-below region
    ((Decimal(5), None, (Decimal(4),)),),                              # outside an open-above region
    ((Decimal(1), Decimal(9), (Decimal(4), Decimal(3))),),             # not ascending
    ((Decimal(1), Decimal(9), (Decimal(3), Decimal(3))),),             # a duplicate level
    ((Decimal(1), Decimal(90), (Decimal("3E+1"),)),),                  # exponent notation (30 inside 1-90)
    ((Decimal(1), Decimal(9), ("3",)),),                               # a string level
    ((Decimal(1), Decimal(9), [Decimal(3)]),),                         # a list, not a tuple
    ((Decimal(1), Decimal(9), Decimal(3)),),                           # a bare level, not a tuple
    ((None, None, (Decimal(3),)),),                                    # no bound at all (that is the touch template)
    ((Decimal(1), Decimal(3)), (Decimal(3), Decimal(5), (Decimal(4),))),  # touching regions stay refused
    ((Decimal(1), Decimal(4), (Decimal(3),)), (Decimal(3), Decimal(5))),  # overlapping regions stay refused
])
def test_level_regions_refuse_a_malformed_except_part(regions) -> None:
    with pytest.raises((TypeError, ValueError)):
        _regions_text(regions)


@pytest.mark.parametrize("length", range(0, 6))
def test_a_region_item_is_exactly_two_or_three_long(length: int) -> None:
    """Allow-list: (lower, upper) or (lower, upper, excepts); every other length is refused (generated, 0-5)."""
    items = (Decimal(1), Decimal(9), (Decimal(3),), Decimal(10), Decimal(11))[:length]
    if length in _ALLOWED_REGION_SHAPES:
        assert _regions_text((items,)).startswith("If NIFTY ends between 1 and 9")
    else:
        with pytest.raises((TypeError, ValueError)):
            _regions_text((items,))


@pytest.mark.parametrize("bad", ["22300", 22300, 22300.0, None, [Decimal(1)], (), (Decimal("NaN"),),
                                 (Decimal(2), Decimal(1)), (Decimal("1E+3"),)])
def test_except_levels_take_only_an_ascending_tuple_of_plain_levels(bad) -> None:
    with pytest.raises((TypeError, ValueError)):
        render_explanation("summary_start_touch", levels=bad)
