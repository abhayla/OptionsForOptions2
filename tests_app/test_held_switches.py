"""W-125 (REQ-079 AC-1, AC-11; REQ-082 AC-1, AC-7): the held-feature switch.

Core proof (step 1): with APP_ENV=production, a held switch set on WITHOUT a recorded permission reference makes the
application refuse to start; in development the same switch reads on. Pinned tables (exact):
- APP_ENV exactly ``development`` or ``test`` -> every held feature on.
- any other APP_ENV (production, staging, unset, ``Test``, `` test ``) -> on only with the setting in 1/true/yes/on
  AND a non-blank reference.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from ofo_app import held_switches as hs
from ofo_app.main import create_app

PROD = {"APP_ENV": "production"}


def _env(app_env, **extra):
    return {**({} if app_env is None else {"APP_ENV": app_env}), **extra}


def test_core_production_without_reference_refuses_to_start_and_development_reads_on(monkeypatch, tmp_path):
    """Core proof: production + switch on + no reference -> create_app() raises; development -> on."""
    monkeypatch.chdir(tmp_path)  # no .env
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OFO_HELD_PLATFORM_STRIKES", "on")
    monkeypatch.delenv("OFO_HELD_PLATFORM_STRIKES_REF", raising=False)
    with pytest.raises(hs.HeldSwitchError):
        create_app()
    assert hs.held_on(hs.PLATFORM_STRIKES) is False
    monkeypatch.setenv("APP_ENV", "development")
    assert hs.held_on(hs.PLATFORM_STRIKES) is True


@pytest.mark.parametrize("app_env", ["development", "test"])
def test_ac1_open_environments_have_every_held_feature_on(app_env):
    """AC-1 (REQ-079, REQ-082): development and test read every switch on."""
    assert hs.features_on(_env(app_env)) == hs.SWITCH_NAMES


@pytest.mark.parametrize("app_env", ["production", "staging", None, "Test", " test ", "testing", "", "DEVELOPMENT"])
def test_ac1_every_other_environment_is_off_without_a_permission(app_env):
    """AC-1: any environment that is not exactly development/test is off, whatever else is set."""
    assert hs.features_on(_env(app_env)) == ()


@pytest.mark.parametrize("ref", ["", "   ", "\t"])
def test_ac11_on_with_an_empty_or_blank_reference_stays_off_and_is_refused_at_start(ref):
    """REQ-079 AC-11 / REQ-082 AC-7 (attack case): setting on, reference empty or whitespace -> off + refused."""
    env = {**PROD, "OFO_HELD_PROBABILITY_OF_PROFIT": "on", "OFO_HELD_PROBABILITY_OF_PROFIT_REF": ref}
    assert hs.held_on(hs.PROBABILITY_OF_PROFIT, env) is False
    with pytest.raises(hs.HeldSwitchError):
        hs.require_valid_configuration(env)


def test_ac11_a_reference_without_the_setting_stays_off():
    """Attack case: reference present but switch off -> off."""
    env = {**PROD, "OFO_HELD_PLATFORM_STRIKES_REF": "Q211-2026-11-01"}
    assert hs.held_on(hs.PLATFORM_STRIKES, env) is False
    hs.require_valid_configuration(env)


@pytest.mark.parametrize("value", ["1", "true", "YES", " On "])
def test_ac1_setting_plus_reference_turns_only_that_feature_on(value):
    """AC-1: production with the setting AND a reference -> that one feature on, the others off."""
    env = {**PROD, "OFO_HELD_PLATFORM_STRIKES": value, "OFO_HELD_PLATFORM_STRIKES_REF": "Q211-written"}
    assert hs.features_on(env) == (hs.PLATFORM_STRIKES,)
    hs.require_valid_configuration(env)


@pytest.mark.parametrize("value", ["0", "off", "no", "false", "maybe", ""])
def test_ac1_a_setting_that_is_not_true_is_off_even_with_a_reference(value):
    """AC-1: only 1/true/yes/on count as on."""
    env = {**PROD, "OFO_HELD_FII_DII": value, "OFO_HELD_FII_DII_REF": "x"}
    assert hs.held_on(hs.FII_DII, env) is False


def test_an_unknown_switch_name_raises():
    """Attack case: unknown name raises (held_on) and an OFO_HELD_ variable of an unknown name is refused at start."""
    with pytest.raises(hs.HeldSwitchError):
        hs.held_on("platform_strike", PROD)
    with pytest.raises(hs.HeldSwitchError):
        hs.require_valid_configuration({**PROD, "OFO_HELD_PLATFORM_STRIKE": "on", "OFO_HELD_PLATFORM_STRIKE_REF": "x"})


def test_an_unreadable_environment_is_off(monkeypatch):
    """Answer state 'setting unreadable': a bad .env (ValueError from app_env) -> off."""
    def broken():
        raise ValueError("bad .env")
    monkeypatch.setattr(hs, "app_env", broken)
    assert hs.features_on() == ()


@pytest.fixture
def prod_app(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "production")
    for name in hs.SWITCH_NAMES:
        monkeypatch.delenv(f"OFO_HELD_{name.upper()}", raising=False)
        monkeypatch.delenv(f"OFO_HELD_{name.upper()}_REF", raising=False)
    return create_app()


async def _features(app, **kwargs):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        return (await client.get("/features", **kwargs)).json()


async def test_ac1_features_lists_nothing_in_production(prod_app):
    """AC-1 / REQ-082 AC-1: production answers an empty list: the browser shows nothing for a held feature."""
    assert (await _features(prod_app))["held"] == []


async def test_ac11_a_request_cannot_turn_a_switch_on(prod_app):
    """Attack case: a header, a query value or a cookie naming a switch changes nothing."""
    body = await _features(prod_app, params={"OFO_HELD_PLATFORM_STRIKES": "on", "held": "platform_strikes"},
                           headers={"OFO_HELD_PLATFORM_STRIKES": "on", "X-Held": "platform_strikes"},
                           cookies={"OFO_HELD_PLATFORM_STRIKES": "on"})
    assert body["held"] == []


async def test_ac1_switch_is_re_read_from_the_one_function(monkeypatch, prod_app):
    """Attack case: flipped at runtime -> the next request sees it, and only through held_switches."""
    monkeypatch.setenv("OFO_HELD_PROBABILITY_OF_PROFIT", "on")
    monkeypatch.setenv("OFO_HELD_PROBABILITY_OF_PROFIT_REF", "Q211-label")
    assert (await _features(prod_app))["held"] == ["probability_of_profit"]


async def test_ac1_features_in_development_lists_all(monkeypatch, tmp_path):
    """AC-1: development lists every held feature."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("APP_ENV", "development")
    assert tuple((await _features(create_app()))["held"]) == hs.SWITCH_NAMES
