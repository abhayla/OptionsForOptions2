"""W-023 fix round (verifier AC-4 fail): a preparation must count orders the platform already sent but the broker's read
does not show yet. Class: any preparation computed from the broker read alone. REQ-058 AC-4 "submits only the
required order(s)"; ADR-017 Q27; ADR-018.

The verifier's attacks, written first: double Complete (130 units sent where 65 were needed); Retry after Close with a
stale read; clearing a reconciliation block with a stale read (in tests/orders/test_hardening.py).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

from partial_inputs import (
    CONTRACTS,
    LOT,
    READ_AT,
    FakeBroker,
    FakePlanner,
    FakeSubmitter,
    book_with_three_filled,
    entry_context,
    plan,
    statuses,
    three_positions,
)

from ofo.engine import Action
from ofo.execution.partial import (
    PartialChoice,
    close_partial_strategy,
    complete_strategy,
    discard_preparation,
    retry_failed_leg,
    submit_confirmed,
)
from ofo.orders import OrderState

LTPS = (D("40.00"), D("80.00"), D("120.00"))


def _units(submitter: FakeSubmitter) -> list[tuple[str, int]]:
    return [(o.contract, o.quantity) for o in submitter.sent]


def test_double_complete_sends_the_missing_leg_once(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 attack 1: two Complete presses on the same stale broker state. The second is refused while the first
    preparation waits, and refused again ("orders in flight") after it is sent: 65 units in total, never 130."""
    book, broker, submitter = book_with_three_filled(), FakeBroker(three_positions(), statuses()), FakeSubmitter()
    first = complete_strategy(plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    second = complete_strategy(plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert first.ready and not second.ready and second.orders == ()
    assert "waiting for your confirmation" in second.reason

    submit_confirmed(first, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-42", submitter=submitter)
    third = complete_strategy(plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    retry = retry_failed_leg(plan(), "leg-4", broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    for prep in (third, retry):
        assert prep.orders == () and "in flight" in prep.reason
    assert _units(submitter) == [(CONTRACTS[3], LOT)]


def test_sent_order_is_registered_in_the_book(catalogue, eligibility) -> None:  # noqa: ANN001
    """Fix (a): each sent order is in the OrderBook as Submitted, with its strategy, leg and version."""
    book = book_with_three_filled()
    prep = complete_strategy(plan(), FakeBroker(three_positions(), statuses()), book, FakePlanner(),
                             entry_context(), catalogue, eligibility)
    submit_confirmed(prep, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by="user:U-42",
                     submitter=FakeSubmitter())
    view = book.order_for("NEW-1")
    assert (view.state, view.strategy_id, view.order.leg_ref, view.order.version_id, view.quantity) == (
        OrderState.SUBMITTED, "S-1", "leg-4", "v1", LOT)


def test_discarded_preparation_frees_the_strategy(catalogue, eligibility) -> None:  # noqa: ANN001
    """Fix (c): the one live preparation is released when the user discards it; a new one can then be made."""
    book, broker = book_with_three_filled(), FakeBroker(three_positions(), statuses())
    first = complete_strategy(plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    discard_preparation(first)
    assert not first.ready
    again = complete_strategy(plan(), broker, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert again.ready and [(o.contract, o.quantity) for o in again.orders] == [(CONTRACTS[3], LOT)]


def test_retry_after_close_with_stale_read_prepares_nothing(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-4 attack 2: the user chose Close and sent it; a Retry on a broker read that does not show the close orders
    yet must not prepare the 23,600 CE buy. Also refused while the Close preparation is still waiting."""
    book = book_with_three_filled()
    stale = FakeBroker(three_positions(LTPS), statuses())
    close = close_partial_strategy(plan(), stale, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert close.ready
    waiting = retry_failed_leg(plan(), "leg-4", stale, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert waiting.orders == ()
    submit_confirmed(close, choice=PartialChoice.CLOSE_PARTIAL_STRATEGY, confirmed_by="user:U-42",
                     acknowledgement=close.guard.acknowledgement,  # W-026: a close changes the risk profile
                     submitter=FakeSubmitter())
    after = retry_failed_leg(plan(), "leg-4", stale, book, FakePlanner(), entry_context(), catalogue, eligibility)
    complete = complete_strategy(plan(), stale, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert after.orders == () and complete.orders == ()


def test_close_then_complete_needs_a_fresh_read(catalogue, eligibility) -> None:  # noqa: ANN001
    """Fix (d): Close chosen (then discarded, nothing sent) -> Complete on the same read is refused; on a read taken
    later it prepares the missing leg again."""
    book = book_with_three_filled()
    stale = FakeBroker(three_positions(LTPS), statuses())
    discard_preparation(close_partial_strategy(plan(), stale, book, FakePlanner(), entry_context(), catalogue,
                                               eligibility))
    same = complete_strategy(plan(), stale, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert same.orders == () and "fresh" in same.reason
    fresh = FakeBroker(three_positions(LTPS), statuses(), read_at=READ_AT + datetime.timedelta(seconds=5))
    later = complete_strategy(plan(), fresh, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert [(o.contract, o.side, o.quantity) for o in later.orders] == [(CONTRACTS[3], Action.BUY, LOT)]


def test_second_close_on_stale_read_prepares_nothing(catalogue, eligibility) -> None:  # noqa: ANN001
    """Fix (b) for Close: exits already in flight are subtracted -- target 0 - (held + in-flight exits) = 0 on every
    leg, so a second Close on the stale read prepares nothing."""
    book = book_with_three_filled()
    stale = FakeBroker(three_positions(LTPS), statuses())
    first = close_partial_strategy(plan(), stale, book, FakePlanner(), entry_context(), catalogue, eligibility)
    submitter = FakeSubmitter()
    submit_confirmed(first, choice=PartialChoice.CLOSE_PARTIAL_STRATEGY, confirmed_by="user:U-42",
                     acknowledgement=first.guard.acknowledgement,  # W-026: a close changes the risk profile
                     submitter=submitter)
    second = close_partial_strategy(plan(), stale, book, FakePlanner(), entry_context(), catalogue, eligibility)
    assert second.orders == ()
    assert sorted(_units(submitter)) == sorted((c, LOT) for c in CONTRACTS[:3])


def test_read_without_timezone_is_refused(catalogue, eligibility) -> None:  # noqa: ANN001
    """Fix (e) input domain: a broker read with a naive read_at prepares nothing (fail closed)."""
    naive = FakeBroker(three_positions(), statuses(), read_at=datetime.datetime(2026, 9, 29, 10, 0))
    prep = complete_strategy(plan(), naive, book_with_three_filled(), FakePlanner(), entry_context(), catalogue,
                             eligibility)
    assert prep.orders == () and not prep.ready
