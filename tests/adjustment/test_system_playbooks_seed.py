"""GC-ADJ2 step 1A leftover: the checked-in system playbook seed is exactly what build_system_playbooks.py writes."""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_build_system_playbooks_check_exits_zero():
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_system_playbooks.py"), "--check"],  # noqa: S603
                         cwd=ROOT, capture_output=True, text=True, timeout=120, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
