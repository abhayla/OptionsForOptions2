"""pr_close_check: GitHub closing references must be whole lines `Fixes #N` (body) and absent otherwise (commits)."""
import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pr_close_check", ROOT / "scripts" / "orchestrator" / "pr_close_check.py")
pcc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pcc)
FIX = ROOT / "tests" / "fixtures" / "pr_bodies"


def body(name):
    return (FIX / name).read_text(encoding="utf-8")


def test_pr283_fails_on_line_1():
    problems = pcc.check(body("pr_283.txt"), [])
    assert len(problems) == 1 and problems[0].startswith("body line 1:") and "Fix #263 items 1-3" in problems[0]


def test_pr284_fails_on_both_lines():
    problems = pcc.check(body("pr_284.txt"), [])
    assert any(p.startswith("body line 1:") and "Fix #279 items 2-3" in p for p in problems)
    assert any("is resolved: #275" in p for p in problems)


def test_pr282_whole_line_is_allowed_but_bold_line_1_is_not():
    # The real #282 body also opens with "**Fix #237 (Tier A): ...**", which is a qualified closing reference.
    problems = pcc.check(body("pr_282.txt"), [])
    assert [p.split(":")[0] for p in problems] == ["body line 1"]
    rest = "\n".join(body("pr_282.txt").splitlines()[1:])
    assert pcc.check(rest, []) == []


@pytest.mark.parametrize("text", ["Fixes #237.", "Fixes #237", "Closes #5", "Resolves #12.", "fixes #3", "CLOSES #4"])
def test_allowed_whole_lines(text):
    assert pcc.check("intro\n" + text + "\nmore", []) == []


@pytest.mark.parametrize("text", [
    "Addresses items 1-3 of #263", "#263 item 4 stays open", "see #271", "prefix fix", "The fix for 12 is #3",
    "Fixed-point math, #4",
])
def test_non_closing_text_passes(text):
    assert pcc.check(text, []) == []


@pytest.mark.parametrize("text", [
    "Fixes: #5", "fix #5 items 1-2", "Closed #7 partly", "resolves owner/repo#9", "Resolved: other-org/x.y#10",
    "`Fixes #5`", "- Fixes #5", "Fixes #5, #6", "FIXED #8", "Fixes  #5 today", "Fixes #5 items 1-2",
])
def test_closing_forms_flagged(text):
    assert len(pcc.check(text, [])) == 1


def test_fenced_code_is_flagged():
    assert len(pcc.check("```\nFixes #5 partly\n```", [])) == 1


def test_commit_message_qualified_fails_and_merge_commit_too():
    problems = pcc.check("ok", ["#275: Fix #275 items 1-5", "Merge pull request #1\n\nCloses #2 and more"])
    assert [p.split(":")[0] for p in problems] == ["commit 1 line 1", "commit 2 line 3"]


def test_commit_whole_line_allowed():
    assert pcc.check("ok", ["subject\n\nFixes #275."]) == []


def test_cli_offline_exit_codes(tmp_path, capsys):
    good = tmp_path / "b.txt"
    good.write_text("Fixes #1.\n", encoding="utf-8")
    assert pcc.main(["--body-file", str(good)]) == 0
    commits = tmp_path / "c.txt"
    commits.write_text("a\nFix #1 items 1-2\n---COMMIT---\nb\n", encoding="utf-8")
    assert pcc.main(["--body-file", str(good), "--commits-file", str(commits)]) == 1
    assert "commit 1 line 2" in capsys.readouterr().out
    assert pcc.main(["--body-file", str(tmp_path / "missing.txt")]) == 2
    assert pcc.main([]) == 2


@pytest.mark.parametrize("text", [
    "Fixes https://github.com/o/r/issues/5 partly", "see: Closes https://github.com/o/r/issues/5",
    "- Fixes https://github.com/o/r/issues/5",
])
def test_issue_url_in_prose_fails(text):
    assert len(pcc.check(text, [])) == 1


def test_issue_url_whole_line_passes():
    assert pcc.check("x\nFixes https://github.com/o/r/issues/5\ny", []) == []
    assert pcc.check("x\nCloses https://github.com/o/r/issues/5.\ny", []) == []


@pytest.mark.parametrize("text", ["**Fixes** #12", "_fixes_ #12", "`Fixes` #12", "**Fixes:** #12", "__Closes__ #3"])
def test_markdown_wrapped_keywords_fail(text):
    assert len(pcc.check(text, [])) == 1
