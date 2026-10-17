"""Finding branch-migration-tests-move-shared-db: after atool runs a branch's migration tests against the shared test
database, it must put the database back at main's head and prove it. Fake runner only: no DB, no subprocess."""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "orchestrator"))
import atool_restore as ar  # noqa: E402

MAIN, WT = "/main", "/wt"
HEADS = "0015_abc (head)\n"


def fake(current="0015_abc (head)\n", down_rc=0, heads=HEADS):
    calls = []

    def run(cmd, cwd):
        calls.append((cmd, cwd))
        if cmd[-1] == "heads":
            return 0, heads
        if "downgrade" in cmd:
            return down_rc, "boom" if down_rc else ""
        if cmd[-1] == "current":
            return 0, current
        raise AssertionError(cmd)
    return run, calls


def test_parse_head():
    assert ar.parse_head("INFO x\n0015_abc (head)\n") == "0015_abc"
    assert ar.parse_head("nothing") is None


def test_restored_ok():
    run, calls = fake()
    ok, msg = ar.restore_main_head(run, MAIN, WT)
    assert ok and msg == "shared DB restored to 0015_abc"
    down = next(c for c in calls if "downgrade" in c[0])
    assert down[1] == WT and down[0][-1] == "0015_abc"
    assert [c[1] for c in calls if c[0][-1] in ("heads", "current")] == [MAIN, MAIN]


def test_current_differs_is_red():
    run, _ = fake(current="0016_def (head)\n")
    ok, msg = ar.restore_main_head(run, MAIN, WT)
    assert not ok and "LEFT AT 0016_def" in msg and "main is 0015_abc" in msg


def test_downgrade_fails_is_red():
    run, _ = fake(down_rc=1)
    ok, msg = ar.restore_main_head(run, MAIN, WT)
    assert not ok and "LEFT AT" in msg and "downgrade failed" in msg


def test_unreadable_heads_is_red():
    run, _ = fake(heads="garbage")
    ok, msg = ar.restore_main_head(run, MAIN, WT)
    assert not ok and "main head" in msg


def test_restore_runs_when_migration_step_raises():
    run, calls = fake()
    results = []

    def step():
        raise RuntimeError("tests blew up")
    with pytest.raises(RuntimeError):
        ar.run_with_restore(step, run, MAIN, WT, results.append)
    assert results == [(True, "shared DB restored to 0015_abc")]
    assert any("downgrade" in c[0] for c in calls)
