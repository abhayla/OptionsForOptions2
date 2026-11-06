"""F-71 baseline from the ENTRY, never from the first check (issues 65/89/36, finding
``rule-entry-baseline-taken-at-first-check``, REQ-159, ADR-258): the background worker's rule memory comes from the
stored rule state (seeded on the rebuild), and its first check's entry baseline comes from the strategy's entry, so a
crossing that existed at entry is never raised as new, and a crossing that did not is never hidden as "already true".

Core proof (scenario ADJ-02 on a throwaway DB, real worker, counted from the DB): the scenario entry is moved past the
T-01 line, so T-01 held at entry. First worker: quiet. Restarted worker: its FIRST cycle reads T-01 as already true
(from the stored memory, not from a fresh baseline) and opens nothing. The spot clears, the worker restarts again, the
spot crosses: the restarted worker's FIRST cycle flags T-01 (the stored "seen clear" memory, never a fresh "already
true" from this check), and exactly one record opens.
"""
from __future__ import annotations

import datetime

import test_background_worker as bw
from ofo.adjustment import playbook_eval as pe
from ofo_app import playbook_store
from test_background_worker import app_db_url  # noqa: F401 - the fixture

ONE_MINUTE_AND_A_BIT = 70


def _t01(worker, sid: int):
    return next(r for r in worker._gate_ctx[sid].evaluation.results if r.rule_id == "T-01")  # noqa: SLF001


async def _run(worker, now, seconds: int) -> None:
    for _ in range(seconds):
        now[0] += bw.ONE_SECOND
        await worker.cycle()


async def test_core_entry_crossing_stays_quiet_across_a_restart_and_a_new_crossing_opens_exactly_one(
        app_db_url, monkeypatch):
    sid, scn = await bw._seeded(app_db_url, monkeypatch)  # noqa: SLF001
    scn.data["position"]["entry"]["spot"] = bw.CROSS_SPOT  # T-01 true AT ENTRY (80 points under the 23500 CE)
    await bw._pin_intraday(app_db_url, sid)  # noqa: SLF001
    now = [scn.clock_at]
    bw._push_spot(scn, bw.CROSS_SPOT, now[0])  # noqa: SLF001
    base = await bw._last_id(app_db_url, sid)  # noqa: SLF001
    first = bw._worker(scn, lambda: now[0])  # noqa: SLF001
    await _run(first, now, ONE_MINUTE_AND_A_BIT)
    assert isinstance(_t01(first, sid), pe.AlreadyTrue), _t01(first, sid)
    async with app_db_url.connect() as conn:
        state = await playbook_store.rule_state(conn, "owner", sid)
    assert state["T-01"] == (True, False), state  # held at entry, not seen clear
    first.stop()

    second = bw._worker(scn, lambda: now[0])  # noqa: SLF001 - restarted, still past the line
    now[0] += bw.ONE_SECOND
    await second.cycle()
    assert isinstance(_t01(second, sid), pe.AlreadyTrue), _t01(second, sid)
    await _run(second, now, ONE_MINUTE_AND_A_BIT)
    assert await bw._t01_rows(app_db_url, sid, base) == []  # noqa: SLF001 - 0 records for the entry crossing

    now[0] += datetime.timedelta(seconds=5)
    bw._push_spot(scn, bw.BEFORE_CROSS_SPOT, now[0])  # noqa: SLF001 - clears
    await _run(second, now, ONE_MINUTE_AND_A_BIT)
    async with app_db_url.connect() as conn:
        assert (await playbook_store.rule_state(conn, "owner", sid))["T-01"] == (True, True)
    second.stop()

    now[0] += datetime.timedelta(seconds=5)
    bw._push_spot(scn, bw.CROSS_SPOT, now[0])  # noqa: SLF001 - a NEW crossing, seen first by a restarted worker
    third = bw._worker(scn, lambda: now[0])  # noqa: SLF001
    now[0] += bw.ONE_SECOND
    await third.cycle()
    first_check = _t01(third, sid)
    await _run(third, now, ONE_MINUTE_AND_A_BIT)
    rows = await bw._t01_rows(app_db_url, sid, base)  # noqa: SLF001
    print(f"CORE-PROOF strategy={sid} entry_spot={bw.CROSS_SPOT} restart_first_check="
          f"{type(first_check).__name__} records_after_new_crossing={len(rows)} rows={rows}")
    assert isinstance(first_check, pe.Flag), first_check  # memory from the DB: seen clear, so a new crossing flags
    assert len(rows) == 1 and rows[0][1] == "open", rows
    assert third.errors == [], third.errors
