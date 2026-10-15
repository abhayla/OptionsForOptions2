"""Every file a work item names in `tests_required` exists (W-067, 2026-10-10: a fix round deleted a listed test file
and every CI check stayed green; only the Tier A verifier noticed, so AC-4's evidence would have pointed at a file that
no longer existed). Project stop-gap until the kit's trace check does this (abhayla/Startup-Factory#94).

Entries read `AC-<n>: path[, path...]`; a `::test_name` suffix names a test inside the file and is ignored here. Only
items that claim the tests exist are checked (status in_review or done); a todo/blocked item lists tests still to write.
"""
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
ENTRY = re.compile(r"^AC-\d+:\s*(?P<paths>.+)$")
CLAIMED = {"in_review", "done"}


def _frontmatter(path: pathlib.Path) -> dict:
    parts = path.read_text(encoding="utf-8").split("---", 2)
    return yaml.safe_load(parts[1]) or {}


def missing_test_files(root: pathlib.Path) -> list[str]:
    missing = []
    for item in sorted((root / "work").glob("W-*.md")):
        front = _frontmatter(item)
        if front.get("status") not in CLAIMED:
            continue
        for entry in front.get("tests_required") or []:
            match = ENTRY.match(str(entry).strip())
            if not match:
                continue  # malformed entries are factory_lint's job
            for raw in match.group("paths").split(","):
                rel = raw.strip().split("::", 1)[0]
                if rel and not (root / rel).is_file():
                    missing.append(f"{item.name}: {rel}")
    return missing


def test_every_tests_required_file_exists():
    assert missing_test_files(ROOT) == []


def test_the_check_catches_a_missing_file(tmp_path):
    (tmp_path / "work").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_here.py").write_text("", encoding="utf-8")
    (tmp_path / "work" / "W-999.md").write_text(
        "---\nid: W-999\nstatus: done\ntests_required:\n- 'AC-1: tests/test_here.py, tests/test_gone.py::test_x'\n---\n",
        encoding="utf-8")
    (tmp_path / "work" / "W-998.md").write_text(
        "---\nid: W-998\nstatus: todo\ntests_required:\n- 'AC-1: tests/test_not_yet.py'\n---\n", encoding="utf-8")
    assert missing_test_files(tmp_path) == ["W-999.md: tests/test_gone.py"]  # the todo item's future test is fine
