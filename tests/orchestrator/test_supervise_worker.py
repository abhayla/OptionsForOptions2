"""k17 (issue #627 item 3): supervise_worker restarts the background worker when it dies. Injected spawn/clock/sleep."""
# ruff: noqa: PLR2004, S603
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "orchestrator"))
import supervise_worker as sw  # noqa: E402


class Clock:
    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


class Child:
    def __init__(self, clock, code, runs=1.0, on_wait=None):
        self.clock, self.code, self.runs, self.on_wait, self.terminated = clock, code, runs, on_wait, False

    def wait(self):
        if self.on_wait:
            self.on_wait()
        self.clock.t += self.runs
        return self.code

    def terminate(self):
        self.terminated = True


def run(codes, runs=1.0):
    clock, log, started = Clock(), [], []
    it = iter(codes)

    def spawn(cmd):
        started.append(cmd)
        c = next(it)
        if c == "raise":
            raise OSError("no such file")
        return Child(clock, c, runs)

    rc = sw.supervise(["x"], spawn=spawn, now=clock.now, sleep=clock.sleep, log=log.append)
    return rc, started, clock.sleeps, log


def test_two_crashes_then_runs_backoff_1_then_2():
    clock, started = Clock(), []
    stop = sw.StopFlag()
    codes = iter([1, 1, 0])

    def spawn(cmd):
        started.append(cmd)
        n = len(started)
        # the third child "stays up": it is stopped by the operator, not by crashing
        return Child(clock, next(codes), on_wait=stop.set if n == 3 else None)
    sw.supervise(["x"], spawn=spawn, now=clock.now, sleep=clock.sleep, log=lambda m: None, stop=stop)
    assert len(started) == 3 and clock.sleeps == [1, 2]


def test_clean_exit_zero_is_not_restarted():
    rc, started, sleeps, log = run([0])
    assert rc == 0 and len(started) == 1 and sleeps == [] and "exit 0" in log[0]


def test_six_fast_crashes_gives_up_after_five_restarts():
    rc, started, sleeps, log = run([1] * 6)
    assert rc != 0 and len(started) == 6 and sleeps == [1, 2, 4, 8, 16] and "giving up" in log[-1]


def test_killed_by_signal_is_restarted():
    rc, started, _, _ = run([-9, 0])
    assert rc == 0 and len(started) == 2


def test_cannot_start_counts_as_a_crash():
    rc, started, sleeps, log = run(["raise", 0])
    assert rc == 0 and len(started) == 2 and sleeps == [1] and any("cannot start" in m for m in log)


def test_backoff_resets_after_healthy_run_and_caps_at_60():
    _, _, sleeps, _ = run([1, 1, 0], runs=700.0)
    assert sleeps == [1, 1]
    assert sw.backoff(10) == 60


def test_supervisor_stopped_terminates_child_and_does_not_restart():
    clock, children = Clock(), []
    stop = sw.StopFlag()

    def spawn(cmd):
        c = Child(clock, 1, on_wait=stop.set)  # Ctrl+C arrives while the child runs
        children.append(c)
        return c
    rc = sw.supervise(["x"], spawn=spawn, now=clock.now, sleep=clock.sleep, log=lambda m: None, stop=stop)
    assert len(children) == 1 and children[0].terminated and rc == 0 and clock.sleeps == []


def test_real_tiny_child_exit_zero():
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "orchestrator" / "supervise_worker.py"), "--",
                        sys.executable, "-c", "pass"], capture_output=True, text=True, timeout=30, check=False)
    assert r.returncode == 0 and "exit 0" in (r.stdout + r.stderr)
