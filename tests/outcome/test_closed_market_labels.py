"""User test U8 (ADR-200 (2)): a closed market's held last close carries no "stale since" on ANY labelled output (every
curve, the payoff table, the target); in market hours the stale label stays (REQ-072 AC-2)."""
import dataclasses
import datetime
from decimal import Decimal

import pytest

from ofo.marketdata.forward import FALLBACK_LABEL, spot_fallback_forward
from ofo.outcome import OutcomeState, build_outcome, read_snapshot
from ofo.outcome.serialize import outcome_to_dict
from ofo.outcome.target import TargetAsk
from ofo.rules.inputs import DataHealth

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from outcome.test_same_engine import RATE, VALUATION, definition

EXPIRY = datetime.date(2026, 10, 13)
STALE = "stale since"


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def _stale_snapshot(provider, *, closed):
    d = definition(provider)
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    spot = dataclasses.replace(snap.spot, health=DataHealth.STALE)
    fwd = spot_fallback_forward(EXPIRY, spot.ltp, spot.timestamp, VALUATION, RATE, spot_health=DataHealth.STALE)
    return d, dataclasses.replace(snap, spot=spot, forwards={EXPIRY: fwd}, market_closed=closed)


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(node, (list, tuple)):
        for v in node:
            yield from _strings(v)


def _answer(provider, closed):
    d, snap = _stale_snapshot(provider, closed=closed)
    target = TargetAsk(level=snap.spot.ltp + Decimal(100))
    return build_outcome(d, snap, both_views=True, payoff_step=Decimal(50), target=target)


def test_closed_market_has_no_stale_since_on_any_output(replayed):
    out = _answer(replayed, closed=True)
    assert out.state is OutcomeState.COMPUTED
    assert [s for s in _strings(outcome_to_dict(out)) if STALE in s] == []
    assert out.output_label == FALLBACK_LABEL  # "estimated from spot" is kept
    for values in (out.scenario, out.other_view, *out.curves, out.payoff_table, out.target):
        label = getattr(values, "output_label", None)
        assert STALE not in (label or "")


def test_market_hours_stale_still_says_stale_since(replayed):
    out = _answer(replayed, closed=False)
    assert out.state is OutcomeState.COMPUTED
    assert out.output_label.startswith(STALE)
    assert out.scenario.output_label.startswith(STALE)
    assert any(STALE in s for s in _strings(outcome_to_dict(out)))
