"""Drift check (issue #207): docs/api/openapi.json is what the frontend proxy rewrite is derived from, so it must equal
the document the app really serves. No database is opened; the document is built without a request."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from ofo_app.broker_config import BrokerSettings, load_broker_config
from ofo_app.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_committed_openapi_matches_the_app():
    config = load_broker_config(BrokerSettings(
        KITE_API_KEY="placeholder", KITE_API_SECRET="placeholder",
        KITE_REDIRECT_URL="http://127.0.0.1:8000/kite/callback", KITE_EXPECTED_USER_ID="ZZ0000",
        BROKER_TOKEN_KEY=base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")))
    built = json.loads(json.dumps(create_app(config).openapi()))
    committed = json.loads((ROOT / "docs" / "api" / "openapi.json").read_text(encoding="utf-8"))
    assert committed == built, (
        "docs/api/openapi.json is stale (the frontend proxy rewrite reads it). Regenerate it with: "
        "python scripts/generate_openapi.py   and commit the result")
