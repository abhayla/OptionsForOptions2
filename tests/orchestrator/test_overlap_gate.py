"""ADR-171 rule 3 by machine: the overlap gate refuses two rows that touch the same file, from their REAL changes."""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("overlap_gate", ROOT / "scripts" / "orchestrator" / "overlap_gate.py")
gate = importlib.util.module_from_spec(_spec)
sys.modules["overlap_gate"] = gate
_spec.loader.exec_module(gate)


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)  # noqa: S603, S607 - fixed git argv


def _repo(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q", "-b", "base")
    _git(main, "config", "user.email", "t@t")
    _git(main, "config", "user.name", "t")
    (main / "shared.py").write_text("x = 1\n", encoding="utf-8")
    (main / "other.py").write_text("y = 1\n", encoding="utf-8")
    _git(main, "add", ".")
    _git(main, "commit", "-q", "-m", "base")
    young = tmp_path / "young"
    _git(main, "worktree", "add", "-q", "-b", "row-ahead", str(young), "base")
    return main, young


def test_disjoint_rows_pass_and_a_shared_committed_file_is_refused(tmp_path, capsys):
    main, young = _repo(tmp_path)
    (main / "shared.py").write_text("x = 2\n", encoding="utf-8")  # older row: uncommitted change
    (young / "other.py").write_text("y = 2\n", encoding="utf-8")
    _git(young, "commit", "-q", "-am", "younger")
    assert gate.main([str(main), "base", str(young)]) == 0
    (young / "shared.py").write_text("x = 3\n", encoding="utf-8")
    _git(young, "commit", "-q", "-am", "younger touches shared")
    assert gate.main([str(main), "base", str(young)]) == 1
    assert "shared.py" in capsys.readouterr().out


def test_an_untracked_or_staged_file_counts_as_a_change(tmp_path, capsys):
    main, young = _repo(tmp_path)
    (main / "new.py").write_text("", encoding="utf-8")  # older row: untracked
    (young / "new.py").write_text("", encoding="utf-8")
    _git(young, "add", "new.py")  # younger row: staged
    assert gate.main([str(main), "base", str(young)]) == 1
    assert "new.py" in capsys.readouterr().out


def test_shared_history_before_the_fork_is_not_counted(tmp_path):
    """Commits both branches already share (before the younger row split off) are neither row's change."""
    main, young = _repo(tmp_path)
    (main / "shared.py").write_text("x = 9\n", encoding="utf-8")
    _git(main, "commit", "-q", "-am", "older row commit after the fork")
    (young / "other.py").write_text("y = 9\n", encoding="utf-8")
    assert gate.main([str(main), "base", str(young)]) == 0


def test_a_planned_file_shared_with_the_older_row_is_refused_before_any_change(tmp_path, capsys):
    """Row 11a (2026-10-23): no real changes yet, but its plan named files row 10 had changed -> refused; a plan that
    shares nothing passes."""
    main, young = _repo(tmp_path)
    (main / "shared.py").write_text("x = 2\n", encoding="utf-8")
    plan = tmp_path / "plan.txt"
    plan.write_text("# row ahead plan\nshared.py\n", encoding="utf-8")
    assert gate.main([str(main), "base", str(young), str(plan)]) == 1
    assert "shared.py" in capsys.readouterr().out
    plan.write_text("other.py\n", encoding="utf-8")
    assert gate.main([str(main), "base", str(young), str(plan)]) == 0


def _both_touch(main, young, *names):
    for n in names:
        for root in (main, young):
            path = root / n
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{root.name}\n", encoding="utf-8")


def test_rows_sharing_only_generated_files_pass(tmp_path, capsys):
    main, young = _repo(tmp_path)
    _both_touch(main, young, "views/spec-digest.md", "docs/process/coverage-stages.yaml")
    assert gate.main([str(main), "base", str(young)]) == 0
    out = capsys.readouterr().out
    assert "shared only generated files" in out
    assert "views/spec-digest.md" in out


def test_a_product_file_plus_a_generated_file_refuses_naming_only_the_product_file(tmp_path, capsys):
    main, young = _repo(tmp_path)
    _both_touch(main, young, "views/build-order.md", "tests/errors/template_pins.json")
    assert gate.main([str(main), "base", str(young)]) == 1
    out = capsys.readouterr().out
    assert "tests/errors/template_pins.json" in out
    assert "build-order" not in out


def test_a_non_listed_file_under_views_still_refuses(tmp_path, capsys):
    main, young = _repo(tmp_path)
    _both_touch(main, young, "views/README.md", "views/extra/spec-digest.md")
    assert gate.main([str(main), "base", str(young)]) == 1
    out = capsys.readouterr().out
    assert "views/README.md" in out
    assert "views/extra/spec-digest.md" in out


def test_generated_list_is_exact_paths_only():
    assert not any("*" in g or g.endswith("/") for g in gate.GENERATED)
    # pinned exactly: a product file swapped into the list would let a real overlap through (review MINOR 2)
    expected = {
        "views/spec-digest.md", "views/build-order.md", "spec/requirements/INDEX.md",
        "knowledge/findings/INDEX.md", "docs/process/coverage-stages.yaml",
    }
    assert set(gate.GENERATED) == expected


def test_an_unreadable_worktree_or_ref_fails_closed(tmp_path):
    main, young = _repo(tmp_path)
    assert gate.main([str(main), "base", str(tmp_path / "missing")]) == 2  # noqa: PLR2004
    assert gate.main([str(main), "no-such-ref", str(young)]) == 2  # noqa: PLR2004
