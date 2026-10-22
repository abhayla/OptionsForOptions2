"""W-125 (REQ-079 AC-1/AC-11, REQ-082 AC-1/AC-7; ADR-150 (2), ADR-156 (1), ADR-165 (4)): held features.

A held feature is built but stays OFF for every user until the Q211 written legal answer clears it. One CLOSED list of
switch names, one function (``_read``) that reads the configuration, no other code reads a held-switch variable
(finding setting-read-from-two-sources). The pattern is ``order_path_switch``: server side, fail closed.

A switch is ON when ``APP_ENV`` is exactly ``development`` or ``test``; in any other environment (production, staging,
unset, a case or space variant) it is ON only when ``OFO_HELD_<NAME>`` is on AND ``OFO_HELD_<NAME>_REF`` is a
non-blank reference to the written answer. A request never carries a value into this module. An unknown switch name
raises; a configuration that sets a switch on without a reference, or names an unknown switch, is refused at start-up
(``require_valid_configuration``). Answer states (standing item d): on / off / setting unreadable (off) / reference
empty (off, and refused at start-up) / unknown name (raises).
"""
from __future__ import annotations

import os
from collections.abc import Mapping

from ofo_app.config import app_env

#: The closed list (REQ-079, REQ-082, and the held features of lanes B5 / B6). Adding a name here needs the same name in
#: ``tests_app/test_production_config_switches.py`` (it fails on any other name found in code).
PLATFORM_STRIKES = "platform_strikes"
PROBABILITY_OF_PROFIT = "probability_of_profit"
DELAYED_PRICES = "delayed_prices"
HISTORY_CHARTS = "history_charts"
EVENTS_CALENDAR = "events_calendar"
FII_DII = "fii_dii"
MARKET_EVENT_WARNING = "market_event_warning"
STRATEGY_PRICE_HISTORY = "strategy_price_history"
SWITCH_NAMES: tuple[str, ...] = (PLATFORM_STRIKES, PROBABILITY_OF_PROFIT, DELAYED_PRICES, HISTORY_CHARTS,
                                 EVENTS_CALENDAR, FII_DII, MARKET_EVENT_WARNING, STRATEGY_PRICE_HISTORY)

PREFIX = "OFO_HELD_"
REF_SUFFIX = "_REF"
OPEN_ENVIRONMENTS = frozenset({"development", "test"})
_TRUE = {"1", "true", "yes", "on"}


class HeldSwitchError(ValueError):
    """An unknown switch name, or a configuration that turns a held feature on without a recorded reference."""


def _check_name(name: str) -> str:
    if name not in SWITCH_NAMES:
        raise HeldSwitchError(f"unknown held switch {name!r}")
    return name


def _variable(name: str) -> str:
    return PREFIX + _check_name(name).upper()


def _read(environ: Mapping[str, str] | None = None) -> tuple[str | None, Mapping[str, str]]:
    """THE one place the configuration is read: (APP_ENV, the process environment). Unreadable -> (None, {})."""
    try:
        return (app_env() if environ is None else environ.get("APP_ENV")), (os.environ if environ is None else environ)
    except (ValueError, OSError):  # a bad .env: every held feature is off
        return None, {}


def _is_on(name: str, env: str | None, environ: Mapping[str, str]) -> bool:
    if env in OPEN_ENVIRONMENTS:
        return True
    variable = _variable(name)
    wanted = environ.get(variable, "").strip().lower() in _TRUE
    return wanted and bool(environ.get(variable + REF_SUFFIX, "").strip())


def held_on(name: str, environ: Mapping[str, str] | None = None) -> bool:
    """True when the held feature ``name`` is on. Raises ``HeldSwitchError`` for a name outside the closed list.
    ``environ`` is for tests that load a production configuration; the app passes nothing."""
    _check_name(name)
    env, source = _read(environ)
    return _is_on(name, env, source)


def features_on(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """The held features that are on (the browser hides every other one: absent, not greyed)."""
    env, source = _read(environ)
    return tuple(name for name in SWITCH_NAMES if _is_on(name, env, source))


def require_valid_configuration(environ: Mapping[str, str] | None = None) -> None:
    """Start-up check: refuse a switch on without a reference, or an ``OFO_HELD_*`` variable of an unknown name."""
    _, source = _read(environ)
    known = {_variable(n) for n in SWITCH_NAMES}
    for key in source:
        if not key.startswith(PREFIX):
            continue
        base = key[: -len(REF_SUFFIX)] if key.endswith(REF_SUFFIX) else key
        if base not in known:
            raise HeldSwitchError(f"{key} names no held switch (known: {sorted(known)})")
    for name in SWITCH_NAMES:
        variable = _variable(name)
        if source.get(variable, "").strip().lower() in _TRUE and not source.get(variable + REF_SUFFIX, "").strip():
            raise HeldSwitchError(f"{variable} is on without a recorded reference ({variable}{REF_SUFFIX})")
