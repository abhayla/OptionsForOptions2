"""REQ-061 AC-1 and AC-2 (W-083, ADR-084): suggested groups per underlying and expiry, resemblance naming only, user
moves, adoption with Zerodha's average price.

Spec basis: AC-1 "On connection the platform fetches open positions and identifies possible multi-leg structures."
AC-2 "For each, the user can add it to an existing strategy, create a new strategy, or leave it standalone".
ADR-084 "A group is named only as a resemblance to a template"; "An adopted leg's entry price is Zerodha's average
price for that position".
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest

from grouping_inputs import (CONDOR_SYMBOLS, EXP_CONDOR, EXP_SECOND, IN_STRATEGY, LOT, SECOND_EXPIRY_CALL, SENSEX_PUT,
                             SPOTS, audit_log, catalogue, clock, instrument_id_of, row, seven_rows, strategies,
                             templates, token_of)
from ofo.engine import Action, Instrument
from ofo.engine.product import Product
from ofo.reconciliation.grouping import (STANDALONE, EntrySource, GroupingError, GroupingSession, ToGroup, ToStrategy,
                                         suggest_groups)
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition


def suggest(rows=None, strategy_map=None):
    return suggest_groups(seven_rows() if rows is None else rows, strategies() if strategy_map is None else strategy_map,
                          catalogue(), templates=templates(), spots=SPOTS)


def session(rows=None, strategy_map=None):
    suggestion = suggest(rows, strategy_map)
    return GroupingSession.start(suggestion, audit=audit_log(), clock=clock, actor="user-1", session_id="sess-1",
                                 strategies=strategies() if strategy_map is None else strategy_map)


def by_id(groups):
    return {g.id: g for g in groups}


# ---- the core (AC-1) -------------------------------------------------------------------------------------------------

def test_core_seven_rows_give_exactly_three_groups_and_adopting_the_condor_keeps_zerodha_prices():
    """Core: 3 groups (condor 4, second-expiry call 1, SENSEX put 1); the in-strategy leg excluded; adoption carries
    Zerodha's average prices and products; one audit entry per step."""
    suggestion = suggest()
    groups = by_id(suggestion.groups)
    assert sorted(groups) == sorted([f"NIFTY:{EXP_SECOND}", f"NIFTY:{EXP_CONDOR}", "SENSEX:2026-10-01"])
    condor = groups[f"NIFTY:{EXP_CONDOR}"]
    assert sorted(p.tradingsymbol for p in condor.positions) == sorted(CONDOR_SYMBOLS)
    assert condor.resembles == "Iron Condor"
    assert [p.tradingsymbol for p in groups[f"NIFTY:{EXP_SECOND}"].positions] == [SECOND_EXPIRY_CALL]
    assert [p.tradingsymbol for p in groups["SENSEX:2026-10-01"].positions] == [SENSEX_PUT]
    assert IN_STRATEGY not in {p.tradingsymbol for g in suggestion.groups for p in g.positions}
    assert len(suggestion.groups) == 3

    log = audit_log()
    s = GroupingSession.start(suggestion, audit=log, clock=clock, actor="user-1", session_id="sess-1",
                              strategies=strategies())
    assert s.adopted == ()  # resemblance is a label; no strategy exists before confirm
    adopted = s.confirm(condor.id, strategy_id="S-NEW")
    legs = {a.tradingsymbol: a for a in adopted.legs}
    assert {k: (a.leg.entry_price, a.product, a.entry_source) for k, a in legs.items()} == {
        "NIFTY26O0622800PE": (D("42.50"), Product.NRML, EntrySource.FROM_ZERODHA),
        "NIFTY26O0623000PE": (D("86.00"), Product.MIS, EntrySource.FROM_ZERODHA),
        "NIFTY26O0623400CE": (D("91.50"), Product.NRML, EntrySource.FROM_ZERODHA),
        "NIFTY26O0623600CE": (D("44.00"), Product.NRML, EntrySource.FROM_ZERODHA),
    }
    assert legs["NIFTY26O0623000PE"].leg.action is Action.SELL and legs["NIFTY26O0622800PE"].leg.action is Action.BUY
    assert all(a.leg.quantity == LOT for a in adopted.legs)
    assert [e.payload["action"] for e in log.events] == ["suggest", "confirm"]


