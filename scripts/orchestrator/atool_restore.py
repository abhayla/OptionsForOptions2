"""Put the shared test database back at main's migration head after atool ran a branch's migration tests (finding
branch-migration-tests-move-shared-db). Pure: `run` is an injected callable (cmd list, cwd) -> (rc, output)."""
import os
import re
import subprocess
import sys

ALEMBIC = ["python", "-m", "alembic", "-c", "backend/ofo_app/alembic.ini"]
_HEAD = re.compile(r"^([0-9A-Za-z_]+)\s+\(head\)", re.M)


def parse_head(text):
    m = _HEAD.search(text or "")
    return m.group(1) if m else None


def real_run(cmd, cwd):
    """Run `cmd` through db_run.py in `cwd` (which sets DATABASE_URL without printing it)."""
    runner = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db_run.py")
    r = subprocess.run([sys.executable, runner, cwd, *cmd],  # noqa: S603 - fixed argv, no shell
                        cwd=cwd, capture_output=True, text=True,
                       check=False)
    return r.returncode, r.stdout + r.stderr


def restore_main_head(run, main_checkout, wt):
    """Downgrade the shared DB to main's head using the branch checkout (it knows the newer revisions), then prove it
    with main's own `current`. Returns (ok, message)."""
    rc, out = run([*ALEMBIC, "heads"], main_checkout)
    main_head = parse_head(out) if rc == 0 else None
    if not main_head:
        return False, f"shared DB LEFT AT unknown - could not read main head (rc {rc}): {(out or '').strip()[-200:]}"
    rc, out = run([*ALEMBIC, "downgrade", main_head], wt)
    if rc:
        return False, f"shared DB LEFT AT unknown - downgrade failed (rc {rc}), main is {main_head}: " \
                      f"{(out or '').strip()[-200:]}"
    rc, out = run([*ALEMBIC, "current"], main_checkout)
    cur = parse_head(out) or (re.search(r"^([0-9A-Za-z_]+)", out or "", re.M) or [None, None])[1]
    if rc == 0 and cur == main_head:
        return True, f"shared DB restored to {main_head}"
    return False, f"shared DB LEFT AT {cur} - main is {main_head}"


def run_with_restore(step, run, main_checkout, wt, report):
    """Run `step()`, then always restore main's head, even if the step raised; report((ok, msg))."""
    try:
        return step()
    finally:
        report(restore_main_head(run, main_checkout, wt))
