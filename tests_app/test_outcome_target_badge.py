# ruff: noqa: E501, PLR2004
"""GC-TP R-19a (REQ-144 AC-1..AC-4, REQ-084; Sensibull study screen 020): the what-if target reply carries the move from
spot, the days to expiry and the Projected profit / loss badge, all made on the server (ADR-008). Route tests run on the
real 2026-10-08 replay (valued 09:20:09 IST, expiry 13 Oct); the badge's zero / margin states are unit tests of the one
function. No database."""
from __future__ import annotations

import datetime
import pathlib
import sys
from decimal import ROUND_HALF_UP, Decimal

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ofo.errors.explanations import render_explanation
from ofo.marketdata.kite_provider import IST
from ofo.outcome.money import CHECKED
from ofo.outcome.service import Margin
from ofo.outcome.target import Target, TargetLimits
from ofo.outcome.target_badge import badge
from test_outcome_route import _body, _post, _post_stored, _spread_body, provider_for_catalogue

CLOSE = datetime.datetime(2026, 10, 13, 15, 30, tzinfo=IST)
HTTP_OK = 200
NO_FUNDS = "% of margin needed not available: Zerodha margin could not be read"


@pytest.fixture(scope="module")
def provider():
    return provider_for_catalogue()


async def _target(provider, **extra) -> dict:
    r = await _post({**_body(provider), "both_views": True, **extra}, provider)
    assert r.status_code == HTTP_OK, r.text
    return r.json()


