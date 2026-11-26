"""ADR-330 (3), (4) and the standing instruction: the ONE alert module, ``ofo_app.actionable_alerts``.

An actionable alert never lapses on its own: it stays in the Active list until the user answers (exit / continue), and
the bell number is the length of that list. Core: the real S-16 sequence of 25 Nov 2026 (fired 11:02:20, value 15.5750,
rule 15.4000, condition stopped 11:05:01). Every test runs in a rolled-back transaction as the limited app role.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.alerts import KINDS
from ofo.timeutil import IST
from ofo_app import actionable_alerts as aa
from ofo_app import playbook_store as pb
from ofo_app import strategy_store
from sqlalchemy import text
from test_strategy_store import _user, _with_draft

D = Decimal
FIRED = datetime.datetime(2026, 11, 25, 11, 2, 20, tzinfo=IST)
STOPPED = datetime.datetime(2026, 11, 25, 11, 5, 1, tzinfo=IST)
LATER = datetime.datetime(2026, 11, 25, 11, 30, 0, tzinfo=IST)
RULE = "T-06"
S16_VALUE = D("15.5750")


@pytest.fixture
async def db(app_engine):
    async with app_engine.connect() as conn:
        outer = await conn.begin()
        try:
            yield conn
        finally:
            await outer.rollback()


async def _strategy(conn, user: str | None = None) -> tuple[str, object]:
    user = user or _user()
    _, stored = await _with_draft(conn, user)
    return user, stored


async def _raise(conn, user, sid, *,  # noqa: PLR0913
                  rule=RULE, kind="plan_loss_stop", value=S16_VALUE, at=FIRED, **extra):
    return await aa.raise_actionable(conn, user, sid, rule, kind, at=at, value=value, threshold=D("15.4000"),
                                     trigger_id=extra.pop("trigger_id", rule), stage=None, **extra)


async def _row(conn, alert_id: int):
    return (await conn.execute(text("SELECT outcome, answer, answered_at, no_longer_true_since, shown_at, value, "
                                    "jsonb_array_length(timeline) AS n FROM public.adjustment_suggestions "
                                    "WHERE id = :id"), {"id": alert_id})).one()


# 1 -------------------------------------------------------------------------------------------------------------
async def test_s16_real_sequence(db):
    """25 Nov: the loss stop fired 11:02:20, the condition stopped 11:05:01; the alert must still be in Active."""
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id)
    assert alert.value == D("15.5750") and alert.threshold == D("15.4000")
    await aa.note_condition(db, user, alert.id, still_true=False, at=STOPPED)
    rows = await aa.unanswered(db, user)
    assert [r.id for r in rows] == [alert.id]
    only = rows[0]
    assert only.fired_at == FIRED and only.fired_at.astimezone(IST).strftime("%H:%M:%S") == "11:02:20"
    assert only.no_longer_true_since == STOPPED
    assert only.no_longer_true_since.astimezone(IST).strftime("%H:%M") == "11:05"
    assert only.outcome == "open" and only.answer is None and only.kind == "plan_loss_stop"
    assert await aa.unanswered_count(db, user) == 1


async def test_note_condition_sets_the_time_once_and_clears_when_true_again(db):
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id)
    first = await aa.note_condition(db, user, alert.id, still_true=False, at=STOPPED)
    n_after_first = (await _row(db, alert.id)).n
    again = await aa.note_condition(db, user, alert.id, still_true=False, at=LATER)  # a later candle: no change
    assert again.no_longer_true_since == first.no_longer_true_since == STOPPED
    assert (await _row(db, alert.id)).n == n_after_first  # no timeline growth on a repeat
    await aa.note_condition(db, user, alert.id, still_true=True, at=LATER)  # still true while never stopped: no-op
    back = (await aa.unanswered(db, user))[0]
    assert back.no_longer_true_since is None  # true again clears it
    again_true = await aa.note_condition(db, user, alert.id, still_true=True, at=LATER)
    assert again_true.no_longer_true_since is None
    assert (await _row(db, alert.id)).n == n_after_first + 1  # exactly one entry for "true again"


# 2 -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("answer", "outcome"), [("exit", "acted_on"), ("continue", "dismissed")])
async def test_a_stated_answer_closes_the_row_and_history_keeps_it(db, answer, outcome):
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id)
    done = await aa.answer(db, user, alert.id, answer, at=LATER)
    assert done.answer == answer and done.answered_at == LATER and done.outcome == outcome
    assert await aa.unanswered(db, user) == []
    kept = await aa.history(db, user)
    assert [h.id for h in kept] == [alert.id]
    assert kept[0].answer == answer and kept[0].answered_at.astimezone(IST).strftime("%H:%M") == "11:30"
    assert kept[0].dismiss_reason is None


async def test_no_answer_given_leaves_the_row_open(db):
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id)
    assert [r.id for r in await aa.unanswered(db, user)] == [alert.id]
    assert (await _row(db, alert.id)).outcome == "open"


async def test_answer_not_found_for_another_users_id_or_a_deleted_strategy(db):
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id)
    with pytest.raises(strategy_store.StrategyStoreError) as other:
        await aa.answer(db, _user(), alert.id, "exit", at=LATER)
    assert other.value.code == pb.SUGGESTION_NOT_FOUND
    await strategy_store.delete_draft(db, user, stored.id, expected_revision=stored.revision)
    with pytest.raises(strategy_store.StrategyStoreError) as hidden:
        await aa.answer(db, user, alert.id, "exit", at=LATER)
    assert hidden.value.code == pb.SUGGESTION_NOT_FOUND
    with pytest.raises(strategy_store.StrategyStoreError) as missing:
        await aa.answer(db, user, 999_999_999, "exit", at=LATER)
    assert missing.value.code == pb.SUGGESTION_NOT_FOUND
    row = await _row(db, alert.id)
    assert (row.outcome, row.answer, row.answered_at) == ("open", None, None)  # nothing written


async def test_a_failed_write_raises_and_leaves_the_row_unchanged(db):
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id)

    class Failing:
        """The connection, except that the closing UPDATE fails."""

        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        async def execute(self, statement, *args, **kwargs):
            if str(statement).lstrip().upper().startswith("UPDATE"):
                raise RuntimeError("the database refused the write")
            return await self._conn.execute(statement, *args, **kwargs)

    with pytest.raises(RuntimeError, match="refused"):
        await aa.answer(Failing(db), user, alert.id, "exit", at=LATER)
    row = await _row(db, alert.id)
    assert (row.outcome, row.answer, row.answered_at) == ("open", None, None)
    assert [r.id for r in await aa.unanswered(db, user)] == [alert.id]


@pytest.mark.parametrize(("kind", "bad"), [("plan_loss_stop", ""), ("plan_loss_stop", "add_legs"),
                                           ("plan_loss_stop", "closed_by_system"), ("plan_loss_stop", None),
                                           ("side_closed", "exit"), ("side_closed", "continue")])
async def test_an_empty_or_ambiguous_answer_is_refused_and_nothing_is_written(db, kind, bad):
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id, kind=kind)
    with pytest.raises(aa.AlertAnswerRefused) as refused:
        await aa.answer(db, user, alert.id, bad, at=LATER)
    assert refused.value.code == aa.ALERT_ANSWER_REFUSED
    row = await _row(db, alert.id)
    assert (row.outcome, row.answer, row.answered_at) == ("open", None, None)


async def test_a_side_closed_alert_takes_its_own_two_answers(db):
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id, kind="side_closed", rule="side.1")
    done = await aa.answer(db, user, alert.id, "confirm_new_shape", at=LATER)
    assert done.answer == "confirm_new_shape" and done.outcome == "dismissed"


async def test_a_second_answer_is_refused_as_not_open(db):
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id)
    await aa.answer(db, user, alert.id, "continue", at=LATER)
    with pytest.raises(strategy_store.StrategyStoreError) as second:
        await aa.answer(db, user, alert.id, "exit", at=LATER)
    assert second.value.code == pb.SUGGESTION_NOT_OPEN
    assert (await _row(db, alert.id)).answer == "continue"


# 3 -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("n", [0, 1, 4])
async def test_the_bell_equals_the_active_list(db, n):
    user = _user()
    for i in range(n):
        _, stored = await _strategy(db, user)
        await _raise(db, user, stored.id, rule=f"T-0{i}")
    listed = await aa.unanswered(db, user)
    assert len(listed) == n == await aa.unanswered_count(db, user)


async def test_one_unanswered_and_three_answered_counts_one(db):
    """The D-29 case of 25 Nov, inverted: the bell is the number of rows in the Active list."""
    user = _user()
    ids = []
    for i in range(4):
        _, stored = await _strategy(db, user)
        ids.append((await _raise(db, user, stored.id, rule=f"T-0{i}")).id)
    for alert_id in ids[:3]:
        await aa.answer(db, user, alert_id, "continue", at=LATER)
    listed = await aa.unanswered(db, user)
    assert [r.id for r in listed] == ids[3:] and await aa.unanswered_count(db, user) == 1
    assert len(await aa.history(db, user)) == len(ids) - 1


# 4 -------------------------------------------------------------------------------------------------------------
async def test_inform_adds_a_history_row_and_never_changes_the_count(db):
    user, stored = await _strategy(db)
    await _raise(db, user, stored.id)
    before = await aa.unanswered_count(db, user)
    note_id = await aa.inform(db, user, stored.id, "stop_fired", "alert_fired_at", {"time": LATER}, at=LATER)
    assert await aa.unanswered_count(db, user) == before == 1
    assert [h.id for h in await aa.history(db, user)] == [note_id]
    note = (await aa.history(db, user))[0]
    assert note.answer == "noted" and note.kind == "stop_fired" and note.note == ("alert_fired_at", {"time": LATER})
    for bad_kind in ("plan_loss_stop", "nonsense"):  # an actionable or unknown kind is never a note
        with pytest.raises(ValueError, match="informational"):
            await aa.inform(db, user, stored.id, bad_kind, "alert_fired_at", {"time": LATER}, at=LATER)
    for bad_words in (("no_such_template", {}), ("alert_fired_at", {}), ("alert_fired_at", {"time": "11:10"})):
        # unknown id, missing slot, plain string for a time: nothing written
        with pytest.raises((ValueError, TypeError)):
            await aa.inform(db, user, stored.id, "settled", *bad_words, at=LATER)
    assert await aa.unanswered_count(db, user) == 1


async def test_inform_once_per_day_writes_one_row_per_rule_per_india_day(db):
    """#732 (ADR-330 (44)): the stored rows are the answer; another rule, another strategy and the next India day (from
    00:00 IST, 18:30 UTC the evening before) each get their own row."""
    user, stored = await _strategy(db)
    _, other = await _strategy(db, user)
    say = {"time": LATER}

    async def once(sid, rule, at):
        return await aa.inform_once_per_day(db, user, sid, "stop_fired", rule, "alert_fired_at", say, at=at)

    first = await once(stored.id, "info:r:1", LATER)
    assert first is not None
    assert await once(stored.id, "info:r:1", LATER + datetime.timedelta(hours=3)) is None  # the same day
    assert await once(stored.id, "info:r:2", LATER) is not None  # another exit
    assert await once(other.id, "info:r:1", LATER) is not None  # another strategy
    midnight = datetime.datetime(2026, 11, 26, 0, 0, 0, tzinfo=IST)
    assert await once(stored.id, "info:r:1", midnight - datetime.timedelta(seconds=1)) is None  # 25 Nov 23:59:59
    assert await once(stored.id, "info:r:1", midnight) is not None  # 26 Nov 00:00:00 IST
    assert await aa.unanswered_count(db, user) == 0


# 5 -------------------------------------------------------------------------------------------------------------
async def test_a_second_raise_for_the_same_rule_is_the_same_row_and_a_worse_value_updates_it(db):
    user, stored = await _strategy(db)
    first = await _raise(db, user, stored.id, cmp="ge")
    n0 = (await _row(db, first.id)).n
    same = await _raise(db, user, stored.id, cmp="ge", at=STOPPED)  # same value: nothing to change
    assert same.id == first.id and (await _row(db, first.id)).n == n0
    worse = await _raise(db, user, stored.id, cmp="ge", value=D("21.2500"), at=LATER)
    assert worse.id == first.id and worse.value == D("21.2500") and worse.fired_at == FIRED
    row = await _row(db, first.id)
    assert row.value == D("21.2500") and row.shown_at == FIRED and row.n == n0 + 1
    better = await _raise(db, user, stored.id, cmp="ge", value=D("16.0000"), at=LATER)  # not worse: kept
    assert better.value == D("21.2500") and (await _row(db, first.id)).n == n0 + 1
    assert len(await aa.unanswered(db, user)) == 1


async def test_a_raise_while_the_condition_is_true_again_clears_no_longer_true_since(db):
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id)
    await aa.note_condition(db, user, alert.id, still_true=False, at=STOPPED)
    again = await _raise(db, user, stored.id, at=LATER)
    assert again.id == alert.id and again.no_longer_true_since is None and again.fired_at == FIRED


async def test_an_unknown_or_informational_kind_cannot_be_raised(db):
    user, stored = await _strategy(db)
    for kind in ("stop_fired", "nonsense"):
        with pytest.raises(ValueError, match="actionable"):
            await _raise(db, user, stored.id, kind=kind)


# 6 -------------------------------------------------------------------------------------------------------------
async def test_a_deleted_strategy_hides_its_alert_and_undo_brings_it_back(db):
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id)
    await strategy_store.delete_draft(db, user, stored.id, expected_revision=stored.revision)
    assert await aa.unanswered(db, user) == [] and await aa.unanswered_count(db, user) == 0
    back = await strategy_store.undelete_draft(db, user, stored.id, expected_revision=stored.revision)
    assert back.id == stored.id
    assert [r.id for r in await aa.unanswered(db, user)] == [alert.id]
    assert await aa.unanswered_count(db, user) == 1


# 7 -------------------------------------------------------------------------------------------------------------
async def test_raising_never_exits_by_itself(db):
    user, stored = await _strategy(db)
    count = text("SELECT count(*) FROM public.paper_orders WHERE strategy_id = :i")
    before = (await db.execute(count, {"i": stored.id})).scalar_one()
    await _raise(db, user, stored.id)
    await _raise(db, user, stored.id, value=D("30.0000"), at=LATER)
    assert (await db.execute(count, {"i": stored.id})).scalar_one() == before == 0


# 8 -------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("reason", [pb.LAPSE_STRATEGY_CLOSED, pb.LAPSE_CONTRACT_EXPIRED, pb.LAPSE_NOT_MONITORED])
async def test_close_by_system_answers_it_and_moves_it_to_history(db, reason):
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id)
    closed = await aa.close_by_system(db, user, stored.id, reason, at=LATER)
    assert [c.id for c in closed] == [alert.id]
    assert await aa.unanswered(db, user) == [] and await aa.unanswered_count(db, user) == 0
    kept = (await aa.history(db, user))[0]
    assert kept.answer == "closed_by_system" and kept.outcome == "lapsed" and kept.closed_reason == reason
    assert kept.answered_at == LATER


@pytest.mark.parametrize("reason", [pb.LAPSE_CONDITION_STOPPED, pb.LAPSE_SUPERSEDED_BY_WORSE,
                                    pb.LAPSE_POSITION_CHANGED, "other"])  # F5a: a basket ends no alert
async def test_close_by_system_refuses_the_reasons_that_no_longer_end_an_alert(db, reason):
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id)
    with pytest.raises(ValueError, match="reason"):
        await aa.close_by_system(db, user, stored.id, reason, at=LATER)
    assert (await _row(db, alert.id)).outcome == "open"


async def test_the_old_lapse_cannot_close_an_alert_of_a_kind(db):
    """The table guard is the structural half of ADR-330 (3): even the old store call cannot lapse a kind row."""
    user, stored = await _strategy(db)
    alert = await _raise(db, user, stored.id)
    with pytest.raises(Exception, match="answer"):
        async with db.begin_nested():
            await pb.lapse(db, user, alert.id, pb.LAPSE_CONDITION_STOPPED)
    assert (await _row(db, alert.id)).outcome == "open"


async def test_dismiss_and_act_on_store_continue_as_the_answer(db):
    user, stored = await _strategy(db)
    one = await _raise(db, user, stored.id)
    two = await _raise(db, user, stored.id, rule="T-01")
    await pb.dismiss(db, user, one.id)
    await pb.act_on(db, user, two.id)
    assert (await _row(db, one.id)).answer == "continue" and (await _row(db, two.id)).answer == "continue"
    assert (await _row(db, one.id)).answered_at is not None
    assert await aa.unanswered(db, user) == []


def test_every_actionable_kind_has_answers_and_the_module_knows_each_kind():
    assert all(k.answers for k in KINDS.values() if k.actionable)
