"""ADR-330 (64): a REAL position row and alert offer no Exit and no Stops; paper unchanged; unreadable tag fails closed.
Answer states: paper, real (held at broker; order without a paper order), none (draft), unknown (a fact unreadable)."""
from __future__ import annotations

import pytest
from ofo_app import position_kind as pk
from ofo_app.routes import alerts as route

REAL_LINE = ("Real position. Zerodha shows its quantity and P&L. Exits and stops you store here are not sent. "
             "Place them in Kite.")  # ADR-330 (73), pending owner read


@pytest.mark.parametrize(("order", "tag", "held", "kind"), [
    (True, "paper", False, "paper"), (True, "paper", True, "real"),  # ADR-292: held at the broker = a real position
    (True, "real", False, "real"), (False, None, False, "none"),
    (True, None, False, "unknown"),  # Lane R1: an order and no stored tag fails closed
    (True, "bogus", False, "unknown"), (False, "bogus", False, "unknown"),
    (None, "paper", False, "unknown"), (True, "paper", None, "unknown")])
def test_the_kind_is_the_stored_fact(order, tag, held, kind):
    assert pk.kind_of(order, tag, held) == kind


def test_only_real_and_unknown_carry_a_line():
    assert pk.line_of("real") == REAL_LINE
    assert "Exit and Stops are not shown" in pk.line_of("unknown")
    assert pk.line_of("paper") is None and pk.line_of("none") is None


def test_an_alert_offers_exit_for_paper_and_real_never_for_none_or_unreadable():
    """Lane R1 (ADR-330 (73)) rewrites (64): a REAL position's exit is stored (a record), so the alert offers it."""
    assert route.offered(("exit", "continue"), "paper") == ("exit", "continue")
    assert route.offered(("exit", "continue"), "real") == ("exit", "continue")
    assert route.offered(("exit", "continue"), "unknown") == ("continue",)
    assert route.offered(("exit", "continue"), "none") == ("continue",)
    assert route.offered(("add_legs", "confirm_new_shape"), "real") == ("add_legs", "confirm_new_shape")
    assert route.offered(("add_legs", "confirm_new_shape"), "unknown") == ("add_legs", "confirm_new_shape")
