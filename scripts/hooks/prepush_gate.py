"""PreToolUse hook (Bash|PowerShell): refuse `git push` unless the project's whole pre-push list passed on exactly the
HEAD being pushed. The proof is a marker file written by scripts/orchestrator/prepush.py
(<git-common-dir>/ofo-prepush/<full sha>.json) only when every step passed on a clean tracked tree.

Finding local-ci-mirror-runs-a-subset (4 occurrences): ci_local mirrors ci.yml only, so pushes reached CI red on the
ruff ratchet, the coverage check and the alembic guard. Prose reminders failed; this is the choke point. Land.py checks
the same marker before its first push.

Judged per step, quote-aware (gate_before_commit's scanner): `git push` after `;`, `&&`, a newline, inside
`bash -c "..."`, `git -C dir push`, `git -c k=v push`, wrappers (env, timeout, time). Text that merely mentions the
words (echo, grep, a commit message) passes. The directory is `-C <dir>`, else a preceding `cd <dir>` step, else the
hook input `cwd`.
Allowed without a marker: --dry-run / -n, --delete / -d, only `:branch` refspecs, --tags alone, and a command
containing PREPUSH_GATE_ALLOW=<non-empty reason>.
A marker is for one sha: an amended or new commit has none, and `prepush.py && git push` in ONE command is refused
(the marker does not exist when the hook looks): run prepush.py first, push in the next command.
Fails open (exit 0) on every error: unreadable input, git failure, missing prepush module, unknown shape.

Known bypasses (out of scope, not chased): `gh api` / REST ref updates, a git alias or wrapper script that pushes,
editing or copying the marker by hand (a marker must still name its own sha), an abbreviated long option
(--dry), a push of a ref other than HEAD (the check is on the HEAD of the directory), a push from a non-Claude shell.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ORCH_DIR = str(Path(__file__).resolve().parents[1] / "orchestrator")
MAX_LEN = 100_000
CD_WORDS = {"cd", "chdir", "pushd", "set-location", "sl"}
PUSH_VALUE_OPTS = {"--repo", "-o", "--push-option", "--receive-pack", "--exec"}
ALLOW = re.compile(r"""PREPUSH_GATE_ALLOW=(?:"[^"]+"|'[^']+'|[^\s"';&|]+)""")
MSYS_DRIVE = re.compile(r"^/([A-Za-z])(?:/|$)")
SHORT_ALLOW = {"n", "d"}  # -n dry run, -d delete
MESSAGE = ("BLOCKED by prepush_gate: commit {short} has no passing pre-push run. Run: python "
           "scripts/orchestrator/prepush.py (finding local-ci-mirror-runs-a-subset). Bypass with a reason: "
           "PREPUSH_GATE_ALLOW=<reason>.")


def _native(path: str) -> str:
    """/d/x (bash on Windows) -> D:/x so Python can open it."""
    m = MSYS_DRIVE.match(path)
    if m and os.name == "nt":
        return m.group(1).upper() + ":/" + path[3:]
    return path


def _join(base: str, path: str) -> str:
    return os.path.abspath(os.path.join(base, _native(path)))


def _cd_target(words: list[str]) -> str | None:
    args = [w for w in words[1:] if w.lower() not in ("-path", "-literalpath")]
    args = [w for w in args if not w.startswith("-") or w == "-"]
    return args[0] if args and args[0] != "-" else None


def _git_push(words: list[str]):
    """(dir options, push args) when the step is a git push, else None."""
    import gate_before_commit as g  # noqa: PLC0415
    from _route_common import head  # noqa: PLC0415

    if head(words) != "git":
        return None
    dirs: list[str] = []
    i = 1
    while i < len(words):
        w = words[i]
        if w == "-C" and i + 1 < len(words):
            dirs.append(words[i + 1])
            i += 2
        elif w in g.GIT_ARG_OPTS:
            i += 2
        elif w.startswith("-"):
            i += 1
        else:
            return (dirs, words[i + 1:]) if w == "push" else None
    return None


def _exempt_push(args: list[str]) -> bool:
    positional: list[str] = []
    tags = False
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--dry-run", "--delete"):
            return True
        if a == "--tags":
            tags = True
        elif a in PUSH_VALUE_OPTS:
            i += 1
        elif re.fullmatch(r"-[A-Za-z]+", a):
            if SHORT_ALLOW & set(a[1:]):
                return True
        elif not a.startswith("-"):
            positional.append(a)
        i += 1
    refspecs = positional[1:]
    if refspecs and all(r.startswith(":") for r in refspecs):
        return True
    return tags and not refspecs


def _head_sha(directory: str) -> str | None:
    if not os.path.isdir(directory):
        return None
    r = subprocess.run(["git", "-C", directory, "rev-parse", "HEAD"], capture_output=True, text=True,  # noqa: S603, S607
                       check=False, timeout=20)
    out = (r.stdout or "").strip()
    return out if r.returncode == 0 and len(out) == 40 else None  # noqa: PLR2004


def decide(tool_name: str, tool_input: dict, cwd: str | None = None) -> str | None:
    if tool_name.lower() not in ("bash", "powershell"):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command or len(command) > MAX_LEN:
        return None
    if ALLOW.search(command):
        return None
    from _route_common import core_steps, head  # noqa: PLC0415

    current = os.path.abspath(_native(cwd or os.getcwd()))
    for words in core_steps(command, tool_name.lower() == "powershell"):
        if head(words) in CD_WORDS:
            target = _cd_target(words)
            current = _join(current, target) if target else current
            continue
        reason = _judge_push(words, current)
        if reason:
            return reason
    return None


def _judge_push(words: list[str], current: str) -> str | None:
    found = _git_push(words)
    if found is None or _exempt_push(found[1]):
        return None
    directory = current
    for d in found[0]:
        directory = _join(directory, d)
    sha = _head_sha(directory)
    if sha is None:
        return None  # not a repository / git failed: fail open
    if ORCH_DIR not in sys.path:
        sys.path.insert(0, ORCH_DIR)
    try:
        import prepush  # noqa: PLC0415

        marked = prepush.has_marker(directory, sha)
    except Exception:  # noqa: BLE001 - missing or broken prepush module: fail open
        return None
    return None if marked else MESSAGE.format(short=sha[:7])


def main() -> int:
    try:
        from _route_common import read_input  # noqa: PLC0415

        data = read_input()
        reason = decide(str(data.get("tool_name", "")), data.get("tool_input") or {}, data.get("cwd") or None)
    except Exception:  # noqa: BLE001 - a hook must never block on its own bug
        return 0
    if not reason:
        return 0
    sys.stderr.write(reason + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
