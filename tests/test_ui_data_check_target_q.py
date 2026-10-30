"""GC-LIVE 30 Oct 2026: the checker's target Greeks use the q the server priced with.

REAL SENSEX short-strangle reply (6 days to expiry, 11:25 IST, `tests/fixtures/outcome-target-sensex-live-1030.json`).
The server's leg theta differs from a theta re-solved with this file's own q by 0.0064 (q is solved from rounded IVs and
prices of another instant; theta moves ~800 per unit of q), which the old tolerance (0.001) called a mismatch.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ui_data_check_q", ROOT / "scripts" / "checks" / "ui_data_check.py")
u = importlib.util.module_from_spec(_spec)
sys.modules["ui_data_check_q"] = u
_spec.loader.exec_module(u)

_LIVE = ROOT / "tests" / "fixtures" / "outcome-target-sensex-live-1030.json"
_SERVER_Q = "0.116535"  # the q that reproduces the server's theta on this reply (measured, replay spike)
_EXPIRY = "2026-11-05"


def _live():
    return json.loads(_LIVE.read_text(encoding="utf-8"))


def _verdicts(rep):
    return {f.name: f.verdict for f in rep.figures}


def test_echoed_q_is_used_as_is_and_an_honest_reply_never_mismatches():
    reply = _live()
    reply["target"]["greeks"]["dividend_yields"] = {_EXPIRY: _SERVER_Q}
    assert u.target_q_by_expiry(reply, u.RISK_FREE_RATE) == {_EXPIRY: (float(_SERVER_Q), 0.0)}
    rep = u.check_target(reply)
    assert set(_verdicts(rep).values()) == {u.MATCH}


def test_without_the_echo_the_solved_q_tolerance_still_covers_the_measured_gap():
    rep = u.check_target(_live())  # an older reply shape: q re-solved, tolerance widened by the measured uncertainty
    assert u.MISMATCH not in _verdicts(rep).values()
    assert u.target_q_by_expiry(_live(), u.RISK_FREE_RATE)[_EXPIRY][1] >= u.Q_SOLVE_FLOOR


def test_a_wrong_server_theta_is_still_a_mismatch_with_or_without_the_echo():
    for echo in (True, False):
        reply = _live()
        if echo:
            reply["target"]["greeks"]["dividend_yields"] = {_EXPIRY: _SERVER_Q}
        reply["target"]["greeks"]["total"]["theta"] = "1850.0000"  # real 1844.9086
        reply["target"]["greeks"]["legs"][0]["theta"] = "860.0000"  # real 849.3955
        v = _verdicts(u.check_target(reply))
        assert v["target theta"] == u.MISMATCH and v["target leg1 theta"] == u.MISMATCH


def test_a_wrong_echoed_q_shows_as_a_mismatch_not_hidden():
    reply = _live()
    reply["target"]["greeks"]["dividend_yields"] = {_EXPIRY: "0.100000"}  # not what the server's figures used
    assert u.MISMATCH in _verdicts(u.check_target(reply)).values()
