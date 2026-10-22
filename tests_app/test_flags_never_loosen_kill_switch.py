"""REQ-117 AC-5 (W-132): the kill switch (the order-path switch, ADR-165) answers the same with every flag on and every
flag off. Its domain-gate siblings are in ``tests/execution/test_flags_never_loosen_gates.py``."""
from __future__ import annotations

import datetime

import pytest
from ofo.broker import capabilities as caps_module
from ofo.broker import kite_capabilities
from ofo_app import order_path_switch

DAY = datetime.date(2026, 10, 22)
SOURCE = "tests_app/test_flags_never_loosen_kill_switch.py"


@pytest.fixture(autouse=True)
def _restore_flags():
    original = kite_capabilities.ZERODHA_DECLARED
    yield
    kite_capabilities.ZERODHA_DECLARED = original  # type: ignore[misc]


def _answers(monkeypatch) -> dict[str, bool]:
    out = {}
    for env in ("on", "off", "garbage", ""):
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.setenv(order_path_switch.ENV_NAME, env)
        out[env] = order_path_switch.order_path_on()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(order_path_switch.ENV_NAME, "on")
    out["production"] = order_path_switch.order_path_on()
    return out


def test_ac5_the_kill_switch_is_the_same_with_every_flag_on_and_every_flag_off(monkeypatch) -> None:
    """AC-5: on only for APP_ENV=test with the switch on; identical answers with all flags on, all off, and held
    triggers on; and no flag is read while it answers (a tripwire on every way to read one)."""
    results = []
    for on, held in ((True, False), (False, False), (False, True)):
        kite_capabilities.ZERODHA_DECLARED = {  # type: ignore[misc]
            n: (held if n == "broker_held_triggers" else on, SOURCE, DAY) for n in caps_module.CAPABILITY_NAMES}
        results.append(_answers(monkeypatch))

    def tripwire(*_a: object, **_k: object) -> None:
        raise AssertionError("the kill switch read a capability flag")

    monkeypatch.setattr(caps_module, "is_supported", tripwire)
    monkeypatch.setattr(kite_capabilities, "load_zerodha_capabilities", tripwire)
    results.append(_answers(monkeypatch))
    assert results[0] == results[1] == results[2] == results[3]
    assert results[0] == {"on": True, "off": False, "garbage": False, "": False, "production": False}
