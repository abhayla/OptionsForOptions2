"""REQ-117 AC-2 (W-132, attack 5): ``broker_held_triggers`` is off for Zerodha and nothing reads it as on.

REQ-100 (stop at Zerodha) does not exist yet. Until its AC-1 core proof has passed, no module may ask the flag: the only
files that may name it are the flag declaration, its Zerodha values and the read-only route that lists all seven. The
scan reads every ``.py``/``.json`` under ``backend/`` and ``.js``/``.vue`` under ``frontend/src`` (found from the
tree) and fails closed on a file it cannot decode. When REQ-100 binds the flag, its module is added here on purpose.
"""
from __future__ import annotations

import pathlib

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parents[2]
NAMES = ("broker_held_triggers", "BROKER_HELD_TRIGGERS", "brokerHeldTriggers")
#: Allow-list by path: the files that may name the flag (declaration, Zerodha values, the route that lists the seven,
#: the frontend's closed list of names).
MAY_NAME_IT = frozenset({
    "backend/ofo/broker/flags.py", "backend/ofo/broker/kite_flags.json", "backend/ofo/broker/kite_flags.py",
    "backend/ofo_app/routes/broker_capabilities.py",
    "frontend/src/lib/brokerCapabilities.js",
})
MIN_FILES = 300
SUFFIXES = frozenset({".py", ".json", ".js", ".vue", ".ts", ".mjs"})


def _files() -> list[pathlib.Path]:
    found = [p for folder in ("backend", "frontend/src") for p in (ROOT / folder).rglob("*")
             if p.is_file() and p.suffix in SUFFIXES and "node_modules" not in p.parts and "__pycache__" not in p.parts]
    assert len(found) > MIN_FILES  # the real tree; fewer means the wrong folder was read
    return found


def test_ac2_no_module_outside_the_allow_list_names_the_held_triggers_flag() -> None:
    """AC-2: nothing but the allow-listed files names the flag, so nothing can read it as on."""
    offenders = []
    for path in _files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            offenders.append(f"{rel}: cannot be read")
            continue
        if rel not in MAY_NAME_IT and any(n in text for n in NAMES):
            offenders.append(rel)
    assert offenders == []


def test_ac2_the_allow_list_files_exist() -> None:
    """AC-2: every allow-listed path is a real file (a renamed file cannot leave a dead exemption behind)."""
    assert [p for p in MAY_NAME_IT if not (ROOT / p).is_file()] == []
