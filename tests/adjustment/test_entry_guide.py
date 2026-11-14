"""GC-ICFIX P2 guided builder (ADR-300, ADR-216, ADR-003): a strategy whose sold strikes break the entry guide gets one
plain line, in three states (breaks / within / cannot tell). The user-test case: strategy 138, sold call delta 0.46,
guide "shorts at 0.15 to 0.20 delta" (the stored text of the system playbooks). Pure: no database."""
from __future__ import annotations

import json
import pathlib
from decimal import Decimal as D

import pytest
from ofo.adjustment import entry_guide as eg
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.playbook_types import TYPE_KEYS
from ofo.errors.explanations import render_explanation

GUIDE = "shorts at 0.15 to 0.20 delta, wings 200 to 400 points out"  # the stored text, system_playbooks.json
NAME = "Iron condor: system default"
PLAYBOOKS = pathlib.Path(__file__).parents[2] / "backend" / "ofo" / "adjustment" / "system_playbooks.json"
#: system playbooks whose entry_guide text states no delta range: each must answer "could not check". Empty today; a
#: wording change that stops a text parsing must fail test_every_system_playbook_guide_reads_or_is_listed.
NO_NUMERIC_GUIDE: frozenset[str] = frozenset()
SYSTEM_PLAYBOOKS = 12


def _short(kind: str, delta: D | None) -> pe.ShortLeg:
    return pe.ShortLeg(D("24500"), delta, D("80"), kind)


def _entries() -> list[dict]:
    return json.loads(PLAYBOOKS.read_text("utf-8"))["playbooks"]


def test_every_system_playbook_guide_reads_or_is_listed() -> None:
    entries = _entries()
    assert len(entries) == SYSTEM_PLAYBOOKS
    for p in entries:
        text = p["body"]["guards"].get("entry_guide")
        got = eg.parse_entry_guide(text)
        if p["strategy_type"] in NO_NUMERIC_GUIDE:
            assert got is None, p["strategy_type"]
        else:
            assert got == (D("0.15"), D("0.20")), (p["strategy_type"], text)


@pytest.mark.parametrize("text", [None, "", "shorts near the money", "shorts at 0.20 to 0.15 delta"])
def test_a_guide_text_with_no_readable_range_reads_as_none(text: str | None) -> None:
    assert eg.parse_entry_guide(text) is None


def test_sold_delta_0_46_against_the_guide_warns_with_both_numbers_and_the_rule_set() -> None:
    line = eg.entry_guide_line((_short("CE", D("0.46")), _short("PE", D("0.44"))), GUIDE, NAME)
    assert line == ("Sold call delta 0.46; the entry guide of the default rule set (Iron condor: system default) "
                    "is 0.15 to 0.20.")


def test_the_put_side_is_named_when_it_is_the_larger() -> None:
    assert eg.entry_guide_line((_short("CE", D("0.12")), _short("PE", D("0.33"))), GUIDE, NAME) == (
        "Sold put delta 0.33; the entry guide of the default rule set (Iron condor: system default) is 0.15 to 0.20.")


@pytest.mark.parametrize("delta", ["0.15", "0.18", "0.20"])
def test_a_sold_delta_within_the_guide_has_no_line(delta: str) -> None:
    assert eg.entry_guide_line((_short("CE", D(delta)), _short("PE", D("0.16"))), GUIDE, NAME) is None


def test_the_worst_leg_not_the_first_decides() -> None:
    assert eg.check_entry_guide((_short("CE", D("0.18")), _short("PE", D("0.30"))), GUIDE).state == "breaks"


