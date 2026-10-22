"""W-127 (REQ-083, REQ-084): the what-if block of ONE outcome reply, on the real 2026-10-08 09:20 frames (NIFTY 13-Oct
iron condor, spot 22,533.25, 65 per lot). Expected values come from the exact At Expiry formula written in
test_same_engine.py, the engine's own consistency (curve point == target figure), and the REQ-027 formula; nothing is
pasted from running the code under test.
"""
import dataclasses
import datetime
from decimal import Decimal

import pytest
from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from ofo.engine.legs import Instrument
from ofo.rules.inputs import DataHealth
from ofo.outcome import OutcomeState, build_outcome, read_snapshot
from ofo.outcome.serialize import outcome_to_dict
from ofo.scenario.whatif import WhatIfInput
from ofo.table import UXLevel
from outcome.test_same_engine import CONDOR, CURRENT, RATE, VALUATION, definition, formula_pnl

BREAKEVEN_COUNT = 2  # an iron condor has a lower and an upper breakeven


@pytest.fixture(scope="module")
def replayed():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    return provider


def build(provider, whatif=None, *, snapshot_edit=None):
    d = definition(provider)
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    if snapshot_edit is not None:
        snap = snapshot_edit(snap)
    out = build_outcome(d, snap, UXLevel.ADVANCED, VALUATION, whatif=whatif)
    assert out.state is OutcomeState.COMPUTED, out.reason
    return out


def test_req083_ac1_both_curves_come_from_one_reply_on_the_same_levels(replayed):
    """REQ-083 AC-1: the At Expiry points and the Estimated points are for the same levels, in one reply."""
    out = build(replayed)
    assert [lvl for lvl, _ in out.whatif.estimated_points] == [lvl for lvl, _ in out.payoff_points]
    assert out.whatif.estimated_available
    for level, pnl in out.payoff_points:  # the At Expiry curve is the exact formula (REQ-033 AC-1)
        assert pnl == formula_pnl(level, replayed)
    assert any(est != exp for (_, est), (_, exp) in zip(out.whatif.estimated_points, out.payoff_points, strict=True))


def test_req084_ac4_default_target_is_spot_now_and_the_figures_agree(replayed):
    """REQ-084 AC-4: with no input the target is the live spot at now; the target P&L is the engine's estimate at that
    level, equal to the curve point at the CURRENT column, and each breakeven is a sign change of the estimate."""
    w = build(replayed).whatif
    assert (w.target_level, w.target_time, w.iv_offset, w.clamp_notes) == (CURRENT, VALUATION, Decimal("0.0"), ())
    curve = dict(w.estimated_points)
    assert w.target_estimated_pnl == curve[CURRENT]
    assert w.target_expiry_pnl == formula_pnl(CURRENT, replayed)
    assert len(w.estimated_breakevens) == BREAKEVEN_COUNT
    lo, hi = w.estimated_breakevens
    points = w.estimated_points
    assert lo < CURRENT < hi
    below = [p for lvl, p in points if lvl < lo][-1]
    inside = next(p for lvl, p in points if lo < lvl < hi)
    assert below < 0 < inside


def test_req084_ac2_target_after_expiry_or_before_now_is_clamped_with_a_reason(replayed):
    """REQ-084 AC-2: a date after the first expiry gives the 15:30 IST close of 13 Oct; one before now gives now."""
    late = build(replayed, WhatIfInput(target_time=datetime.datetime(2027, 1, 1, tzinfo=VALUATION.tzinfo))).whatif
    assert late.target_time == datetime.datetime(2026, 10, 13, 15, 30, tzinfo=VALUATION.tzinfo) == late.time_max
    assert [str(n) for n in late.clamp_notes] == [
        "The target date was after the first expiry; the estimate is shown at that expiry's 15:30 IST close."]
    assert late.greeks is None and "not defined at the expiry close" in str(late.greeks_reason)
    early = build(replayed, WhatIfInput(target_time=VALUATION - datetime.timedelta(days=1))).whatif
    assert early.target_time == VALUATION and "before now" in str(early.clamp_notes[0])
    assert late.estimated_available  # at the close every leg is worth its expiry value
    assert late.target_estimated_pnl == formula_pnl(late.target_level, replayed)


def test_req084_ac3_an_iv_change_to_zero_is_refused_but_the_expiry_figure_stays(replayed):
    """REQ-084 AC-3 / AC-7: -100.0 points takes every IV to zero or below: no estimate, the reason, and the exact At
    Expiry P&L at the target level is still given."""
    w = build(replayed, WhatIfInput(target_level=Decimal("22600"), iv_offset=Decimal("-100.0"))).whatif
    assert not w.estimated_available and w.estimated_points == () and w.greeks is None
    assert "zero or below" in str(w.estimated_reason)
    assert w.target_expiry_pnl == formula_pnl(Decimal("22600"), replayed)


