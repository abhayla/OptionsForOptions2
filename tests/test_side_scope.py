"""ADR-330 (2): which side of an entered strategy is closed, and which rules still fit (P7)."""
import datetime
import json
from decimal import Decimal
from pathlib import Path

from ofo.adjustment import side_scope
from ofo.adjustment.approaches import PositionLeg
from ofo.adjustment.side_scope import closed_sides

EXPIRY = datetime.date(2026, 12, 1)
CONDOR = (("SELL", "CE", 24500), ("BUY", "CE", 24700), ("SELL", "PE", 24000), ("BUY", "PE", 23800))
CLOSED_CALL = "Not applicable: the call side is closed"


def leg(side, kind, strike):
    return PositionLeg(side, kind, Decimal(strike), EXPIRY, 1, Decimal(50), f"N{strike}{kind}")


ENTRY = tuple(leg(*x) for x in CONDOR)


def open_of(*drop):
    return tuple(x for x in ENTRY if (x.type, int(x.strike)) not in drop)


def test_call_side_closed():
    assert closed_sides(ENTRY, open_of(("CE", 24500), ("CE", 24700))) == frozenset({"call"})


def test_put_side_closed():
    assert closed_sides(ENTRY, open_of(("PE", 24000), ("PE", 23800))) == frozenset({"put"})


def test_one_leg_of_a_side_exited_is_not_closed():
    assert closed_sides(ENTRY, open_of(("CE", 24500))) == frozenset()


def test_all_exited_is_a_closed_strategy_not_a_closed_side():
    assert closed_sides(ENTRY, ()) == frozenset()


def test_nothing_exited_and_unreadable_entry():
    assert closed_sides(ENTRY, ENTRY) == frozenset()
    assert closed_sides(None, ENTRY) == frozenset()
    assert closed_sides(ENTRY, None) == frozenset()


def test_a_rolled_leg_is_not_closed():
    rolled = (leg("SELL", "CE", 24600), leg("BUY", "CE", 24800), *ENTRY[2:])
    assert closed_sides(ENTRY, rolled) == frozenset()


def test_every_trigger_of_the_playbooks_has_a_side_scope():
    from ofo.adjustment import playbook_eval
    data = json.loads((Path(side_scope.__file__).parent / "system_playbooks.json").read_text())
    ids = set()
    for p in data["playbooks"]:
        ids |= set(p["body"]["triggers"])
    table = side_scope.SCOPE
    assert ids <= set(table), sorted(ids - set(table))
    assert set(playbook_eval._EVALUATORS) <= set(table)
    assert set(table.values()) <= {"both", "call", "put", "none"}
    assert table["T-05"] == "both"


def test_rule_note_names_the_closed_side():
    body = {"triggers": {"T-05": {}, "T-01": {}},
            "rules": [{"id": "r1", "any_of": ["T-05"]}, {"id": "r2", "any_of": ["T-01"]},
                      {"id": "r3", "any_of": ["T-05", "T-01"]}, {"id": "r4", "all_of": ["T-05", "T-01"]}]}
    notes = side_scope.rule_notes(body, frozenset({"call"}))
    assert notes == {"r1": CLOSED_CALL, "r4": CLOSED_CALL}
    assert side_scope.rule_notes(body, frozenset()) == {}
    assert side_scope.rule_notes(None, frozenset({"call"})) == {}
