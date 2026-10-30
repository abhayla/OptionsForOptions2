"""GC-LIVE 30 Oct 2026 (round 2): the main outcome check takes the q the server priced with from the reply.

REAL SENSEX short-strangle replies (tests/fixtures/gclive-1030-r3, 11:44 IST, 6 days to expiry) with the chains and
futures read around them. Without the echo the checker's own parity q (a point plus a ONE-sided band) put the leg decay
16.4 and 10.6 Rs away from the server's against tolerances of 14.5 and 9.4. One q (0.1049566081, fitted to leg 1's decay
by bisection; the server's own echo is exact) explains every figure of both legs, so the cause is q and nothing else.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ui_data_check_eq", ROOT / "scripts" / "checks" / "ui_data_check.py")
u = importlib.util.module_from_spec(_spec)
sys.modules["ui_data_check_eq"] = u
_spec.loader.exec_module(u)

FIX = ROOT / "tests" / "fixtures" / "gclive-1030-r3"
EXPIRY = "2026-11-05"
SERVER_Q = "0.10495660810284113"


def _run(est_edit=None, echo=SERVER_Q):
    est, atx, before, after, fut = u.load_replay(FIX)
    est, atx = copy.deepcopy(est), copy.deepcopy(atx)
    for reply in (est, atx):
        if echo is not None:
            reply["dividend_yields"] = {EXPIRY: echo}
    if est_edit:
        est_edit(est)
    return u.check_outcome("r3", est, atx, before, after, fut)


def _bad(rep):
    return [f.name for f in rep.figures if f.verdict == u.MISMATCH]


def _decay_cell(est, leg):
    row = next(r for r in est["table"]["rows"] if r["row_id"] == str(leg))
    return row["cells"]["decay"]


def test_echoed_q_clears_the_decay_theta_and_vega_mismatches():
    assert _bad(_run()) == []


def test_without_the_echo_the_old_one_sided_band_still_mismatches_decay():
    """Documents the fallback's limit: the point + one-sided band misses a server q below our mid (not a pass)."""
    bad = _bad(_run(echo=None))
    assert any("leg1 decay" in n for n in bad) and any("leg2 decay" in n for n in bad)


def test_a_wrong_server_decay_is_still_caught_with_the_echo():
    def edit(est):
        _decay_cell(est, 1)["value"] = "2800.0000"  # real 2788.4977

    bad = _bad(_run(edit))
    assert any("leg1 decay" in n for n in bad)


def test_an_echoed_q_outside_our_parity_band_is_a_mismatch():
    bad = _bad(_run(echo="0.20"))
    assert any(n.startswith("dividend yield") for n in bad)
