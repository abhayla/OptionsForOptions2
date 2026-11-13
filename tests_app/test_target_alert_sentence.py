# ruff: noqa: E501
"""GC-ICFIX u103 (ADR-294 (2)): the target alert says which figure it used, in words, with the after-charges result
beside it: "Profit before charges +Rs X reached your target of Y%; after charges -Rs Z". No database.

Real case, strategy 143 (13 Nov 2026): profit +61.75 before charges, -218.85 after. The after-charges figure comes only
from ``ofo.engine.extremes_charges.book_after_charges`` (ADR-008: the alert code never subtracts charges itself).
Spec basis: ADR-294 (2); ADR-008; ADR-263; ADR-245 (the value actually used); ADR-304 (3); ADR-003.
"""
from __future__ import annotations

import dataclasses
import datetime
import inspect
import json
import pathlib
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
import t19_support as s
from ofo.adjustment import alert_gate
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.approaches import Position, PositionLeg
from ofo.charges import ChargeRates
from ofo.charges.paper_charges import PaperFill, paper_charges
from ofo.engine.extremes import ContractTerms
from ofo.engine.extremes_charges import book_after_charges, open_exit_charges
from ofo.engine.legs import Instrument
from ofo.engine.orderbook import PaperOrder, net_positions
from ofo.marketdata.spot_source import SpotAnswer
from ofo_app import adjustment_check as check
from ofo_app import background, playbook_store
from ofo_app import db as app_db
from ofo_app.paper_reasons import reason_text
from ofo_app.routes import adjustment_check as check_route
from ofo_app.routes import playbooks
from ofo_app.routes.adjustment_check import result_out
from ofo_app.routes.adjustment_opportunities import condition_text

SEED = json.loads((pathlib.Path(__file__).parent.parent / "backend/ofo/adjustment/system_playbooks.json")
                  .read_text(encoding="utf-8"), parse_float=D)
BODY = next(p["body"] for p in SEED["playbooks"] if p["body"]["strategy_type"] == "ic")
LABEL = BODY["triggers"]["T-07"]["label"]
AT = datetime.datetime(2026, 11, 13, 11, 0, tzinfo=datetime.UTC)
EXPIRY = datetime.date(2026, 11, 3)
T0 = datetime.datetime(2026, 10, 29, 4, 0, tzinfo=datetime.UTC)
LOT = 65
RATES = ChargeRates(
    brokerage_per_order=D("20"), stt_sell_rate=D("0.0015"), stt_exercise_rate=D("0.0015"),
    transaction_rates={"NSE_FO": D("0.0003553"), "BSE_FO": D("0.000325")}, sebi_rate=D("0.000001"),
    stamp_buy_rate=D("0.00003"), gst_rate=D("0.18"), read_on=datetime.date(2026, 10, 15),
    source_url="https://zerodha.com/charges")
# an iron condor: (contract id, instrument, strike, side, entry price, live price)
LEGS = (("1", Instrument.PE, D("22600"), "BUY", D("60.65"), D("55.00")),
        ("2", Instrument.PE, D("22700"), "SELL", D("86.35"), D("70.00")),
        ("3", Instrument.CE, D("22950"), "SELL", D("107.50"), D("90.00")),
        ("4", Instrument.CE, D("23000"), "BUY", D("86.95"), D("75.00")))
LIVE = {cid: live for cid, *_rest, live in LEGS}


def _flag(value="1.7700", threshold="1.0000") -> pe.Flag:
    return pe.Flag(rule_id="T-07", trigger_id="T-07", cmp="ge", value=D(value), threshold=D(threshold), stage_name="Early")


def _position() -> Position:
    legs = tuple(PositionLeg(side, kind.value, strike, EXPIRY, 1, entry, cid) for cid, kind, strike, side, entry, _ in LEGS)
    return Position("NIFTY", LOT, "weekly", EXPIRY, legs)


