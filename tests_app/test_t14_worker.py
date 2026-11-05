# ruff: noqa: PLR2004 - check and read counts are the point
"""Stage B2 (goal contract ic-e2e-paper, design decision 8): T-14 through the real worker -> gate -> record path on
the seeded scenario ADJ-02 (scenario mode; spot held at 23000, T-01 clear). The margin blocked comes through the
worker's margin seam (``screen_margin_reader``, the screen's own block). Each check's state is recorded through the
worker's ``observe`` seam and T-14 is read from an evaluation of that state: a Flag, a NotChecked(code), or CLEAR
(a checked-and-clear rule leaves no entry in ``ev.results``; its memory says ``seen_clear``).

Huge margin -> the 1% loss far under the stage value: T-14 clear, 0 records. The margin falls to Rs 1,000 (read at
the next refresh, ``MARGIN_REFRESH_S`` later) -> exactly 1 T-14 record at the crossing, 0 before. No margin seam
(margin absent) -> 0 records and T-14 "not checked: missing_margin" on every check.
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
from ofo.settings import hhmm_text
from ofo_app import background
from sqlalchemy import text

app_db_url = bw.app_db_url  # the harness's fixture (DATABASE_URL on the fresh test DB)
GAP_UNTIL = hhmm_text(registry_defaults()["adjustments.gap_at_open_until"])
CLEAR = "clear"
REFRESH = int(background.MARGIN_REFRESH_S)


class _Margin:
    """The route's ``ApproachMargin`` seam: legs -> Zerodha's margin; ``value`` changeable between refreshes."""

    def __init__(self, value: D) -> None:
        self.value, self.calls = value, 0

    async def __call__(self, _legs):
        self.calls += 1
        at = datetime.datetime(2026, 11, 6, 11, 40, tzinfo=datetime.UTC)
        return Margin(MARGIN_CHECKED, "", needed=self.value, broker_needed=self.value, checked_at=at)


def _t14_of(body, state: pe.StrategyState):
    """T-14's answer on this state: the Flag, the NotChecked code, or CLEAR (no entry, memory seen_clear)."""
    ev = pe.evaluate(body, state, {}, None, gap_until=GAP_UNTIL)
    hits = [r for r in ev.results if r.trigger_id == "T-14"]
    if not hits:
        assert ev.memory["T-14"]["seen_clear"] is True, ev.memory.get("T-14")
        return CLEAR
    (r,) = hits
    return r if isinstance(r, pe.Flag) else r.code


async def _t14_total(engine, sid: int) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT count(*) FROM public.adjustment_suggestions "
                                        "WHERE strategy_id = :s AND rule_id = 'T-14'"), {"s": sid})).scalar_one()


async def _start(app_db_url, monkeypatch, margin: _Margin | None):
    sid, scn = await bw._seeded(app_db_url, monkeypatch)
    await bw._pin_intraday(app_db_url, sid)
    now = [scn.clock_at]
    checks: list[tuple] = []  # (time, margin, gamma, T-14 answer) per check the worker built

    def observe(w, state):
        if w.strategy_id == sid:
            checks.append((now[0], state.margin, state.gamma, _t14_of(w.body, state)))

    async def preferences(_user_ref):
        return from_values(registry_defaults())

    async def user_values(_user_ref):
        return registry_defaults()
    worker = bw._Draining(provider_for=lambda _owner: scn.provider,
                          lister=lambda: background.owner_lister(scn.provider), clock=lambda: now[0],
                          settings=lambda _at: registry_defaults(), preferences=preferences, user_values=user_values,
                          observe=observe,
                          margin_of=None if margin is None else background.screen_margin_reader(margin))
    bw._push_spot(scn, bw.BEFORE_CROSS_SPOT, now[0])
    return sid, now, worker, checks


async def _run(worker, now, seconds: int) -> None:
    """One-second cycles, a margin refresh pass after each (the refresh itself reads at most once per window)."""
    for _ in range(seconds):
        await worker.cycle()
        await worker.refresh_margins()
        now[0] += datetime.timedelta(seconds=1)


async def test_t14_clear_with_a_huge_margin_then_exactly_one_record_at_the_crossing(app_db_url, monkeypatch):
    margin = _Margin(D("1000000000"))
    sid, now, worker, checks = await _start(app_db_url, monkeypatch, margin)
    base = await _t14_total(app_db_url, sid)
    await _run(worker, now, 150)
    assert worker.errors == []
    first = checks[0]
    assert first[1] is None and first[3] == f"{pe.P}missing_margin"  # before the first refresh: not checked
    after = [c for c in checks[1:] if c[1] is not None]
    assert len(after) >= 2 and all(c[1] == D("1000000000") for c in after), checks
    assert all(c[2] is not None and c[2].reason is None for c in after)  # figures valued on every such check
    assert checks[-1][3] == CLEAR, checks[-1]
    assert worker.margins.calls == {sid: 1} and margin.calls == 1
    assert await _t14_total(app_db_url, sid) == base  # not crossing: 0 records

    margin.value = D("1000")  # the margin falls: the worst 1% loss is far over the stage value
    await _run(worker, now, REFRESH - 150 - 5)  # still the old figure: up to just before the next refresh window
    assert worker.errors == [] and margin.calls == 1
    assert await _t14_total(app_db_url, sid) == base  # 0 before the crossing
    assert checks[-1][3] == CLEAR
    await _run(worker, now, 140)  # the refresh reads Rs 1,000; the crossing confirms at a candle close
    assert worker.errors == [] and margin.calls == 2
    assert isinstance(checks[-1][3], pe.Flag), checks[-1]
    assert await _t14_total(app_db_url, sid) == base + 1  # exactly 1 record at the crossing


async def test_t14_margin_absent_raises_no_record_and_answers_not_checked(app_db_url, monkeypatch):
    sid, now, worker, checks = await _start(app_db_url, monkeypatch, None)
    base = await _t14_total(app_db_url, sid)
    await _run(worker, now, 150)
    assert worker.errors == []
    assert await _t14_total(app_db_url, sid) == base
    assert len(checks) >= 2 and all(c[3] == f"{pe.P}missing_margin" for c in checks), checks[:3]
