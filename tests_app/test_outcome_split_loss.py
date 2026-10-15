"""W-066 resumed round (issue #172, REQ-034 AC-7, ADR-072): a loss split by a single zero point renders as one region
with an "except exactly" level, through the real outcome service on the 2026-10-08 replay. No database is needed.

Expected sentences are written by hand from the payoff, never from the code under test:
- #172 repro: P&L per unit = -|S-22400| + 2*max(|S-22400|-200, 0): 0 at 22,400, below zero on 22,000-22,400 and
  22,400-22,800, above zero beyond -> one bounded region 22,000-22,800 except exactly 22,400.
- sell 22400 CE and PE at 0, buy 2x 22600 CE at 0: P&L = -|S-22400| + 2*max(S-22600, 0); above 22,600 it is
  S - 22,800. Below zero everywhere below 22,800 except exactly 22,400, zero at 22,800, positive above -> "below
  22,800 (except exactly 22,400)".
- the same with both sold legs at 50 (100 received): P&L = 100 - |S-22400| + 2*max(S-22600, 0); above 22,600 it is S - 22,700.
  Crossings at 22,300, 22,500 and 22,700; below zero below 22,300 and on 22,500-22,700 (at 22,600: -100) -> "below
  22,300 or between 22,500 and 22,700"; no except level (every zero is a crossing into profit).
"""
from __future__ import annotations

import datetime
import pathlib
import sys
from decimal import Decimal

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tests_app"))

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay  # noqa: E402

from ofo.errors.explanations import ExplanationText  # noqa: E402
from ofo.marketdata.kite_provider import IST  # noqa: E402

VALUATION = datetime.datetime(2026, 10, 8, 9, 20, 9, tzinfo=IST)
RATE = Decimal("0.065")
# NIFTY 13-Oct-2026 contracts in tests/fixtures/kite_ws/instruments-2026-10-08-subscribed.csv
CE22400, PE22400, CE22600, PE22200 = "NSE_FO:44602", "NSE_FO:44604", "NSE_FO:44616", "NSE_FO:44595"


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def _outcome(provider, legs):
    from ofo_app.routes.outcome import MarketContext, OutcomeRequest, strategy_outcome

    body = [{"instrument_id": iid, "action": action, "lots": lots, "planned_entry": entry,
             "captured_at": VALUATION.isoformat()} for iid, action, lots, entry in legs]
    request = OutcomeRequest.model_validate({"underlying": "NIFTY", "legs": body, "ux_level": "standard"})
    return strategy_outcome(request, MarketContext(provider, lambda: VALUATION, RATE))


def test_ac7_the_172_repro_renders_one_bounded_region_with_one_excluded_level(replayed) -> None:
    """AC-7: the literal #172 repro answers "Where do I start losing?" with one bounded region except exactly 22,400."""
    out = _outcome(replayed, [(CE22400, "SELL", 1, "0"), (PE22400, "SELL", 1, "0"),
                              (CE22600, "BUY", 2, "0"), (PE22200, "BUY", 2, "0")])
    start = out.summary.where_do_i_start_losing
    assert type(start) is ExplanationText
    assert str(start) == "If NIFTY ends between 22,000 and 22,800 (except exactly 22,400) at expiry."


def test_ac7_an_unbounded_below_loss_split_at_one_strike_renders_below_with_except(replayed) -> None:
    """AC-7: an open-below loss split at 22,400 reads "below 22,800 (except exactly 22,400)"."""
    out = _outcome(replayed, [(CE22400, "SELL", 1, "0"), (PE22400, "SELL", 1, "0"), (CE22600, "BUY", 2, "0")])
    assert str(out.summary.where_do_i_start_losing) == (
        "If NIFTY ends below 22,800 (except exactly 22,400) at expiry.")


def test_ac7_shape_e_a_profit_gap_narrower_than_a_paisa_is_named_as_the_excluded_level(replayed) -> None:
    """AC-7 (W-066 round 8, verifier's shape E): SELL 12 lots CE22400 @0.05, BUY 1 lot CE22400 @0.55, SELL 11 lots
    PE22400 @0. Hand computation per lot of 65 units: at 22,400 every option expires worthless, P&L = 12*0.05*65 -
    0.55*65 = 39.00 - 35.75 = +3.25; either side the net slope is 11 lots, so the zeros sit 3.25 / (11*65) = 0.004545...
    points away. Both crossings round to 22,400.00, so the profit stretch is narrower than the display step: before
    round 8 the two loss regions were merged silently ("At every level at expiry.", false at 22,400). The sentence
    names 22,400 as the excluded level instead (ADR-072's except wording)."""
    out = _outcome(replayed, [(CE22400, "SELL", 12, "0.05"), (CE22400, "BUY", 1, "0.55"), (PE22400, "SELL", 11, "0")])
    assert str(out.summary.where_do_i_start_losing) == "At every level except exactly 22,400 at expiry."


def test_ac7_a_sub_paisa_stretch_with_one_exact_edge_still_reads_one_excluded_level(replayed) -> None:
    """AC-7 (round 8, mixed member): shape E with 10 lots of PE sold. Below 22,400 the slope is 10 lots, so the lower
    zero is 22,400 - 3.25/650 = 22,399.995 exactly (it terminates); above it is 22,400 + 3.25/715 = 22,400.0045...
    Both print as 22,400.00 at the 0.01 display step, so a plain list would read "below 22,400.00 or above 22,400"
    (two names for one level). The stretch is reported as the excluded level instead."""
    out = _outcome(replayed, [(CE22400, "SELL", 12, "0.05"), (CE22400, "BUY", 1, "0.55"), (PE22400, "SELL", 10, "0")])
    assert str(out.summary.where_do_i_start_losing) == "At every level except exactly 22,400 at expiry."


def test_ac7_two_regions_without_a_zero_point_keep_the_plain_list(replayed) -> None:
    """AC-7 (other branch): crossings into profit are region edges, never "except" levels."""
    out = _outcome(replayed, [(CE22400, "SELL", 1, "50"), (PE22400, "SELL", 1, "50"), (CE22600, "BUY", 2, "0")])
    assert str(out.summary.where_do_i_start_losing) == (
        "If NIFTY ends below 22,300 or between 22,500 and 22,700 at expiry.")