def _paid() -> D:
    return paper_charges([PaperFill("open", side, LOT, entry, True) for _, _, _, side, entry, _ in LEGS], "NIFTY", RATES).shown


def _engine_after() -> tuple[D, D | None]:
    """What the paper book's own route code gets for the same book at the same prices."""
    view = net_positions([PaperOrder(cid, side, LOT, entry, "open", T0) for cid, _, _, side, entry, _ in LEGS], LIVE)
    terms = {cid: ContractTerms(kind, strike, EXPIRY) for cid, kind, strike, *_ in LEGS}
    exit_, why = open_exit_charges(view, terms, LIVE, "NIFTY", RATES)
    got = book_after_charges(view, _paid(), exit_, why)
    return got.total_before, got.total_after


# (a) both figures known -> the sentence of ADR-294 (2), exact text
def test_t07_fired_with_both_figures_says_before_and_after_in_words():
    line = check.condition_line("T-07", LABEL, "%", "1.7700", "1.0000", target=check.TargetFigures(D("61.75"), D("-218.85"), None))
    assert str(line) == "Profit before charges +Rs 61.75 reached your target of 1%; after charges \u2212Rs 218.85"


def test_the_after_charges_figure_is_the_paper_books_own_number_for_the_same_trade():
    before, after = _engine_after()
    assert (before, after) == (D("1056.25"), D("818.01"))
    got = check.after_charges_of(before, _position(), LIVE, _paid(), RATES)
    assert got == (after, None)  # one engine function, same inputs, same figure (ADR-008)
    state = pe.StrategyState(expiry_kind="weekly", pnl=before, pnl_after=got[0], pnl_after_reason=got[1], stops=None)
    assert str(check.condition_line("T-07", LABEL, "%", "1.7700", "1.0000", target=check.target_of(state))) == (
        "Profit before charges +Rs 1,056.25 reached your target of 1%; after charges +Rs 818.01")


# (b) the after-charges figure unknown -> says so with the existing reason, never a guessed number
@pytest.mark.parametrize(("rates", "ltp", "paid", "code"), [
    (None, LIVE, "paid", "rates_unavailable"),
    (RATES, {**LIVE, "3": None}, "paid", "prices_not_live"),
    (RATES, LIVE, None, "not_priced"),
])
def test_after_charges_unknown_gives_a_reason_code_and_no_number(rates, ltp, paid, code):
    got = check.after_charges_of(D("61.75"), _position(), ltp, _paid() if paid else None, rates)
    assert got == (None, code)


def test_t07_fired_without_the_after_figure_says_not_available_with_the_existing_reason_sentence():
    line = check.condition_line("T-07", LABEL, "%", "1.7700", "1.0000", target=check.TargetFigures(D("61.75"), None, "rates_unavailable"))
    assert str(line) == f"Profit before charges +Rs 61.75 reached your target of 1%; after charges not available: {reason_text('rates_unavailable')}"
    assert "218" not in str(line)


# (c) the percent line of the OTHER triggers is unchanged, even when a target is passed
@pytest.mark.parametrize("tid", ["T-01", "T-03", "T-06", "T-09"])
def test_other_triggers_keep_their_percent_line(tid):
    t = BODY["triggers"][tid]
    plain = check.condition_line(tid, t["label"], t["unit"], "0.3416", "0.5000")
    assert check.condition_line(tid, t["label"], t["unit"], "0.3416", "0.5000", target=check.TargetFigures(D("1"), D("2"), None)) == plain
    assert "before charges reached" not in str(plain)


def test_t07_without_target_figures_keeps_the_old_line():
    assert check.condition_line("T-07", LABEL, "%", "1.7700", "1.0000") == f"{LABEL}: 1.7700 % before charges (rule 1.0000 %)"


# (d) the playbook value in force (no plan Target) gives the same sentence with that value
def test_the_playbook_value_in_force_gives_the_same_sentence():
    line = check.condition_line("T-07", LABEL, "%", "52.0000", "50.0000", target=check.TargetFigures(D("1400.50"), D("1200.10"), None))
    assert str(line) == "Profit before charges +Rs 1,400.50 reached your target of 50%; after charges +Rs 1,200.10"


