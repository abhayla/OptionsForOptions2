"""REQ-077 AC-9 / AC-3 (W-149, row 21d): with no live data, a strategy whose EVERY leg has a planned entry shows its At
Expiry numbers from the ONE engine at those prices, labelled "From your prices - no live data"; nothing typed is shown
as a live price; a partly priced strategy keeps today's answer (ADR-085).

Hand-computed on the real 2026-10-08 NIFTY 13-Oct catalogue (lot 65): BUY 22800 CE at 81.30, SELL 23000 CE at 30.00.
Net debit (81.30 - 30.00) x 65 = Rs 3,334.50; max loss = the net debit; max profit (200 - 51.30) x 65 = Rs 9,665.50;
breakeven 22800 + 51.30 = 22,851.30. The level grid centres on the middle strike (the lower of two) 22,800.
"""
import dataclasses
from decimal import Decimal

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from ofo.engine.legs import Action
from ofo.errors.explanations import render_explanation
from ofo.outcome import (
    FROM_ENTRIES_LABEL,
    OutcomeState,
    PlannedLeg,
    StrategyDefinition,
    from_entries,
    not_connected,
    read_snapshot,
)
from ofo.scenario.views import View
from outcome.test_same_engine import RATE, VALUATION

LOW, HIGH = "NSE_FO:44624", "NSE_FO:44632"  # 22800 CE, 23000 CE (13-Oct)
LOT = 65
LABEL = "From your prices - no live data"


def _stored():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    snap = read_snapshot(provider, "NIFTY", [LOW, HIGH], VALUATION, RATE)
    return {iid: snap.legs[iid].contract for iid in (LOW, HIGH)}


def _spread(entry_low="81.30", entry_high="30.00"):
    legs = (PlannedLeg(LOW, Action.BUY, 1, None if entry_low is None else Decimal(entry_low), VALUATION),
            PlannedLeg(HIGH, Action.SELL, 1, None if entry_high is None else Decimal(entry_high), VALUATION))
    return StrategyDefinition("NIFTY", legs)


def _pnl(level):
    """REQ-033 AC-1 written out in Decimal: BUY (V - E) x Q, SELL (E - V) x Q, CE value max(L - K, 0)."""
    buy = (max(level - Decimal(22800), Decimal(0)) - Decimal("81.30")) * LOT
    sell = (Decimal("30.00") - max(level - Decimal(23000), Decimal(0))) * LOT
    return buy + sell


def test_core_bull_call_spread_from_your_prices_with_no_live_data():
    out = from_entries(_spread(), None, _stored(), VALUATION)
    assert out is not None and out.state is OutcomeState.FROM_ENTRIES
    assert out.status_label == LABEL == FROM_ENTRIES_LABEL and out.output_label == LABEL
    assert out.summary.max_loss == Decimal("3334.50")  # (81.30 - 30.00) x 65, the net debit
    assert out.summary.max_profit == Decimal("9665.50")  # (200 - 51.30) x 65
    assert out.summary.breakevens == (Decimal("22851.30"),)
    levels, totals = out.scenario.levels, out.scenario.totals
    assert out.scenario.available and len(levels) > len(totals) - 1 > 0
    assert list(totals) == [_pnl(level) for level in levels]  # every cell is the hand formula
    assert out.payoff_points == tuple(zip(levels, totals, strict=True))


def test_attack_1_nothing_is_a_live_price():
    out = from_entries(_spread(), None, _stored(), VALUATION)
    assert out.spot_level is None and out.spot_at is None
    assert out.table.spot_level is None and out.table.spot_at is None and out.table.output_label == LABEL
    assert all(leg.ltp is None and leg.iv is None and leg.health is None for leg in out.legs)
    assert [leg.planned_entry for leg in out.legs] == [Decimal("81.30"), Decimal("30.00")]
    assert not any(c.is_current for c in out.level_set.columns)  # the centre is not a market price
    assert not any("CURRENT" in c.markers for c in out.table.columns)
    live_ids = {"LTP", "CURRENT_VALUE", "UNREALIZED_PNL", "PNL_PERCENT", "IV", "DELTA", "GAMMA", "THETA", "VEGA"}
    for row in out.table.rows:  # no live column is filled in any row
        filled = [k.name for k, cell in row.cells.items()
                  if getattr(k, "name", None) in live_ids and cell.value is not None]
        assert filled == [], (row.row_id, filled)


def test_attack_2_a_leg_without_an_entry_keeps_todays_answer():
    d = _spread(entry_high=None)
    assert from_entries(d, None, _stored(), VALUATION) is None
    today = not_connected(d, None, _stored())
    assert today.state is OutcomeState.NOT_CONNECTED and today.table is None and today.summary is None


def test_attack_2b_an_unknown_contract_keeps_todays_answer():
    assert from_entries(_spread(), None, {}, VALUATION) is None


def test_attack_3_estimated_now_is_unavailable_with_its_reason():
    out = from_entries(_spread(), None, _stored(), VALUATION, view=View.ESTIMATED_NOW)
    assert out.state is OutcomeState.FROM_ENTRIES
    assert out.scenario.view is View.ESTIMATED_NOW and out.scenario.available is False
    assert out.scenario.totals is None and out.payoff_points == ()
    assert out.scenario.unavailable_reason == render_explanation("outcome_from_entries_no_estimate")
    assert out.summary.max_loss == Decimal("3334.50")  # the At Expiry summary is still the engine's


def test_attack_4_the_grid_centres_on_the_middle_strike_and_says_so():
    out = from_entries(_spread(), None, _stored(), VALUATION)
    assert out.centre_label == render_explanation("outcome_from_entries_centre", level=Decimal(22800))
    assert "22,800" in out.centre_label
    assert out.level_set.start < Decimal(22800) and out.level_set.end > Decimal(23000)
    assert Decimal(22800) in out.level_set.levels


def test_attack_5_sensex_uses_its_own_lot_size_and_step():
    stored = {iid: dataclasses.replace(
        c, contract=dataclasses.replace(c.contract, name="SENSEX", lot_size=20,
                                        strike=c.contract.strike + (Decimal(55200) if iid == LOW else Decimal(55300))))
              for iid, c in _stored().items()}  # SENSEX 78000 / 78300 strikes, lot 20 from the data
    d = StrategyDefinition("SENSEX", _spread().legs)
    out = from_entries(d, None, stored, VALUATION)
    assert out is not None and out.state is OutcomeState.FROM_ENTRIES
    assert [leg.lot_size for leg in out.legs] == [20, 20]
    width = stored[HIGH].contract.strike - stored[LOW].contract.strike
    assert out.summary.max_loss == Decimal("51.30") * 20
    assert out.summary.max_profit == (width - Decimal("51.30")) * 20
    assert out.level_set.step == Decimal(300)
