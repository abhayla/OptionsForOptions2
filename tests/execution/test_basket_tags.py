"""W-080 AC-2 (REQ-073): a tag fits Kite Publisher's basket limit of 8 characters, identifies strategy + plan version +
leg, is unique per order and decodes back with the pure ``parse_tag``; ids above a ceiling are refused, never
truncated. Kite's basket answered "`tag` should be max 8 characters" for ``OFS11V1L0`` on 2026-10-19 (finding
basket-tag-exceeds-publisher-limit). Legacy ``OFS<s>V<v>L<i>`` tags (Zerodha's book, stored plans) keep their meaning."""
from __future__ import annotations

import random

import pytest
from basket_inputs import FakeFreeze, OkMargin, real_catalogue, real_plan
from ofo.execution.basket import (
    _LEGACY_TAG_RE,
    _TAG_RE,
    MAX_TAG_LEG_INDEX,
    MAX_TAG_LENGTH,
    MAX_TAG_PLAN_VERSION,
    MAX_TAG_STRATEGY_ID,
    BasketRefused,
    TagParts,
    build_basket,
    make_tag,
    parse_tag,
)

KITE_BASKET_TAG_LIMIT = 8  # Kite's own message, independent of the module constant (a raised constant must fail here)


def test_strategy_or_plan_of_ten_or_more_fits_the_basket_limit() -> None:
    # Fails on main: OFS11V1L0 and OFS9V10L0 are 9 characters.
    for args in ((11, 1, 0), (9, 10, 0), (12, 2, 1)):
        tag = make_tag(*args)
        assert len(tag) <= KITE_BASKET_TAG_LIMIT, tag
        assert parse_tag(tag) == TagParts(*args)


def test_known_tags_are_exact() -> None:
    assert make_tag(11, 1, 0) == "Q000B010"
    assert make_tag(12, 1, 0) == "Q000C010"
    assert make_tag(12, 2, 0) == "Q000C020"
    assert make_tag(1679615, 1295, 35) == "QZZZZZZZ"


@pytest.mark.parametrize("args", [(1, 1, 0), (35, 1, 35), (36, 1, 0), (1679615, 1295, 35), (1295, 36, 10)])
def test_round_trip_at_the_boundaries(args) -> None:
    tag = make_tag(*args)
    assert len(tag) == KITE_BASKET_TAG_LIMIT and tag.isascii() and tag.isalnum() and tag == tag.upper()
    assert parse_tag(tag) == TagParts(*args)


def test_ceilings_are_the_stated_values() -> None:
    assert (MAX_TAG_STRATEGY_ID, MAX_TAG_PLAN_VERSION, MAX_TAG_LEG_INDEX) == (1_679_615, 1_295, 35)
    assert MAX_TAG_LENGTH == KITE_BASKET_TAG_LIMIT


@pytest.mark.parametrize("args", [(1679616, 1, 0), (1, 1296, 0), (1, 1, 36), (10**12, 1, 0)])
def test_above_a_ceiling_is_refused_not_truncated(args) -> None:
    with pytest.raises(ValueError, match="ceiling"):
        make_tag(*args)


def test_a_basket_above_the_ceiling_is_refused() -> None:
    cat = real_catalogue()
    with pytest.raises(BasketRefused):
        build_basket(real_plan(cat, strategy_id="S-1679616"), cat, 1, freeze_check=FakeFreeze(), margin_source=OkMargin())


def test_tags_of_a_real_basket_decode_to_the_same_strategy_and_version() -> None:
    cat = real_catalogue()
    basket = build_basket(real_plan(cat), cat, 3, freeze_check=FakeFreeze(), margin_source=OkMargin())
    parts = [parse_tag(o.tag) for o in basket.orders]
    assert {(p.strategy_id, p.plan_version) for p in parts} == {(9, 3)}
    assert [p.leg_index for p in parts] == [0, 1, 2, 3]
    assert len({o.tag for o in basket.orders}) == 4  # noqa: PLR2004


def test_strategy_twelve_basket_tags_are_eight_characters() -> None:
    cat = real_catalogue()
    basket = build_basket(real_plan(cat, strategy_id="S-12"), cat, 1, freeze_check=FakeFreeze(), margin_source=OkMargin())
    tags = [o.tag for o in basket.orders]
    assert all(len(t) == KITE_BASKET_TAG_LIMIT for t in tags), tags
    assert [parse_tag(t) for t in tags[:2]] == [TagParts(12, 1, 0), TagParts(12, 1, 1)]


@pytest.mark.parametrize("args", [(0, 1, 0), (1, 0, 0), (1, 1, -1), (True, 1, 0), (1.5, 1, 0), ("1", 1, 0)])
def test_invalid_parts_are_refused(args) -> None:
    with pytest.raises(ValueError):
        make_tag(*args)


@pytest.mark.parametrize("tag", ["", "OFS1V1L", "OFS01V1L0", "OFS1V1L00", "ofs1v1l0", "OFS1V1L0 ", "OFS1-V1L0",
                                 "XFS1V1L0", "OFS1V1L0x", "OFS١V1L0", "OFS1V1L0\n", None, 5,  # noqa: RUF001
                                 "q000B010", "Q000b010", "Q000B01", "Q000B0100", "Q0000010", "Q000B000", "O000B010",
                                 "Q000B01 ", "Q000B01\n", "Q000-010", "Q٠٠٠B010"])  # noqa: RUF001
def test_parse_tag_refuses_anything_not_made_by_make_tag(tag) -> None:
    with pytest.raises(ValueError):
        parse_tag(tag)


@pytest.mark.parametrize(("tag", "parts"), [("OFS9V1L0", (9, 1, 0)), ("OFS9V2L0", (9, 2, 0)), ("OFS11V1L0", (11, 1, 0)),
                                            ("OFS1V1L0", (1, 1, 0)), ("OFS12V3L1", (12, 3, 1))])
def test_legacy_tags_keep_their_old_meaning(tag, parts) -> None:
    assert parse_tag(tag) == TagParts(*parts)


def test_no_string_matches_both_grammars() -> None:
    rng = random.Random(20261019)  # noqa: S311 - a reproducible sample, not security
    for _ in range(2000):
        s, v, i = rng.randint(1, MAX_TAG_STRATEGY_ID), rng.randint(1, MAX_TAG_PLAN_VERSION), rng.randint(0, 35)
        new = make_tag(s, v, i)
        assert _LEGACY_TAG_RE.fullmatch(new) is None
        legacy = f"OFS{s}V{v}L{i}"
        assert _TAG_RE.fullmatch(legacy) is None


def test_two_legs_never_share_a_tag() -> None:
    assert len({make_tag(5, 2, i) for i in range(MAX_TAG_LEG_INDEX + 1)}) == MAX_TAG_LEG_INDEX + 1
    assert len({make_tag(5, 21, 1), make_tag(52, 1, 1), make_tag(5, 2, 11), make_tag(5, 211, 1)}) == 4  # noqa: PLR2004


def test_tags_are_unique_over_a_large_sample() -> None:
    rng = random.Random(8)  # noqa: S311 - a reproducible sample, not security
    triples = {(rng.randint(1, MAX_TAG_STRATEGY_ID), rng.randint(1, MAX_TAG_PLAN_VERSION), rng.randint(0, 35))
               for _ in range(20000)}
    triples |= {(s, v, i) for s in range(1, 40) for v in range(1, 40) for i in range(0, 36)}
    tags = {make_tag(*t) for t in triples}
    assert len(tags) == len(triples)
