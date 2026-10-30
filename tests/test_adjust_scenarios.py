# ruff: noqa: E501, PLR2004, PERF401, PLR0915 - one trigger per line in the recomputation
"""Adjustment scenario library (tests/fixtures/adjust_scenarios/): every scenario is internally correct, the generator
reproduces it byte for byte, and the repo's engine agrees with the hand-derived at-expiry numbers of every Before
position (owner 2026-10-30: test data for every adjustment scenario, since live data cannot cover them).

Three checks, each a separate path:
1. Schema + reproducibility: each file has the fields the GC-ADJ1 build reads; regenerating gives identical bytes.
2. Engine cross-check: ``ofo.engine`` (strategy_metrics, breakevens_with_shift) on the Before legs equals the
   generator's intrinsic-value hand values to the paisa, booked P&L added as a flat shift (F-74).
3. Trigger consistency: the fired triggers are recomputed here from the scenario's market numbers and _playbooks.json.
Trigger evaluation and approach building are NOT product code yet (GC-ADJ1 builds them on these files).
"""
from __future__ import annotations

import datetime
import json
from decimal import Decimal as D
from pathlib import Path

import adjust_scenarios_gen as gen
import pytest
from ofo.engine import Action, Instrument, Leg, Strategy, strategy_metrics
from ofo.engine.metrics import UNLIMITED, MultiExpiryError, breakevens_with_shift

FIX = Path(__file__).resolve().parent / "fixtures" / "adjust_scenarios"
IDS = sorted(p.stem for p in FIX.glob("ADJ-*.json"))
PLAYBOOKS = json.loads((FIX / "_playbooks.json").read_text(encoding="utf-8"))


def load(sid: str) -> dict:
    return json.loads((FIX / f"{sid}.json").read_text(encoding="utf-8"))


def test_library_is_not_empty_and_indexed():
    assert len(IDS) >= 40
    index = (FIX / "INDEX.md").read_text(encoding="utf-8")
    missing = [sid for sid in IDS if f"| {sid} |" not in index]
    assert not missing


def test_generator_output_is_byte_identical(tmp_path):
    first = gen.generate(tmp_path / "a")
    second = gen.generate(tmp_path / "b")
    committed = sorted(p.name for p in FIX.iterdir() if p.is_file())
    assert first == second == committed
    for name in first:
        a = (tmp_path / "a" / name).read_bytes()
        assert a == (tmp_path / "b" / name).read_bytes(), name
        assert a == (FIX / name).read_bytes(), f"{name} differs from a fresh run: regenerate the library"


TOP = {"id", "title", "group", "refs", "family", "playbook_ref", "underlying", "lot", "tick", "strike_step", "exchange",
       "clock", "expiry", "expiry_kind", "dte", "market", "events", "data_state", "position", "broker", "expected"}
ROW = {"strike", "type", "ltp", "bid", "ask", "iv", "oi", "delta", "gamma", "listed", "tradable", "low_oi", "tradingsymbol"}
LEG = {"side", "type", "strike", "expiry", "lots", "quantity", "entry", "tradingsymbol"}
EXPECTED = {"stage", "stage_index", "suggest", "pnl_now", "triggers_fired", "triggers_close", "triggers_not_evaluated",
            "day_rules", "situations", "approaches", "at_expiry_whole_trade", "notes"}


@pytest.mark.parametrize("sid", IDS)
def test_schema(sid):
    sc = load(sid)
    assert sc["id"] == sid
    assert set(sc) >= TOP, TOP - set(sc)
    assert sc["family"] in PLAYBOOKS["families"]
    assert sc["expiry_kind"] in ("weekly", "monthly")
    assert {"ist", "weekday", "day_type"} <= set(sc["clock"])
    assert sc["clock"]["weekday"] == datetime.datetime.fromisoformat(sc["clock"]["ist"]).strftime("%A")
    assert sc["dte"] == (datetime.date.fromisoformat(sc["expiry"])
                         - datetime.datetime.fromisoformat(sc["clock"]["ist"]).date()).days
    assert {"prices", "age_seconds", "spot_source"} <= set(sc["data_state"])
    for c in sc["market"]["chains"]:
        assert c["rows"]
        for r in c["rows"]:
            assert set(r) >= ROW, ROW - set(r)
            if r["listed"]:
                assert D(r["bid"]) <= D(r["ltp"]) <= D(r["ask"])
                assert D(r["ltp"]) % D("0.05") == 0
    for leg in sc["position"]["legs"]:
        assert set(leg) >= LEG, LEG - set(leg)
        assert leg["quantity"] == leg["lots"] * sc["lot"]
    assert {"state", "value", "reply"} <= set(sc["broker"]["margin"])
    assert sc["broker"]["quote"]["legs"]
    assert set(sc["expected"]) >= EXPECTED, EXPECTED - set(sc["expected"])
    approaches = sc["expected"]["approaches"]
    if sc["expected"]["suggest"]:
        assert "A-36" in approaches["applicable"], "No change is always an approach"
        for r in approaches["refused"] + approaches["greyed"]:
            assert r["reason"]


