# ruff: noqa: E501
"""IC e2e paper contract, Stage C2: the exit frames of PATH-50 really cross the rule each exit stands for (no DB).

The pure evaluator (playbook_eval, the approved iron condor body of the playbook fixture) is fed each frame of the weekly
path: T-07 flags on the profit frame, T-06 on the stop frame, T-09 on the pennies frame, and the time exit (guard
``time_exit`` + the expiry-day rule) is not yet due at 14:29 and due at 14:31. Money in Decimal; the max profit / loss are the
condor's own (credit received; wing width x quantity - credit), the P&L is from the frame's own chain prices.
"""
from __future__ import annotations

import datetime
import json
import pathlib
from dataclasses import replace
from decimal import Decimal as D

from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.playbook_eval import Flag, ShortLeg, StrategyState, body_from_fixture
from test_adjust_scenarios import PLAYBOOKS
from test_playbook_eval import _row, _stops

PATH = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "adjust_paths" / "PATH-50"
F_STOP, F_PROFIT, F_QUIET, F_1420, F_1429, F_1431, F_PENNIES, F_SETTLE = range(8)
GAP_UNTIL = "09:30"


def frame(k: int) -> dict:
    return json.loads((PATH / f"frame-{k:03d}.json").read_text(encoding="utf-8"), parse_float=D)


def state_at(k: int) -> tuple[dict, StrategyState]:
    sc = frame(k)
    clock = datetime.datetime.fromisoformat(sc["clock"]["ist"])
    legs = sc["position"]["legs"]
    sign = {"BUY": 1, "SELL": -1}

    def ltp(x):
        return D(_row(sc, x)["ltp"])
    pnl = sum(sign[x["side"]] * x["quantity"] * (ltp(x) - D(x["entry"])) for x in legs)
    credit = D(sc["position"]["credit_received"])
    qty = legs[0]["quantity"]
    width = max(D(x["strike"]) for x in legs if x["type"] == "CE") - min(D(x["strike"]) for x in legs if x["type"] == "CE")
    shorts = tuple(ShortLeg(D(x["strike"]), abs(D(_row(sc, x)["delta"])), ltp(x)) for x in legs if x["side"] == "SELL")
    days_left = (datetime.date.fromisoformat(sc["expiry"]) - clock.date()).days
    state = StrategyState(
        stops=None, expiry_kind=sc["expiry_kind"], days_left=days_left, hhmm=clock.strftime("%H:%M"), spot=D(sc["market"]["spot"]),
        shorts=shorts, pnl=pnl, max_loss=width * qty - credit, max_profit=credit, margin=D(sc["broker"]["margin"]["value"]),
        atm_iv=D(sc["market"]["atm_iv"]), entry_atm_iv=D(sc["position"]["entry"]["atm_iv"]), day_open=None,
        prev_close=None, adjustments_used=0, prices_fresh=True)
    body = body_from_fixture(PLAYBOOKS, "ic")
    return body, replace(state, stops=_stops(body, state))


def fired(k: int) -> dict[str, Flag]:
    body, state = state_at(k)
    ev = pe.evaluate(body, state, {}, None, gap_until=GAP_UNTIL)
    return {r.rule_id: r for r in ev.results if isinstance(r, Flag)}


def test_profit_frame_flags_t07():
    got = fired(F_PROFIT)
    assert "T-07" in got, (sorted(got), state_at(F_PROFIT)[1].pnl, state_at(F_PROFIT)[1].max_profit)


def test_stop_frame_flags_t06():
    got = fired(F_STOP)
    assert "T-06" in got, (sorted(got), state_at(F_STOP)[1].pnl, state_at(F_STOP)[1].max_loss, state_at(F_STOP)[1].stops)


def test_pennies_frame_flags_t09():
    got = fired(F_PENNIES)
    assert "T-09" in got, (sorted(got), [s.ltp for s in state_at(F_PENNIES)[1].shorts])


def test_the_profit_frame_does_not_flag_the_stop_and_the_stop_frame_does_not_flag_the_target():
    assert "T-06" not in fired(F_PROFIT)
    assert "T-07" not in fired(F_STOP)


def test_time_exit_is_not_due_at_1429_and_due_at_1431_on_expiry_day():
    body, s1429 = state_at(F_1429)
    guards = body["guards"]
    assert guards["time_exit"] == "14:30"
    assert pe.exit_inputs(body, guards, s1429).hhmm < pe.exit_inputs(body, guards, s1429).time_exit
    _body, s1431 = state_at(F_1431)
    exits = pe.exit_inputs(body, guards, s1431)
    assert s1431.days_left == 0 and exits.hhmm >= exits.time_exit
