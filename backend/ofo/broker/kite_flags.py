"""What Zerodha can do, as named flags (REQ-117 AC-2, W-132; ADR-016 Zerodha is the authority).

The values are declared in ``kite_flags.json`` next to this module: each flag with on/off, the source it rests on and
the date it was checked. A source is a Kite docs address or a path in this repo (the real reply, or the module that
makes the call). ``broker_held_triggers`` stays OFF until REQ-100 AC-1's core proof has passed; turning it on is a
deliberate edit of that file, with the proof as its new source. The flags only describe Zerodha: feature code asks the
flag by name and never compares the broker's name (REQ-117 AC-3, ``tests/test_no_broker_name_in_feature_code.py``).
Nothing is fetched at runtime; a file that is missing, unreadable or malformed refuses the load (callers that must not
fail use ``flags_or_off``, which gives every flag off).
"""
from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Final

from ofo.broker.flags import FlagLoadError, FlagSet, load_flags

FLAG_FILE: Final = Path(__file__).with_name("kite_flags.json")
_ENTRY_KEYS: Final = frozenset({"on", "source", "date"})
#: the only date text accepted: Python's ``fromisoformat`` also takes '20261022', week dates and other ISO forms
_DAY_TEXT: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", re.ASCII)


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """A repeated key would silently let the last one win (a second ``on: true``); refuse it, so every flag is off."""
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate key in the flag file")
    return dict(pairs)


def declared() -> dict[str, tuple[bool, str, datetime.date]]:
    """The file's ``{name: (on, source, date)}``. Raises ``FlagLoadError`` for anything but the exact shape: an
    unreadable file, bad JSON, an entry not exactly ``on``/``source``/``date``, a date not YYYY-MM-DD."""
    try:
        data = json.loads(FLAG_FILE.read_text(encoding="utf-8"), object_pairs_hook=_no_duplicate_keys)
    except (OSError, ValueError) as error:  # ValueError covers JSON, UTF-8 decoding and duplicate-key errors
        raise FlagLoadError("the flag file cannot be read") from error
    if not isinstance(data, dict):
        raise FlagLoadError("the flag file must hold an object")
    out = {}
    for name, entry in data.items():
        if not isinstance(entry, dict) or set(entry) != _ENTRY_KEYS:
            raise FlagLoadError(f"flag {name}: expected exactly on, source and date")
        stamp = entry["date"]
        if not isinstance(stamp, str) or not _DAY_TEXT.fullmatch(stamp):
            raise FlagLoadError(f"flag {name}: the date is text YYYY-MM-DD")
        try:
            day = datetime.date.fromisoformat(stamp)
        except ValueError as error:
            raise FlagLoadError(f"flag {name}: the date is not a date") from error
        out[name] = (entry["on"], entry["source"], day)
    return out


def load_zerodha_flags() -> FlagSet:
    """Zerodha's declared flags. Raises ``FlagLoadError`` when the declaration is bad."""
    return load_flags(declared())


__all__ = ["FLAG_FILE", "declared", "load_zerodha_flags"]
