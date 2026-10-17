"""AC-4 (W-076): migration 0013 builds its allowlist on its predecessor's text, and the predecessor is read from
``down_revision`` alone. A re-chain that leaves the allowlist built from a stale predecessor would silently drop the
newer blocks of a security function; these tests go red instead. No database needed."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

VERSIONS = Path(__file__).resolve().parents[1] / "backend" / "ofo_app" / "alembic" / "versions"
THIS = "0013_exchange_freeze_limits"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location("ofo_chain_" + path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _earlier_markers() -> dict[str, str]:
    """Every other migration's own allowlist marker, for every file numbered below this one."""
    out = {}
    for path in sorted(VERSIONS.glob("[0-9][0-9][0-9][0-9]_*.py")):
        if path.stem >= THIS:
            continue
        marker = getattr(_load(path), "ALLOWLIST_BLOCK_MARKER", None)
        if marker:
            out[path.stem] = marker
    return out


def test_allowlist_contains_every_earlier_migrations_block() -> None:
    """AC-4: the text 0013 installs holds the marker block of every earlier migration that has one (0002..0009 at
    least), and its own block exactly once."""
    mine = _load(VERSIONS / f"{THIS}.py")
    text = mine.extended_allowlist_sql()
    markers = _earlier_markers()
    assert len(markers) >= 8, markers
    missing = {name: m for name, m in markers.items() if m not in text}
    assert missing == {}
    assert text.count(mine.ALLOWLIST_BLOCK_MARKER) == 1


def test_own_marker_number_is_not_used_by_an_earlier_block() -> None:
    """AC-4: block numbers are unique; 0013's own number differs from every earlier marker's number."""
    mine = _load(VERSIONS / f"{THIS}.py")
    number = re.match(r"-- (\d+)\.", mine.ALLOWLIST_BLOCK_MARKER)
    assert number is not None
    earlier = {re.match(r"-- (\d+)\.", m).group(1) for m in _earlier_markers().values()}
    assert number.group(1) not in earlier


def test_predecessor_comes_from_down_revision_alone() -> None:
    """AC-4: the loaded predecessor IS the file named by down_revision, and the source holds no second hard-coded
    predecessor file name (a re-chain edits one line)."""
    mine = _load(VERSIONS / f"{THIS}.py")
    assert Path(mine._PREVIOUS.__file__).name == f"{mine.down_revision}.py"
    assert mine._PREVIOUS.revision == mine.down_revision
    source = (VERSIONS / f"{THIS}.py").read_text(encoding="utf-8")
    assert re.findall(r"""_load\(\s*["']\d{4}_""", source) == []
