# ruff: noqa: PLR2004, E501 - exact texts quoted whole
"""GC-IC1 step 9 (live 2026-11-04 12:06): a Compare liquidity cell naming 2+ legs raised TypeError (Recorded slot).

Core: compare() with several new legs, OI known, low_oi_state not stated, no playbook limit renders the legs.
Class: no explanation template slot named ``legs``/``legs2`` is Recorded."""
from __future__ import annotations

import re
from dataclasses import replace

import pytest
from ofo.adjustment.compare import compare
from ofo.errors import explanations as ex
from ofo.errors.explanations import render_explanation
from test_approach_compare import build_columns
from test_approach_compare import row as compare_row


def _new_legs():
    _, cols, ctx = build_columns("ADJ-02")
    a11 = next(c for c in cols if c.built.id == "A-11")
    old = {x.tradingsymbol for x in ctx.position.legs}
    return tuple(x.tradingsymbol for x in a11.built.after if x.tradingsymbol not in old)


NEW = _new_legs()


def _cell(chain_edit, **ctx_edit):
    _, cols, ctx = build_columns("ADJ-02")
    a11 = next(c for c in cols if c.built.id == "A-11")
    old = {x.tradingsymbol for x in ctx.position.legs}
    new = [x.tradingsymbol for x in a11.built.after if x.tradingsymbol not in old]
    chain = [chain_edit(r, new) for r in ctx.chain]
    return new, compare_row(compare(cols, replace(ctx, chain=chain, **ctx_edit)), "liquidity").values["A-11"]


def _not_stated(r, new):
    return replace(r, low_oi_state="unknown") if r.tradingsymbol in new else r


def test_core_several_new_legs_with_unstated_oi_render_instead_of_raising():
    new, cell = _cell(_not_stated)
    assert len(new) >= 2
    assert ", ".join(new) in cell.text and "Zerodha may refuse fresh orders in" in cell.text


def test_one_new_leg_text_is_the_same_as_before():
    assert render_explanation("adjust_cmp_low_oi", value="1.00", legs=(NEW[0],)).endswith(
        f"in {NEW[0]} if its open interest is too low; this app could not check that)")


def test_three_legs_render_in_flagged_templates_too():
    legs = tuple(NEW[:3])
    assert len(legs) == 3
    text = render_explanation("adjust_cmp_flagged", value="1", flag=render_explanation("adjust_flag_oi_unknown"), legs=legs)
    assert text.endswith("OI not known: " + ", ".join(legs) + ")")


def test_empty_and_overlong_and_joined_string_fail_closed():
    for bad in ((), "A,B", ("X" * 65,)):
        with pytest.raises((TypeError, ValueError)):
            render_explanation("adjust_cmp_low_oi", value="1", legs=bad)


def test_class_no_legs_slot_is_recorded():
    with open(ex.__file__, encoding="utf-8") as f:
        src = f.read()
    assert re.findall(r'"legs2?":\s*Recorded', src) == []