def test_req084_ac3_an_iv_offset_moves_the_curve(replayed):
    """REQ-084 AC-3 (red case): +5.0 points changes the Estimated curve and not the At Expiry curve."""
    base, up = build(replayed), build(replayed, WhatIfInput(iv_offset=Decimal("5.0")))
    assert up.payoff_points == base.payoff_points
    assert up.whatif.estimated_points != base.whatif.estimated_points


def test_req084_ac8_greeks_rows_sum_to_the_total_and_per_unit_is_total_over_lot(replayed):
    """REQ-084 AC-8: per-leg Greeks sum to the TOTAL (each rounded once: within 0.0001 per leg); per unit = per position
    / 65 (the NIFTY lot)."""
    g = build(replayed).whatif.greeks
    assert len(g.rows) == len(CONDOR)
    for name in ("delta", "gamma", "theta", "vega"):
        parts = sum(getattr(r.per_position, name) for r in g.rows)
        assert abs(parts - getattr(g.total_per_position, name)) <= Decimal("0.0001") * len(g.rows)
        assert abs(getattr(g.total_per_unit, name) * 65 - getattr(g.total_per_position, name)) <= Decimal("0.0033")
    # an iron condor: short options either side - negative gamma and positive theta
    assert g.total_per_position.gamma < 0 < g.total_per_position.theta


def test_req084_ac9_rupee_examples_are_the_engines_numbers(replayed):
    """REQ-084 AC-9: the delta example is the position delta x 10 points, the theta example is the position theta."""
    g = build(replayed).whatif.greeks
    by = {e.greek: str(e.sentence) for e in g.examples}
    assert by["delta"].startswith(f"Delta {g.total_per_position.delta}: if NIFTY rises 10 points, about Rs ")
    rupees = Decimal(by["delta"].split("about Rs ")[1].split(" ")[0])
    assert abs(rupees - g.total_per_position.delta * 10) <= Decimal("0.01")
    assert by["theta"].startswith(f"Theta {g.total_per_position.theta}: about Rs ")
    assert abs(Decimal(by["theta"].split("about Rs ")[1].split(" ")[0]) - g.total_per_position.theta) <= Decimal("0.01")
    assert by["vega"].endswith("(estimate).") and by["gamma"].endswith("(estimate).")


def test_req083_ac4_bands_are_symmetric_and_two_sd_is_twice_one_sd(replayed):
    """REQ-083 AC-4: -2SD -1SD 1SD 2SD around the live spot; 2 SD is twice 1 SD (REQ-027 formula, tested on its own
    numbers in test_whatif_core)."""
    w = build(replayed).whatif
    assert [b.label for b in w.bands] == ["-2SD", "-1SD", "1SD", "2SD"]
    m2, m1, p1, p2 = (b.level for b in w.bands)
    assert p1 - CURRENT == CURRENT - m1 > 0 and p2 - CURRENT == 2 * (p1 - CURRENT) == CURRENT - m2


def test_req083_ac4_no_atm_iv_means_no_bands_with_a_reason(replayed):
    """REQ-083 AC-4 (red case): with no option chain read there is no ATM IV: no bands, the reason."""
    w = build(replayed, snapshot_edit=lambda s: dataclasses.replace(s, chains={})).whatif
    assert w.bands == () and "no at-the-money implied volatility" in str(w.bands_reason)


def test_req083_ac5_oi_is_todays_chain_per_strike_for_the_expiry(replayed):
    """REQ-083 AC-5: one row per strike of the strategy's expiry, with the call and put OI of the quotes read."""
    out = build(replayed)
    w = out.whatif
    assert w.oi is not None and w.oi.expiry == datetime.date(2026, 10, 13)
    assert [s.strike for s in w.oi.strikes] == sorted({s.strike for s in w.oi.strikes})
    snap = read_snapshot(replayed, "NIFTY", [iid for iid, *_ in CONDOR], VALUATION, RATE)
    ce = {q.strike: q.oi for q in snap.chains[w.oi.expiry] if q.instrument_type is Instrument.CE}
    assert {s.strike: s.call_oi for s in w.oi.strikes if s.call_oi is not None} == {k: v for k, v in ce.items()
                                                                                    if v is not None}


def test_req083_ac6_missing_oi_is_a_message_never_zero_bars(replayed):
    """REQ-083 AC-6: when no quote carries OI there is no overlay and the reason; a strike without an OI figure is
    None, not 0."""
    def no_oi(snap):
        return dataclasses.replace(snap, chains={e: tuple(dataclasses.replace(q, oi=None, oi_change=None) for q in c)
                                                 for e, c in snap.chains.items()})
    w = build(replayed, snapshot_edit=no_oi).whatif
    assert w.oi is None and str(w.oi_reason) == "OI is not available for this expiry."

    def one_missing(snap):
        first = next(iter(snap.chains))
        chain = list(snap.chains[first])
        chain[0] = dataclasses.replace(chain[0], oi=None)
        return dataclasses.replace(snap, chains={**snap.chains, first: tuple(chain)})
    w2 = build(replayed, snapshot_edit=one_missing).whatif
    assert any(v is None for s in w2.oi.strikes for v in (s.call_oi, s.put_oi))
    assert w2.oi.stale is False


