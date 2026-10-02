"""AC-1: several preferred strategy types, all with equal priority; unknown ids refused.

Spec: REQ-068 AC-1; REQ-025 AC-4 ("A preferred strategy is never silently forced or auto-selected.").
Template ids come from the real catalogue loader, never a typed list.
"""
from __future__ import annotations

import dataclasses

import pytest

from ofo.strategy.loader import load_templates
from ofo.strategy.preferences import StrategyPreferences, known_template_ids

IDS = [t.id for t in load_templates()]
A, B, C = "iron_condor", "bull_call_spread", "short_straddle"


def test_core_several_preferred_equal_priority_and_unknown_refused():
    """AC-1: core proof on real ids."""
    assert {A, B, C} <= set(IDS)
    prefs = StrategyPreferences.of([A, B, C])
    assert prefs.template_ids == frozenset({A, B, C})
    assert StrategyPreferences.of([C, A, B]) == prefs  # no order, so no priority
    assert hash(StrategyPreferences.of([C, A, B])) == hash(prefs)
    with pytest.raises(ValueError, match="unknown"):
        prefs.add("not_a_real_strategy")


def test_known_ids_come_from_the_loader():
    """AC-1: the accepted ids are exactly the loaded catalogue."""
    assert known_template_ids() == frozenset(IDS)
    assert len(IDS) >= 10


def test_every_catalogue_id_is_accepted():
    """AC-1: all real templates can be preferred together (maximum legal size)."""
    assert len(StrategyPreferences.of(IDS).template_ids) == len(IDS)


def test_add_and_remove_return_new_instances():
    """AC-1: immutable value object."""
    empty = StrategyPreferences()
    one = empty.add(A)
    two = one.add(B)
    assert empty.template_ids == frozenset()
    assert one.template_ids == frozenset({A})
    assert two.template_ids == frozenset({A, B})
    back = two.remove(A)
    assert back.template_ids == frozenset({B})
    assert two.template_ids == frozenset({A, B})
    assert back is not two


def test_frozen_no_raw_state_change():
    """AC-1: a raw attribute assignment is refused."""
    prefs = StrategyPreferences.of([A])
    with pytest.raises(dataclasses.FrozenInstanceError):
        prefs.template_ids = frozenset({B})  # type: ignore[misc]
    with pytest.raises(AttributeError):
        prefs.template_ids.add(B)  # type: ignore[attr-defined]


def test_direct_constructor_cannot_bypass_validation():
    """AC-1: unknown ids or a non-frozenset through the constructor are refused."""
    with pytest.raises(ValueError, match="unknown"):
        StrategyPreferences(frozenset({"nope"}))
    with pytest.raises(TypeError):
        StrategyPreferences([A])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        StrategyPreferences(frozenset({1}))  # type: ignore[arg-type]


def test_duplicates_refused():
    """AC-1: the same id twice is refused everywhere."""
    with pytest.raises(ValueError, match="duplicate"):
        StrategyPreferences.of([A, A])
    with pytest.raises(ValueError, match="already"):
        StrategyPreferences.of([A]).add(A)
    with pytest.raises(ValueError, match="not preferred"):
        StrategyPreferences.of([A]).remove(B)


def test_unknown_and_malformed_ids_refused():
    """AC-1: unknown, case-variant, padded, empty and non-string ids are refused; nothing is normalised."""
    for bad in ("", " iron_condor", "IRON_CONDOR", "iron_condor\n", "iron_condor ", "x" * 10_000):
        with pytest.raises(ValueError, match="unknown"):
            StrategyPreferences.of([bad])
    for bad in (None, 5, b"iron_condor", ("iron_condor",)):
        with pytest.raises(TypeError):
            StrategyPreferences.of([bad])  # type: ignore[list-item]
    with pytest.raises(TypeError):
        StrategyPreferences().add(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        StrategyPreferences.of(A)  # a bare string is not a list of ids


def test_absurd_size_capped_without_consuming_it():
    """AC-1: an endless or huge input is refused after at most catalogue-size + 1 items."""
    consumed = 0

    def endless():
        nonlocal consumed
        while True:
            consumed += 1
            yield A

    with pytest.raises(ValueError):
        StrategyPreferences.of(endless())
    assert consumed <= len(IDS) + 1
    with pytest.raises(ValueError, match="too many"):
        StrategyPreferences.of(IDS + [A])


def test_no_ranking_field_exists():
    """AC-1 / REQ-025 AC-4: the only field is the set; no rank, weight, order or 'primary'."""
    assert [f.name for f in dataclasses.fields(StrategyPreferences)] == ["template_ids"]
    assert isinstance(StrategyPreferences.of([A]).template_ids, frozenset)
    public = {n for n in dir(StrategyPreferences) if not n.startswith("_")}
    assert public == {"of", "add", "remove", "template_ids"}


def test_one_thousand_adds_stay_fast_and_bounded():
    """AC-1: repeated add/remove does not re-validate history; a full set cannot be exceeded."""
    prefs = StrategyPreferences()
    for _ in range(1000):
        prefs = prefs.add(A).remove(A)
    assert prefs.template_ids == frozenset()
    full = StrategyPreferences.of(IDS)
    with pytest.raises(ValueError):
        full.add(A)
