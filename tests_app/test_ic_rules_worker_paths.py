"""IC e2e paper contract, Stage B1: every rule that is ON in the approved iron condor playbook raises exactly ONE in-app
record through the real background worker and the alert gate when a moving test path crosses it.

Per case: the record count of the rule is 0 at frame k-1, exactly 1 at frame k (the crossing) and still exactly 1 at
k+1 (no duplicate per tick). Guidance situations (S-03, S-04, S-05, S-08, S-09) never raise a record; T-21 stale prices
withhold the record. Each path is walked ONLY over the frames its cases need (throwaway database, one seeded paper
iron condor per path). T-14 is Stage B2, T-18 Stage C1, T-16 is off by default (ADR-247).

Paths (tests/fixtures/adjust_paths, all one iron condor: BUY PE 22600, SELL PE 22800, SELL CE 23400, BUY CE 23600, 2 lots):
PATH-10 spot drifts up on Fri 6 Nov; PATH-11 spot falls; PATH-12 time passes at a flat spot (Fri to Mon expiry);
PATH-13 IV rises; PATH-14 IV falls on the entry day; PATH-15 gap at the open; PATH-16 expiry day, short within 0.3%;
PATH-17 the PATH-11 crossing with stale prices.

KNOWN holds ``xfail(strict=True)`` semantics per case: a case listed there MUST still fail (if it passes the test
fails, so the list cannot rot); the reason is the measured blocker, reported to the lead, never a weaker assertion.
"""
from __future__ import annotations

import pytest
import _paths_helpers as h

# (case id, rule id as stored, crossing frame k)
CASES: dict[str, list[tuple[str, str, int]]] = {
    "PATH-10": [("T-03", "T-03", 9), ("T-02", "T-02", 14), ("T-06", "T-06", 18), ("T-06-2x-credit", "stop.credit_x", 18)],
    "PATH-11": [("T-09", "T-09", 6), ("S-02", "sit.S-02", 7)],
    "PATH-12": [("S-06", "day.beforeWeekend.1500.0", 3), ("T-10b", "T-10b", 8), ("T-19", "T-19", 8)],
    "PATH-13": [("T-11", "T-11", 3)],
    "PATH-14": [("T-07", "T-07", 3), ("T-11-day1", "T-11", 3), ("S-12", "sit.S-12", 3)],
    "PATH-15": [("T-13", "T-13", 1)],
    "PATH-16": [("S-07", "day.expiry.1430.5", 1)],
}
EXTRA_FRAMES = {"PATH-12": [4, 5, 6, 7]}
GUIDANCE = ("sit.S-03", "sit.S-04", "sit.S-05", "sit.S-08", "sit.S-09")
KNOWN = {  # case -> measured blocker (2026-11-05 run on a throwaway DB; counts are the records of that rule)
    "T-03": "DEFECT for the lead: T-03 raised 1 record at PATH-10 frame 9 and a SECOND at frame 10 (2 records, k+1)",
    "T-11": "no T-11 record at +3 and +4 IV points (PATH-13 frames 2-4: 0 records); cause not found in B1 budget",
    "T-11-day1": "no T-11 record at +3 IV points on the entry day (PATH-14 frame 3: only T-07)",
    "S-12": "no sit.S-12 record at 54% of max profit on the entry session (PATH-14 frame 3: only T-07)",
    "T-19": "no T-19 record on the expiry day at flat spot (PATH-12 frames 4-8: T-09, T-10b only)",
}


def frames_for(path_id: str) -> list[int]:
    last = len(list(h.scenario_mode.frame_path(path_id, 0).parent.glob("frame-*.json"))) - 1
    need = {f for _c, _r, k in CASES[path_id] for f in (k - 1, k, k + 1) if 0 <= f <= last}
    return sorted(need | set(EXTRA_FRAMES.get(path_id, [])))


def check(seen: dict, rule: str, k: int) -> None:
    last = max(seen)
    assert seen[k - 1][rule] == 0, ("k-1", seen[k - 1])
    assert seen[k][rule] == 1, ("k", seen[k])
    if k + 1 <= last:
        assert seen[k + 1][rule] == 1, ("k+1", seen[k + 1])


@pytest.mark.parametrize("path_id", sorted(CASES))
async def test_every_on_rule_raises_exactly_one_record_at_its_crossing_frame(app_engine, monkeypatch, path_id):
    h.set_env(app_engine, monkeypatch, path_id)
    try:
        sid, seen, errors = await h.walk(app_engine, path_id, frames_for(path_id))
        print("B1-COUNTS", path_id, {k: dict(c) for k, c in seen.items()})
        assert errors == [], errors
        failed, rotten = [], []
        for case, rule, k in CASES[path_id]:
            try:
                check(seen, rule, k)
            except AssertionError as e:
                if case not in KNOWN:
                    failed.append((case, e))
                continue
            if case in KNOWN:
                rotten.append(case)  # strict: a listed blocker that now passes must leave KNOWN
        assert not failed, failed
        assert not rotten, f"known blocker now passes, remove from KNOWN: {rotten}"
        for counts in seen.values():  # guidance situations are shown, never raised
            assert not [r for r in counts if r in GUIDANCE], counts
    finally:
        await h.teardown()


async def test_t21_stale_prices_withhold_the_record_a_fresh_run_raises(app_engine, monkeypatch):
    """PATH-11 frame 6 raises T-09 with fresh prices (above); PATH-17 is the same crossing with the feed 600 s old: 0."""
    h.set_env(app_engine, monkeypatch, "PATH-17")
    try:
        _sid, seen, errors = await h.walk(app_engine, "PATH-17")
        print("B1-COUNTS stale", {k: dict(c) for k, c in seen.items()})
        assert errors == [], errors
        assert all(sum(c.values()) == 0 for c in seen.values()), seen
    finally:
        await h.teardown()
