"""W-065 / issue #206: ``not_live`` - the live market is connected but this strategy's inputs are not streaming.
ADR-068 (2): the REST fallback is "labelled as not live"; REQ-049 AC-4: no old number is presented as live; REQ-049 AC-5:
"When live data drops ... 'Live market data disconnected. Last updated: <time>. Live strategy monitoring is paused.'" -
only when a quote was held and then lost; ADR-020 Q185: "Draft — Live data not connected" when nothing was ever held.
Real 2026-10-08 replay."""
import dataclasses
import datetime

from ofo.errors.explanations import render_explanation
from ofo.outcome import NOT_CONNECTED_LABEL, OutcomeState, build_outcome, not_live, read_snapshot
from ofo.rules.inputs import DataHealth
from ofo.table import UXLevel

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from outcome.test_same_engine import RATE, VALUATION, definition


def _snap():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    d = definition(provider)
    return d, read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)


def _never_held(snap):
    return dataclasses.replace(snap, spot=None, legs={k: dataclasses.replace(v, quote=None)
                                                      for k, v in snap.legs.items()})


def test_ac4_not_live_after_quotes_were_held_shows_ac5_with_the_newest_held_time():
    """AC-4: quotes were held, then the inputs stopped streaming -> state NOT_CONNECTED, REQ-049 AC-5's message stamped
    with the newest quote time held (spot or a leg; never the request time), the same label on every leg, no
    LTP/IV/health/table/summary, no reason text, the planned entry kept."""
    d, snap = _snap()
    newest = max([snap.spot.timestamp] + [lm.quote.timestamp for lm in snap.legs.values()])
    snap = dataclasses.replace(snap, valuation=newest + datetime.timedelta(minutes=7))  # asked 7 min after the last tick
    assert render_explanation("outcome_feed_disconnected", time=snap.valuation) != render_explanation(
        "outcome_feed_disconnected", time=newest)  # so a request-time stamp would fail the assertion below
    expected = render_explanation("outcome_feed_disconnected", time=newest)
    out = not_live(d, snap, UXLevel.ADVANCED)
    assert out.state is OutcomeState.NOT_CONNECTED and out.ux_level is UXLevel.ADVANCED
    assert out.status_label == expected and out.reason is None
    assert all(leg.label == expected and leg.ltp is None and leg.iv is None and leg.health is None for leg in out.legs)
    assert [leg.planned_entry for leg in out.legs] == [p.planned_entry for p in d.legs]
    assert out.table is None and out.summary is None and out.spot_level is None


def test_ac4_not_live_with_no_quote_ever_held_is_the_q185_draft_label():
    """AC-4 red branch: nothing was ever received for any input -> no "Last updated" claim at all; the label is ADR-020
    Q185's draft label (catalogue `outcome_not_connected`) on the state and on every leg."""
    d, snap = _snap()
    out = not_live(d, _never_held(snap))
    assert out.status_label == NOT_CONNECTED_LABEL
    assert "Last updated" not in out.status_label
    assert all(leg.label == NOT_CONNECTED_LABEL for leg in out.legs)


def test_ac4_feed_message_with_no_quote_ever_held_is_the_q185_draft_label():
    """AC-4: build_outcome's feed-not-live message follows the same rule - with the feed not live and no quote ever
    held, the label is Q185's draft label, not AC-5's "Last updated: <request time>"."""
    d, snap = _snap()
    down = dataclasses.replace(_never_held(snap), status=dataclasses.replace(snap.status, health=DataHealth.UNAVAILABLE))
    out = build_outcome(d, down)
    assert out.status_label is not None
    assert NOT_CONNECTED_LABEL in (out.status_label, *getattr(out.status_label, "parts", ()))  or \
        str(NOT_CONNECTED_LABEL) in str(out.status_label)
    assert "Last updated" not in str(out.status_label)
