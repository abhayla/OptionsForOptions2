# ruff: noqa: PLR2004, E501 - strikes, limits and counts of the scenario case; catalogue texts quoted whole
"""GC-MU A1 (ADR-230 (1); REQ-159 AC-6; F-78): the three saved playbook liquidity limits are read and applied.

Core: ``ofo.adjustment.liquidity`` on the generated scenario ADJ-50 (one thin strike) flags exactly that strike and
passes the rest; a roll whose debit is above ``roll_debit_limit`` is refused with the reason. Class guard: every guard
key in every system playbook has a named reader (or a reasoned KNOWN_UNREAD entry)."""
from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pytest
from ofo.adjustment import liquidity as lq
from ofo.adjustment.approaches import build_approach
from ofo.adjustment.compare import _symbols_token, compare
from ofo.errors.explanations import PLAYBOOK_GUARD_LABEL_TEXT
from test_approach_compare import build_columns
from test_approach_compare import row as compare_row
from test_approaches import CFG, inputs, load

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOKS = ROOT / "backend" / "ofo" / "adjustment" / "system_playbooks.json"
BOTH = lq.limits_from_guards({"hide_oi_below": 10000, "hide_spread_pct_of_mid_above": "5"})
FLAG, UNKNOWN = lq.FLAG_BELOW, lq.FLAG_OI_UNKNOWN


def _d(v):
    return None if v is None else D(str(v))


# ---- core -----------------------------------------------------------------------------------------------------------

def test_core_adj50_flags_exactly_the_thin_strike_and_passes_the_rest():
    sc = load("ADJ-50")
    rows = [r for c in sc["market"]["chains"] for r in c["rows"]]
    assert len(rows) == 84
    states = {(r["strike"], r["type"]): lq.evaluate_strike(BOTH, r["oi"], _d(r["bid"]), _d(r["ask"])) for r in rows}
    assert len(states) == 84  # none dropped (ADR-230: never removed silently)
    flagged = {k: v for k, v in states.items() if v.flags}
    assert list(flagged) == [("23100", "CE")] or [(str(k[0]), k[1]) for k in flagged] == [("23100", "CE")]
    assert next(iter(flagged.values())).flags == (FLAG,)
    assert all(v.oi == "ok" and v.spread == "ok" for k, v in states.items() if k not in flagged)


def test_core_roll_above_the_debit_limit_is_refused_with_the_reason():
    position, chain, spot = inputs(load("ADJ-20a"))
    free = build_approach(position, chain, spot, "A-05", CFG)
    assert free.refusal is None  # the roll is a 1,579.50 debit: (42.15 + 3.10 - 27.40 - 5.70) x 130
    limited = build_approach(position, chain, spot, "A-05", CFG, limits=lq.limits_from_guards({"roll_debit_limit": "Rs 500"}))
    assert limited.trades == () and limited.after == ()
    assert limited.refusal == "This roll costs ₹1,579.50 net, which is more than the ₹500 your playbook allows for one roll."
    assert limited.refusal_message is not None and limited.refusal_message.what_is_blocked == "This approach."


# ---- answer states: strike ------------------------------------------------------------------------------------------

@pytest.mark.parametrize(("guards", "oi", "bid", "ask", "oi_state", "spread_state", "flags"), [
    ({"hide_oi_below": 10000}, 20000, None, None, "ok", "unset", ()),                 # stated and passes
    ({"hide_oi_below": 10000}, 500, None, None, "below", "unset", (FLAG,)),           # stated and breaks
    ({"hide_oi_below": 10000}, 10000, None, None, "ok", "unset", ()),                 # boundary: equal passes
    ({"hide_oi_below": 10000}, None, None, None, "unknown", "unset", (UNKNOWN,)),     # OI absent: never passing
    ({}, None, None, None, "unset", "unset", ()),                                     # no limit set: no flag
    ({"hide_oi_below": "ten thousand"}, 99999, None, None, "unreadable", "unset", (FLAG,)),  # fail closed
    ({"hide_oi_below": True}, 99999, None, None, "unreadable", "unset", (FLAG,)),
    ({"hide_spread_pct_of_mid_above": "5"}, None, D("100"), D("104"), "unset", "ok", ()),
    ({"hide_spread_pct_of_mid_above": "5"}, None, D("100"), D("110"), "unset", "above", (FLAG,)),
    ({"hide_spread_pct_of_mid_above": "5"}, None, None, D("110"), "unset", "unknown", (FLAG,)),   # no bid: fail closed
    ({"hide_spread_pct_of_mid_above": "5"}, None, D("0"), D("110"), "unset", "unknown", (FLAG,)),
    ({"hide_spread_pct_of_mid_above": "x%"}, None, D("100"), D("101"), "unset", "unreadable", (FLAG,)),
    ({"hide_oi_below": 10000, "hide_spread_pct_of_mid_above": "5"}, None, D("100"), D("110"), "unknown", "above",
     (FLAG, UNKNOWN)),
])
def test_strike_answer_states(guards, oi, bid, ask, oi_state, spread_state, flags):
    state = lq.evaluate_strike(lq.limits_from_guards(guards), oi, bid, ask)
    assert (state.oi, state.spread, state.flags) == (oi_state, spread_state, flags)


