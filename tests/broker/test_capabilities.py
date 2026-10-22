"""REQ-117 AC-1, AC-2, AC-4 (W-132): the broker declares a closed set of named capability flags, each with the source
and date it rests on, and a flag that is missing, unknown or cannot be loaded counts as OFF (fail closed).

Core proof (step 1): remove ``basket_margin_quote`` from the Zerodha set and the feature that asks it is hidden with a
plain reason (``feature_state``); the same for an unknown name and for a flag source that fails to load.
"""
from __future__ import annotations

import datetime
import json
import pathlib
from collections.abc import Callable
from typing import Any

import pytest

from ofo.broker.capabilities import (
    CAPABILITY_NAMES,
    Capability,
    CapabilityLoadError,
    CapabilitySet,
    MARGIN_LINE_HIDDEN_REASON,
    feature_state,
    is_supported,
    load_capabilities,
    load_or_off,
)
from ofo_app.kite_capabilities import ZERODHA_DECLARED, load_zerodha_capabilities

ROOT = pathlib.Path(__file__).resolve().parents[2]
SEVEN = ("basket_page_orders", "broker_held_triggers", "intraday_product", "order_update_stream", "funds_read",
         "positions_read", "basket_margin_quote")  # REQ-117 AC-1, copied from the requirement text
DAY = datetime.date(2026, 10, 22)


def _declared_without(name: str) -> dict[str, Any]:
    return {k: v for k, v in ZERODHA_DECLARED.items() if k != name}


def test_core_removing_basket_margin_quote_hides_the_margin_line_with_a_plain_reason() -> None:
    """AC-4 core: with the flag the margin line is shown; without it (removed, unknown name, unloadable source) it is
    hidden and the reason is plain and names no broker."""
    shown = feature_state(load_capabilities(ZERODHA_DECLARED), Capability.BASKET_MARGIN_QUOTE, MARGIN_LINE_HIDDEN_REASON)
    assert (shown.visible, shown.reason) == (True, None)
    removed = feature_state(load_capabilities(_declared_without("basket_margin_quote")), Capability.BASKET_MARGIN_QUOTE, MARGIN_LINE_HIDDEN_REASON)
    assert (removed.visible, removed.reason) == (False, MARGIN_LINE_HIDDEN_REASON)
    unknown = feature_state(load_capabilities(ZERODHA_DECLARED), "basket_margin_quote_v2", MARGIN_LINE_HIDDEN_REASON)
    assert (unknown.visible, unknown.reason) == (False, MARGIN_LINE_HIDDEN_REASON)

    def broken() -> CapabilitySet:
        raise OSError("flag file unreadable")

    failed = feature_state(load_or_off(broken), Capability.BASKET_MARGIN_QUOTE, MARGIN_LINE_HIDDEN_REASON)
    assert (failed.visible, failed.reason) == (False, MARGIN_LINE_HIDDEN_REASON)
    assert MARGIN_LINE_HIDDEN_REASON == "Margin from the broker is not available for this account."
    assert "zerodha" not in MARGIN_LINE_HIDDEN_REASON.lower() and "kite" not in MARGIN_LINE_HIDDEN_REASON.lower()


def test_ac1_the_flag_set_is_closed_and_exactly_the_seven_named_flags() -> None:
    """AC-1: exactly the seven named flags, nothing more, nothing less."""
    assert tuple(c.value for c in Capability) == SEVEN
    assert CAPABILITY_NAMES == frozenset(SEVEN)


def test_ac2_zerodha_declares_every_flag_with_a_source_and_a_date() -> None:
    """AC-2: each flag carries the source it rests on and a date; the set covers all seven."""
    caps = load_zerodha_capabilities()
    assert set(ZERODHA_DECLARED) == set(SEVEN)
    for name in SEVEN:
        value = caps.value(name)
        assert value is not None and value.source.strip() and value.as_of == DAY
        assert type(value.as_of) is datetime.date
    assert {n: caps.value(n).supported for n in SEVEN} == {  # type: ignore[union-attr]
        "basket_page_orders": True, "broker_held_triggers": False, "intraday_product": True,
        "order_update_stream": True, "funds_read": True, "positions_read": True, "basket_margin_quote": True}


def test_ac2_broker_held_triggers_is_off_and_nothing_reads_it_as_on() -> None:
    """AC-2 (attack 5): the trigger flag is off until REQ-100 AC-1's core proof, and its source says why."""
    caps = load_zerodha_capabilities()
    assert is_supported(caps, "broker_held_triggers") is False
    assert is_supported(caps, Capability.BROKER_HELD_TRIGGERS) is False
    assert "REQ-100 AC-1" in caps.value("broker_held_triggers").source  # type: ignore[union-attr]
    for path in (ROOT / "backend").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name in ("capabilities.py", "kite_capabilities.py", "broker_capabilities.py"):
            continue  # the declaration, its Zerodha values and the read-only route that lists all seven
        assert "broker_held_triggers" not in text and "BROKER_HELD_TRIGGERS" not in text, path


