"""REQ-077 AC-9 / AC-3 (W-149, row 21d): with no live data, a strategy whose EVERY leg has a planned entry shows its At
Expiry numbers from the ONE engine at those prices, labelled "From your prices - no live data"; nothing typed is shown
as a live price; a partly priced strategy keeps today's answer (ADR-085).

Hand-computed (REQ-077 AC-3's own strikes) on the real 2026-10-08 NIFTY 13-Oct catalogue (lot 65): BUY 23000 CE at
81.30, SELL 23200 CE at 30.00. Net debit (81.30 - 30.00) x 65 = Rs 3,334.50; max loss = the net debit; max profit
(200 - 51.30) x 65 = Rs 9,665.50; breakeven 23000 + 51.30 = 23,051.30. The level grid centres on the middle strike (the
lower of two) 23,000.
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
    build_outcome,
    from_entries,
    not_connected,
    read_snapshot,
)
from ofo.scenario.views import View
from outcome.test_same_engine import RATE, VALUATION

LOW, HIGH = "NSE_FO:44632", "NSE_FO:44650"  # 23000 CE, 23200 CE (13-Oct)
LOT = 65
_EXTRA = ("NSE_FO:44624", "NSE_FO:44604", "NSE_FO:44595")  # 22800 CE, 22400 PE, 22200 PE (centre tests)
LABEL = "From your prices - no live data"


def _stored():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    snap = read_snapshot(provider, "NIFTY", [LOW, HIGH, *_EXTRA], VALUATION, RATE)
    return {iid: snap.legs[iid].contract for iid in (LOW, HIGH, *_EXTRA)}


def _spread(entry_low="81.30", entry_high="30.00"):
    legs = (PlannedLeg(LOW, Action.BUY, 1, None if entry_low is None else Decimal(entry_low), VALUATION),
            PlannedLeg(HIGH, Action.SELL, 1, None if entry_high is None else Decimal(entry_high), VALUATION))
    return StrategyDefinition("NIFTY", legs)


def _pnl(level):
    """REQ-033 AC-1 written out in Decimal: BUY (V - E) x Q, SELL (E - V) x Q, CE value max(L - K, 0)."""
    buy = (max(level - Decimal(23000), Decimal(0)) - Decimal("81.30")) * LOT
    sell = (Decimal("30.00") - max(level - Decimal(23200), Decimal(0))) * LOT
    return buy + sell


def test_core_bull_call_spread_from_your_prices_with_no_live_data():
    out = from_entries(_spread(), None, _stored(), VALUATION)
    assert out is not None and out.state is OutcomeState.FROM_ENTRIES
    assert out.status_label == LABEL == FROM_ENTRIES_LABEL and out.output_label == LABEL
    assert out.summary.max_loss == Decimal("3334.50")  # (81.30 - 30.00) x 65, the net debit
    assert out.summary.max_profit == Decimal("9665.50")  # (200 - 51.30) x 65
    assert out.summary.breakevens == (Decimal("23051.30"),)
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
    assert out.centre_label == render_explanation("outcome_from_entries_centre", level=Decimal(23000))
    assert "23,000" in out.centre_label
    assert out.level_set.start < Decimal(23000) and out.level_set.end > Decimal(23200)
    assert Decimal(23000) in out.level_set.levels


def test_attack_5_sensex_uses_its_own_lot_size_and_step():
    stored = {iid: dataclasses.replace(
        c, contract=dataclasses.replace(c.contract, name="SENSEX", lot_size=20,
                                        strike=c.contract.strike + (Decimal(55000) if iid == LOW else Decimal(55100))))
              for iid, c in _stored().items()}  # SENSEX 78000 / 78300 strikes, lot 20 from the data
    d = StrategyDefinition("SENSEX", _spread().legs)
    out = from_entries(d, None, stored, VALUATION)
    assert out is not None and out.state is OutcomeState.FROM_ENTRIES
    assert [leg.lot_size for leg in out.legs] == [20, 20]
    width = stored[HIGH].contract.strike - stored[LOW].contract.strike
    assert out.summary.max_loss == Decimal("51.30") * 20
    assert out.summary.max_profit == (width - Decimal("51.30")) * 20
    assert out.level_set.step == Decimal(300)


def _snapshot_after_drop():
    """The replay's last frame (09:20:09 IST) held, then every subscription ended: the feed has dropped."""
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return read_snapshot(provider, "NIFTY", [LOW, HIGH], VALUATION, RATE)


def test_attack_6_dropped_feed_status_is_ac5_message_and_output_label_is_from_your_prices():
    """REQ-049 AC-5 and REQ-077 AC-9 both hold: a snapshot that held quotes gives status_label = AC-5's message with the
    newest time held; output_label stays the from-your-prices label; still no live value."""
    snap = _snapshot_after_drop()
    out = from_entries(_spread(), snap, None, VALUATION)
    assert out is not None and out.state is OutcomeState.FROM_ENTRIES
    assert out.status_label.startswith("Live market data disconnected. Last updated: ")
    assert out.status_label.endswith(". Live strategy monitoring is paused.")
    assert out.output_label == LABEL and out.table.output_label == LABEL
    assert out.spot_level is None and all(leg.ltp is None for leg in out.legs)
    assert out.summary.max_loss == Decimal("3334.50")


def test_attack_6b_a_leg_without_an_entry_keeps_not_live_exactly_with_a_dropped_snapshot():
    snap = _snapshot_after_drop()
    assert from_entries(_spread(entry_high=None), snap, None, VALUATION) is None


