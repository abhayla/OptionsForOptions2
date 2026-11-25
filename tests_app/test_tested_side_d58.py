"""GC-ICLIVE-E D-58: after an adjustment the T-01 rule line names the tested side (the side whose short is nearer
spot), from the evaluator's own nearest-short answer. Real case: a condor with the put short 25,600 and the call short
25,800 at spot 25,700 after adjustment 1 (C3 / C5). No side known: no suffix, no crash. No database."""
from __future__ import annotations

from decimal import Decimal

import pytest
from ofo.adjustment import playbook_eval as pe
from ofo.strategy.stored_form import shown_broker, shown_name
from ofo_app import adjustment_check as check
from ofo_app.routes import adjustment_check as route

D = Decimal
SHORTS = (pe.ShortLeg(D("25600"), None, None, "PE"), pe.ShortLeg(D("25800"), None, None, "CE"))
LABEL, UNIT = "Spot within this % of a short strike", "%"


def test_the_nearest_short_names_the_side():
    assert pe.nearest_short_side(D("25640"), SHORTS) == "PE"
    assert pe.nearest_short_side(D("25760"), SHORTS) == "CE"
    assert pe.nearest_short_side(D("25700"), SHORTS) == "CE"  # a tie is the call side, as in approaches.tested_side


@pytest.mark.parametrize("shorts", [(), (pe.ShortLeg(D("25600"), None, None, None),),
                                    (pe.ShortLeg(D("25600"), None, None, "FUT"),)])
def test_no_known_side_gives_none(shorts):
    assert pe.nearest_short_side(D("25640"), shorts) is None


@pytest.mark.parametrize(("side", "word"), [("PE", "put"), ("CE", "call")])
def test_the_line_names_the_tested_side(side, word):
    line = str(check.condition_line("T-01", LABEL, UNIT, "0.2335", "0.5000", None, None, side))
    assert line == f"{LABEL}: 0.2335 % (rule 0.5000 %) ({word} side tested)"


def test_no_side_no_suffix_and_a_breached_line_is_left_alone():
    assert "tested" not in str(check.condition_line("T-01", LABEL, UNIT, "0.2335", "0.5000", None, None, None))
    beyond = ("CE", D("25800"), D("12"))
    assert "tested" not in str(check.condition_line("T-01", LABEL, UNIT, "0", "0.5000", beyond, None, "CE"))
    assert "tested" not in str(check.condition_line("T-02", LABEL, UNIT, "1", "0", None, None, "PE"))  # only T-01


def test_the_check_route_takes_the_side_from_the_flags_own_hit():
    hit = pe.Hit("T-01", D("0.2335"), D("0.5"), "le", True, None, "PE")
    flag = pe.Flag("R1", "T-01", "Early", D("0.2335"), D("0.5"), "le", (hit,), None)
    body = {"triggers": {"T-01": {"label": LABEL, "unit": "%"}}}
    assert str(route._condition(flag, body)).endswith("(put side tested)")
    bare = pe.Flag("R1", "T-01", "Early", D("0.2335"), D("0.5"), "le", (), None)
    assert "tested" not in str(route._condition(bare, body))


# D-58 quote characters: the stored name and broker text carry NO quotes; the server adds one pair when it serves them
# (ADR-003: the user's own words are quoted word for word in a labelled field). The one place that removes the pair for
# display is the front end's plainName, so the server must not strip it too (that would break every other reader).
def test_stored_text_has_no_quotes_and_the_server_serves_exactly_one_pair():
    assert str(shown_name("Condor C3")) == '"Condor C3"'
    assert str(shown_broker("Zerodha")) == '"Zerodha"'
