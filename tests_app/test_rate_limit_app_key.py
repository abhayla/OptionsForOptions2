"""REQ-118 AC-1 (F-60, one bucket per group for the whole app), review F2 item 4 / attack 4: the app key comes from the
broker settings - a key that is only in the ``.env`` file (not in the process environment) still makes the keyless
instrument download share the app's 'other' bucket, never a stray '-' bucket that would double the app's call rate."""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from fake_pacer import FakePacer
from ofo.broker import rate_limit as rl
from ofo_app.broker_config import BrokerSettings, load_broker_config
from ofo_app.main import create_app

ENV_KEY = "envfilekey1"


def _env_file(tmp_path: Path) -> Path:
    env = tmp_path / ".env"
    env.write_text("\n".join([
        f"KITE_API_KEY={ENV_KEY}", "KITE_API_SECRET=secret-in-env-file",
        "KITE_REDIRECT_URL=http://127.0.0.1:8000/kite/callback", "FRONTEND_ORIGIN=http://127.0.0.1:5173",
        "KITE_EXPECTED_USER_ID=AB1234", f"BROKER_TOKEN_KEY={base64.urlsafe_b64encode(os.urandom(32)).decode()}",
    ]) + "\n", encoding="utf-8")
    return env


def test_f2_attack4_a_key_only_in_the_env_file_makes_the_instrument_download_share_the_apps_bucket(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Attack 4: no KITE_API_KEY in the process environment (the limiter would key keyless calls on '-'); the app is
    built from a settings file holding it; the keyless /instruments request then takes the app's slot in 'other'."""
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    limiter = rl.RateLimiter(pacer=FakePacer(auto=True))  # what a process without the key in its environment builds
    assert limiter._app_key == ""
    with rl.use(limiter):
        create_app(load_broker_config(BrokerSettings(_env_file=_env_file(tmp_path))))  # type: ignore[call-arg]
        key, _ = rl.identity(None, None)  # the instrument download names no key
        assert key == rl.NO_KEY
        rl.acquire(rl.GROUP_OTHER, key)
        rl.acquire(rl.GROUP_OTHER, ENV_KEY)
    assert list(limiter._buckets) == [(rl.GROUP_OTHER, ENV_KEY)]  # one bucket: the app's, never ("other", "-")


def test_f2_item4_the_app_key_must_be_plain_text() -> None:
    """Fail closed: the limiter's app key is a plain str."""
    with pytest.raises(TypeError):
        rl.RateLimiter().set_app_key(None)  # type: ignore[arg-type]