def test_empty_candidate_list_gives_an_empty_answer():
    assert lq.evaluate_rows(BOTH, []) == {}


def test_every_candidate_row_is_returned_none_dropped():
    _, chain, _ = inputs(load("ADJ-50"))
    chain = [replace(r, oi=500 if r.strike == D("23100") and r.type == "CE" else 50000) for r in chain]
    answer = lq.evaluate_rows(BOTH, chain)
    assert len(answer) == len(chain)
    assert [(r.strike, r.type) for r, s in answer.items() if s.flags] == [(D("23100"), "CE")]


# ---- answer states: roll debit --------------------------------------------------------------------------------------

@pytest.mark.parametrize(("raw", "expected"), [
    ("Rs 500", lq.DebitLimit(D("500"))),
    ("Rs 500 or 10% of max profit", lq.DebitLimit(D("500"), D("10"))),
    ("rs. 1500.50 or 2.5 % of max profit", lq.DebitLimit(D("1500.50"), D("2.5"))),
    ("500", None), ("", None), ("Rs", None), ("Rs 500 or 10% of margin", None), ("Rs -5", None), (None, None), (500, None),
])
def test_debit_limit_parser_reads_one_shape_and_nothing_else(raw, expected):
    assert lq.parse_debit_limit(raw) == expected


def test_limits_from_the_real_system_playbook_text():
    guards = json.loads(PLAYBOOKS.read_text(encoding="utf-8"))["playbooks"][0]["body"]["guards"]
    limits = lq.limits_from_guards(guards)
    assert (limits.oi_below, limits.spread_pct_above, limits.debit) == (D(10000), D(5), lq.DebitLimit(D(500), D(10)))


@pytest.mark.parametrize(("guards", "debit", "max_profit", "allowed", "reason"), [
    ({"roll_debit_limit": "Rs 500"}, D("500"), None, True, "ok"),                               # stated and passes (boundary)
    ({"roll_debit_limit": "Rs 500"}, D("500.01"), None, False, "over"),                         # stated and breaks
    ({"roll_debit_limit": "Rs 500 or 10% of max profit"}, D("1500"), D("20000"), True, "ok"),   # the higher bound permits
    ({"roll_debit_limit": "Rs 500 or 10% of max profit"}, D("2500"), D("20000"), False, "over"),
    ({"roll_debit_limit": "Rs 500 or 10% of max profit"}, D("600"), None, False, "cannot_confirm"),  # % part unknown
    ({"roll_debit_limit": "Rs 500 or 10% of max profit"}, D("400"), None, True, "ok"),
    ({"roll_debit_limit": "Rs 500"}, D("-300"), None, True, "ok"),                              # a credit roll
    ({}, D("99999"), None, True, "no_limit"),                                                   # limit not set
    ({"roll_debit_limit": "about five hundred"}, D("10"), None, False, "unreadable"),           # fail closed
    ({"roll_debit_limit": "about five hundred"}, D("-10"), None, True, "ok"),                   # a credit is never refused
])
def test_roll_debit_answer_states(guards, debit, max_profit, allowed, reason):
    verdict = lq.check_roll_debit(lq.limits_from_guards(guards), debit, max_profit)
    assert (verdict.allowed, verdict.reason) == (allowed, reason)


def test_roll_builder_each_limit_state():
    position, chain, spot = inputs(load("ADJ-20a"))

    def built(guards, max_profit=None):
        return build_approach(position, chain, spot, "A-05", CFG, limits=lq.limits_from_guards(guards), max_profit=max_profit)

    assert built({"roll_debit_limit": "Rs 2000"}).refusal is None
    assert built({}).refusal is None  # not set
    assert built({"roll_debit_limit": "Rs 500 or 10% of max profit"}, D("20000")).refusal is None  # 2,000 allowed
    assert built({"roll_debit_limit": "Rs 500 or 10% of max profit"}, D("10000")).refusal is not None  # 1,000 < 1,579.50
    unreadable = built({"roll_debit_limit": "five hundred"})
    assert unreadable.refusal == "The roll limit saved in your playbook could not be read, so this roll costing ₹1,579.50 net was not built."


def test_limits_do_not_touch_a_non_roll_approach():
    position, chain, spot = inputs(load("ADJ-20a"))
    limits = lq.limits_from_guards({"roll_debit_limit": "Rs 1"})
    assert build_approach(position, chain, spot, "A-28", CFG, limits=limits).refusal is None


