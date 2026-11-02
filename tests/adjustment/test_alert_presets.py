# ruff: noqa: PLR2004 - exact expected values from the REQ-170 table are the assertion (tests rule: assert exact values)
"""REQ-170 AC-6 / AC-7, Q-AD-2: the alert presets resolve from the REAL registry plus a user's values (GC-ALERT1).

Core proof: with no user values the three presets built from backend/ofo/settings/registry.json are exactly the gate's
INTRADAY / WEEKLY / MONTHLY; a user cap above the admin cap never reaches the gate (min fence); the style comes from
the strategy (days to expiry, expiry kind) unless a pin is set; an unknown kind or days is refused, never guessed.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from ofo import settings as registry_mod
from ofo.adjustment import alert_gate, alert_presets


def _admin() -> dict[str, Decimal]:
    return registry_mod.defaults()


@pytest.mark.parametrize(("style", "expected"), [("intraday", alert_gate.INTRADAY), ("weekly", alert_gate.WEEKLY),
                                                 ("monthly", alert_gate.MONTHLY)])
def test_registry_defaults_give_the_gate_presets(style: str, expected: alert_gate.Preset) -> None:
    assert alert_presets.preset_for(style, _admin(), _admin()) == expected


def test_every_style_key_is_in_the_registry() -> None:
    reg = registry_mod.registry()
    for style in alert_presets.STYLES:
        for key in alert_presets.style_keys(style):
            assert key in reg, key
        assert alert_presets.speed_key(style) in reg
    assert "speeds.background_check_seconds" in reg  # the worker still reads the old key until a later step


def test_user_keys_are_exactly_the_four_user_values() -> None:
    names = {k.rsplit(".", 1)[1] for k in alert_presets.USER_KEYS}
    assert names == {"confirm_candle_minutes", "cooldown_minutes", "quiet_until", "daily_cap"}
    assert len(alert_presets.USER_KEYS) == 12
    assert not any("rearm" in k for k in alert_presets.USER_KEYS)  # admin only


def test_user_values_are_used() -> None:
    mine = _admin() | {"alerts.intraday.daily_cap": Decimal(3),
                       "alerts.intraday.cooldown_minutes": Decimal(7),
                       "alerts.intraday.quiet_until": Decimal(925),
                       "alerts.intraday.confirm_candle_minutes": Decimal(2)}
    p = alert_presets.preset_for("intraday", mine, _admin())
    assert p.daily_cap == 3 and p.cooldown.total_seconds() == 420 and p.quiet_until.strftime("%H:%M") == "09:25"
    assert p.candle.total_seconds() == 120
    assert p.rearm_fraction == Decimal("0.10")


def test_user_cap_above_admin_cap_is_fenced() -> None:
    mine = _admin() | {"alerts.intraday.daily_cap": Decimal(8)}
    assert alert_presets.preset_for("intraday", mine, _admin()).daily_cap == 6


def test_rearm_comes_from_admin_not_user_mapping() -> None:
    admin = _admin() | {"alerts.weekly.rearm_percent": Decimal(30)}
    assert alert_presets.preset_for("weekly", _admin(), admin).rearm_fraction == Decimal("0.30")


def test_missing_key_is_a_keyerror_not_a_default() -> None:
    mine = _admin()
    del mine["alerts.monthly.cooldown_minutes"]
    with pytest.raises(KeyError):
        alert_presets.preset_for("monthly", mine, _admin())


def test_unknown_style_refused() -> None:
    with pytest.raises(alert_presets.StyleRefused):
        alert_presets.preset_for("scalping", _admin(), _admin())


@pytest.mark.parametrize(("kind", "days", "pin", "style"), [
    ("weekly", 0, None, "intraday"), ("weekly", 1, None, "intraday"), ("weekly", 2, None, "weekly"),
    ("monthly", 0, None, "intraday"), ("monthly", 1, None, "intraday"), ("monthly", 2, None, "monthly"),
    ("monthly", 20, None, "monthly"),
    ("weekly", 0, "monthly", "monthly"), ("monthly", 20, "intraday", "intraday"), ("weekly", 5, "weekly", "weekly"),
    (None, None, "weekly", "weekly"),  # a pin wins even when the strategy's expiry cannot be read
])
def test_style_for(kind: str | None, days: int | None, pin: str | None, style: str) -> None:
    assert alert_presets.style_for(kind, days, pin) == style


@pytest.mark.parametrize(("kind", "days", "pin"), [
    ("quarterly", 5, None), (None, 5, None), ("", 5, None),  # unknown / absent / empty kind
    ("weekly", None, None), ("weekly", -1, None),  # absent or past days
    ("weekly", 3, "scalping"), ("weekly", 3, ""),  # a pin that is no style
])
def test_style_for_refuses_rather_than_guesses(kind: str | None, days: int | None, pin: str | None) -> None:
    with pytest.raises(alert_presets.StyleRefused):
        alert_presets.style_for(kind, days, pin)