def engine_strategy(sc: dict) -> Strategy:
    legs = []
    for leg in sc["position"]["legs"]:
        legs.append(Leg(Action(leg["side"]), Instrument(leg["type"]),
                        None if leg["strike"] is None else D(leg["strike"]),
                        datetime.date.fromisoformat(leg["expiry"]), leg["quantity"], D(leg["entry"])))
    return Strategy(tuple(legs))


def as_text(value) -> str:
    return "UNLIMITED" if value is UNLIMITED else value


@pytest.mark.parametrize("sid", IDS)
def test_engine_agrees_with_hand_expiry_numbers(sid):
    """The repo's engine and the generator's intrinsic-value hand path give the same whole-trade numbers."""
    sc = load(sid)
    hand = sc["expected"]["at_expiry_whole_trade"]
    strategy = engine_strategy(sc)
    booked = D(sc["position"]["booked_pnl"])
    if not hand["exact"]:
        with pytest.raises(MultiExpiryError):
            strategy_metrics(strategy)
        return
    m = strategy_metrics(strategy)
    max_profit = m.max_profit if m.max_profit is UNLIMITED else m.max_profit + booked
    if m.min_pnl is UNLIMITED:
        max_loss = UNLIMITED
    else:
        low = m.min_pnl + booked
        max_loss = -low if low < 0 else D(0)
    assert as_text(max_profit) == hand["max_profit"] or max_profit == D(hand["max_profit"])
    assert as_text(max_loss) == hand["max_loss"] or max_loss == D(hand["max_loss"])
    assert list(breakevens_with_shift(strategy, booked)) == [D(b) for b in hand["breakevens"]]
    if "at_expiry_after_charges" in sc["expected"]:  # F-75 shape: an after-charges breakeven finer than paise
        after = sc["expected"]["at_expiry_after_charges"]
        shifted = breakevens_with_shift(strategy, booked - D(sc["position"]["charges_round_trip"]))
        assert list(shifted) == [D(b) for b in after["breakevens"]]
        assert any(b.as_tuple().exponent < -2 for b in shifted)


def test_engine_crosscheck_covers_every_before_position(capsys):
    exact = multi = 0
    for sid in IDS:
        if load(sid)["expected"]["at_expiry_whole_trade"]["exact"]:
            exact += 1
        else:
            multi += 1
    with capsys.disabled():
        print(f"\nengine cross-check: {exact} exact Before positions + {multi} multi-expiry (MultiExpiryError) "
              f"= {exact + multi} of {len(IDS)} scenarios")
    assert exact + multi == len(IDS)
    assert exact >= len(IDS) - 2


# ---- 3. trigger consistency, recomputed from the scenario's own numbers ----------------------------------------------
def _row(sc: dict, leg: dict) -> dict:
    if leg["type"] == "FUT":
        return sc["market"]["futures"][0]
    for c in sc["market"]["chains"]:
        if c["expiry"] == leg["expiry"]:
            for r in c["rows"]:
                if r["type"] == leg["type"] and D(r["strike"]) == D(leg["strike"]):
                    return r
    raise AssertionError(f"no chain row for {leg}")


def _limit(sc: dict, tid: str, stage: int, tighten: D | None) -> D | str:
    over = sc["playbook_ref"]["plan_overrides"].get("triggers", {}).get(tid, {}).get(sc["expiry_kind"])
    raw = (over or PLAYBOOKS["triggers"][tid][sc["expiry_kind"]])[stage]
    if tid == "T-10b" or raw == "":
        return raw
    lim = D(raw)
    if tighten is not None and tid in gen.TIGHTENED:
        lim = lim * (1 + tighten / 100) if PLAYBOOKS["triggers"][tid]["cmp"] == "le" else lim * (1 - tighten / 100)
    return lim


