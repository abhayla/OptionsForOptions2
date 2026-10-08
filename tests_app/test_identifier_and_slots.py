"""W-024 round 10 item 4 (issue 30 round-9 MINOR): `Identifier` is a closed pattern, and the SlotType set is pinned."""

from __future__ import annotations

import pytest
from pydantic import ValidationError


def _out():
    from ofo_app.api_models import ApiModel, Identifier

    class Out(ApiModel):
        id: Identifier

    return Out


@pytest.mark.parametrize("value", ["access_token:abc123", "api_key=abc", "two words", "a\tb", "x" * 65, ""])
def test_identifier_refuses_pairs_whitespace_and_overlength(value):
    with pytest.raises(ValidationError):
        _out()(id=value)


@pytest.mark.parametrize("value", ["NIFTY26OCT22800PE", "ERR-1a2b", "leg_1", "v1.2", "x" * 64])
def test_identifier_accepts_closed_tokens(value):
    assert _out()(id=value).id == value


def test_identifier_max_is_stated():
    from ofo_app import api_models

    assert api_models.IDENTIFIER_MAX == 64


def _all_subclasses(cls):
    out = set()
    for sub in cls.__subclasses__():
        out.add(f"{sub.__module__}.{sub.__qualname__}")
        out |= _all_subclasses(sub)
    return out


PINNED_SLOT_TYPES = frozenset({
    *(f"ofo.errors.explanations.{n}" for n in (
        "Recorded", "Explained", "Quoted", "UserText", "Amount", "Days", "ClockHm", "InputLabels", "YesNo", "Values",
        "LegacyRecorded", "OpWords", "ActionWords", "MeasureWords", "DirectionWords", "FollowUpLabel", "InputLabel")),
    *(f"ofo.errors.gate_slots.{n}" for n in (
        "LegRef", "LegContract", "Date", "Strikes", "Rupees", "WorstCase", "VersionStateName", "VersionStates",
        "DataInputName", "DataHealthState", "ExecutionStatusName", "Symbol", "Clock", "ContractSymbol", "RiskRows",
        "OrderRef", "UnitsByContract")),
    *(f"ofo.errors.slots.{n}" for n in (
        "Money", "PnLMoney", "Int", "Count", "Time", "Instrument", "Code", "Underlying", "ExternalText")),
})


def test_the_slot_type_set_is_pinned():
    """A new SlotType (a new way for a value to reach a message) fails here until it is reviewed and added."""
    import ofo.errors  # noqa: F401  (loads every slot module)
    import ofo.errors.explanations  # noqa: F401
    import ofo.errors.gate_slots  # noqa: F401
    from ofo.errors.slots import SlotType

    found = {n for n in _all_subclasses(SlotType) if not n.startswith(("tests", "test_"))}
    assert found == PINNED_SLOT_TYPES
