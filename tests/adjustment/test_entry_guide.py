"""GC-ICFIX P2 guided builder (ADR-300, ADR-216, ADR-003): a strategy whose sold strikes break the entry guide gets one
plain line, in three states (breaks / within / cannot tell). The user-test case: strategy 138, sold call delta 0.46,
guide "shorts at 0.15 to 0.20 delta" (the stored text of the iron condor system playbook). Pure: no database."""
from __future__ import annotations

import json
import pathlib
from decimal import Decimal as D

import pytest

from ofo.adjustment import entry_guide as eg
from ofo.adjustment import playbook_eval as pe

GUIDE = "shorts at 0.15 to 0.20 delta, wings 200 to 400 points out"  # the stored text, system_playbooks.json
PLAYBOOKS = pathlib.Path(__file__).parents[2] / "backend" / "ofo" / "adjustment" / "system_playbooks.json"


def _short(kind: str, delta: D | None) -> pe.ShortLeg:
    return pe.ShortLeg(D("24500"), delta, D("80"), kind)


def test_the_stored_guide_text_of_every_system_playbook_reads_as_a_delta_range() -> None:
    guides = [p["body"]["guards"]["entry_guide"] for p in json.loads(PLAYBOOKS.read_text("utf-8"))["playbooks"]
              if "entry_guide" in p["body"].get("guards", {})]
    assert guides and {eg.parse_entry_guide(g) for g in guides} == {(D("0.15"), D("0.20"))}


@pytest.mark.parametrize("text", [None, "", "shorts near the money", "shorts at 0.20 to 0.15 delta"])
def test_a_guide_text_with_no_readable_range_reads_as_none(text: str | None) -> None:
    assert eg.parse_entry_guide(text) is None


def test_sold_delta_0_46_against_the_guide_warns_with_both_numbers() -> None:
    line = eg.entry_guide_line((_short("CE", D("0.46")), _short("PE", D("0.44"))), GUIDE)
    assert line == "Sold call delta 0.46; the entry guide is 0.15 to 0.20."


def test_the_put_side_is_named_when_it_is_the_larger() -> None:
    assert eg.entry_guide_line((_short("CE", D("0.12")), _short("PE", D("0.33"))), GUIDE) == (
        "Sold put delta 0.33; the entry guide is 0.15 to 0.20.")


@pytest.mark.parametrize("delta", ["0.15", "0.18", "0.20"])
def test_a_sold_delta_within_the_guide_has_no_line(delta: str) -> None:
    assert eg.entry_guide_line((_short("CE", D(delta)), _short("PE", D("0.16"))), GUIDE) is None


def test_the_worst_leg_not_the_first_decides() -> None:
    assert eg.check_entry_guide((_short("CE", D("0.18")), _short("PE", D("0.30"))), GUIDE).state == "breaks"


@pytest.mark.parametrize("shorts, guide", [
    ((_short("CE", None), _short("PE", D("0.18"))), GUIDE),  # a delta missing
    ((_short("CE", D("0.46")),), "shorts near the money"),  # no readable guide value
    ((_short("CE", D("0.46")),), None),
    ((), GUIDE),  # nothing sold
])
def test_missing_delta_or_guide_says_it_could_not_check_never_silence(shorts, guide) -> None:
    assert eg.check_entry_guide(shorts, guide).state == "unknown"
    assert eg.entry_guide_line(shorts, guide) == "Could not check against the entry guide."


def test_one_function_gives_the_sold_leg_delta_to_the_entry_line_and_to_t03() -> None:
    shorts = (_short("CE", D("0.46")), _short("PE", D("0.44")))
    assert pe.sold_leg_delta(shorts) == D("0.46") == eg.check_entry_guide(shorts, GUIDE).delta
    assert pe.sold_leg_delta((_short("CE", None),)) is None


def test_the_lines_carry_no_advice_words() -> None:
    from ofo.errors.explanations import render_explanation

    for line in (eg.entry_guide_line((_short("CE", D("0.46")),), GUIDE), eg.entry_guide_line((), GUIDE)):
        assert line and "should" not in line.lower() and "recommend" not in line.lower()
    assert render_explanation("entry_guide_unchecked") == "Could not check against the entry guide."
