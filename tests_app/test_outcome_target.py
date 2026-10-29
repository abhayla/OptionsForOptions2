"""REQ-084 AC-1/AC-2/AC-4/AC-6/AC-7 (GC-TP step 6a): the what-if target through POST /api/strategies/outcome on the
real 2026-10-08 replay (NIFTY 13-Oct iron condor, valued 09:20:09 IST). Every target figure is the one engine's: at the
valuation time the target equals the Estimated Now curve, at the expiry close the At Expiry curve. No database."""
from __future__ import annotations

import datetime
import pathlib
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_outcome_route import (  # noqa: E402,F401  (replayed is the module fixture)
    VALUATION,
    WORST_CASE,
    _body,
    _legs_body,
    _mixed_condor,
    _post,
    _post_stored,
    _spread_body,
    replayed,
)

from ofo.marketdata.kite_provider import IST  # noqa: E402

CLOSE = datetime.datetime(2026, 10, 13, 15, 30, tzinfo=IST)  # the condor's expiry close
HTTP_OK = 200
HTTP_UNPROCESSABLE = 422


def _point(curve: dict, level: str) -> str:
    return next(p["pnl"] for p in curve["points"] if Decimal(p["level"]) == Decimal(level))


async def _target(provider, **extra) -> dict:
    body = {**_body(provider), "both_views": True, **extra}
    r = await _post(body, provider)
    assert r.status_code == HTTP_OK, r.text
    return r.json()


