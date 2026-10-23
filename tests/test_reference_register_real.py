"""ADR-176 (2): the real difference register passes every record check and its generated page is current.

CI runs this with the guard tests, so a bad record or a hand-edited / stale page fails the build.
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("reference_register_real",
                                               ROOT / "scripts" / "orchestrator" / "reference_register.py")
rr = importlib.util.module_from_spec(_spec)
sys.modules["reference_register_real"] = rr
_spec.loader.exec_module(rr)


def test_the_real_register_passes_check_and_the_page_is_current(capsys):
    """Attack 7: `--check` over the real folder exits 0 (records valid, page current)."""
    code = rr.main(["--root", str(ROOT), "--check"])
    assert code == 0, capsys.readouterr().out
