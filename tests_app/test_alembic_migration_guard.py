"""scripts/alembic_migration_guard.py refuses an empty migration and passes the real baseline."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("guard", ROOT / "scripts" / "alembic_migration_guard.py")
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)  # type: ignore[union-attr]


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "0002_x.py"
    path.write_text(f"from alembic import op\nrevision = 'x'\ndown_revision = 'y'\n\ndef upgrade():\n{body}\n")
    return path


def test_real_versions_pass() -> None:
    assert guard.main() == 0


def test_empty_upgrade_is_refused(tmp_path: Path) -> None:
    _write(tmp_path, "    pass")
    assert guard.main(tmp_path) == 1


def test_upgrade_without_op_call_is_refused(tmp_path: Path) -> None:
    _write(tmp_path, "    x = 1")
    assert guard.main(tmp_path) == 1


def test_upgrade_with_op_execute_passes(tmp_path: Path) -> None:
    _write(tmp_path, "    op.execute('SELECT 1')")
    assert guard.main(tmp_path) == 0


def test_missing_versions_dir_fails_closed(tmp_path: Path) -> None:
    assert guard.main(tmp_path / "absent") == 1
