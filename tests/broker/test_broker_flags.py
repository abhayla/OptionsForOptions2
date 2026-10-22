"""REQ-117 AC-1, AC-2, AC-4 (W-132): the broker declares a closed set of named flags, each with the source and date it
rests on, and a flag that is missing, unknown or cannot be loaded counts as OFF (fail closed).

Core proof (step 1): remove ``basket_margin_quote`` from the Zerodha flag set and the flag answers off (so the margin
line, which asks it, is hidden: ``frontend/tests/outcome-margin.test.js`` shows the line and its plain reason); the same
for an unknown name and for a flag source that fails to load.
"""
from __future__ import annotations

import datetime
import json
import pathlib
from collections.abc import Callable
from typing import Any

import pytest
from ofo.broker import kite_flags
from ofo.broker.flags import (
    FLAG_NAMES,
    BrokerFlag,
    FlagLoadError,
    FlagSet,
    flags_or_off,
    is_supported,
    load_flags,
)
from ofo.broker.kite_flags import declared, load_zerodha_flags

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEVEN = ("basket_page_orders", "broker_held_triggers", "intraday_product", "order_update_stream", "funds_read",
         "positions_read", "basket_margin_quote")  # REQ-117 AC-1, copied from the requirement text
DAY = datetime.date(2026, 10, 22)


def _declared_without(name: str) -> dict[str, Any]:
    return {k: v for k, v in declared().items() if k != name}


def test_core_removing_basket_margin_quote_turns_that_flag_off_and_only_that_flag() -> None:
    """AC-4 core: with the flag the margin quote is on; removed, unknown name, or an unloadable source -> off."""
    assert is_supported(load_flags(declared()), BrokerFlag.BASKET_MARGIN_QUOTE) is True
    removed = load_flags(_declared_without("basket_margin_quote"))
    assert is_supported(removed, BrokerFlag.BASKET_MARGIN_QUOTE) is False
    assert is_supported(removed, "basket_margin_quote") is False
    assert is_supported(removed, "funds_read") is True  # the other flags are untouched
    assert is_supported(load_flags(declared()), "basket_margin_quote_v2") is False

    def broken() -> FlagSet:
        raise OSError("flag file unreadable")

    assert is_supported(flags_or_off(broken), BrokerFlag.BASKET_MARGIN_QUOTE) is False


def test_ac1_the_flag_set_is_closed_and_exactly_the_seven_named_flags() -> None:
    """AC-1: exactly the seven named flags, nothing more, nothing less."""
    assert [c.value for c in BrokerFlag] == list(SEVEN)
    assert set(FLAG_NAMES) == set(SEVEN)


def test_ac2_zerodha_declares_every_flag_with_a_source_and_a_date() -> None:
    """AC-2: each flag carries the source it rests on and a date; the set covers all seven; held triggers are off."""
    flags = load_zerodha_flags()
    assert set(declared()) == set(SEVEN)
    for name in SEVEN:
        value = flags.value(name)
        assert value is not None and value.source.strip() and value.as_of == DAY
        assert type(value.as_of) is datetime.date
    assert {n: flags.value(n).supported for n in SEVEN} == {  # type: ignore[union-attr]
        "basket_page_orders": True, "broker_held_triggers": False, "intraday_product": True,
        "order_update_stream": True, "funds_read": True, "positions_read": True, "basket_margin_quote": True}


def test_ac2_broker_held_triggers_is_off_and_says_why() -> None:
    """AC-2 (attack 5): the trigger flag is off until REQ-100 AC-1's core proof, and its source names that gate."""
    flags = load_zerodha_flags()
    assert is_supported(flags, "broker_held_triggers") is False
    assert is_supported(flags, BrokerFlag.BROKER_HELD_TRIGGERS) is False
    assert "REQ-100 AC-1" in flags.value("broker_held_triggers").source  # type: ignore[union-attr]


def test_ac2_every_zerodha_source_is_a_repo_path_that_exists_or_a_kite_docs_address() -> None:
    """AC-2: a repo-path source names a file that exists (a typed-from-memory path fails here)."""
    for name, (_, source, _) in declared().items():
        if source.startswith(("https://kite.trade/docs/", "REQ-")):
            continue
        assert (ROOT / source.split(" ")[0]).exists(), (name, source)