def test_group_key_is_underlying_and_expiry_the_second_expiry_call_never_joins_the_condor():
    groups = by_id(suggest().groups)
    assert EXP_SECOND != EXP_CONDOR and f"NIFTY:{EXP_SECOND}" in groups
    assert SECOND_EXPIRY_CALL not in {p.tradingsymbol for p in groups[f"NIFTY:{EXP_CONDOR}"].positions}
    assert all(len({p.expiry for p in g.positions}) == 1 and len({p.underlying for p in g.positions}) == 1
               for g in groups.values())


def test_leg_in_a_strategy_is_matched_by_contract_identity_not_symbol_text():
    """A row whose symbol text is different but whose instrument token is the strategy's contract is still excluded."""
    renamed = row("RENAMED-BY-ZERODHA", -LOT, "70.00", token=token_of(IN_STRATEGY))
    rows = [r for r in seven_rows() if r["tradingsymbol"] != IN_STRATEGY] + [renamed]
    suggestion = suggest(rows)
    assert "RENAMED-BY-ZERODHA" not in {p.tradingsymbol for g in suggestion.groups for p in g.positions}
    assert suggestion.unresolved == ()


def test_a_contract_held_by_another_strategy_is_excluded_even_when_it_is_the_only_row():
    suggestion = suggest([row(IN_STRATEGY, -LOT, "70.00")])
    assert suggestion.groups == () and suggestion.unresolved == ()


def test_zero_quantity_rows_are_not_open_positions():
    rows = seven_rows() + [row("NIFTY26O0623300CE", 0, "0.01")]
    assert "NIFTY26O0623300CE" not in {p.tradingsymbol for g in suggest(rows).groups for p in g.positions}


def test_custom_shape_has_no_resemblance_label():
    s = suggest([row("NIFTY26O0623400CE", -LOT, "91.50"), row("NIFTY26O0623600PE", LOT, "40.00")])
    (g,) = s.groups
    assert g.resembles is None


def test_unknown_contract_is_shown_but_cannot_be_adopted_with_a_four_part_message():
    stray = {**row(SECOND_EXPIRY_CALL, -LOT, "10.00"), "tradingsymbol": "NIFTY99ZZ99999CE", "instrument_token": 999999999}
    s = session(seven_rows() + [stray])
    assert [u.tradingsymbol for u in s.suggestion.unresolved] == ["NIFTY99ZZ99999CE"]
    with pytest.raises(GroupingError) as err:
        s.move_unresolved("NIFTY99ZZ99999CE", ToGroup("NIFTY:2026-10-06"))
    message = err.value.user_message
    assert message is not None and message.what_happened and message.impact
    assert message.what_is_blocked and message.next_action


def test_quantity_not_a_lot_multiple_is_refused_for_adoption():
    s = session([row("NIFTY26O0623400CE", -(LOT + 5), "91.50")])
    assert s.suggestion.groups == ()
    assert [u.reason for u in s.suggestion.unresolved] == ["not_lot_multiple"]


# ---- AC-2: moves, entry price, standalone ----------------------------------------------------------------------------

def test_move_between_groups_of_the_same_underlying_is_allowed_by_explicit_move_a_calendar():
    s = session()
    call = instrument_id_of(SECOND_EXPIRY_CALL)
    s.move(call, ToGroup(f"NIFTY:{EXP_CONDOR}"))
    groups = by_id(s.groups())
    assert SECOND_EXPIRY_CALL in {p.tradingsymbol for p in groups[f"NIFTY:{EXP_CONDOR}"].positions}
    assert f"NIFTY:{EXP_SECOND}" not in groups  # an empty group disappears
    assert groups[f"NIFTY:{EXP_CONDOR}"].resembles is None  # five legs, no template: Custom -> no label


