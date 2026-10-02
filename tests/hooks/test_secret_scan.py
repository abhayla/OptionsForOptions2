"""secret_scan hook: real-looking secrets are refused, placeholders pass, input shapes from Write/Edit/MultiEdit work.

Fake secrets are built by joining pieces so this file never contains a literal the hook would refuse.
"""
import io
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "hooks"))
import secret_scan  # noqa: E402

AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
GH = "ghp" + "_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
DB = "postgresql+asyncpg://ofo_app:" + "S3cr" + "etP4ss" + "@127.0.0.1:5432/ofo_test"
KEY = "api_secret = '" + "q8w7e6r5t4y3u2i1o0p9" + "'"
PWD = "password = '" + "Hunter2Hunter2" + "'"


@pytest.mark.parametrize("text,label", [
    (AWS, "AWS access key id"),
    (GH, "GitHub token"),
    (DB, "database URL with a password"),
    (KEY, "API key or token assignment"),
    (PWD, "hardcoded password"),
])
def test_real_looking_secret_is_found(text, label):
    assert label in secret_scan.scan(f"before\n{text}\nafter")


@pytest.mark.parametrize("text", [
    "postgresql+asyncpg://ofo_app:${DB_PASSWORD}@127.0.0.1:5432/ofo_test",
    "postgresql://user:<password>@localhost/db",
    "api_key = 'your_api_key_goes_here_12'",
    "password = 'changeme-in-production'",
    "DATABASE_URL=postgresql+asyncpg://localhost/ofo_test",
    "no secrets here, just prose about tokens and passwords",
])
def test_placeholder_or_prose_passes(text):
    assert secret_scan.scan(text) == []


def _run(monkeypatch, payload):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    return secret_scan.main()


def test_write_with_secret_is_blocked(monkeypatch, capsys):
    rc = _run(monkeypatch, {"tool_input": {"file_path": "docs/x.md", "content": DB}})
    assert rc == 2
    assert "database URL with a password" in capsys.readouterr().err


def test_edit_and_multiedit_shapes_are_scanned(monkeypatch):
    assert _run(monkeypatch, {"tool_input": {"file_path": "a.py", "new_string": KEY}}) == 2
    assert _run(monkeypatch, {"tool_input": {"file_path": "a.py", "edits": [{"new_string": "ok"}, {"new_string": GH}]}}) == 2


def test_clean_write_and_binary_and_bad_input_pass(monkeypatch):
    assert _run(monkeypatch, {"tool_input": {"file_path": "a.py", "content": "x = 1"}}) == 0
    assert _run(monkeypatch, {"tool_input": {"file_path": "logo.png", "content": AWS}}) == 0
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert secret_scan.main() == 0