def test_req084_ac6_what_if_inputs_change_nothing_but_the_what_if_block(replayed):
    """REQ-084 AC-6: two different what-if inputs give identical legs, table, summary and At Expiry points; only the
    what-if block differs, and the planned definition is untouched."""
    d_before = definition(replayed)
    a = outcome_to_dict(build(replayed))
    b = outcome_to_dict(build(replayed, WhatIfInput(Decimal("22700"), VALUATION + datetime.timedelta(days=2),
                                                    Decimal("2.0"))))
    assert definition(replayed) == d_before
    for key in ("legs", "table", "summary", "payoff", "scenario", "margin"):
        assert a[key] == b[key]
    assert a["whatif"] != b["whatif"] and b["whatif"]["target_level"] == "22700.00"


def test_req084_ac3_iv_offset_must_be_a_step_of_a_tenth():
    """REQ-084 AC-3 (red case): an offset that is not in steps of 0.1 is refused at construction."""
    with pytest.raises(ValueError):
        WhatIfInput(iv_offset=Decimal("2.05"))
    with pytest.raises(ValueError):
        WhatIfInput(target_time=datetime.datetime(2026, 10, 9))


def test_req083_ac4_bands_follow_the_target_date_when_one_is_set(replayed):
    """REQ-083 AC-4: with a target date two days on, the horizon is 2 calendar days, so the bands are narrower than the
    default (to the 13 Oct expiry, 5 days): 1 SD x sqrt(5/2) apart, within the whole-point rounding."""
    full = build(replayed).whatif.bands
    short = build(replayed, WhatIfInput(target_time=VALUATION + datetime.timedelta(days=2))).whatif.bands
    one_full, one_short = full[2].level - CURRENT, short[2].level - CURRENT
    assert one_short < one_full and abs(one_short * Decimal(5).sqrt() - one_full * Decimal(2).sqrt()) <= Decimal(4)


def test_req084_ac1_a_target_level_outside_the_range_is_clamped_with_a_reason(replayed):
    """REQ-084 AC-1: the server sends its limits (the level set's start, end and step); a level beyond them is clamped
    to the nearest end and the screen is told."""
    out = build(replayed)
    w = build(replayed, WhatIfInput(target_level=out.level_set.end + 5000)).whatif
    assert (w.level_min, w.level_max, w.level_step) == (out.level_set.start, out.level_set.end, out.level_set.step)
    assert w.target_level == out.level_set.end
    assert str(w.clamp_notes[0]) == ("The target level was outside the range shown; "
                                     "the nearest end of the range is used.")
    below = build(replayed, WhatIfInput(target_level=out.level_set.start - 5000)).whatif
    assert below.target_level == out.level_set.start


def test_req083_ac3_a_leg_without_iv_gives_the_expiry_curve_only_with_the_reason(replayed):
    """REQ-083 AC-3 / REQ-084 AC-7: one option leg has no quote, so no IV: no Estimated curve and no Greeks, the reason
    is stated, and the exact At Expiry curve and the target-level At Expiry P&L are still there."""
    def drop_quote(snap):
        iid = CONDOR[0][0]
        return dataclasses.replace(snap, legs={**snap.legs, iid: dataclasses.replace(snap.legs[iid], quote=None)})
    out = build(replayed, snapshot_edit=drop_quote)
    w = out.whatif
    assert not w.estimated_available and w.estimated_points == () and w.greeks is None
    assert "no implied volatility" in str(w.estimated_reason) and w.greeks_reason == w.estimated_reason
    assert out.payoff_points and w.target_expiry_pnl == formula_pnl(w.target_level, replayed)


def test_req083_ac4_an_unhealthy_atm_quote_gives_no_bands(replayed):
    """REQ-083 AC-4 (red case): when the at-the-money call quote is UNHEALTHY there is no ATM IV: no bands, the reason;
    the same chain with a healthy quote gives four bands (test above)."""
    def sour_atm(snap):
        chain = snap.chains[next(iter(snap.chains))]
        atm = min({q.strike for q in chain}, key=lambda k: (abs(k - CURRENT), k))
        hit = lambda q: q.strike == atm and q.instrument_type is Instrument.CE  # noqa: E731
        sick = tuple(dataclasses.replace(q, health=DataHealth.UNHEALTHY) if hit(q)
                     else q for q in chain)
        return dataclasses.replace(snap, chains={**snap.chains, next(iter(snap.chains)): sick})
    w = build(replayed, snapshot_edit=sour_atm).whatif
    assert w.bands == () and "no at-the-money implied volatility" in str(w.bands_reason)
