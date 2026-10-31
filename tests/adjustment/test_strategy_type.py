"""GC-ADJ2 step 1C item 1: the template -> playbook type map is data, closed to the catalogue and the twelve keys,
and ``type_of`` fails closed (B4 c) on any shape the matcher cannot name."""
from __future__ import annotations

import datetime
import json
import pathlib
from decimal import Decimal as D

import pytest
from ofo.adjustment import strategy_type as st
from ofo.adjustment.playbook_types import TYPE_KEYS
from ofo.engine.legs import Action, Instrument, Leg
from ofo.strategy.loader import load_templates

FIX = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "adjust_scenarios"
EXPIRY = datetime.date(2026, 11, 9)


def _legs(sid: str) -> list[Leg]:
    doc = json.loads((FIX / f"{sid}.json").read_text(encoding="utf-8"))
    return [Leg(Action(x["side"]), Instrument(x["type"]), D(x["strike"]), datetime.date.fromisoformat(x["expiry"]),
                x["quantity"], D(x["entry"])) for x in doc["position"]["legs"]]


def test_every_mapped_id_is_a_catalogue_template_and_every_value_one_of_the_twelve():
    ids = {t.id for t in load_templates()}
    mapping = st.template_types()
    assert set(mapping) <= ids, set(mapping) - ids
    assert set(mapping.values()) <= set(TYPE_KEYS)
    assert mapping["iron_condor"] == "ic"


def test_an_unknown_type_value_is_refused_at_load(tmp_path, monkeypatch):
    bad = tmp_path / "t.json"
    bad.write_text('{"iron_condor": "condorish"}', encoding="utf-8")
    monkeypatch.setattr(st, "TEMPLATE_TYPES_PATH", bad)
    st.template_types.cache_clear()
    try:
        with pytest.raises(ValueError, match="condorish"):
            st.template_types()
    finally:
        st.template_types.cache_clear()


def test_adj02_iron_condor_is_ic():
    assert st.type_of(_legs("ADJ-02"), D("23420"), D("50")) == "ic"


@pytest.mark.parametrize(("spot", "gap"), [(None, D("50")), (D("23420"), None), (D("0"), D("50")), (D("23420"), D("0"))])
def test_missing_spot_or_gap_is_generic(spot, gap):
    assert st.type_of(_legs("ADJ-02"), spot, gap) is None


def test_custom_shape_and_off_grid_strike_are_generic():
    legs = _legs("ADJ-02")
    assert st.type_of(legs[:3], D("23420"), D("50")) is None  # three legs of a condor: Custom
    assert st.type_of(legs, D("23420"), D("300")) is None  # strikes off a 300 grid: the matcher cannot place them
    assert st.type_of([], D("23420"), D("50")) is None


def test_a_template_the_map_does_not_name_is_generic():
    jade = [t for t in load_templates() if t.id == "jade_lizard"]
    assert "jade_lizard" not in st.template_types()
    legs = [Leg(Action.SELL, Instrument.PE, D("23300"), EXPIRY, 65, D("50")),
            Leg(Action.SELL, Instrument.CE, D("23500"), EXPIRY, 65, D("50")),
            Leg(Action.BUY, Instrument.CE, D("23600"), EXPIRY, 65, D("20"))]
    assert st.type_of(legs, D("23400"), D("50"), jade) is None
