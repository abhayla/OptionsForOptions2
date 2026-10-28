"""GC-UI D-B48 core proof (REQ-109 AC-2, AC-4; ADR-008): each tracked leg carries its own paper P&L from the one engine
(ofo.tracking.paper.paper_pnl on that single leg), and the legs' figures add up to the strategy's paper total exactly.

Real numbers: strategy 54's recorded tracking reply (2026-10-28 13:40 IST), NIFTY 3 Nov bull call spread, 65 a leg:
BUY 22600 CE entry 193.70, LTP 271.45; SELL 22800 CE entry 106.35, LTP 156.90; recorded total 1768.00 (unbooked).
By hand: BUY (271.45 - 193.70) x 65 = 77.75 x 65 = +5,053.75;
SELL (106.35 - 156.90) x 65 = -50.55 x 65 = -3,285.75; sum +1,768.00.
"""
from __future__ import annotations

import datetime
import json
import pathlib
from decimal import Decimal

import pytest
from ofo.engine.legs import Action, Instrument
from ofo.tracking import paper

D = Decimal
EXPIRY = datetime.date(2026, 11, 3)
AT = datetime.datetime(2026, 10, 28, 5, 59, 45, tzinfo=datetime.UTC)
S54 = [paper.TrackedLeg("NSE_FO:53720", Action.BUY, Instrument.CE, D("22600"), EXPIRY, 65, D("193.70"), AT),
       paper.TrackedLeg("NSE_FO:53794", Action.SELL, Instrument.CE, D("22800"), EXPIRY, 65, D("106.35"), AT)]
LTP = [D("271.45"), D("156.90")]
FUT = paper.TrackedLeg("NSE_FO:9", Action.SELL, Instrument.FUT, None, EXPIRY, 75, D("22700.00"), AT)


def test_core_strategy_54_each_leg_has_its_own_pnl_and_they_add_to_the_total():
    pnls = paper.leg_pnls(S54, dict(enumerate(LTP)), {})
    assert pnls == (D("5053.75"), D("-3285.75"))
    assert sum(pnls) == paper.paper_pnl(S54, LTP) == D("1768.00")


def test_core_the_exited_view_carries_the_same_figures():
    view = paper.tracking_view(None, S54, D("0.5"), [None, None], {0: D("271.45"), 1: D("156.90")})
    assert view.leg_pnls == (D("5053.75"), D("-3285.75")) and sum(view.leg_pnls) == view.paper_pnl


def test_one_exited_at_its_exit_price_and_one_open_still_sum_to_the_total():
    """BUY exited at 280.00 (booked +5,609.50, frozen), SELL still open at 156.90 (-3,285.75): total 2,323.75."""
    split = paper.pnl_split(S54, {1: LTP[1]}, {0: D("280.00")})
    pnls = paper.leg_pnls(S54, {1: LTP[1]}, {0: D("280.00")})
    assert pnls == (D("5609.50"), D("-3285.75"))
    assert sum(pnls) == split.total == D("2323.75")
    # the exited leg is never valued at the current price: 271.45 would give 5,053.75
    assert pnls[0] != paper.leg_pnl(S54[0], LTP[0])


def test_a_leg_with_no_live_price_has_no_figure_never_zero():
    assert paper.leg_pnls(S54, {0: LTP[0]}, {}) == (D("5053.75"), None)


def test_a_future_leg_is_valued_by_the_same_engine():
    """SELL 75 x FUT: (22700.00 - 22650.50) x 75 = +3,712.50."""
    assert paper.leg_pnls([FUT], {0: D("22650.50")}, {}) == (D("3712.50"),)


def test_a_leg_in_both_maps_or_unknown_is_refused():
    with pytest.raises(ValueError, match="once"):
        paper.leg_pnls(S54, {0: LTP[0]}, {0: D("1.00")})
    with pytest.raises(ValueError, match="leg"):
        paper.leg_pnls(S54, {5: LTP[0]}, {})


def test_recorded_reply_numbers_match_the_engine():
    path = pathlib.Path("D:/Abhay/scratch/gcui-checker/run1/tracking_54.json")
    if not path.exists():
        pytest.skip("recorded reply not on this machine")
    reply = json.loads(path.read_text(encoding="utf-8"))
    legs = reply["legs"]
    got = [paper.leg_pnl(S54[i], D(legs[i]["current_price"])) for i in range(2)]
    assert sum(got) == D(reply["paper_pnl"])


def test_leg_pnl_text_to_the_paisa_from_the_exact_figure_every_answer_state():
    """REQ-109 AC-2: the server's leg text is the exact pnl to the paisa, signed; zero has no sign (round 2)."""
    from ofo.errors.explanations import render_explanation

    def text(v):
        return render_explanation("summary_paisa_signed", amount=v)

    legs = paper.leg_pnls(S54, dict(enumerate(LTP)), {})
    assert [text(v) for v in legs] == ["+5,053.75", "−3,285.75"]
    assert text(D("0.00")) == "0.00" and text(D("-0.00")) == "0.00" and text(D("-0.004")) == "0.00"
    assert text(legs[0] + legs[1]) == "+1,768.00"  # the total reads in the same form as the legs