@pytest.mark.parametrize("shorts, guide", [
    ((_short("CE", None), _short("PE", D("0.18"))), GUIDE),  # a delta missing
    ((_short("CE", D("0.46")),), "shorts near the money"),  # no readable guide value
    ((_short("CE", D("0.46")),), None),
    ((), GUIDE),  # nothing sold
])
def test_missing_delta_or_guide_says_it_could_not_check_never_silence(shorts, guide) -> None:
    assert eg.check_entry_guide(shorts, guide).state == "cannot_tell"
    assert eg.entry_guide_line(shorts, guide, NAME) == "Could not check against the entry guide."


def test_one_function_gives_the_sold_leg_delta_to_the_entry_line_and_to_t03() -> None:
    shorts = (_short("CE", D("0.46")), _short("PE", D("0.44")))
    assert pe.sold_leg_delta(shorts) == D("0.46") == eg.check_entry_guide(shorts, GUIDE).delta
    assert pe.sold_leg_delta((_short("CE", None),)) is None


def test_the_lines_carry_no_advice_words() -> None:
    for line in (eg.entry_guide_line((_short("CE", D("0.46")),), GUIDE, NAME), eg.entry_guide_line((), GUIDE, NAME)):
        assert line and "should" not in line.lower() and "recommend" not in line.lower()
    assert render_explanation("entry_guide_unchecked") == "Could not check against the entry guide."


# ---- the whole answer for a priced strategy: sold (kind, |delta|) legs + the shape's default rule set ----------------
def test_the_default_rule_set_of_a_shape_is_the_system_playbook_of_its_type() -> None:
    names = {p["strategy_type"]: p["name"] for p in _entries()}
    assert eg.system_rule_set("strangle") == (names["strangle"], GUIDE)
    assert eg.system_rule_set("no_such_shape") is None
    assert eg.system_rule_set(None) is None


def test_the_138_numbers_through_the_whole_answer() -> None:
    ans = eg.entry_guide_for((("CE", D("0.46")), ("PE", D("0.44"))), "ic")
    assert ans.state == "breaks" and ans.line == (
        "Sold call delta 0.46; the entry guide of the default rule set (Iron condor: system default) is 0.15 to 0.20.")
    assert eg.entry_guide_for((("CE", D("0.18")), ("PE", D("0.17"))), "ic").state == "within"
    assert eg.entry_guide_for((("CE", D("0.18")), ("PE", D("0.17"))), "ic").line is None


def test_an_applicable_shape_with_a_missing_delta_cannot_tell() -> None:
    ans = eg.entry_guide_for((("CE", None), ("PE", D("0.17"))), "ic")
    assert ans.state == "cannot_tell" and ans.line == "Could not check against the entry guide."


def test_a_shape_with_no_sold_option_leg_has_no_answer() -> None:
    assert eg.entry_guide_for((), "ic") is None


def test_an_unknown_shape_has_no_line_and_no_state() -> None:
    assert eg.entry_guide_for((("CE", D("0.46")),), None) is None
    assert eg.entry_guide_for((("CE", D("0.46")),), "a_new_type") is None


#: ADR-300 is about a condor outside its entry guide: the guide applies to shapes whose sold legs are meant to be out of
#: the money (iron condor, short strangle, credit spreads) and to no other. Decided per type from what the shape IS.
APPLIES = {"ic", "strangle", "credit"}
NOT_APPLY = {"straddle", "ifly", "dirfly", "calendar", "debit", "longopt", "longvol", "ratio", "other"}


def test_every_shape_type_is_classified_deliberately() -> None:
    assert set(TYPE_KEYS) == APPLIES | NOT_APPLY and not APPLIES & NOT_APPLY  # new type: fails until classified
    assert set(eg.GUIDE_APPLIES) == set(TYPE_KEYS)


@pytest.mark.parametrize("stype", sorted(APPLIES | NOT_APPLY))
def test_the_line_applies_or_not_per_shape_type(stype: str) -> None:
    ans = eg.entry_guide_for((("CE", D("0.46")), ("PE", D("0.44"))), stype)
    if stype in APPLIES:
        assert ans is not None and ans.state == "breaks"
    else:
        assert ans is None
