"""REQ-050 AC-1/AC-3 core proof (issue #519, GC-MU step 1): 1,000 strategies holding the same NIFTY strike, fed the
recorded 2026-10-08 ticks in 3 price updates, run each engine function (IV solve, per-unit leg Greeks, parity forward)
exactly ONCE per update per contract - never once per strategy - and every strategy reads the same figures.

The ticks are the real recording (tests/fixtures/kite_ws), replayed in three slices: each slice is one price update
(a newer snapshot instant). Counts work, not time."""
import datetime
from collections import Counter
from decimal import Decimal

import ofo.outcome.snapshot as snapshot_module
import pytest
from _kite_fixture import all_instrument_ids, new_provider, recorded_frames
from ofo.engine.legs import Action
from ofo.marketdata.shared_compute import FeedScope, SharedCompute
from ofo.outcome import PlannedLeg, StrategyDefinition, build_outcome, read_snapshot, service

RATE = Decimal("0.065")
CE, PE = "NSE_FO:44614", "NSE_FO:44615"  # the 22550 CE and PE of the 2026-10-13 expiry
STRATEGIES = 1_000
UPDATES = 3
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
T0 = datetime.datetime(2026, 10, 8, 9, 20, tzinfo=IST)


def strategies():
    """1,000 different strategies, every one holding the 22550 PE: straddles and single legs, both sides, 1-5 lots,
    different entry prices - so nothing but the shared market figures is common to them."""
    out = []
    for n in range(STRATEGIES):
        lots, premium = 1 + n % 5, Decimal("90.00") + n % 37
        action = Action.SELL if n % 2 else Action.BUY
        ids = (CE, PE) if n % 3 else (PE,)
        out.append(StrategyDefinition("NIFTY", tuple(PlannedLeg(i, action, lots, premium, T0) for i in ids)))
    return out


@pytest.fixture
def engine_calls(monkeypatch):
    """Counting wrappers on the engine functions the outcome path calls; key = (function, contract)."""
    calls: Counter = Counter()
    real_iv, real_fwd, real_gk = service.implied_vol, snapshot_module.parity_forward, service.greeks_unrounded

    def iv(em, kind, price, strike):
        calls[("iv", kind.value, strike)] += 1
        return real_iv(em, kind, price, strike)

    def fwd(chain, spot, expiry, valuation, rate):
        calls[("forward", expiry)] += 1
        return real_fwd(chain, spot, expiry, valuation, rate)

    def gk(em, kind, strike, vol):
        calls[("greeks", kind.value, strike)] += 1
        return real_gk(em, kind, strike, vol)

    monkeypatch.setattr(service, "implied_vol", iv)
    monkeypatch.setattr(snapshot_module, "parity_forward", fwd)
    monkeypatch.setattr(service, "greeks_unrounded", gk)
    return calls


def test_core_1000_strategies_on_one_strike_compute_each_figure_once_per_price_update(engine_calls):
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    frames = recorded_frames()
    provider.on_connected(frames[0][0])
    cut = len(frames) // UPDATES
    scope = FeedScope(SharedCompute(), "user-1")
    defs = strategies()
    instants = []
    for update in range(UPDATES):
        for at, frame in frames[update * cut: (update + 1) * cut if update < UPDATES - 1 else None]:
            clock.now = at
            provider.on_frame(frame, at)
        engine_calls.clear()
        ivs = set()
        snap = None
        for definition in defs:
            snap = read_snapshot(provider, "NIFTY", [leg.instrument_id for leg in definition.legs], clock.now, RATE,
                                 scope)
            out = build_outcome(definition, snap, valuation=snap.valuation, shared=scope)
            ivs.add(next(leg.iv for leg in out.legs if leg.instrument_id == PE))
        instants.append(snap.valuation)
        # every engine function ran once per contract in this update, whatever the number of strategies
        assert engine_calls, "the outcome path computed nothing"
        assert set(engine_calls.values()) == {1}, engine_calls
        assert ("forward", datetime.date(2026, 10, 13)) in engine_calls
        assert ("iv", "PE", Decimal("22550")) in engine_calls and ("greeks", "PE", Decimal("22550")) in engine_calls
        assert len(ivs) == 1 and None not in ivs  # every strategy read the one IV of the shared strike
        print(f"update {update + 1} at {snap.valuation.isoformat()}: {sorted(engine_calls.items(), key=str)}")
    assert len(set(instants)) == UPDATES  # three distinct price updates (three snapshot instants)
