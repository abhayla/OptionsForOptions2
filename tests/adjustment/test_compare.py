# ruff: noqa: PLR2004 - exact expected amounts are the assertions
"""REQ-156 AC-1..AC-4 at data level: the approach compare's criteria, leaders, leads and curves.

Expected values never come from the code under test: max loss / max profit / breakevens and booked P&L are the
scenario library's hand values (``expected.approach_after``, the generator's intrinsic-value path), spot-move P&L is
``adjust_scenarios_gen.hand_pnl_at`` (intrinsic at spot x (1 + p)) less the stated charge lines, premium left and
credit are sums over the scenario's own chain rows and hand trades, and every leader is the hand ranking of those.
"""
from __future__ import annotations

import datetime
import itertools
import json
import re
from dataclasses import replace
from decimal import Decimal as D
from fractions import Fraction
from pathlib import Path

import adjust_scenarios_gen as gen
import pytest
from ofo.adjustment.approaches import APPROACH_IDS, ChainRow, Position, PositionLeg, build_approach, load_config
from ofo.adjustment.compare import (
    MOVES,
    Cell,
    Column,
    Context,
    MarginRead,
    column_order,
    compare,
    leaders,
)
from ofo.engine.black_scholes import Greeks
from ofo.engine.legs import Action, Instrument, Leg
from ofo.engine.strategy import Strategy
from ofo.engine.whole_trade import whole_trade_after
from ofo.errors.explanations import (
    ADJUSTMENT_CRITERION_LABEL_TEXT,
    ADJUSTMENT_LEADER_LABEL_TEXT,
    render_explanation,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "adjust_scenarios"
CFG = load_config()
PAID, ADJ, EXIT = D("150.25"), D("92.40"), D("60.10")  # stated charge lines (each subtracted once)
FORBIDDEN = re.compile(r"\b(best|winner|rank\w*|score\w*|better)\b", re.IGNORECASE)


def load(sid: str) -> dict:
    return json.loads((FIX / f"{sid}.json").read_text(encoding="utf-8"))


def _d(v: object) -> D | None:
    return None if v is None else D(str(v))


def inputs(sc: dict) -> tuple[Position, list[ChainRow], D]:
    expiry = sc["expiry"]
    rows = [ChainRow(D(r["strike"]), r["type"], datetime.date.fromisoformat(c["expiry"]), r["tradingsymbol"],
                     _d(r["ltp"]), _d(r["bid"]), _d(r["ask"]), _d(r["delta"]), r["listed"], r["tradable"],
                     r["low_oi"]["state"], r["low_oi"]["blocked"])
            for c in sc["market"]["chains"] if c["expiry"] == expiry for r in c["rows"]]
    legs = tuple(PositionLeg(x["side"], x["type"], D(x["strike"]), datetime.date.fromisoformat(x["expiry"]), x["lots"],
                             D(x["entry"]), x["tradingsymbol"]) for x in sc["position"]["legs"])
    today = datetime.date.fromisoformat(sc["clock"]["ist"][:10])
    return Position(sc["underlying"], sc["lot"], sc["expiry_kind"], today, legs), rows, D(sc["market"]["spot"])


def greeks_of(sc: dict) -> dict[str, Greeks]:
    """Per-unit Greeks from the scenario rows (delta, gamma stated; theta / vega 0 so those rows tie)."""
    return {r["tradingsymbol"]: Greeks(D(r["delta"]), D(r["gamma"]), D(0), D(0))
            for c in sc["market"]["chains"] for r in c["rows"] if r["delta"] is not None and r["gamma"] is not None}


def build_columns(sid: str, margins: dict[str, D] | None = None, pop_on: bool = False):
    sc = load(sid)
    position, chain, spot = inputs(sc)
    cols = []
    for a in APPROACH_IDS:
        built = build_approach(position, chain, spot, a, CFG)
        if built.refusal is not None:
            continue
        booked = D(sc["expected"]["approach_after"][a]["booked_pnl"])
        strategy = Strategy(tuple(Leg(Action(x.side), Instrument(x.type), x.strike, x.expiry, x.lots * position.lot,
                                      x.entry) for x in built.after)) if built.after else None
        whole = whole_trade_after(strategy, booked_pnl=booked, paid_charges=PAID,
                                  adjustment_charges=ADJ if built.trades else D(0),
                                  open_exit_charges=EXIT if built.after else D(0))
        value = (margins or {}).get(a)
        cols.append(Column(built, whole, None, True, MarginRead(value, None if value is not None else
                                                                 render_explanation("adjust_margin_empty"))))
    ctx = Context(position, spot, chain, None, pop_on, MarginRead(D("100000")), greeks_of(sc),
                  sc["position"]["adjustments_used"])
    return sc, cols, ctx


def total(sc: dict, a: str) -> D:
    legs = sc["expected"]["approach_legs"][a]
    return PAID + (ADJ if legs["trades"] else 0) + (EXIT if legs["after"] else 0)


def row(cmp, rid: str):
    return next(c for c in cmp.criteria if c.id == rid)


def hand_leaders(values: dict[str, D | None], high: bool) -> tuple[str, ...]:
    ok = {k: v for k, v in values.items() if v is not None}
    best = max(ok.values()) if high else min(ok.values())
    return tuple(k for k in values if ok.get(k) == best)


def chain_rows(sc: dict) -> dict[str, dict]:
    return {r["tradingsymbol"]: r for c in sc["market"]["chains"] for r in c["rows"]}


@pytest.mark.parametrize("sid", ["ADJ-02", "ADJ-13"])
def test_core_every_criterion_has_a_value_or_reason_and_money_equals_the_hand_values(sid):
    """AC-2 (core proof): every AC-2 criterion has a value or "-" with a reason for each approach; max loss, max
    profit, spot moves, premium left and credit equal the hand computation to the paisa; leaders match the hand
    ranking."""
    sc, cols, ctx = build_columns(sid)
    cmp = compare(cols, ctx)
    ids = [c.built.id for c in cols]
    assert [c.id for c in cmp.criteria] == list(ADJUSTMENT_CRITERION_LABEL_TEXT)
    for crit in cmp.criteria:
        assert list(crit.values) == column_order(ids)
        for cell in crit.values.values():
            assert (cell.value is not None or cell.text == "Unlimited" or cell.unavailable_reason is not None
                    or cell.rank is not None), (crit.id, cell)
            if cell.text == "-":
                assert cell.unavailable_reason, crit.id
    after, legs = sc["expected"]["approach_after"], sc["expected"]["approach_legs"]
    spot = Fraction(sc["market"]["spot"])
    rows = chain_rows(sc)
    hand: dict[str, dict[str, D]] = {r: {} for r in ("max_loss", "max_profit", "premium_left", "credit", *MOVES)}
    for a in ids:
        hand["max_loss"][a] = D(after[a]["max_loss"]) + total(sc, a)
        hand["max_profit"][a] = D(after[a]["max_profit"]) - total(sc, a)
        hand["credit"][a] = sum((D(t["price"]) * t["quantity"] * (1 if t["action"] == "SELL" else -1)
                                 for t in legs[a]["trades"]), D(0))
        hand["premium_left"][a] = sum((-gen.sign(x["side"]) * x["quantity"] * D(rows[x["tradingsymbol"]]["ltp"])
                                       for x in legs[a]["after"]), D(0))
        for rid, p in MOVES.items():
            level = spot * (1 + Fraction(p))
            pnl = gen.hand_pnl_at(legs[a]["after"], Fraction(after[a]["booked_pnl"]), level)
            hand[rid][a] = D(pnl.numerator) / D(pnl.denominator) - total(sc, a)
    for rid, values in hand.items():
        crit = row(cmp, rid)
        assert {a: crit.values[a].value for a in ids} == values, rid
        high = rid not in ("max_loss",)
        assert crit.leaders == hand_leaders(values, high), rid
    if sid == "ADJ-02":  # the scenario's own stated premium left of the current legs
        assert row(cmp, "premium_left").values["A-36"].value == D(sc["expected"]["premium_left"])
    delta = row(cmp, "delta")
    for a in ids:
        want = sum((gen.sign(x["side"]) * x["quantity"] * D(rows[x["tradingsymbol"]]["delta"])
                    for x in legs[a]["after"]), D(0))
        assert delta.values[a].value == want.quantize(D("0.0001")), a


def test_ac2_breakevens_and_margin_change_and_adjustments_rows():
    """AC-2: breakevens show the hand levels with the profit range; margin change = After - current; adjustments
    used +1 when the approach trades, with no plan maximum set."""
    sc, cols, ctx = build_columns("ADJ-02", margins={"A-36": D("100000"), "A-01": D("98000.50"),
                                                     "A-05": D("103000"), "A-31": D(0)})
    cmp = compare(cols, ctx)
    be = row(cmp, "breakevens")
    legs, after = sc["expected"]["approach_legs"], sc["expected"]["approach_after"]
    for a in ("A-36", "A-01", "A-11"):  # hand zeros of the intrinsic payoff less the charges, between strikes
        def pnl(x, a=a):
            return gen.hand_pnl_at(legs[a]["after"], Fraction(after[a]["booked_pnl"]), x) - Fraction(total(sc, a))
        points = sorted({Fraction(x["strike"]) for x in legs[a]["after"]})
        zeros = []
        for lo, hi in itertools.pairwise(points):
            if (pnl(lo) < 0) != (pnl(hi) < 0):
                z = lo + (hi - lo) * pnl(lo) / (pnl(lo) - pnl(hi))
                zeros.append((D(z.numerator) / D(z.denominator)).quantize(D("0.01")))
        assert len(zeros) == 2, a
        cell = be.values[a]
        assert cell.text.startswith(f"{zeros[0]}/{zeros[1]} (profit range ") and cell.value == zeros[1] - zeros[0]
    assert be.leaders == hand_leaders({a: be.values[a].value for a in be.values}, True)
    assert be.values["A-31"].text == "No breakeven: a loss at every level" and be.values["A-31"].value == 0
    mc = row(cmp, "margin_change")
    assert mc.values["A-36"].value == D(0) and mc.values["A-01"].value == D("-1999.50")
    assert mc.values["A-31"].value == D("-100000") and mc.leaders == ("A-31",)
    a29 = mc.values["A-29"]
    assert a29.text == "-" and "Zerodha answered without a margin figure" in a29.unavailable_reason
    adj = row(cmp, "adjustments")
    assert adj.values["A-36"].text == "0 used; no plan maximum set" and adj.values["A-05"].value == 1
    assert adj.leaders == ("A-36",)


def test_ac3_pop_held_every_value_dash_no_leader():
    """AC-3 / attack 2: POP held (switch off) -> every POP value "-" with the held reason, no leader."""
    _, cols, ctx = build_columns("ADJ-02", pop_on=False)
    pop = row(compare(cols, ctx), "pop")
    assert pop.leaders == ()
    assert all(c.text == "-" and c.unavailable_reason == render_explanation("adjust_pop_held")
               for c in pop.values.values())


def test_ac3_tie_names_every_leader():
    """AC-3 / attack 1: two approaches with exactly equal max loss are both named leaders."""
    _, cols, ctx = build_columns("ADJ-02")
    same = replace(cols[0], built=replace(cols[0].built, id="A-01"))  # the No change answer under a second id
    crit = row(compare([cols[0], same], ctx), "max_loss")
    assert crit.values["A-36"].value == crit.values["A-01"].value
    assert crit.leaders == ("A-36", "A-01")


def test_ac3_unavailable_cannot_lead_and_row_nobody_computes_has_no_leader():
    """AC-3: a rankless cell never leads even when its shown value would; a row of only dashes has no leader."""
    dash = Cell(render_explanation("adjust_cmp_dash"), None, render_explanation("adjust_pop_held"), None)
    low = Cell(render_explanation("adjust_cmp_value", value=D(1)), D(1), None, D(1))
    hidden = Cell(render_explanation("adjust_cmp_value", value=D(0)), D(0), None, None)  # e.g. "Unlimited"
    assert leaders({"A-36": low, "A-01": hidden, "A-05": dash}, "low") == ("A-36",)
    assert leaders({"A-36": dash, "A-01": dash}, "high") == ()
    assert leaders({"A-36": low, "A-01": low}, "high") == ("A-36", "A-01")


def test_ac3_unlimited_max_loss_shown_and_cannot_lead():
    """Attack 4: an After with a naked short call -> max loss "Unlimited", never the "Smallest max loss" leader."""
    _, cols, ctx = build_columns("ADJ-02")
    base = cols[0]
    naked = tuple(x for x in base.built.after if not (x.type == "CE" and x.side == "BUY"))
    strategy = Strategy(tuple(Leg(Action(x.side), Instrument(x.type), x.strike, x.expiry, x.lots * 65, x.entry)
                              for x in naked))
    whole = whole_trade_after(strategy, booked_pnl=D(0), paid_charges=PAID, adjustment_charges=D(0),
                              open_exit_charges=EXIT)
    col = Column(replace(base.built, id="A-01", after=naked), whole, None, True, MarginRead(None, None))
    crit = row(compare([base, col], ctx), "max_loss")
    assert crit.values["A-01"].text == "Unlimited" and crit.values["A-01"].rank is None
    assert crit.leaders == ("A-36",)


def test_ac2_liquidity_no_bid_dashes_that_approach_only():
    """Attack 5: a NEW leg with no bid -> liquidity "-" with its reason for that approach; the others keep values."""
    _, cols, ctx = build_columns("ADJ-02")
    a05 = next(c for c in cols if c.built.id == "A-05")
    a11 = next(c for c in cols if c.built.id == "A-11")
    new = ({x.tradingsymbol for x in a05.built.after} - {x.tradingsymbol for x in ctx.position.legs}
           - {x.tradingsymbol for x in a11.built.after})
    assert new
    chain = [replace(r, bid=None) if r.tradingsymbol in new else r for r in ctx.chain]
    crit = row(compare(cols, replace(ctx, chain=chain)), "liquidity")
    assert crit.values["A-05"].text == "-" and "has no bid or no ask" in crit.values["A-05"].unavailable_reason
    assert crit.values["A-11"].value is not None and crit.values["A-36"].text == "-"  # No change opens nothing
    sc = load("ADJ-02")
    rows = chain_rows(sc)
    hand = max((D(rows[s]["ask"]) - D(rows[s]["bid"])) / ((D(rows[s]["ask"]) + D(rows[s]["bid"])) / 2) * 100
               for s in {x.tradingsymbol for x in a11.built.after} - {x.tradingsymbol for x in ctx.position.legs})
    assert crit.values["A-11"].value == hand.quantize(D("0.01"))


def test_ac1_refused_approach_takes_no_part():
    """AC-1 / attack 3: ADJ-20d's A-05 is refused by the builder; the compare refuses to rank a refused column."""
    sc, cols, ctx = build_columns("ADJ-20d")
    assert "A-05" not in [c.built.id for c in cols]
    position, chain, spot = inputs(sc)
    refused = build_approach(position, chain, spot, "A-05", CFG)
    assert refused.refusal is not None
    with pytest.raises(ValueError, match="refused approach"):
        compare([*cols, Column(refused, None, None, False, MarginRead(None, None))], ctx)
    cmp = compare(cols, ctx)
    assert "A-05" not in cmp.curves and all("A-05" not in c.values for c in cmp.criteria)


def test_ac4_leads_n_of_m_fixed_order_and_no_ranking_words():
    """AC-4: "Leads on N of M" per approach, M = rows with a leader; No change first then catalogue order whatever
    the input order; no best / winner / rank / score / better word in any label or rendered text."""
    _, cols, ctx = build_columns("ADJ-02")
    cmp = compare(list(reversed(cols)), ctx)
    assert list(cmp.leads) == ["A-36", *[a for a in APPROACH_IDS[1:] if a in cmp.leads]]
    m = sum(1 for c in cmp.criteria if c.leaders)
    for a, (n, mm) in cmp.leads.items():
        assert mm == m and n == sum(1 for c in cmp.criteria if a in c.leaders)
    texts = [*ADJUSTMENT_CRITERION_LABEL_TEXT.values(), *ADJUSTMENT_LEADER_LABEL_TEXT.values()]
    texts += [str(x) for c in cmp.criteria for x in (c.label, c.leader_label)]
    texts += [str(x) for c in cmp.criteria for v in c.values.values() for x in (v.text, v.unavailable_reason) if x]
    assert [t for t in texts if FORBIDDEN.search(t)] == []
    assert FORBIDDEN.search("Best approach")  # the check itself bites


def test_ac2_curves_equal_the_hand_payoff_at_every_level():
    """REQ-156 AC-5 data: each curve point = intrinsic whole-trade P&L less charges at that level (hand path)."""
    sc, cols, ctx = build_columns("ADJ-13")
    before = cols[0].whole
    cmp = compare(cols, ctx, before=before, before_charges_known=True)
    legs, after = sc["expected"]["approach_legs"], sc["expected"]["approach_after"]
    assert set(cmp.curves) == {"before", *[c.built.id for c in cols]}
    for a, points in cmp.curves.items():
        key = "A-36" if a == "before" else a
        lo, hi = points[0][0], points[-1][0]
        assert lo == (D(sc["market"]["spot"]) * D("0.94")).quantize(D("0.01"))
        assert hi == (D(sc["market"]["spot"]) * D("1.06")).quantize(D("0.01"))
        for level, pnl in points:
            h = gen.hand_pnl_at(legs[key]["after"], Fraction(after[key]["booked_pnl"]), Fraction(level))
            assert pnl == D(h.numerator) / D(h.denominator) - total(sc, key), (a, level)
