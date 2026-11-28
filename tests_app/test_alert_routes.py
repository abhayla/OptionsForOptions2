"""ADR-330 (3), (4): GET /api/alerts/active, POST /api/alerts/{id}/answer, GET /api/alerts/answered (real DB).

Asserts the EXACT key set of each reply: the frontend contract (frontend/src/lib/paperAlerts.js, mocked in
frontend/tests/alerts-actionable.test.js) reads exactly these names.
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D
from http import HTTPStatus

import test_adjustment_check as check_test
from ofo.timeutil import IST
from ofo_app import actionable_alerts as aa
from ofo_app import adjustment_readers as readers
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_adjustment_check import _seeded
from test_adjustment_opportunities import _call, _clean

app_db_url = check_test.app_db_url
OK, NOT_FOUND, CONFLICT, REFUSED = 200, 404, 409, 422
TRADES = 3  # strategies sharing one name in the alert-label test
FIRED = datetime.datetime(2026, 11, 25, 11, 2, 20, tzinfo=IST)
STOPPED = datetime.datetime(2026, 11, 25, 11, 5, 1, tzinfo=IST)
ACTIVE_KEYS = {"id", "strategy_id", "strategy_name", "kind", "text", "fired_at", "fired_line", "no_longer_true_since",
               "no_longer_true_line", "escalated_at", "worse_line", "answers",
               "position_kind", "position_kind_text"}  # the last two: ADR-330 (64)
HISTORY_KEYS = {"id", "strategy_id", "strategy_name", "kind", "text", "fired_at", "fired_line", "escalated_at",
                "worse_line", "answer", "answer_label", "answered_at", "closed_reason"}


async def _raise(engine, sid: int) -> int:
    async with engine.begin() as conn:
        alert = await aa.raise_actionable(conn, "owner", sid, "T-06", "plan_loss_stop", at=FIRED, value=D("15.5750"),
                                          threshold=D("15.4000"), trigger_id="T-06", stage=None)
        await aa.note_condition(conn, "owner", alert.id, still_true=False, at=STOPPED)
    return alert.id


async def test_active_answer_history_replies_and_errors(app_db_url, monkeypatch):
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    alert_id = await _raise(app_db_url, sid)
    status, active = await _call("GET", "/api/alerts/active")
    assert status == OK and set(active) == {"count", "alerts"} and active["count"] == len(active["alerts"])
    mine = next(a for a in active["alerts"] if a["id"] == alert_id)
    assert set(mine) == ACTIVE_KEYS and mine["kind"] == "plan_loss_stop"
    assert (mine["fired_line"], mine["no_longer_true_line"]) == ("Fired at 11:02", "no longer true since 11:05")
    assert (mine["fired_at"], mine["no_longer_true_since"]) == ("2026-11-25T05:32:20Z", "2026-11-25T05:35:01Z")
    assert (mine["escalated_at"], mine["worse_line"]) == (None, None)  # never worse: null, not an empty line
    assert [a["code"] for a in mine["answers"]] == ["exit", "continue"] and set(mine["answers"][0]) == {"code", "label"}
    for body, code in (({"answer": ""}, REFUSED), ({"answer": "add_legs"}, REFUSED),  # empty, not for this kind
                       ({"answer": "continue", "unnamed": 1}, REFUSED)):  # a closed body: an extra field is refused
        assert (await _call("POST", f"/api/alerts/{alert_id}/answer", body))[0] == code
    other = await _call("POST", f"/api/alerts/{alert_id}/answer", {"answer": "continue"}, user="someone-else")
    assert other[0] == NOT_FOUND
    assert (await _call("GET", "/api/alerts/active"))[1]["count"] == active["count"]  # nothing written by a refusal
    status, done = await _call("POST", f"/api/alerts/{alert_id}/answer", {"answer": "continue"})
    assert status == OK and set(done) == {"id", "answer", "answer_label", "answered_at"}
    assert (await _call("POST", f"/api/alerts/{alert_id}/answer", {"answer": "exit"}))[0] == CONFLICT
    assert (await _call("GET", "/api/alerts/active"))[1]["count"] == active["count"] - 1
    status, history = await _call("GET", "/api/alerts/answered")
    row = next(i for i in history["items"] if i["id"] == alert_id)
    assert status == OK and set(history) == {"items"} and set(row) == HISTORY_KEYS
    assert (row["answer"], row["answer_label"]) == ("continue", "Continue with the position")
    assert (row["fired_line"], row["answered_at"]) == ("Fired at 11:02", done["answered_at"])
    assert row["closed_reason"] is None
    # the user's name in the quoted slot, then the trade's number and nearest expiry (ADR-330 (19)(b))
    assert mine["strategy_name"] == row["strategy_name"] == f'"Scenario ADJ-02" (#{sid}, 9 Nov)'


ESCALATED = datetime.datetime(2026, 11, 25, 11, 9, 0, tzinfo=IST)


async def test_a_worse_reading_shows_escalated_at_and_the_worse_line_in_active_and_history(app_db_url, monkeypatch):
    """P1 round 3 F3 (contract): the open alert carries when a WORSE value of the same rule last updated it, and the
    catalogue's line; a later answer keeps both in History; a second worse reading moves escalated_at."""
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    async with app_db_url.begin() as conn:
        alert = await aa.raise_actionable(conn, "owner", sid, "T-06", "plan_loss_stop", at=FIRED, value=D("15.5750"),
                                          threshold=D("15.4000"), trigger_id="T-06", stage=None, unit="%", cmp="ge")
        worse = await aa.raise_actionable(conn, "owner", sid, "T-06", "plan_loss_stop", at=ESCALATED,
                                          value=D("16.2000"), threshold=D("15.4000"), trigger_id="T-06", stage=None)
    assert worse.id == alert.id
    status, active = await _call("GET", "/api/alerts/active")
    mine = next(a for a in active["alerts"] if a["id"] == alert.id)
    assert status == OK and set(mine) == ACTIVE_KEYS
    assert mine["escalated_at"] == "2026-11-25T05:39:00Z"
    assert mine["worse_line"] == "Worse than when it fired: 16.2000 % (fired at 15.5750 %)"
    assert mine["fired_at"] == "2026-11-25T05:32:20Z"  # the first-shown time never moves
    assert (await _call("POST", f"/api/alerts/{alert.id}/answer", {"answer": "continue"}))[0] == OK
    row = next(i for i in (await _call("GET", "/api/alerts/answered"))[1]["items"] if i["id"] == alert.id)
    assert set(row) == HISTORY_KEYS and (row["escalated_at"], row["worse_line"]) == (
        mine["escalated_at"], mine["worse_line"])


