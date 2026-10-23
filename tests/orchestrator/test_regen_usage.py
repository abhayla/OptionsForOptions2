"""regen.py: a bare or repeated --only exits 2 with the usage message, no traceback."""
import pathlib
import subprocess
import sys

import pytest

REGEN = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "orchestrator" / "regen.py"
USAGE_EXIT = 2


@pytest.mark.parametrize("args", [["--only"], [".", "--only"],
                                  ["--only", "build_order.py", "--only", "build_spec_index.py"]])
def test_bad_only_usage_exits_2_without_traceback(args, tmp_path):
    r = subprocess.run([sys.executable, str(REGEN), *args], capture_output=True, text=True,  # noqa: S603
                       check=False, cwd=tmp_path)
    assert r.returncode == USAGE_EXIT
    assert "usage: regen.py" in r.stderr and "Traceback" not in r.stderr