def test_ac2_the_profile_source_really_lists_mis() -> None:
    """AC-2: the intraday_product source is the real profile reply and it lists MIS (read here, not assumed)."""
    reply = json.loads((ROOT / "tests/fixtures/kite_replies/user-profile-2026-10-22-redacted.json").read_text("utf-8"))
    assert "MIS" in reply["data"]["products"]
    assert "user-profile-2026-10-22-redacted.json" in declared()["intraday_product"][1]


# --- AC-4: fail closed ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", [*SEVEN, "", "unknown_flag", "BASKET_MARGIN_QUOTE", None, 7, ("a",), b"funds_read"])
def test_ac4_a_missing_or_unknown_name_is_off_and_never_raises(name: object) -> None:
    """AC-4: an empty set answers False for every name, and the full set answers False for every non-flag name."""
    assert is_supported(FlagSet({}), name) is False
    if name not in SEVEN:
        assert is_supported(load_zerodha_flags(), name) is False


@pytest.mark.parametrize("flags", [None, {}, [], "funds_read", 5, object(), {"funds_read": True}])
def test_ac4_a_set_that_is_not_a_loaded_set_is_off_for_every_flag(flags: object) -> None:
    """AC-4: anything but a FlagSet (None, a bare dict claiming a flag on) is off: a caller cannot hand in a verdict."""
    assert [is_supported(flags, n) for n in SEVEN] == [False] * 7


def test_ac4_removing_each_flag_turns_exactly_that_flag_off() -> None:
    """AC-4: for each of the seven, a set without it answers off for it and on/off unchanged for the other six."""
    full = load_zerodha_flags()
    for name in SEVEN:
        part = load_flags(_declared_without(name))
        assert is_supported(part, name) is False
        for other in SEVEN:
            if other != name:
                assert is_supported(part, other) is is_supported(full, other)


def _entry(**over: Any) -> tuple[Any, Any, Any]:
    base: dict[str, Any] = {"on": True, "source": "tests/x.py", "date": DAY}
    base.update(over)
    return base["on"], base["source"], base["date"]


BAD_ENTRIES: list[tuple[str, Callable[[], Any]]] = [
    ("no source", lambda: _entry(source="")),
    ("blank source", lambda: _entry(source="   ")),
    ("source None", lambda: _entry(source=None)),
    ("source not str", lambda: _entry(source=5)),
    ("no date", lambda: _entry(date=None)),
    ("date as text", lambda: _entry(date="2026-10-22")),
    ("datetime not date", lambda: _entry(date=datetime.datetime(2026, 10, 22, 9, 0, tzinfo=datetime.UTC))),
    ("on as int", lambda: _entry(on=1)),
    ("on as text", lambda: _entry(on="true")),
    ("on None", lambda: _entry(on=None)),
]


@pytest.mark.parametrize(("label", "make"), BAD_ENTRIES, ids=[b[0] for b in BAD_ENTRIES])
def test_ac4_an_entry_without_a_proper_source_or_date_refuses_the_whole_load_and_every_flag_is_off(
        label: str, make: Callable[[], Any]) -> None:
    """AC-4 (attack 3): one bad entry refuses the load; ``flags_or_off`` then gives every flag off, none half-on."""
    raw = {**declared(), "funds_read": make()}
    with pytest.raises(FlagLoadError):
        load_flags(raw)
    off = flags_or_off(lambda: load_flags(raw))
    assert [is_supported(off, n) for n in SEVEN] == [False] * 7


@pytest.mark.parametrize("raw", [None, [], "x", 3, [("funds_read", _entry())], {"funds_read": None},
                                 {"funds_read": _entry()[:2]}, {"funds_read": "on"}, {"funds_read": [True]},
                                 {"funds_reed": _entry()}, {7: _entry()}, {"funds_read": _entry(), "extra": _entry()}])