def _legs(*specs):
    return StrategyDefinition("NIFTY", tuple(PlannedLeg(iid, action, 1, Decimal(entry), VALUATION)
                                              for iid, action, entry in specs))


def _centre(definition):
    out = from_entries(definition, None, _stored(), VALUATION)
    assert out is not None and out.state is OutcomeState.FROM_ENTRIES
    return out


def test_centre_is_the_lower_middle_strike_whatever_the_leg_order():
    """Two strikes, in BOTH orders: 23000 is the centre; a rule taking the first (or last) leg's strike fails one."""
    for specs in ((("NSE_FO:44632", Action.BUY, "81.30"), ("NSE_FO:44650", Action.SELL, "30.00")),
                  (("NSE_FO:44650", Action.SELL, "30.00"), ("NSE_FO:44632", Action.BUY, "81.30"))):
        out = _centre(_legs(*specs))
        assert out.centre_label == render_explanation("outcome_from_entries_centre", level=Decimal(23000))
        assert "23,000" in out.centre_label and Decimal(23000) in out.level_set.levels


def test_centre_of_three_legs_is_the_middle_strike_not_first_or_last():
    """Strikes 22800 / 23000 / 23200 given scrambled (23200 first or 22800 first, 23000 always in between)."""
    for specs in ((("NSE_FO:44650", Action.SELL, "30.00"), ("NSE_FO:44632", Action.BUY, "81.30"),
                   ("NSE_FO:44624", Action.SELL, "120.00")),
                  (("NSE_FO:44624", Action.SELL, "120.00"), ("NSE_FO:44632", Action.BUY, "81.30"),
                   ("NSE_FO:44650", Action.SELL, "30.00"))):
        out = _centre(_legs(*specs))
        assert out.centre_label == render_explanation("outcome_from_entries_centre", level=Decimal(23000))
        assert Decimal(23000) in out.level_set.levels


def test_centre_of_four_legs_is_the_lower_of_the_two_middle_strikes():
    """Strikes 22200 / 22400 / 22800 / 23000: the middle two are 22400 and 22800, the centre is 22400 (the lower, as
    decided). Given as 23000, 22200, 22800, 22400, so neither first nor last nor len//2 of the sorted list is it."""
    out = _centre(_legs(("NSE_FO:44632", Action.SELL, "81.30"), ("NSE_FO:44595", Action.BUY, "20.00"),
                        ("NSE_FO:44624", Action.SELL, "120.00"), ("NSE_FO:44604", Action.BUY, "40.00")))
    assert out.centre_label == render_explanation("outcome_from_entries_centre", level=Decimal(22400))
    assert "22,400" in out.centre_label and Decimal(22400) in out.level_set.levels


def test_never_held_status_is_from_your_prices_and_dropped_status_is_ac5_text():
    """No quote ever held: nothing dropped, so the status is the from-your-prices text, not the draft not-connected
    label. A quote held then lost: REQ-049 AC-5's message. The two must differ."""
    provider, _clock, _items = new_provider()
    fresh = read_snapshot(provider, "NIFTY", [LOW, HIGH], VALUATION, RATE)
    never = from_entries(_spread(), fresh, _stored(), VALUATION)
    assert never.status_label == LABEL == FROM_ENTRIES_LABEL
    assert never.status_label != render_explanation("outcome_not_connected")
    dropped = from_entries(_spread(), _snapshot_after_drop(), None, VALUATION)
    assert dropped.status_label.startswith("Live market data disconnected. Last updated: ")
    assert dropped.status_label != never.status_label and dropped.output_label == never.output_label == LABEL


def _ended(snap):
    return dataclasses.replace(snap, status=dataclasses.replace(snap.status, session_ended=True))


def test_an_ended_session_with_every_leg_priced_is_from_entries_never_not_connected():
    """REQ-077 AC-9 "with no live data" includes a Kite session that ended while the provider is up: the same answer as
    a dropped feed (AC-5's message, from-your-prices output label), the engine's numbers, no live value."""
    out = build_outcome(_spread(), _ended(_snapshot_after_drop()), VALUATION)
    assert out.state is OutcomeState.FROM_ENTRIES
    assert out.status_label.startswith("Live market data disconnected. Last updated: ")
    assert out.output_label == out.table.output_label == LABEL
    assert out.summary.max_loss == Decimal("3334.50") and out.summary.max_profit == Decimal("9665.50")
    assert out.spot_level is None and all(leg.ltp is None for leg in out.legs)


def test_an_ended_session_that_never_held_a_quote_says_from_your_prices():
    provider, _clock, _items = new_provider()
    stored = _stored()
    fresh = read_snapshot(provider, "NIFTY", [LOW, HIGH], VALUATION, RATE)
    ended = _ended(dataclasses.replace(fresh, legs={
        iid: dataclasses.replace(lm, contract=stored[iid]) for iid, lm in fresh.legs.items()}))
    out = build_outcome(_spread(), ended, VALUATION)
    assert out.state is OutcomeState.FROM_ENTRIES and out.status_label == LABEL == out.output_label


def test_an_ended_session_with_a_leg_without_an_entry_keeps_not_connected():
    out = build_outcome(_spread(entry_high=None), _ended(_snapshot_after_drop()), VALUATION)
    assert out.state is OutcomeState.NOT_CONNECTED and out.table is None and out.summary is None