# (e) the page and the background give the same sentence for the same state (one builder, two callers)
def _state(**kw) -> pe.StrategyState:
    return pe.StrategyState(expiry_kind="weekly", pnl=D("61.75"), pnl_after=D("-218.85"), stops=None, **kw)


def _record(state: pe.StrategyState) -> playbook_store.Suggestion:
    stamp = check_route.target_record("T-07", state)
    timeline = {"cmp": "ge", "label": LABEL, "unit": "%", "limit": "1.0000", **stamp}
    return playbook_store.Suggestion(9, 143, "T-07", "T-07", "Early", D("1.7700"), D("1.0000"), AT, "open", None, [timeline])


@pytest.mark.parametrize("state", [_state(), pe.StrategyState(expiry_kind="weekly", pnl=D("61.75"), pnl_after=None,
                                                              pnl_after_reason="not_priced", stops=None)])
def test_the_background_record_and_the_check_page_say_the_same_sentence(state):
    page = result_out(_flag(), "w", None, body=BODY, target=check.target_of(state))["condition"]
    assert str(condition_text(_record(state))) == str(page)
    assert str(page).startswith("Profit before charges +Rs 61.75 reached your target of 1%; after charges ")


def test_an_older_record_without_figures_keeps_its_percent_line_and_a_non_target_rule_stores_none():
    old = playbook_store.Suggestion(9, 143, "T-07", "T-07", "Early", D("1.7700"), D("1.0000"), AT, "open", None,
                                    [{"cmp": "ge", "label": LABEL, "unit": "%", "limit": "1.0000"}])
    assert old.target is None and "reached your target" not in str(condition_text(old))
    assert check_route.target_record("T-03", _state()) == {} and check_route.target_record("T-07", None) == {}


class _Db:
    async def commit(self) -> None:
        return None


class _Session:
    async def __aenter__(self) -> _Db:
        return _Db()

    async def __aexit__(self, *exc) -> None:
        return None


@pytest.mark.asyncio
async def test_the_worker_stores_both_figures_with_the_record(monkeypatch):
    stamped: dict = {}

    async def open_suggestion(db, user, sid, rule, **fields):
        stamped.update(fields)
        return SimpleNamespace(id=1)

    monkeypatch.setattr(playbook_store, "open_suggestion", open_suggestion)
    monkeypatch.setattr(app_db, "get_sessionmaker", lambda: _Session)
    monkeypatch.setattr(check_route, "cheapest", lambda state: None)
    rv = SimpleNamespace(rule_id="T-07", trigger_id="T-07", value=D("1.7700"), threshold=D("1.0000"), cmp="ge",
                         beyond=None, approaches=(), carry=None)
    ctx = background.GateContext(SimpleNamespace(values=[rv], results=[], stage_name="Early"), _state())
    watched = SimpleNamespace(user_ref="owner", strategy_id=143, body=BODY, is_system=True,
                              tracked=SimpleNamespace(adjustments_used=0))
    await background.DbGateStore().apply(watched, [alert_gate.Opened("T-07", AT, 1, D("1"), D("1.77"), None)], ctx)
    assert stamped["target"] == {"before": "61.75", "after": "-218.85", "reason": None}


# ---- round 2 ----
NOT_READ = "Charges paid on broker orders are not read by this app, so the result after charges is not shown."


def test_a_real_book_strategy_gets_its_own_true_reason_not_a_false_could_not_be_worked_out():
    got = check.after_charges_of(D("61.75"), _position(), LIVE, None, RATES, real_book=True)
    assert got == (None, "charges_not_read")
    line = check.condition_line("T-07", LABEL, "%", "1.7700", "1.0000", target=check.TargetFigures(D("61.75"), None, got[1]))
    assert str(line) == f"Profit before charges +Rs 61.75 reached your target of 1%; after charges not available: {NOT_READ}"
    assert "could not be worked out" not in str(line)


