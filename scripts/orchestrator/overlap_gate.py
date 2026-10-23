"""overlap_gate.py <older-worktree> <older-row-start-ref> <younger-worktree> [<younger-planned-files.txt>]

The planned-files list (the younger row's Measure file list) is REQUIRED before the younger builder starts: its real
changes are empty then, so only the plan can show an overlap.

ADR-171 rule 3 by machine (owner 2026-10-23: "This should be clear cut rule and should be binding"): two rows in flight
never touch the same file. Reads the REAL changes of each row - the older row's files changed since its start ref, the
younger row's since the point its branch split from the older row's branch (git merge-base), each plus every
uncommitted change (staged, unstaged, untracked) in its worktree - and exits 1 naming each shared file. Exit 0 only when
the two sets are disjoint. Run before the younger row's builder starts, when it reports, and before its rebase. A
worktree or ref that cannot be read fails closed (exit 2).
"""
import subprocess
import sys


def _git(worktree: str, *args: str) -> list[str]:
    out = subprocess.run(["git", "-C", worktree, *args],  # noqa: S603, S607 - fixed git argv, no shell
                         capture_output=True, text=True, check=True).stdout
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def changed_files(worktree: str, base: str) -> set[str]:
    """Every path the worktree's row has changed since ``base``: commits, staged, unstaged and untracked."""
    files = set(_git(worktree, "diff", "--name-only", f"{base}..HEAD"))
    files |= set(_git(worktree, "diff", "--name-only", "HEAD"))
    files |= set(_git(worktree, "diff", "--name-only", "--cached"))
    files |= set(_git(worktree, "ls-files", "--others", "--exclude-standard"))
    return files


def _planned(path: str) -> set[str]:
    """The younger row's PLANNED files (one repo-relative path per line, from its Measure), so an overlap is refused
    before any of them is touched (2026-10-23: row 11a's plan shared 5 files with row 10 while its real changes were
    0)."""
    with open(path, encoding="utf-8") as f:
        return {line.strip().replace("\\", "/") for line in f if line.strip() and not line.startswith("#")}


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4):  # three arguments, plus an optional planned-files list
        sys.stderr.write(__doc__)
        return 2
    older, older_start, younger = argv[:3]
    try:
        older_head = _git(older, "rev-parse", "HEAD")[0]
        fork = _git(younger, "merge-base", "HEAD", older_head)[0]
        a, b = changed_files(older, older_start), changed_files(younger, fork)
        if len(argv) == 4:  # noqa: PLR2004 - the optional fourth argument
            b |= _planned(argv[3])
    except (subprocess.CalledProcessError, FileNotFoundError, OSError, IndexError) as exc:
        sys.stderr.write(f"OVERLAP GATE: cannot read a worktree or ref ({type(exc).__name__}) - fail closed\n")
        return 2
    shared = sorted(a & b)
    if shared:
        sys.stdout.write("OVERLAP GATE: REFUSED - both rows touch: " + ", ".join(shared) + "\n")
        return 1
    sys.stdout.write(f"OVERLAP GATE: OK - older row {len(a)} files, younger row {len(b)} files, none shared\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