async def test_a_noted_row_in_history_is_catalogue_worded_and_never_a_500(app_db_url, monkeypatch):
    """P1 round 3 F4: an informational note (answer 'noted') comes back from the catalogue id and values it was stored
    with; it is never a stored plain string returned as catalogue text (that was a 500 for the whole History)."""
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    async with app_db_url.begin() as conn:
        note_id = await aa.inform(conn, "owner", sid, "stop_fired", "stop_fired_loss", {
            "loss": D("12000.00"), "loss_pct": D("61.5"), "stop": D("11700.00"), "stop_pct": D("60")}, at=FIRED)
    status, history = await _call("GET", "/api/alerts/answered")
    row = next(i for i in history["items"] if i["id"] == note_id)
    assert status == OK and set(row) == HISTORY_KEYS and (row["answer"], row["kind"]) == ("noted", "stop_fired")
    assert row["text"] == ("Stop reached: loss now ₹12,000.00 (61.5 % of max loss); "
                           "stop line ₹11,700.00 (60 % of max loss)")
    active = (await _call("GET", "/api/alerts/active"))[1]
    # never counted
    assert active["count"] == len(active["alerts"]) and note_id not in [a["id"] for a in active["alerts"]]


async def test_answered_after_returns_only_rows_with_a_higher_id(app_db_url, monkeypatch):
    """W2-A: the header's pop-up reader asks only for what is new since the last row it saw (?after=)."""
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    async with app_db_url.begin() as conn:
        first = await aa.inform(conn, "owner", sid, "stop_fired", "alert_fired_at", {"time": FIRED}, at=FIRED)
        second = await aa.inform(conn, "owner", sid, "stop_fired", "alert_fired_at", {"time": FIRED}, at=FIRED)

    def ids(body):
        return [i["id"] for i in body["items"]]

    assert {first, second} <= set(ids((await _call("GET", "/api/alerts/answered"))[1]))
    assert ids((await _call("GET", f"/api/alerts/answered?after={first}"))[1]) == [second]
    assert ids((await _call("GET", f"/api/alerts/answered?after={second}"))[1]) == []
    assert (await _call("GET", "/api/alerts/answered?after=-1"))[0] == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_alert_lists_carry_the_trade_number_and_expiry_beside_the_name(app_db_url, monkeypatch):
    """ADR-330 (19)(b): three strategies may share a name (REQ-134 AC-1); each Active / History row says which one."""
    sids = []
    for _ in range(TRADES):  # the seed reuses a strategy by name, so each is renamed before the next is seeded
        sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-03"))
        async with app_db_url.begin() as conn:
            await conn.execute(text("UPDATE public.strategies SET name = 'Short Iron Condor' WHERE id = :id"),
                               {"id": sid})
        sids.append(sid)
    assert len(set(sids)) == TRADES
    ids = {sid: await _raise(app_db_url, sid) for sid in sids}
    status, active = await _call("GET", "/api/alerts/active")
    assert status == OK
    named = {a["id"]: a["strategy_name"] for a in active["alerts"]}
    assert [named[ids[sid]] for sid in sids] == [f'"Short Iron Condor" (#{sid}, 9 Nov)' for sid in sids]
    assert (await _call("POST", f"/api/alerts/{ids[sids[0]]}/answer", {"answer": "continue"}))[0] == OK
    history = {i["id"]: i["strategy_name"] for i in (await _call("GET", "/api/alerts/answered"))[1]["items"]}
    assert history[ids[sids[0]]] == f'"Short Iron Condor" (#{sids[0]}, 9 Nov)'


