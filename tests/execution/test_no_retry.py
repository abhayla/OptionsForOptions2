"""REQ-058 AC-6: V1 never resubmits a failed order automatically; the failure is shown with its reason and the user
chooses the next action (Q193). Golden Iron Condor, 23,600 CE buy rejected."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from partial_inputs import (
    READ_AT,
    REJECT_TEXT,
    FakeBroker,
    FakePlanner,
    FakeSubmitter,
    book_with_three_filled,
    entry_context,
    plan,
    statuses,
    three_positions,
)

import ofo.execution.partial as partial
from ofo.execution import CheckCode
from ofo.execution.partial import (
    PartialChoice,
    assess,
    complete_strategy,
    retry_failed_leg,
    submit_confirmed,
)


def _prep(catalogue, eligibility, fn=complete_strategy, *extra):  # noqa: ANN001, ANN202
    return fn(plan(), *extra, FakeBroker(three_positions(), statuses()), book_with_three_filled(), FakePlanner(),
              entry_context(), catalogue, eligibility)


def test_ac6_failure_shown_with_reason_and_nothing_sent() -> None:
    """AC-6: assessing the rejection shows the broker's reason and the user's choices; nothing is sent."""
    submitter = FakeSubmitter()
    a = assess(plan(), three_positions(), statuses(), book_with_three_filled(), FakePlanner(), read_at=READ_AT)
    assert [f.reason for f in a.failures] == [REJECT_TEXT]
    assert a.choices[0] is PartialChoice.COMPLETE_STRATEGY
    assert submitter.sent == []


def test_ac6_missing_reason_is_said_not_invented() -> None:
    """AC-6: a rejection with no broker text says so plainly instead of a made-up cause."""
    a = assess(plan(), three_positions(), statuses(reason=None), book_with_three_filled(), FakePlanner(), read_at=READ_AT)
    assert [f.reason for f in a.failures] == ["no reason given by the broker"]


def test_ac6_preparing_sends_nothing(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6: Complete and Retry only PREPARE; no submitter is even reachable from them."""
    for prep in (_prep(catalogue, eligibility), _prep(catalogue, eligibility, retry_failed_leg, "leg-4")):
        assert prep.ready and all(o.broker_order_id is None for o in prep.orders)


def test_ac6_refused_submission_is_not_retried(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6: the confirmed order is refused by the broker -> exactly one submit call, the broker's text recorded,
    and the same preparation cannot be sent again (a new try needs a new user choice and a fresh preparation)."""
    prep = _prep(catalogue, eligibility, retry_failed_leg, "leg-4")
    submitter = FakeSubmitter(refuse=1)
    result = submit_confirmed(prep, choice=PartialChoice.RETRY_FAILED_LEG, confirmed_by="user:U-42",
                              submitter=submitter)
    assert len(submitter.sent) == 1
    assert result.failed == ("leg-4", "Order rejected: RMS:Margin Exceeds") and result.submitted == ()
    with pytest.raises(ValueError, match="already sent"):
        submit_confirmed(prep, choice=PartialChoice.RETRY_FAILED_LEG, confirmed_by="user:U-42", submitter=submitter)
    assert len(submitter.sent) == 1


def test_ac6_submission_needs_the_users_matching_choice(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6: sending requires the user's explicit choice matching the preparation and a named user."""
    prep = _prep(catalogue, eligibility)
    submitter = FakeSubmitter()
    with pytest.raises(ValueError):
        submit_confirmed(prep, choice=PartialChoice.RETRY_FAILED_LEG, confirmed_by="user:U-42", submitter=submitter)
    with pytest.raises(ValueError):
        submit_confirmed(prep, choice=PartialChoice.COMPLETE_STRATEGY, confirmed_by=" ", submitter=submitter)
    assert submitter.sent == []


def test_ac6_retry_only_for_a_failed_leg(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6 negative: retrying a leg that did not fail (a filled leg) is refused, never turned into an order."""
    with pytest.raises(ValueError, match="no failed order"):
        _prep(catalogue, eligibility, retry_failed_leg, "leg-1")


def test_ac6_blocked_preparation_cannot_be_sent(catalogue, eligibility) -> None:  # noqa: ANN001
    """AC-6: a retry goes through the W-014 gate; a disconnected broker blocks it, no order is prepared, and the
    preparation cannot be sent."""
    prep = retry_failed_leg(plan(), "leg-4", FakeBroker(three_positions(), statuses()), book_with_three_filled(),
                            FakePlanner(), entry_context(broker_connected=False), catalogue, eligibility)
    assert prep.gate is not None and CheckCode.BROKER_NOT_CONNECTED in prep.gate.failed_codes
    assert prep.orders == ()
    with pytest.raises(ValueError):
        submit_confirmed(prep, choice=PartialChoice.RETRY_FAILED_LEG, confirmed_by="user:U-42",
                         submitter=FakeSubmitter())


def test_ac6_no_scheduling_or_loop_around_submission() -> None:
    """AC-6 structural guard: the module imports nothing that schedules or sleeps, has no while-loop, and calls
    ``submit`` from exactly one place -- the one loop over a preparation's orders inside ``submit_confirmed``, which
    is not itself inside any other loop or retry handler."""
    tree = ast.parse(Path(partial.__file__).read_text(encoding="utf-8"))
    banned = {"threading", "sched", "asyncio", "time", "concurrent", "multiprocessing"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not {a.name.split(".")[0] for a in node.names} & banned
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in banned
        assert not isinstance(node, ast.While), "a while-loop could resubmit"
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "submit"]
    assert len(calls) == 1
    (func,) = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "submit_confirmed"]
    loops = [n for n in ast.walk(func) if isinstance(n, (ast.For, ast.AsyncFor))]
    assert len(loops) == 1 and isinstance(loops[0].iter, ast.Call)
    assert loops[0].iter.func.id == "enumerate" and ast.unparse(loops[0].iter.args[0]) == "orders"  # W-026: the snapshot the guard checked
    # the except handler inside the loop returns (stops); it never continues to another submit
    handlers = [n for n in ast.walk(loops[0]) if isinstance(n, ast.ExceptHandler)]
    assert handlers and all(isinstance(h.body[-1], ast.Return) for h in handlers)