def _a_grid_level(out: dict) -> str:
    """A whole-point level near the middle of the curve (a request level is whole points)."""
    points = out["curves"]["estimated_now"]["points"]
    whole = [Decimal(p["level"]) for p in points if Decimal(p["level"]) % 1 == 0]
    return str(int(whole[len(whole) // 2]))


async def test_target_at_now_is_the_estimated_now_curve(replayed):  # noqa: F811
    base = await _target(replayed)
    level = _a_grid_level(base)
    out = await _target(replayed, target_level=level)
    t = out["target"]
    assert t["kind"] == "estimate" and t["model"]
    assert datetime.datetime.fromisoformat(t["at"]) == VALUATION and t["at_clamped"] is False and t["clamp"] is None
    assert t["pnl"]["value"] == _point(out["curves"]["estimated_now"], level)
    assert t["curve"]["points"] == out["curves"]["estimated_now"]["points"]  # same function, same levels
    assert t["greeks"]["total"] is not None and t["greeks"]["unavailable"] is None
    assert len(t["greeks"]["legs"]) == len(out["legs"])
    assert isinstance(t["breakevens"], list) and t["breakevens_reason"] is None


async def test_target_at_the_expiry_close_is_the_at_expiry_payoff(replayed):  # noqa: F811
    base = await _target(replayed)
    level = _a_grid_level(base)
    out = await _target(replayed, target_level=level, target_at=CLOSE.isoformat())
    t = out["target"]
    assert datetime.datetime.fromisoformat(t["at"]) == CLOSE and t["at_clamped"] is False
    assert t["pnl"]["value"] == _point(out["curves"]["at_expiry"], level)
    assert t["greeks"]["total"] is None and t["greeks"]["unavailable"] == "no_time_left"
    assert t["greeks"]["legs"] == [None, None, None, None]


async def test_target_between_now_and_expiry_moves_every_figure(replayed):  # noqa: F811
    base = await _target(replayed)
    level = _a_grid_level(base)
    mid = datetime.datetime(2026, 10, 10, 12, 0, tzinfo=IST)
    out = await _target(replayed, target_level=level, target_at=mid.isoformat())
    t = out["target"]
    assert datetime.datetime.fromisoformat(t["at"]) == mid
    now_pnl, expiry_pnl = _point(out["curves"]["estimated_now"], level), _point(out["curves"]["at_expiry"], level)
    assert t["pnl"]["value"] not in (now_pnl, expiry_pnl)
    assert t["curve"]["points"] != out["curves"]["estimated_now"]["points"]
    assert t["greeks"]["total"] is not None
    for be in t["breakevens"]:  # each breakeven is where the target-time curve crosses zero
        assert Decimal(be) > 0


async def test_target_after_the_first_expiry_is_clamped_to_its_close(replayed):  # noqa: F811
    out = await _target(replayed, target_at="2026-10-15T10:00:00+05:30")
    t = out["target"]
    assert t["at_clamped"] is True and t["clamp"] == "after_first_expiry"
    assert datetime.datetime.fromisoformat(t["at"]) == CLOSE


async def test_target_before_now_is_clamped_to_now(replayed):  # noqa: F811
    out = await _target(replayed, target_at="2026-10-07T10:00:00+05:30")
    t = out["target"]
    assert t["at_clamped"] is True and t["clamp"] == "before_now"
    assert datetime.datetime.fromisoformat(t["at"]) == VALUATION


async def test_target_level_limits_are_spot_ten_percent_snapped_and_clamp_outside(replayed):  # noqa: F811
    out = await _target(replayed, target_level="99999")
    t, spot = out["target"], Decimal(out["spot_level"])
    lim = {k: Decimal(v) for k, v in t["limits"].items()}
    assert lim["step"] == Decimal(50)
    assert lim["min"] % 50 == 0 and lim["max"] % 50 == 0
    assert spot * Decimal("0.9") <= lim["min"] < spot * Decimal("0.9") + 50
    assert spot * Decimal("1.1") - 50 < lim["max"] <= spot * Decimal("1.1")
    assert t["level_clamped"] is True and Decimal(t["level"]) == lim["max"]
    low = (await _target(replayed, target_level="1"))["target"]
    assert low["level_clamped"] is True and Decimal(low["level"]) == lim["min"]
    inside = (await _target(replayed, target_level=str(int(lim["min"]) + 50)))["target"]
    assert inside["level_clamped"] is False


async def test_target_level_alone_uses_spot_inside_limits(replayed):  # noqa: F811
    out = await _target(replayed, target_at=VALUATION.isoformat())
    assert Decimal(out["target"]["level"]) == Decimal(out["spot_level"]).quantize(Decimal("0.01"))
    assert out["target"]["level_clamped"] is False


async def test_multi_expiry_target_has_no_breakevens_with_the_reason(replayed):  # noqa: F811
    body = {**_legs_body(replayed, _mixed_condor()), "target_at": "2026-10-10T12:00:00+05:30"}
    r = await _post(body, replayed)
    assert r.status_code == HTTP_OK, r.text
    t = r.json()["target"]
    assert t["breakevens"] is None and t["breakevens_reason"] == WORST_CASE
    assert t["pnl"] is not None and t["curve"]["available"] is True


async def test_no_live_data_target_gives_at_expiry_and_refuses_the_time():
    body = {**_spread_body(), "both_views": True, "target_level": "23000", "target_at": "2026-10-10T12:00:00+05:30"}
    r = await _post_stored(body)
    assert r.status_code == HTTP_OK, r.text
    out = r.json()
    t = out["target"]
    assert out["state"] == "FROM_ENTRIES"
    assert t["kind"] == "exact" and t["at"] is None and t["at_refused_reason"]
    assert t["curve"] is None and t["greeks"] is None and t["model"] is None
    assert t["pnl"]["value"] == _point(out["curves"]["at_expiry"], t["level"])


async def test_no_target_fields_keep_the_reply_without_a_target(replayed):  # noqa: F811
    assert "target" not in await _target(replayed)


@pytest.mark.parametrize("bad", [{"target_level": "23000.5"}, {"target_level": 23000},
                                 {"target_at": "2026-10-10T12:00:00"}])
async def test_malformed_target_inputs_are_refused(replayed, bad):  # noqa: F811
    r = await _post({**_body(replayed), **bad}, replayed)
    assert r.status_code == HTTP_UNPROCESSABLE


async def test_target_is_analysis_only_never_changes_legs_or_the_margin_plan(replayed):  # noqa: F811
    """AC-6: the target never changes a leg, the planned entries or the margin plan (the margin cache's key)."""
    from ofo_app.routes.outcome import OutcomeRequest, margin_legs

    plain = _body(replayed)
    with_target = {**plain, "target_level": "25000", "target_at": "2026-10-10T12:00:00+05:30"}
    assert margin_legs(OutcomeRequest.model_validate(with_target)) == margin_legs(OutcomeRequest.model_validate(plain))
    a, b = (await _post(plain, replayed)).json(), (await _post(with_target, replayed)).json()
    for key in ("legs", "margin", "table", "scenario", "summary", "payoff"):
        assert a[key] == b[key], key
