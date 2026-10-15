"""W-065 / issue #206: ``not_live`` - the live market is connected but this strategy's inputs are not streaming.
ADR-068 (2): the REST fallback is "labelled as not live"; REQ-049 AC-4: no old number is presented as live; REQ-049 AC-5:
the message is "Live market data disconnected. Last updated: <time>. Live strategy monitoring is paused." Real
2026-10-08 replay."""
import dataclasses

from ofo.errors.explanations import render_explanation
from ofo.outcome import OutcomeState, not_live, read_snapshot
from ofo.table import UXLevel

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from outcome.test_same_engine import RATE, VALUATION, definition


def _snap():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    d = definition(provider)
    return d, read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)


def test_ac4_not_live_shows_no_number_and_the_ac5_message_with_the_newest_input_time():
    """AC-4: state NOT_CONNECTED, REQ-049 AC-5's message stamped with the newest quote time held (spot or a leg), the
    same label on every leg, no LTP/IV/health/table/summary, no reason text, the planned entry kept."""
    d, snap = _snap()
    newest = max([snap.spot.timestamp] + [lm.quote.timestamp for lm in snap.legs.values()])
    expected = render_explanation("outcome_feed_disconnected", time=newest)
    out = not_live(d, snap, UXLevel.ADVANCED)
    assert out.state is OutcomeState.NOT_CONNECTED and out.ux_level is UXLevel.ADVANCED
    assert out.status_label == expected and out.reason is None
    assert all(leg.label == expected and leg.ltp is None and leg.iv is None and leg.health is None for leg in out.legs)
    assert [leg.planned_entry for leg in out.legs] == [p.planned_entry for p in d.legs]
    assert out.table is None and out.summary is None and out.spot_level is None


def test_ac4_not_live_with_no_quote_held_stamps_the_valuation_time():
    """AC-4 red branch: nothing was ever received for any input -> the time is the snapshot's valuation time (the same
    fallback as the feed-dropped message in build_outcome)."""
    d, snap = _snap()
    empty = dataclasses.replace(snap, spot=None, legs={k: dataclasses.replace(v, quote=None) for k, v in snap.legs.items()})
    assert not_live(d, empty).status_label == render_explanation("outcome_feed_disconnected", time=snap.valuation)
