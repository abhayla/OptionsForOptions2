"""supervise_worker.py [-- <child command...>]: run the background worker and start it again when it dies (issue #627
item 3, REQ-115 AC-6, ADR-286). Default child: python -m ofo_app.background. Child gets this process's environment.
Exit 0 of the child: stop. Any other exit, a kill by signal, or a failed start: log, back off 1, 2, 4 .. 60 s, restart.
5 restarts inside 10 minutes: give up with exit 1 (the API's heartbeat watch then says "stopped"). Ctrl+C / SIGTERM:
the child is stopped by its PID (never by command line) and not restarted. Standard library only."""
import signal
import subprocess
import sys
import threading
import time

DEFAULT_CHILD = [sys.executable, "-m", "ofo_app.background"]
MAX_RESTARTS, WINDOW_S, HEALTHY_S, CAP_S = 5, 600, 600, 60


def backoff(failures):
    """Seconds to wait before restart number `failures` (1-based)."""
    return min(2 ** (failures - 1), CAP_S)


class StopFlag:
    def __init__(self):
        self._e, self.child = threading.Event(), None

    def set(self):
        self._e.set()

    def is_set(self):
        return self._e.is_set()

    def wait(self, s):
        self._e.wait(s)


def supervise(cmd, spawn=subprocess.Popen, now=time.monotonic, sleep=None, log=print, stop=None):  # noqa: PLR0913 (spawn/clock/sleep/log/stop are the test seams)
    stop = stop or StopFlag()
    sleep = sleep or stop.wait
    restarts, failures = [], 0  # restart times inside the window; consecutive quick failures
    while not stop.is_set():
        t0 = now()
        try:
            child = spawn(cmd)
            stop.child = child
            try:
                code = child.wait()
            except KeyboardInterrupt:
                stop.set()
                code = None
            if stop.is_set():
                child.terminate()
                log("supervisor stopped: child stopped by pid, not restarted")
                return 0
        except OSError as e:
            code = None
            log(f"cannot start {cmd}: {e}")
        ran = now() - t0
        if code == 0:
            log(f"child exit 0 after {ran:.0f}s: clean exit, not restarted")
            return 0
        if code is not None:
            log(f"child exit {code} after {ran:.0f}s")
        failures = 1 if ran >= HEALTHY_S else failures + 1
        restarts = [t for t in restarts if now() - t < WINDOW_S]
        if len(restarts) >= MAX_RESTARTS:
            log(f"giving up: {MAX_RESTARTS} restarts inside {WINDOW_S // 60} minutes")
            return 1
        wait_s = backoff(failures)
        log(f"restarting in {wait_s}s")
        sleep(wait_s)
        restarts.append(now())
    return 0


def main(argv):
    cmd = argv[argv.index("--") + 1:] if "--" in argv else []
    stop = StopFlag()

    def on_signal(*_):
        stop.set()
        if stop.child is not None:
            stop.child.terminate()  # by PID, through the Popen handle
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    return supervise(cmd or DEFAULT_CHILD, log=lambda m: print(m, flush=True), stop=stop)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