# ---- compare cell ---------------------------------------------------------------------------------------------------

def _new_symbols(cols, ctx):
    a11 = next(c for c in cols if c.built.id == "A-11")
    old = {x.tradingsymbol for x in ctx.position.legs}
    return a11, [x.tradingsymbol for x in a11.built.after if x.tradingsymbol not in old]  # the cell's own order


def test_compare_cell_flags_a_strike_below_the_limit_and_one_with_unknown_oi():
    _, cols, ctx = build_columns("ADJ-02")
    _, new = _new_symbols(cols, ctx)
    plain = compare_row(compare(cols, ctx), "liquidity").values["A-11"]
    # every row of the test's chain carries no OI: with the OI limit set, each new leg reads "OI not known"
    unknown = compare_row(compare(cols, replace(ctx, limits=BOTH)), "liquidity").values["A-11"]
    assert unknown.value == plain.value and unknown.rank == plain.rank
    assert unknown.text == f"{plain.value}% (OI not known: {_symbols_token(new)})"
    # first new leg thin, the others deep: the thin one is flagged, nothing else is
    chain = [replace(r, oi=500 if r.tradingsymbol == new[0] else 50000) for r in ctx.chain]
    flagged = compare_row(compare(cols, replace(ctx, chain=chain, limits=BOTH)), "liquidity").values["A-11"]
    assert flagged.text == f"{plain.value}% (Below your liquidity limit: {new[0]})"
    assert flagged.value == plain.value and flagged.rank == plain.rank
    # both states at once
    chain = [replace(r, oi=500) if r.tradingsymbol == new[0] else r for r in ctx.chain]
    both = compare_row(compare(cols, replace(ctx, chain=chain, limits=BOTH)), "liquidity").values["A-11"]
    assert both.text.startswith(f"{plain.value}% (Below your liquidity limit: {new[0]}; OI not known: ")


def test_compare_cell_is_unchanged_without_limits_or_when_every_strike_passes():
    _, cols, ctx = build_columns("ADJ-02")
    plain = compare_row(compare(cols, ctx), "liquidity").values["A-11"]
    deep = [replace(r, oi=50000) for r in ctx.chain]
    passing = compare_row(compare(cols, replace(ctx, chain=deep, limits=BOTH)), "liquidity").values["A-11"]
    assert passing.text == plain.text


# ---- class guard ----------------------------------------------------------------------------------------------------

def _guard_keys() -> set[str]:
    keys: set[str] = set()
    for pb in json.loads(PLAYBOOKS.read_text(encoding="utf-8"))["playbooks"]:
        keys |= set(pb["body"].get("guards", {}))
    return keys


def test_class_every_playbook_guard_key_has_a_reader_or_a_reasoned_known_unread_entry():
    keys = _guard_keys() | set(PLAYBOOK_GUARD_LABEL_TEXT)  # the editor's label list is part of the class
    assert keys, "no guard keys found"
    missing = sorted(k for k in keys if k not in lq.GUARD_READERS and k not in lq.KNOWN_UNREAD)
    assert missing == [], f"guard keys saved in a playbook with no reader: {missing}"
    assert all(reason.strip() for reason in lq.KNOWN_UNREAD.values())
    assert not set(lq.GUARD_READERS) & set(lq.KNOWN_UNREAD)


def test_symbols_token_fits_the_slot_limit_and_counts_the_rest():
    names = [f"NIFTY26N0923{n}00CE" for n in range(10, 18)]
    token = _symbols_token(names)
    assert len(token) <= 64 and " " not in token
    assert token.startswith(names[0]) and token.endswith("more")
    assert _symbols_token(names[:2]) == ",".join(names[:2])


def test_class_the_named_reader_file_really_mentions_the_key():
    for key, path in lq.GUARD_READERS.items():
        source = (ROOT / path).read_text(encoding="utf-8")
        if path.endswith("liquidity.py"):
            assert f'"{key}"' in source, key
        else:
            assert key in source, (key, path)


def test_class_the_three_liquidity_keys_are_read_by_this_module():
    assert {lq.OI_KEY, lq.SPREAD_KEY, lq.DEBIT_KEY} == {"hide_oi_below", "hide_spread_pct_of_mid_above", "roll_debit_limit"}
    assert all(lq.GUARD_READERS[k].endswith("liquidity.py") for k in (lq.OI_KEY, lq.SPREAD_KEY, lq.DEBIT_KEY))


def test_class_guard_fails_for_a_key_with_no_reader():
    """Mutation: a new saved key nobody reads is reported."""
    keys = _guard_keys() | {"brand_new_limit"}
    assert [k for k in keys if k not in lq.GUARD_READERS and k not in lq.KNOWN_UNREAD] == ["brand_new_limit"]
