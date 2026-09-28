"""Spec integrity checks the kit lint does not make.

Guards knowledge/findings/duplicate-acceptance-criterion-id.json.
"""
import pathlib
import re

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _frontmatter(path):
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    return yaml.safe_load(parts[1])


def _requirement_files():
    files = sorted((ROOT / "spec" / "requirements").glob("REQ-*.md"))
    assert files, "no requirement files found"
    return files


def duplicate_ac_ids(frontmatter):
    ids = [ac.get("id") for ac in frontmatter.get("acceptance_criteria") or []]
    return sorted({i for i in ids if ids.count(i) > 1})


def test_acceptance_criterion_ids_are_unique_per_requirement():
    offenders = {}
    for path in _requirement_files():
        dups = duplicate_ac_ids(_frontmatter(path))
        if dups:
            offenders[path.name] = dups
    assert offenders == {}, f"duplicate AC ids: {offenders}"


def test_duplicate_detector_flags_a_duplicate():
    # red case: proves the check can fail
    assert duplicate_ac_ids({"acceptance_criteria": [{"id": "AC-1"}, {"id": "AC-2"}, {"id": "AC-1"}]}) == ["AC-1"]
    assert duplicate_ac_ids({"acceptance_criteria": [{"id": "AC-1"}, {"id": "AC-2"}]}) == []


def duplicate_test_basenames(paths):
    seen = {}
    for p in paths:
        seen.setdefault(p.name, []).append(p)
    return {name: ps for name, ps in seen.items() if len(ps) > 1}


def test_test_file_names_are_unique_across_test_folders():
    # a test folder without __init__.py is not a package, so pytest imports its tests by bare file name;
    # two such folders holding the same file name collide ("import file mismatch") only once both reach
    # main (finding: duplicate-test-basename-collision). Files inside package folders are imported by a
    # dotted name and cannot collide this way, so they are left out.
    tests = sorted(
        p for p in (ROOT / "tests").rglob("test_*.py") if not (p.parent / "__init__.py").exists()
    )
    assert duplicate_test_basenames(tests) == {}


def test_duplicate_test_basename_detector_flags_a_collision():
    a = pathlib.Path("tests/rules/test_model.py")
    b = pathlib.Path("tests/strategy/test_model.py")
    assert set(duplicate_test_basenames([a, b])) == {"test_model.py"}
    assert duplicate_test_basenames([a, pathlib.Path("tests/strategy/test_strategy_model.py")]) == {}


def test_work_items_link_exactly_one_requirement():
    # evidence is keyed evidence/<W-id>/<AC-id>.md, so a work item linking two requirements would
    # make AC-1 of both collide in one file
    for path in sorted((ROOT / "work").glob("W-*.md")):
        fm = _frontmatter(path)
        assert len(fm.get("requirement_ids") or []) == 1, f"{path.name} must link exactly one requirement"
        for entry in fm.get("tests_required") or []:
            assert re.match(r"^AC-\d+(:|$)", entry), f"{path.name}: tests_required entry must start with AC-<n>: {entry!r}"
