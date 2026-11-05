"""Stage B2 (goal contract ic-e2e-paper, design decision 8): T-14 through the real worker -> gate -> record path on
the seeded scenario ADJ-02 (spot held at 23000, T-01 clear). The margin blocked comes through the worker's margin
seam (``screen_margin_reader``, the screen's own block): a huge margin keeps the 1% loss far under the stage value
(0 records); the margin falling to Rs 1,000 crosses it (exactly 1 T-14 record at a candle close); no margin seam
(margin absent) -> 0 records and every check answers T-14 "not checked: missing_margin", as other rules do.

Reuses the harness of tests_app/test_background_worker.py (imported, not copied).
"""
from __future__ import annotations

import datetime
from decimal import Decimal as D

import test_background_worker as bw
from ofo.adjustment import playbook_eval as pe
from ofo.adjustment.preferences import from_values
from ofo.outcome.service import MARGIN_CHECKED, Margin
from ofo.settings import defaults as registry_defaults
from ofo.timeutil import IST
from ofo_app import background
from sqlalchemy import text

app_db_url = bw.app_db_url  # the harness's fixture (DATABASE_URL on the fresh test DB)
CLOCK0 = datetime.datetime(2026, 11, 6, 11, 40, tzinfo=IST)  # ADJ-02's clock: the margin's checked-at


class _Seen(bw._Draining):
    """The real worker; every evaluation it counts is kept, so a test reads T-14's answer on each check."""

    seen: list

    def _count_outcomes(self, ev: pe.Evaluation) -> None:
        self.seen.append(ev)
        super()._count_outcomes(ev)


class _Margin:
    """The route's ``ApproachMargin`` seam: legs -> Zerodha's margin, ``value`` changeable between refreshes."""

    def __init__(self, value: D, at: datetime.datetime) -> None:
        self.value, self.at = value, at

    async def __call__(self, _legs):
        return Margin(MARGIN_CHECKED, "", needed=self.value, broker_needed=self.value, checked_at=self.at)


async def _t14_total(engine, sid: int) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT count(*) FROM public.adjustment_suggestions "
                                        "WHERE strategy_id = :s AND rule_id = 'T-14'"), {"s": sid})).scalar_one()


async def _start(app_db_url, monkeypatch, margin: _Margin | None):
    sid, scn = await bw._seeded(app_db_url, monkeypatch)
    await bw._pin_intraday(app_db_url, sid)
    now = [scn.clock_at]

    async def preferences(_user_ref):
        return from_values(registry_defaults())

    async def user_values(_user_ref):
        return registry_defaults()
    worker = _Seen(provider_for=lambda _owner: scn.provider, lister=lambda: background.owner_lister(scn.provider),
                   clock=lambda: now[0], settings=lambda _at: registry_defaults(), preferences=preferences,
                   user_values=user_values,
                   margin_of=None if margin is None else background.screen_margin_reader(margin))
    worker.seen = []
    bw._push_spot(scn, bw.BEFORE_CROSS_SPOT, now[0])
    return sid, scn, now, worker


async def _run(worker, scn, now, seconds: int) -> None:
    """One-second cycles with a refresh pass after each; spot ticks 23000 / 23001 every 10 s (T-01 stays clear), so
    each 10 s check is a fresh evaluation (an unchanged feed is not re-evaluated)."""
    for i in range(seconds):
        if i % 10 == 0:
            bw._push_spot(scn, "23001" if (i // 10) % 2 else bw.BEFORE_CROSS_SPOT, now[0])
        await worker.cycle()
        await worker.refresh_margins()
        now[0] += datetime.timedelta(seconds=1)


def _t14_answers(worker) -> list:
    return [r for ev in worker.seen for r in ev.results if r.trigger_id == "T-14"]


async def test_t14_crossing_raises_exactly_one_record_and_not_crossing_none(app_db_url, monkeypatch):
    sid, scn, now, worker = await _start(app_db_url, monkeypatch, margin := _Margin(D("1000000000"), CLOCK0))
    base = await _t14_total(app_db_url, sid)
    await _run(worker, scn, now, 150)  # two 1-minute closes with the huge margin: checked, clear
    assert worker.errors == []
    assert await _t14_total(app_db_url, sid) == base  # not crossing: 0 records
    answers = _t14_answers(worker)
    assert answers and not any(isinstance(r, pe.Flag) for r in answers[-5:])
    assert not any(isinstance(r, pe.NotChecked) for r in answers[-5:]), answers[-5:]  # checked, not skipped
    margin.value = D("1000")  # the margin falls: the worst 1% loss is far over the stage value
    worker.margins._entries.clear()  # the next refresh reads the new figure now (refresh window is 5 min)
    await _run(worker, scn, now, 150)
    assert worker.errors == []
    assert await _t14_total(app_db_url, sid) == base + 1  # crossing: exactly 1 record
    assert isinstance(_t14_answers(worker)[-1], pe.Flag)


async def test_t14_margin_absent_raises_no_record_and_answers_not_checked(app_db_url, monkeypatch):
    sid, scn, now, worker = await _start(app_db_url, monkeypatch, None)
    base = await _t14_total(app_db_url, sid)
    await _run(worker, scn, now, 150)
    assert worker.errors == []
    assert await _t14_total(app_db_url, sid) == base
    answers = _t14_answers(worker)
    assert answers and all(r == pe.NotChecked("T-14", "T-14", f"{pe.P}missing_margin") for r in answers), answers[:3]