def test_the_paper_reasons_are_unchanged_and_a_paper_book_is_not_marked_real():
    assert check.after_charges_of(D("61.75"), _position(), LIVE, None, RATES) == (None, "not_priced")
    assert check.after_charges_of(D("61.75"), _position(), LIVE, None, None) == (None, "rates_unavailable")
    assert check.after_charges_of(D("1056.25"), _position(), LIVE, _paid(), RATES)[1] is None
    assert s.inputs(s.load("ADJ-02"))[0].real_book is False  # the field that tells them apart: Tracked.real_book


def _adj02_state(tracked=None, **kw) -> pe.StrategyState:
    sc = s.load("ADJ-02")
    base, m, spot = s.inputs(sc)
    return check.state_of(tracked or base, m, SpotAnswer(spot, "feed", m.now), None, s.RATES, True, s.body_of(sc),
                          config=s.PREFS.approach, user_values=None, strategy_layer=None, entry_facts=None,
                          resolved=None, **kw)


def test_state_of_wiring_reaches_the_sentence_for_paper_and_real_book():
    st = _adj02_state()
    assert st.pnl is not None and st.pnl_after is not None and st.pnl_after_reason is None
    assert str(check.condition_line("T-07", LABEL, "%", "1", "1", target=check.target_of(st))).startswith("Profit before charges ")
    assert "; after charges " in str(check.condition_line("T-07", LABEL, "%", "1", "1", target=check.target_of(st)))
    real = _adj02_state(dataclasses.replace(s.inputs(s.load("ADJ-02"))[0], paid_charges=None, real_book=True))
    assert (real.pnl_after, real.pnl_after_reason) == (None, "charges_not_read")
    assert NOT_READ in str(check.condition_line("T-07", LABEL, "%", "1", "1", target=check.target_of(real)))


@pytest.mark.parametrize("boom", [KeyError("side"), ValueError("bad"), AttributeError("rates")])
def test_a_failure_in_the_optional_figure_never_stops_the_rule_check(monkeypatch, boom):
    def fail(*a, **k):
        raise boom
    monkeypatch.setattr(check, "open_exit_charges", fail)
    st = _adj02_state()
    assert st.pnl is not None and st.pnl_after is None and st.pnl_after_reason == "not_priced"
    body = s.body_of(s.load("ADJ-02"))
    for tid in ("T-06", "T-07"):
        body["triggers"][tid]["on"] = True
        body["triggers"][tid].pop("greyed", None)
        body["rules"].append({"id": tid, "any_of": [tid]})
    ev = pe.evaluate(body, st, gap_until="09:30")
    assert {"T-06", "T-07"} <= {r.rule_id for r in ev.results} | {v.rule_id for v in ev.values}
    assert "after charges not available: " in str(check.condition_line("T-07", LABEL, "%", "1", "1", target=check.target_of(st)))


@pytest.mark.parametrize("bad", [{"before": "61.75", "after": [1]}, {"before": "61.75", "after": "abc"},
                                 {"before": ["61.75"], "after": "1"}, {"before": "61.75", "after": {"x": 1}}])
def test_a_malformed_stored_target_falls_back_to_the_percent_line_for_that_row_only(bad):
    rec = playbook_store.Suggestion(9, 143, "T-07", "T-07", "Early", D("1.7700"), D("1.0000"), AT, "open", None,
                                    [{"cmp": "ge", "label": LABEL, "unit": "%", "limit": "1.0000", "target": bad}])
    assert rec.target is None
    assert str(condition_text(rec)) == f"{LABEL}: 1.7700 % before charges (rule 1.0000 %)"


def test_the_playbook_test_route_passes_the_target_figures_too():
    src = inspect.getsource(playbooks)
    assert src.count("target=check.target_of(state)") == 1 and "result_out(r, None, target=" in src
