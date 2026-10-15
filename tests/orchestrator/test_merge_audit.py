"""Process tooling: merge_audit.py fails when a conflict marker is left in a file the merge changed."""
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "orchestrator" / "merge_audit.py"
MARKED = "a\n<<<<<<< HEAD\nx\n=======\ny\n>>>>>>> origin/main\nb\n"


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          capture_output=True, text=True, check=True).stdout.strip()


def build(tmp_path, merged):
    """base -> branch (edits both.txt + branch.txt) and main (edits both.txt + main.txt); merged = {file: text}."""
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    for f in ("both.txt", "branch.txt", "main.txt"):
        (r / f).write_text("base\n")
    git(r, "add", ".")
    git(r, "commit", "-qm", "base")
    git(r, "checkout", "-qb", "br")
    (r / "both.txt").write_text("base\nbranch\n")
    (r / "branch.txt").write_text("branch\n")
    git(r, "commit", "-qam", "branch")
    tip = git(r, "rev-parse", "HEAD")
    git(r, "checkout", "-q", "main")
    (r / "both.txt").write_text("main\nbase\n")
    (r / "main.txt").write_text("main\n")
    git(r, "commit", "-qam", "main")
    git(r, "checkout", "-q", "br")
    git(r, "merge", "-q", "--no-commit", "main")
    for f, t in merged.items():
        (r / f).write_text(t)
    git(r, "add", ".")
    git(r, "commit", "-qm", "merge")
    return r, tip, git(r, "rev-parse", "main"), git(r, "rev-parse", "HEAD")


def audit(r, tip, main_ref, head):
    p = subprocess.run([sys.executable, str(SCRIPT), str(r), tip, main_ref, head], capture_output=True, text=True)
    return p.returncode, p.stdout


def test_marker_in_file_changed_on_both_sides_fails_naming_file_and_line(tmp_path):
    code, out = audit(*build(tmp_path, {"both.txt": MARKED}))
    assert code == 1
    assert "conflict marker left in both.txt:2" in out
    assert "conflict marker left in both.txt:4" in out
    assert "conflict marker left in both.txt:6" in out


def test_marker_in_file_changed_on_one_side_fails(tmp_path):
    code, out = audit(*build(tmp_path, {"both.txt": "main\nbase\nbranch\n", "main.txt": MARKED}))
    assert code == 1
    assert "conflict marker left in main.txt:2" in out


def test_clean_merge_passes_and_bare_underline_is_not_a_marker(tmp_path):
    code, out = audit(*build(tmp_path, {"both.txt": "Title\n=======\nmain\nbranch\n"}))
    assert "conflict marker" not in out
    assert code == 0