def recompute_fired(sc: dict) -> set[str]:  # noqa: C901, PLR0912 - one trigger per branch, kept flat to read
    exp = sc["expected"]
    stages = PLAYBOOKS["stages"][sc["expiry_kind"]]
    stage = next(i for i, s in enumerate(stages) if sc["dte"] >= s["from"] and (s["to"] is None or sc["dte"] <= s["to"]))
    assert stage == exp["stage_index"] and stages[stage]["name"] == exp["stage"]
    clock = datetime.datetime.fromisoformat(sc["clock"]["ist"])
    hhmm = clock.strftime("%H:%M")
    rule = next(r for r in PLAYBOOKS["day_rules"] if r["when"] == "expiry")
    tighten = D(rule["percent"]) if clock.date().isoformat() == sc["expiry"] and hhmm >= rule["at"] else None
    spot = D(sc["market"]["spot"])
    legs = sc["position"]["legs"]
    unpriced = {q["tradingsymbol"] for q in sc["broker"]["quote"]["legs"] if q["state"] != "stated"}
    sign = {"BUY": 1, "SELL": -1}
    shorts = [x for x in legs if x["side"] == "SELL" and x["type"] != "FUT"]
    booked = D(sc["position"]["booked_pnl"])
    priced = not unpriced
    pnl = booked + sum(sign[x["side"]] * x["quantity"] * (D(_row(sc, x)["ltp"]) - D(x["entry"])) for x in legs) if priced else None
    whole = exp["at_expiry_whole_trade"]
    options = [x for x in legs if x["type"] != "FUT"]
    left = sum(-sign[x["side"]] * x["quantity"] * D(_row(sc, x)["ltp"]) for x in options) if priced and options else None
    cost = sum((D(_row(sc, x)["ask"]) - D(_row(sc, x)["bid"])) * x["quantity"] + 40 for x in options)
    margin = sc["broker"]["margin"]
    on = [t for t in PLAYBOOKS["families"][sc["family"]]["triggers_on"] if t in gen.EVALUATED]
    fired = set()
    for tid in on:
        lim = _limit(sc, tid, stage, tighten) if tid not in ("T-02", "T-18", "T-21") else None
        value = None
        if tid == "T-01" and shorts:
            value = min(abs(D(x["strike"]) - spot) / spot * 100 for x in shorts)
        elif tid == "T-02" and whole["exact"]:
            if engine_strategy(sc).expiry_pnl_at(spot) + booked < 0:
                fired.add(tid)
        elif tid == "T-03" and shorts:
            value = max(abs(D(_row(sc, x)["delta"])) for x in shorts)
        elif tid == "T-06" and pnl is not None and whole["exact"] and whole["max_loss"] not in ("UNLIMITED", "0"):
            value = max(-pnl, D(0)) / D(whole["max_loss"]) * 100
        elif tid == "T-07" and pnl is not None and whole["exact"] and whole["max_profit"] != "UNLIMITED":
            value = max(pnl, D(0)) / D(whole["max_profit"]) * 100
        elif tid == "T-09" and shorts and not ({x["tradingsymbol"] for x in shorts} & unpriced):
            value = min(D(_row(sc, x)["ltp"]) for x in shorts)
        elif tid == "T-10b" and lim != "" and hhmm >= lim:
            fired.add(tid)
        elif tid == "T-11":
            value = abs(D(sc["market"]["atm_iv"]) - D(sc["position"]["entry"]["atm_iv"])) * 100
        elif tid == "T-13" and hhmm <= "09:30" and sc["market"]["day_open"] is not None:
            value = abs(D(sc["market"]["day_open"]) - D(sc["market"]["prev_close"])) / D(sc["market"]["prev_close"]) * 100
        elif tid == "T-16" and margin["state"] == "stated" and pnl is not None:
            value = max(-pnl, D(0)) / D(margin["value"]) * 100
        elif tid == "T-18":
            mx = sc["playbook_ref"]["plan_overrides"].get("max_adjustments", PLAYBOOKS["guards"]["max_adjustments"])
            if sc["position"]["adjustments_used"] >= mx:
                fired.add(tid)
        elif tid == "T-19" and left is not None and left >= 0:
            value = left / cost
        if value is not None and lim not in (None, ""):
            cmp = PLAYBOOKS["triggers"][tid]["cmp"]
            if (value <= lim) if cmp == "le" else (value >= lim):
                fired.add(tid)
    return fired


@pytest.mark.parametrize("sid", IDS)
def test_trigger_expectations_match_playbook_values(sid):
    sc = load(sid)
    exp = sc["expected"]
    fired = {f["id"] for f in exp["triggers_fired"]}
    if not exp["suggest"]:
        assert not fired and "withheld" in exp["approaches"], "no suggestion on stale data or with no spot (S-10, T-21)"
        assert "S-10" in exp["situations"]
        return
    assert recompute_fired(sc) == fired