async def test_a_trade_with_no_readable_open_leg_shows_its_number_only(app_db_url, monkeypatch):
    """No expiry readable (the book is flat, or cannot be read): "(#id)" only, never a guessed date."""
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    alert_id = await _raise(app_db_url, sid)

    async def flat(*args, **kwargs):
        return None  # no open option leg
    async def none_batched(*args, **kwargs):
        return {}  # the batch answers for no trade: each is asked on its own (a real book, nothing traded)
    monkeypatch.setattr(readers, "nearest_expiry", flat)
    monkeypatch.setattr(readers, "nearest_expiries", none_batched)
    status, active = await _call("GET", "/api/alerts/active")
    named = {a["id"]: a["strategy_name"] for a in active["alerts"]}
    assert status == OK and named[alert_id] == f'"Scenario ADJ-02" (#{sid})'


async def test_a_failed_expiry_read_for_one_trade_never_stops_the_lists_or_the_bell(app_db_url, monkeypatch, caplog):
    """ADR-330 (3)(4): any failure reading ONE trade's book (a plain error, a database error) leaves that row as
    "(#id)", the other rows labelled, and Active / History answering 200 with the count unchanged."""
    sids = []
    for _ in range(2):  # the seed reuses a strategy by name, so the first is renamed before the second is seeded
        sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-03"))
        async with app_db_url.begin() as conn:
            await conn.execute(text("UPDATE public.strategies SET name = 'Short Iron Condor' WHERE id = :id"),
                               {"id": sid})
        sids.append(sid)
    good, bad = sids
    ids = {sid: await _raise(app_db_url, sid) for sid in (good, bad)}
    real = readers.nearest_expiry
    baseline = (await _call("GET", "/api/alerts/active"))[1]["count"]
    assert baseline >= len(ids)  # the seeds raise their own open alerts too
    for failure in (RuntimeError("boom"), DBAPIError("SELECT 1", None, Exception("db"))):
        async def lookup(db, sid, _failure=failure):
            if sid == bad:
                if isinstance(_failure, DBAPIError):
                    await db.execute(text("SELECT * FROM public.no_such_table"))  # really aborts the transaction
                raise _failure
            return await real(db, sid)
        async def batch_fails(db, ids, _failure=failure):
            if isinstance(_failure, DBAPIError):
                await db.execute(text("SELECT * FROM public.no_such_table"))  # really aborts the transaction
            raise _failure
        monkeypatch.setattr(readers, "nearest_expiry", lookup)
        monkeypatch.setattr(readers, "nearest_expiries", batch_fails)  # the batch fails: each trade is read alone
        status, active = await _call("GET", "/api/alerts/active")
        by_trade = {(a["strategy_id"], a["strategy_name"]) for a in active["alerts"]}
        assert status == OK and active["count"] == len(active["alerts"]) == baseline
        assert (bad, f'"Short Iron Condor" (#{bad})') in by_trade
        assert [n for i, n in by_trade if i == good and n.startswith(f'"Short Iron Condor" (#{good}, ')]
        history = await _call("GET", "/api/alerts/answered")
        assert history[0] == OK
    assert (await _call("POST", f"/api/alerts/{ids[bad]}/answer", {"answer": "continue"}))[0] == OK
    answered = (await _call("GET", "/api/alerts/answered"))[1]["items"]
    assert [i["strategy_name"] for i in answered if i["id"] == ids[bad]] == [f'"Short Iron Condor" (#{bad})']
    assert "expiry" in caplog.text


async def _raise_side_closed(app_db_url, monkeypatch):
    """A paper iron condor with its call side exited (25 Nov); the one side_closed alert raised; its id."""
    from ofo_app import side_closed  # noqa: PLC0415
    from test_side_closed_alert import CALL_EXITED  # noqa: PLC0415
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    async with app_db_url.begin() as conn:
        alert_id = await side_closed.raise_if_closed(conn, "owner", sid, CALL_EXITED, at=FIRED, source=None)
    assert alert_id is not None
    return next(a for a in (await _call("GET", "/api/alerts/active"))[1]["alerts"] if a["id"] == alert_id)


