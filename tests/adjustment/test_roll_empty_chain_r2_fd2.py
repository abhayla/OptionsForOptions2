"""#857 (Lane FD2): a spot stated beside an EMPTY option chain (a market that is not connected) answers a stated refusal
naming the leg, never a KeyError that would end the whole check. Spec basis: ADR-239, ADR-003 (suggest only)."""
from __future__ import annotations

from dataclasses import replace

import pytest
from ofo.adjustment.approaches import build_approach
from test_roll_basis import CFG20, SPOT, _chain, _condor


@pytest.mark.parametrize("approach", ["A-02", "A-04", "A-05"])
@pytest.mark.parametrize("kind", ["weekly", "monthly", ""])
def test_an_empty_chain_with_a_stated_spot_is_a_refusal_naming_the_leg_not_a_key_error(approach, kind):
    built = build_approach(replace(_condor(), expiry_kind=kind), [], SPOT, approach, CFG20)
    assert isinstance(built.refusal, str) and built.refusal  # a stated answer, in the catalogue's words
    assert not built.trades


def test_an_unknown_expiry_kind_with_a_chain_is_a_refusal_not_a_key_error():
    built = build_approach(replace(_condor(), expiry_kind=""), _chain(), SPOT, "A-05", CFG20)
    assert built.refusal is not None


def test_the_target_delta_rule_with_a_known_kind_still_places_the_short_where_it_did():
    built = build_approach(_condor(), _chain(), SPOT, "A-05", CFG20)
    assert built.refusal is None
    # the roll basis resolver is unchanged: the same call as test_roll_basis's today's-result case
    assert built.step_basis == "delta"
