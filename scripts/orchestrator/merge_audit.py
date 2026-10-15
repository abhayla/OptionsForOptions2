"""merge_audit.py <repo-dir> <branch-tip-before-merge> <main-ref> <merged-head> [allowed-extra-file...]

Proves a merge of main into a branch lost nothing (owner rule 2026-10-08: "make sure nothing gets lost due to any PR
or code merging"). Exit 1 when:
1. a file only the branch changed differs at the merged head from the branch tip (a branch change was dropped);
2. a file only main changed differs at the merged head from main (a main change was dropped or reverted);
3. the merged head differs from main in a file that is neither the branch's own nor an allowed extra.
4. any file changed by the merge (branch-only, main-only or both) holds a conflict marker at the merged head: a line
   starting `<<<<<<< ` or `>>>>>>> `, or exactly `=======` when a `<<<<<<< ` line is in the same file.
Files changed on BOTH sides are listed for reading (check both sides' lines survived).
Example: python scripts/orchestrator/merge_audit.py . e8114de 9f075f1 34b8346
"""
import subprocess
import sys


def find_markers(text):
    """Return [(line_no, line)] of conflict markers; a bare ======= counts only if a <<<<<<< line exists too."""
    lines = text.splitlines()
    has_open = any(line.startswith("<<<<<<< ") for line in lines)
    return [(n, line) for n, line in enumerate(lines, 1)
            if line.startswith("<<<<<<< ") or line.startswith(">>>>>>> ") or (has_open and line == "=======")]


def main():
    repo, tip, main_ref, head = sys.argv[1:5]
    extras = set(sys.argv[5:])

    def git(*a):
        return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, check=True).stdout

    def changed(a, b):
        return {line for line in git("diff", "--name-only", a, b).splitlines() if line}

    base = git("merge-base", tip, main_ref).strip()
    branch_files, main_files = changed(base, tip), changed(base, main_ref)
    both = branch_files & main_files
    lost_branch = sorted(f for f in branch_files - both if f in changed(tip, head))
    lost_main = sorted(f for f in main_files - both - extras if f in changed(main_ref, head))
    unexpected = sorted(changed(main_ref, head) - branch_files - extras)
    print(f"merge base {base[:7]} | branch changed {len(branch_files)} files | main changed {len(main_files)} "
          f"| both {len(both)}")
    print("branch changes altered by the merge:", lost_branch or "none")
    print("main changes altered by the merge:", lost_main or "none")
    print("head differs from main outside the branch's own files + extras:", unexpected or "none")
    print("changed on both sides (read these):", sorted(both) or "none")
    markers = []
    for f in sorted(branch_files | main_files):
        shown = subprocess.run(["git", "-C", repo, "show", f"{head}:{f}"], capture_output=True)
        if shown.returncode != 0:  # deleted at the merged head
            continue
        markers += [f"{f}:{n}" for n, _ in find_markers(shown.stdout.decode("utf-8", errors="replace"))]
    for loc in markers:
        print(f"conflict marker left in {loc}")
    return 1 if (lost_branch or lost_main or unexpected or markers) else 0


if __name__ == "__main__":
    sys.exit(main())