def test_ac2_every_zerodha_source_is_a_repo_path_that_exists_or_a_kite_docs_address() -> None:
    """AC-2: a repo-path source names a file that exists (a typed-from-memory path fails here)."""
    for name, (_, source, _) in ZERODHA_DECLARED.items():
        if source.startswith("https://kite.trade/docs/"):
            continue
        path_part = source.split(" ")[0]
        if path_part.startswith("REQ-"):
            continue
        assert (ROOT / path_part).exists(), (name, source)


def test_ac2_the_profile_source_really_lists_mis() -> None:
    """AC-2: the intraday_product source is the real profile reply and it lists MIS (read here, not assumed)."""
    reply = json.loads((ROOT / "tests/fixtures/kite_replies/user-profile-2026-10-22-redacted.json").read_text("utf-8"))
    assert "MIS" in reply["data"]["products"]
    assert "user-profile-2026-10-22-redacted.json" in ZERODHA_DECLARED["intraday_product"][1]


# --- AC-4: fail closed ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", [*SEVEN, "", "unknown_flag", "BASKET_MARGIN_QUOTE", None, 7, ("a",), b"funds_read"])
def test_ac4_a_missing_or_unknown_name_is_off_and_never_raises(name: object) -> None:
    """AC-4: an empty set answers False for every name, and the full set answers False for every non-flag name."""
    assert is_supported(CapabilitySet({}), name) is False
    if name not in SEVEN:
        assert is_supported(load_zerodha_capabilities(), name) is False


@pytest.mark.parametrize("flags", [None, {}, [], "funds_read", 5, object(), {"funds_read": True}])
def test_ac4_a_set_that_is_not_a_loaded_set_is_off_for_every_flag(flags: object) -> None:
    """AC-4: anything but a CapabilitySet (None, a bare dict claiming a flag on) is off - a caller cannot hand in a verdict."""
    assert [is_supported(flags, n) for n in SEVEN] == [False] * 7


def test_ac4_removing_each_flag_turns_exactly_that_flag_off() -> None:
    """AC-4: for each of the seven, a set without it answers off for it and on/off unchanged for the other six."""
    full = load_zerodha_capabilities()
    for name in SEVEN:
        part = load_capabilities(_declared_without(name))
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
    """AC-4 (attack 3): one bad entry refuses the load; ``load_or_off`` then gives every flag off, none half-on."""
    raw = {**ZERODHA_DECLARED, "funds_read": make()}
    with pytest.raises(CapabilityLoadError):
        load_capabilities(raw)
    off = load_or_off(lambda: load_capabilities(raw))
    assert [is_supported(off, n) for n in SEVEN] == [False] * 7


@pytest.mark.parametrize("raw", [None, [], "x", 3, [("funds_read", _entry())], {"funds_read": None},
                                 {"funds_read": _entry()[:2]}, {"funds_read": "on"}, {"funds_read": [True]},
                                 {"funds_reed": _entry()}, {7: _entry()}, {"funds_read": _entry(), "extra": _entry()}])
def test_ac4_malformed_data_is_refused_at_load(raw: object) -> None:
    """AC-4: not a mapping, entries of the wrong shape, an unknown or misspelled key: refused, never ignored."""
    with pytest.raises(CapabilityLoadError):
        load_capabilities(raw)  # type: ignore[arg-type]


def test_ac4_load_or_off_turns_every_kind_of_loader_failure_into_all_off() -> None:
    """AC-4: a loader that raises (any Exception) or returns the wrong type gives an all-off set, never an exception."""
    def boom() -> CapabilitySet:
        raise RuntimeError("boom")

    def wrong() -> CapabilitySet:
        return {"funds_read": True}  # type: ignore[return-value]

    for loader in (boom, wrong):
        caps = load_or_off(loader)
        assert isinstance(caps, CapabilitySet)
        assert [is_supported(caps, n) for n in SEVEN] == [False] * 7


def test_ac4_the_loaded_set_cannot_be_changed_from_outside() -> None:
    """AC-4: no public way to flip a flag on a loaded set (frozen)."""
    caps = load_zerodha_capabilities()
    with pytest.raises((AttributeError, TypeError)):
        caps.flags = {}  # type: ignore[misc]
    with pytest.raises(TypeError):
        caps.flags["funds_read"] = None  # type: ignore[index]
    assert is_supported(caps, "funds_read") is True
