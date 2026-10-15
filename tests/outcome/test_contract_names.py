"""W-073 (ADR-086 item 1; REQ-035 AC-4): the not-connected and not-live answers name each leg's contract (symbol,
instrument, strike, expiry) from the same snapshot lookup the COMPUTED answer uses; a contract the catalogue does not
know keeps None, so the page's fixed wording stays. Real 2026-10-08 replay."""
import dataclasses

from ofo.outcome import OutcomeState, build_outcome, not_connected, not_live, read_snapshot
from ofo.outcome.snapshot import LegMarket

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from outcome.test_same_engine import RATE, VALUATION, definition

FIELDS = ("symbol", "instrument", "strike", "expiry")


def _setup():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    d = definition(provider)
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    return d, snap


def _unknown_first(snap, d):
    first = d.legs[0].instrument_id
    return first, dataclasses.replace(snap, legs={**snap.legs, first: LegMarket(first, None, None)})


def _names(out):
    return [tuple(getattr(leg, f) for f in FIELDS) for leg in out.legs]


def test_not_live_names_every_known_contract_like_the_computed_answer():
    d, snap = _setup()
    computed = build_outcome(d, snap)
    assert computed.state is OutcomeState.COMPUTED
    out = not_live(d, snap)
    assert _names(out) == _names(computed)
    assert all(symbol and instrument is not None and expiry is not None for symbol, instrument, _strike, expiry in _names(out))
    assert any(strike is not None for _s, _i, strike, _e in _names(out))  # an option leg carries its strike


def test_not_live_keeps_none_for_a_contract_the_catalogue_does_not_know():
    d, snap = _setup()
    first, snap = _unknown_first(snap, d)
    out = not_live(d, snap)
    assert _names(out)[0] == (None, None, None, None)
    assert all(None not in (n[0], n[1], n[3]) for n in _names(out)[1:])  # the others still named
    assert out.legs[0].instrument_id == first


def test_not_connected_after_a_session_ended_names_known_contracts_and_not_unknown_ones():
    d, snap = _setup()
    first, snap = _unknown_first(snap, d)
    ended = dataclasses.replace(snap, status=dataclasses.replace(snap.status, session_ended=True))
    out = build_outcome(d, ended)
    assert out.state is OutcomeState.NOT_CONNECTED
    assert _names(out)[0] == (None, None, None, None)
    assert all(None not in (n[0], n[1], n[3]) for n in _names(out)[1:])


def test_not_connected_with_no_snapshot_has_no_catalogue_to_ask_so_every_contract_is_none():
    d, _snap = _setup()
    out = not_connected(d)
    assert _names(out) == [(None, None, None, None)] * len(d.legs)


def test_each_leg_keeps_its_own_contract_when_the_snapshot_is_built_in_another_order():
    """MAJOR 2 (W-073 round 2): the lookup is by instrument id, never by position."""
    d, snap = _setup()
    reversed_snap = dataclasses.replace(snap, legs=dict(reversed(list(snap.legs.items()))))
    assert list(reversed_snap.legs) != list(snap.legs)
    computed = build_outcome(d, snap)
    for out in (not_live(d, reversed_snap), build_outcome(d, dataclasses.replace(
            reversed_snap, status=dataclasses.replace(reversed_snap.status, session_ended=True)))):
        assert [leg.instrument_id for leg in out.legs] == [p.instrument_id for p in d.legs]
        assert _names(out) == _names(computed)
    assert len({n[0] for n in _names(not_live(d, reversed_snap))}) == len(d.legs)  # four different symbols
