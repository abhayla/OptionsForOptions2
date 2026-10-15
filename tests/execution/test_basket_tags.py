"""W-080 AC-2 (REQ-073): a tag is at most 20 alphanumeric characters, identifies strategy + plan version + leg, is
unique per order and decodes back with the pure ``parse_tag``; ids that cannot fit are refused, never truncated."""
from __future__ import annotations

import pytest
from basket_inputs import FakeFreeze, OkMargin, real_catalogue, real_plan

from ofo.execution.basket import BasketRefused, TagParts, build_basket, make_tag, parse_tag


def test_round_trip_over_generated_ids() -> None:
    for s in (1, 7, 12, 999, 10**6, 10**8):
        for v in (1, 2, 30, 4096):
            for i in (0, 1, 5, 19):
                tag = make_tag(s, v, i)
                assert len(tag) <= 20 and tag.isascii() and tag.isalnum()
                assert parse_tag(tag) == TagParts(s, v, i)


def test_tags_of_a_real_basket_decode_to_the_same_strategy_and_version() -> None:
    cat = real_catalogue()
    basket = build_basket(real_plan(cat), cat, 3, freeze_check=FakeFreeze(), margin_check=OkMargin())
    parts = [parse_tag(o.tag) for o in basket.orders]
    assert {(p.strategy_id, p.plan_version) for p in parts} == {(9, 3)}
    assert [p.leg_index for p in parts] == [0, 1, 2, 3]
    assert len({o.tag for o in basket.orders}) == 4


def test_ids_that_cannot_fit_are_refused_not_truncated() -> None:
    with pytest.raises(ValueError):
        make_tag(10**12, 10**6, 19)  # more than 20 characters
    cat = real_catalogue()
    with pytest.raises(BasketRefused):
        build_basket(real_plan(cat, strategy_id="S-1000000000000"), cat, 10**6, freeze_check=FakeFreeze(), margin_check=OkMargin())


@pytest.mark.parametrize("args", [(0, 1, 0), (1, 0, 0), (1, 1, -1), (True, 1, 0), (1.5, 1, 0), ("1", 1, 0)])
def test_invalid_parts_are_refused(args) -> None:
    with pytest.raises(ValueError):
        make_tag(*args)


@pytest.mark.parametrize("tag", ["", "OFS1V1L", "OFS01V1L0", "OFS1V1L00", "ofs1v1l0", "OFS1V1L0 ", "OFS1-V1L0",
                                 "XFS1V1L0", "OFS1V1L0x", "OFS١V1L0", "OFS1V1L0\n", None, 5])
def test_parse_tag_refuses_anything_not_made_by_make_tag(tag) -> None:
    with pytest.raises(ValueError):
        parse_tag(tag)


def test_two_legs_never_share_a_tag() -> None:
    assert len({make_tag(5, 2, i) for i in range(20)}) == 20
    assert len({make_tag(5, 21, 1), make_tag(52, 1, 1), make_tag(5, 2, 11), make_tag(5, 211, 1)}) == 4