def _level(out: dict) -> str:
    whole = [Decimal(p["level"]) for p in out["curves"]["estimated_now"]["points"] if Decimal(p["level"]) % 1 == 0]
    return str(int(whole[len(whole) // 2]))


def _move(level: str, spot: str) -> str:
    pct = ((Decimal(level) - Decimal(spot)) * 100 / Decimal(spot)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{pct:+.1f}%"


async def test_reply_carries_move_days_and_badge(provider):
    """Item 1 (a)(b)(c): the move equals an independent (level - spot) x 100 / spot; 3 days at 10 Oct, 0 at the close."""
    base = await _target(provider)
    level = _level(base)
    mid = datetime.datetime(2026, 10, 10, 12, 0, tzinfo=IST)
    t = (await _target(provider, target_level=level, target_at=mid.isoformat()))["target"]
    assert t["move_pct_display"] == _move(level, base["spot_level"]) and t["move_pct_reason"] is None
    assert t["days_to_expiry"] == 3 and t["days_to_expiry_display"] == "3D to expiry"
    b, pnl = t["badge"], Decimal(t["pnl"]["value"])
    assert b["state"] == ("profit" if pnl > 0 else "loss" if pnl < 0 else "zero") and Decimal(b["amount"]) == pnl
    assert b["label"].startswith("Projected ") and b["output_label"] == t["output_label"]
    close = (await _target(provider, target_level=level, target_at=CLOSE.isoformat()))["target"]
    assert close["days_to_expiry_display"] == "0D to expiry"


async def test_days_are_never_negative(provider):
    """Attack 2: after the last expiry the target is clamped to the close -> 0D; before now it counts from now."""
    after = (await _target(provider, target_at="2026-10-15T10:00:00+05:30"))["target"]
    assert after["clamp"] == "after_first_expiry" and after["days_to_expiry"] == 0
    before = (await _target(provider, target_at="2026-10-07T10:00:00+05:30"))["target"]
    assert before["clamp"] == "before_now" and before["days_to_expiry"] == 5


async def test_plain_reply_has_captions_and_a_not_available_badge_with_its_reason(provider):
    """Every answer state, no target: the spot's own move (0.0%), days from now, badge unavailable + reason, no number."""
    t = (await _target(provider))["target"]
    assert t["days_to_expiry_display"] == "5D to expiry" and t["move_pct_display"] == "0.0%"
    b = t["badge"]
    assert b["state"] == "unavailable" and b["label"] == "Projected figure not available"
    assert b["reason"] == "No target is set." and b["amount"] is None and b["percent"] is None


async def test_no_margin_read_keeps_the_amount_and_says_why_the_percent_is_absent(provider):
    """Attack 4 / REQ-144 AC-3 through the route: this replay has no Zerodha read."""
    b = (await _target(provider, target_level=_level(await _target(provider))))["target"]["badge"]
    assert b["amount"] is not None and b["percent"] is None and b["percent_text"] is None
    assert b["percent_reason"] == NO_FUNDS


async def test_no_live_price_gives_no_move_and_an_unavailable_badge():
    """Attack 1 + AC-4: stored prices only -> no spot, so no move (not from the grid centre); no estimate, no badge figure."""
    body = {**_spread_body(), "both_views": True, "target_level": "23000", "target_at": "2026-10-10T12:00:00+05:30"}
    t = (await _post_stored(body)).json()["target"]
    assert t["move_pct"] is None and t["move_pct_display"] is None and t["move_pct_reason"]
    assert t["badge"]["state"] == "unavailable" and t["badge"]["reason"] == t["at_refused_reason"]
    assert t["badge"]["amount"] is None and t["days_to_expiry"] >= 0


def _target_with(pnl: Decimal | None, kind: str = "estimate") -> Target:
    return Target(TargetLimits(Decimal(1), Decimal(2), Decimal(1)), Decimal(24000), False, None, False, None, None, kind,
                  None, None, pnl, None, None, None, None, Decimal(23000), 4)


def _margin(needed: Decimal | None, state: str = CHECKED) -> Margin:
    read = datetime.datetime(2026, 10, 8, 9, 20, tzinfo=IST) if needed is not None else None
    return Margin(state, render_explanation("target_badge_no_target"), needed=needed, checked_at=read)


@pytest.mark.parametrize(("pnl", "state", "label"), [
    (Decimal("7714"), "profit", "Projected profit: ₹7,714.00"),
    (Decimal("-3200"), "loss", "Projected loss: ₹3,200.00"),
    (Decimal("0.01"), "profit", "Projected profit: ₹0.01"),
    (Decimal("-0.01"), "loss", "Projected loss: ₹0.01"),
    (Decimal("0"), "zero", "Projected P&L: ₹0.00"),
    (Decimal("-0.00"), "zero", "Projected P&L: ₹0.00"),
])
def test_badge_label_flips_exactly_at_zero_and_a_true_zero_has_no_sign(pnl, state, label):
    """Attack 5 (REQ-152 AC-4)."""
    b = badge(_target_with(pnl), _margin(Decimal(61163)))
    assert (b["state"], b["label"]) == (state, label)
    if state == "zero":
        assert b["amount"] == "0" and "-" not in b["amount_display"]


def test_badge_percent_is_of_margin_needed_and_absent_when_it_is_unreadable():
    """REQ-144 AC-2 / AC-3 with ADR-207 (8): 7,714 of 61,163 = 12.6%; every unreadable margin state drops only the percent."""
    b = badge(_target_with(Decimal("7714")), _margin(Decimal(61163)))
    assert b["percent"] == "12.6" and b["percent_text"] == "12.6% of margin needed" and b["percent_reason"] is None
    loss = badge(_target_with(Decimal("-3200")), _margin(Decimal(61163)))
    assert loss["percent_text"] == "5.2% of margin needed"  # the share of the absolute amount
    for margin in (None, _margin(None, "NOT_AVAILABLE_YET"), _margin(Decimal(0)), _margin(Decimal(61163), "FAILED")):
        got = badge(_target_with(Decimal("7714")), margin)
        assert got["amount"] == "7714" and got["percent"] is None and got["percent_reason"] == NO_FUNDS


def test_badge_is_not_available_without_an_estimate_with_the_reason_never_a_number():
    reason = render_explanation("outcome_from_entries_no_estimate")
    t = _target_with(Decimal("5"), kind="exact")
    object.__setattr__(t, "at_refused_reason", reason)
    b = badge(t, _margin(Decimal(61163)))
    assert b["state"] == "unavailable" and b["reason"] == reason and b["amount"] is None