def test_move_into_a_group_of_another_underlying_is_refused_and_changes_nothing():
    s = session()
    with pytest.raises(GroupingError) as err:
        s.move(instrument_id_of(SENSEX_PUT), ToGroup(f"NIFTY:{EXP_CONDOR}"))
    assert err.value.user_message is not None
    assert SENSEX_PUT in {p.tradingsymbol for p in by_id(s.groups())["SENSEX:2026-10-01"].positions}


def test_move_into_an_existing_strategy_needs_the_same_underlying():
    s = session()
    s.move(instrument_id_of(SECOND_EXPIRY_CALL), ToStrategy("S-1"))
    with pytest.raises(GroupingError):
        s.move(instrument_id_of(SENSEX_PUT), ToStrategy("S-1"))
    with pytest.raises(GroupingError):
        s.move(instrument_id_of(SENSEX_PUT), ToStrategy("S-DOES-NOT-EXIST"))
    proposal = s.confirm_existing("S-1")
    assert [a.tradingsymbol for a in proposal.legs] == [SECOND_EXPIRY_CALL] and proposal.strategy_id == "S-1"
    assert proposal.legs[0].leg.entry_price == D("120.25")


def test_standalone_position_is_shown_and_never_adopted():
    s = session()
    s.move(instrument_id_of(SENSEX_PUT), STANDALONE)
    assert [p.tradingsymbol for p in s.standalone()] == [SENSEX_PUT]
    assert "SENSEX:2026-10-01" not in by_id(s.groups())
    with pytest.raises(GroupingError):
        s.confirm("SENSEX:2026-10-01", strategy_id="S-X")
    adopted = s.confirm(f"NIFTY:{EXP_CONDOR}", strategy_id="S-C")
    assert SENSEX_PUT not in {a.tradingsymbol for a in adopted.legs}


def test_edited_entry_price_is_marked_edited_and_the_average_is_kept_otherwise():
    s = session()
    leg = instrument_id_of("NIFTY26O0623400CE")
    s.set_entry(leg, D("95.05"))
    adopted = s.confirm(f"NIFTY:{EXP_CONDOR}", strategy_id="S-C")
    legs = {a.tradingsymbol: a for a in adopted.legs}
    assert legs["NIFTY26O0623400CE"].leg.entry_price == D("95.05")
    assert legs["NIFTY26O0623400CE"].entry_source is EntrySource.EDITED
    assert legs["NIFTY26O0623600CE"].entry_source is EntrySource.FROM_ZERODHA
    assert legs["NIFTY26O0623600CE"].leg.entry_price == D("44.00")


@pytest.mark.parametrize("bad", [D("0"), D("-1"), D("91.52"), 91.5, "91.50", D("NaN")])
def test_entry_price_must_be_a_positive_tick_valid_decimal(bad):
    s = session()
    with pytest.raises(GroupingError):
        s.set_entry(instrument_id_of("NIFTY26O0623400CE"), bad)


def test_a_group_is_confirmed_once():
    s = session()
    s.confirm(f"NIFTY:{EXP_CONDOR}", strategy_id="S-C")
    with pytest.raises(GroupingError):
        s.confirm(f"NIFTY:{EXP_CONDOR}", strategy_id="S-C2")


def test_confirming_a_new_strategy_under_an_existing_id_is_refused():
    s = session()
    with pytest.raises(GroupingError):
        s.confirm(f"NIFTY:{EXP_CONDOR}", strategy_id="S-1")


def test_a_position_not_in_the_suggestion_cannot_be_moved():
    s = session()
    with pytest.raises(GroupingError):
        s.move(instrument_id_of(IN_STRATEGY), STANDALONE)