async def test_a_side_closed_row_in_active_has_no_adjustment_wording(app_db_url, monkeypatch):
    """P7 checker 3: the side_closed notice is raised with no source, so its Active text never says the adjustment
    heading words ("Adjustment opportunity detected" / "Your rule was triggered")."""
    mine = await _raise_side_closed(app_db_url, monkeypatch)
    assert mine["kind"] == "side_closed"
    for words in ("Adjustment opportunity detected", "Your rule was triggered"):
        assert words not in str(mine["text"])


async def test_a_side_closed_row_in_active_names_the_closed_side_and_the_shape_that_remains(app_db_url, monkeypatch):
    """P7 page flow (ADR-330 (2)(b)): the row says the call side is closed and asks; the text names the shape that
    remains (bull put spread when the call side closed); both answers are offered."""
    mine = await _raise_side_closed(app_db_url, monkeypatch)
    assert "call side of this trade is closed" in str(mine["text"])
    assert "Bull Put Spread" in str(mine["text"])
    assert [x["code"] for x in mine["answers"]] == ["add_legs", "confirm_new_shape"]


async def test_an_alert_with_no_worded_condition_shows_its_rule_not_the_trade_name(app_db_url, monkeypatch):
    """Item 2 (27 Nov): the row's reason was only the trade name ("Scenario ADJ-02"); now the rule and its figures."""
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    alert_id = await _raise(app_db_url, sid)
    mine = next(a for a in (await _call("GET", "/api/alerts/active"))[1]["alerts"] if a["id"] == alert_id)
    assert mine["text"] == "Plan loss stop: 15.5750 (rule 15.4000)"
    async with app_db_url.begin() as conn:  # absent figures: still the rule's kind, never the name
        other = await aa.raise_actionable(conn, "owner", sid, "T-07", "plan_profit_target", at=FIRED, value=None,
                                          threshold=None, trigger_id="T-07", stage=None)
    row = next(a for a in (await _call("GET", "/api/alerts/active"))[1]["alerts"] if a["id"] == other.id)
    assert row["text"] == "Plan profit target"


async def _statements_of(url: str) -> tuple[int, int, dict]:
    """(status, statements run, body) of one GET, counted from the engine's cursor events (not wall time: not flaky)."""
    from httpx import ASGITransport, AsyncClient  # noqa: PLC0415
    from ofo_app import db as app_db  # noqa: PLC0415
    from ofo_app.main import create_app  # noqa: PLC0415
    from sqlalchemy import event  # noqa: PLC0415
    from test_adjustment_check import _reset_engine  # noqa: PLC0415
    _reset_engine()
    app = create_app()
    count = [0]
    event.listen(app_db.get_engine().sync_engine, "before_cursor_execute",
                 lambda *_a: count.__setitem__(0, count[0] + 1))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        r = await ac.get(url)
    await app_db.close_db()
    return r.status_code, count[0], r.json()


async def _answered_trades(app_db_url, monkeypatch, n: int) -> list[int]:
    sids = []
    for _ in range(n):
        sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-03"))
        async with app_db_url.begin() as conn:
            await conn.execute(text("UPDATE public.strategies SET name = 'Short Iron Condor' WHERE id = :id"),
                               {"id": sid})
        sids.append(sid)
    for sid in sids:
        alert_id = await _raise(app_db_url, sid)
        assert (await _call("POST", f"/api/alerts/{alert_id}/answer", {"answer": "continue"}))[0] == OK
    return sids


async def test_the_alert_lists_run_the_same_statements_for_2_and_12_strategies(app_db_url, monkeypatch):
    """W-13 (server half): Active and History label each row with its trade's nearest expiry; that read is ONE batch
    (one orders read, one contract read), so the statement count does not grow with the number of strategies (it was
    3 to 4 statements per distinct strategy: 6 s on a history of 12). Same labels per row as before."""
    few = await _answered_trades(app_db_url, monkeypatch, 2)
    counts = {}
    for url in ("/api/alerts/answered", "/api/alerts/active"):
        status, counts[url, 2], _ = await _statements_of(url)
        assert status == OK
    many = few + await _answered_trades(app_db_url, monkeypatch, 10)
    for url in ("/api/alerts/answered", "/api/alerts/active"):
        status, counts[url, 12], _ = await _statements_of(url)
        assert status == OK
        assert counts[url, 12] == counts[url, 2], counts
    _, _, history = await _statements_of("/api/alerts/answered")
    named = {i["strategy_id"]: i["strategy_name"] for i in history["items"]}
    assert [named[sid] for sid in many] == [f'"Short Iron Condor" (#{sid}, 9 Nov)' for sid in many]
