"""brief_path.py: a brief path written with either separator resolves on every platform (CI class 2, 092889ce).

The string cases are platform-independent: they fail on Windows too if the helper stops reading a backslash as a
separator, so the Linux-runner failure is reproduced here without a Linux machine."""

from __future__ import annotations

import pathlib
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "hooks"))
sys.path.insert(0, str(REPO / "scripts" / "orchestrator"))
import brief_path as bp  # noqa: E402

REL = "docs/process/builder-sequence-briefs/row-99-x.md"


@pytest.mark.parametrize("raw, expected", [
    ("docs\\process\\row-1.md", "docs/process/row-1.md"),
    ("\\srv\\work-0\\docs\\process\\row-1.md", "/srv/work-0/docs/process/row-1.md"),
    ("/srv/work-0/docs/process/row-1.md", "/srv/work-0/docs/process/row-1.md"),
    ("D:\\repo\\docs\\process\\row-1.md", "D:/repo/docs/process/row-1.md"),
])
def test_normalise_ref_reads_both_separators(raw, expected):
    assert bp.normalise_ref(raw) == expected


@pytest.mark.parametrize("sep", ["/", "\\"])
def test_resolve_brief_finds_a_relative_brief_under_a_base_with_either_separator(tmp_path, sep):
    target = tmp_path / REL
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert bp.resolve_brief(REL.replace("/", sep), [other, tmp_path]) == tmp_path / REL


@pytest.mark.parametrize("sep", ["/", "\\"])
def test_resolve_brief_finds_an_absolute_brief_with_either_separator(tmp_path, sep):
    target = tmp_path / REL
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")
    written = str(target).replace("\\", "/").replace("/", sep)
    assert bp.resolve_brief(written, []) is not None


def test_resolve_brief_returns_none_for_a_missing_file_or_no_base(tmp_path):
    assert bp.resolve_brief(REL, [tmp_path]) is None
    assert bp.resolve_brief(REL, []) is None
