"""Stage B2 (goal contract ic-e2e-paper, design decision 8): T-14's figures reach the ONE state the screen check and
the worker both build (``adjustment_check.state_of`` -> ``with_gamma``), valued on the check's own engine model
(``carry_model``) of the real ADJ-02 position, and the margin answer states reach T-14 as their reasons.
No DB: the model is built from the scenario's own chain IVs, spot, rate and clock.
"""
from __future__ import annotations

import datetime
import inspect
import sys
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import pytest
from ofo.adjustment import gamma
from ofo.adjustment import playbook_eval as pe
from ofo.marketdata.forward import spot_fallback_forward
from ofo.rules.inputs import DataHealth
from ofo_app import adjustment_check as check
from ofo_app import background, scenario_mode

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "adjustment"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_adjust_scenarios import load
from test_playbook_eval import _row, body_of, evaluate, state_of
from test_t14_gamma import _hand

SC = load("ADJ-02")
CLOCK = datetime.datetime.fromisoformat(SC["clock"]["ist"])
SPOT, RATE = D(SC["market"]["spot"]), D(SC["market"]["rate"])
EXPIRY = datetime.date.fromisoformat(SC["expiry"])


def _market(ivs: bool = True) -> SimpleNamespace:
    fwd = spot_fallback_forward(EXPIRY, SPOT, CLOCK, CLOCK, RATE, days_in_year=365, spot_health=DataHealth.AVAILABLE)
    chain = tuple(SimpleNamespace(tradingsymbol=x["tradingsymbol"], ltp=D(_row(SC, x)["ltp"]))
                  for x in SC["position"]["legs"])
    leg_ivs = {x["tradingsymbol"]: D(_row(SC, x)["iv"]) for x in SC["position"]["legs"]} if ivs else {}
    return SimpleNamespace(now=CLOCK, forward_model=fwd, chain=chain, leg_ivs=leg_ivs)


def _tracked() -> SimpleNamespace:
    legs = tuple(SimpleNamespace(tradingsymbol=x["tradingsymbol"], side=x["side"], type=x["type"],
                                 strike=D(x["strike"]), expiry=EXPIRY, lots=x["lots"], entry=D(x["entry"]))
                 for x in SC["position"]["legs"])
    return SimpleNamespace(position=SimpleNamespace(underlying="NIFTY", lot=SC["lot"], legs=legs), booked=D("0"))


@pytest.fixture
def scenario(monkeypatch):
    """Scenario mode on, through the single mode reader (``scenario_mode.current``) every T-14 gate reads."""
    monkeypatch.setattr(scenario_mode, "current", lambda: SimpleNamespace(id="ADJ-02"))


@pytest.fixture
def live(monkeypatch):
    monkeypatch.delenv(scenario_mode.ENV_NAME, raising=False)
    assert scenario_mode.current() is None


def test_live_mode_t14_answers_exactly_as_before_on_the_screen_and_worker_state(live):
    """Review F1: in live mode T-14 is NOT evaluated: no figures, and the answer is 9e8e4eae's T14_PENDING."""
    state = check.with_gamma(state_of(SC), body_of(SC), _tracked(), _market())
    assert state.gamma is None
    t = [r for r in evaluate(body_of(SC), state, {}, None).results if r.trigger_id == "T-14"]
    assert t == [pe.NotChecked("T-14", "T-14", pe.T14_PENDING)], t


def test_live_mode_margin_needed_is_unchanged_by_t14(live):
    t14_only = {"triggers": {"T-16": {"on": False}, "T-14": {"on": True}}}
    assert background.margin_needed(t14_only) is False  # as at 9e8e4eae: no live margin read for T-14


def test_scenario_mode_margin_is_read_for_t14(scenario):
    assert background.margin_needed({"triggers": {"T-16": {"on": False}, "T-14": {"on": True}}}) is True
    assert background.margin_needed({"triggers": {"T-16": {"on": False}, "T-14": {"on": False}}}) is False


def test_screen_and_worker_both_build_t14_through_state_of():
    assert "with_gamma(" in inspect.getsource(check.state_of)
    assert "check.state_of(" in inspect.getsource(background.state_from_market)  # the worker's one path


def test_with_gamma_values_adj02_on_the_checks_own_model_equal_to_an_independent_repricing(scenario):
    body = body_of(SC)
    assert body["triggers"]["T-14"]["on"] is True
    got = check.with_gamma(state_of(SC), body, _tracked(), _market())
    figs = got.gamma
    assert figs.reason is None and figs.levels == (D("23654.20"), D("23185.80")) and figs.at == CLOCK
    assert abs(figs.up - _hand(D("23654.20"))) <= 1 and abs(figs.down - _hand(D("23185.80"))) <= 1, figs
    t = [r for r in evaluate(body, got, {}, None).results if r.trigger_id == "T-14"]
    assert not any(isinstance(r, pe.NotChecked) for r in t), t


def test_with_gamma_is_skipped_when_t14_is_off_and_unknown_without_ivs(scenario):
    body = body_of(SC)
    body["triggers"]["T-14"]["on"] = False
    assert check.with_gamma(state_of(SC), body, _tracked(), _market()).gamma is None
    got = check.with_gamma(state_of(SC), body_of(SC), _tracked(), _market(ivs=False)).gamma
    assert got == gamma.gamma_figures(None) and got.reason == pe.GAMMA_UNKNOWN


@pytest.mark.parametrize(("block", "want"), [
    (None, (None, False)),
    ({"state": "stated", "value": "98765.40"}, (D("98765.40"), False)),
    ({"state": "empty", "value": None}, (None, False)),
    ({"state": "failed", "value": None}, (None, True)),
    ({"state": "stated", "value": "n/a"}, (None, True)),
    ({"state": "stated", "value": "NaN"}, (None, True)),
    ({"state": "stated"}, (None, True)),
])
def test_margin_in_every_answer_state(block, want):
    assert check.margin_in(block) == want


def test_an_unreadable_margin_reaches_t14_as_its_reason_never_a_pass(scenario):
    state = check.with_gamma(state_of(SC), body_of(SC), _tracked(), _market())
    from dataclasses import replace  # noqa: PLC0415
    for margin, unreadable, code in ((None, True, pe.MARGIN_UNREADABLE), (None, False, f"{pe.P}missing_margin")):
        t = [r for r in evaluate(body_of(SC), replace(state, margin=margin, margin_unreadable=unreadable), {},
                                 None).results if r.trigger_id == "T-14"]
        assert t == [pe.NotChecked("T-14", "T-14", code)], t