def test_ac4_malformed_data_is_refused_at_load(raw: object) -> None:
    """AC-4: not a mapping, entries of the wrong shape, an unknown or misspelled key: refused, never ignored."""
    with pytest.raises(FlagLoadError):
        load_flags(raw)  # type: ignore[arg-type]


def test_ac4_flags_or_off_turns_every_kind_of_loader_failure_into_all_off() -> None:
    """AC-4: a loader that raises (any Exception) or returns the wrong type gives an all-off set, never an exception."""
    def boom() -> FlagSet:
        raise RuntimeError("boom")

    def wrong() -> FlagSet:
        return {"funds_read": True}  # type: ignore[return-value]

    for loader in (boom, wrong):
        flags = flags_or_off(loader)
        assert isinstance(flags, FlagSet)
        assert [is_supported(flags, n) for n in SEVEN] == [False] * 7


def test_ac4_the_loaded_set_cannot_be_changed_from_outside() -> None:
    """AC-4: no public way to flip a flag on a loaded set (frozen, read-only mapping)."""
    flags = load_zerodha_flags()
    with pytest.raises((AttributeError, TypeError)):
        flags.flags = {}  # type: ignore[misc]
    with pytest.raises(TypeError):
        flags.flags["funds_read"] = None  # type: ignore[index]
    assert is_supported(flags, "funds_read") is True


# --- AC-4: the real flag FILE that cannot be loaded -------------------------------------------------------------------

def _file(tmp_path: pathlib.Path, text: str | bytes | None) -> pathlib.Path:
    path = tmp_path / "kite_flags.json"
    if isinstance(text, bytes):
        path.write_bytes(text)
    elif text is not None:
        path.write_text(text, encoding="utf-8")
    return path


GOOD = {"on": True, "source": "tests/x.py", "date": "2026-10-22"}
BAD_FILES = {
    "missing": None, "empty": "", "not json": "{nope", "not utf-8": b"\xff\xfe\x00{", "a list": "[]", "null": "null",
    "entry is a list": json.dumps({"funds_read": [True, "x", "2026-10-22"]}),
    "entry missing source": json.dumps({"funds_read": {"on": True, "date": "2026-10-22"}}),
    "entry has an extra key": json.dumps({"funds_read": {**GOOD, "note": "x"}}),
    "no date": json.dumps({"funds_read": {"on": True, "source": "x"}}),
    "date not a date": json.dumps({"funds_read": {**GOOD, "date": "22/10/2026"}}),
    "date with a time": json.dumps({"funds_read": {**GOOD, "date": "2026-10-22T09:00:00"}}),
    "date a number": json.dumps({"funds_read": {**GOOD, "date": 20261022}}),
    "on is text": json.dumps({"funds_read": {**GOOD, "on": "true"}}),
    "blank source": json.dumps({"funds_read": {**GOOD, "source": " "}}),
    "unknown flag": json.dumps({"funds_read": GOOD, "teleport": GOOD}),
}


@pytest.mark.parametrize("label", sorted(BAD_FILES))
def test_ac4_a_flag_file_that_cannot_be_loaded_gives_every_flag_off(
        tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, label: str) -> None:
    """AC-4 (attack 3): a missing, unreadable or malformed flag file refuses the load, and the fail-closed wrapper gives
    every flag off (none half-on, no exception to the caller)."""
    monkeypatch.setattr(kite_flags, "FLAG_FILE", _file(tmp_path, BAD_FILES[label]))
    with pytest.raises(FlagLoadError):
        load_zerodha_flags()
    flags = flags_or_off(load_zerodha_flags)
    assert [is_supported(flags, n) for n in SEVEN] == [False] * 7


def test_ac4_a_partial_flag_file_loads_and_the_missing_flags_are_off(
        tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-4: a well-formed file that lacks flags is a valid set; the lacking flags are off, the present one is on."""
    monkeypatch.setattr(kite_flags, "FLAG_FILE", _file(tmp_path, json.dumps({"funds_read": GOOD})))
    flags = load_zerodha_flags()
    assert [is_supported(flags, n) for n in SEVEN] == [n == "funds_read" for n in SEVEN]
