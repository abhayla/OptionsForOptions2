"""PostToolUse hook (Write|Edit|MultiEdit): lint the one file just written and tell the session what is wrong.

REQ-075 AC-8, ADR-093. A slip is reported the moment it is made, not at PR time. Python files get ruff with the
hard-error rules only (F, E9, B, DTZ, BLE: undefined names and syntax, bug patterns, naive datetimes, broad except);
``.vue``/``.js`` under ``frontend/src`` get the project's ESLint config. Measured cost: ruff ~0.2 s, ESLint ~1 s per
file (``node .../eslint.js``, never ``npx``, which is twice as slow).

Never blocks: always exits 0. Findings go back as ``additionalContext`` (at most 20 lines). A missing linter prints one
"linter unavailable" line; a timeout kills the linter; a file outside a checkout of this repo is skipped; a missing file
or any error = silent no-op (fail open).
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RUFF_RULES = "F,E9,B,DTZ,BLE"
MAX_LINES = 20
TIMEOUT_S = 10
REPO_MARKER = "scripts/hooks/edit_lint.py"  # present in every checkout of this repo, absent elsewhere


def repo_root(path: Path) -> Path | None:
    """The checkout holding ``path`` (main or a worktree: the nearest folder with a ``.git`` entry)."""
    for folder in path.resolve().parents:
        if (folder / ".git").exists():
            return folder
    return None


def is_this_repo(root: Path) -> bool:
    """True when ``root`` is a checkout of THIS repo (main or a worktree): it carries this hook script.

    A file in another repo (its own ``.git``, no marker) must not be linted with this repo's rules.
    """
    return (root / REPO_MARKER).is_file()


def ruff_argv() -> list[str] | None:
    """The ruff executable as an argv prefix, or None when ruff is not installed.

    The binary is run directly: ``python -m ruff`` starts ruff.exe as a child, and on Windows killing the python
    parent leaves ruff.exe holding the output pipe, so a timeout did not stop anything.
    """
    with contextlib.suppress(Exception):  # any failure to locate the packaged binary means "try PATH"
        from ruff.__main__ import find_ruff_bin  # noqa: PLC0415 - optional dependency
        found = Path(find_ruff_bin())
        if found.is_file():
            return [str(found)]
    which = shutil.which("ruff")
    return [which] if which else None


def _is_python(rel: str) -> bool:
    return rel.endswith(".py") and not rel.startswith("backend/ofo_app/alembic/versions/")


def _is_frontend(rel: str) -> bool:
    return rel.startswith("frontend/src/") and rel.endswith((".vue", ".js"))


def _rel(path: Path, root: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def _eslint(root: Path) -> Path:
    return root / "frontend" / "node_modules" / "eslint" / "bin" / "eslint.js"


def command_for(path: Path, root: Path) -> list[str] | None:
    """The lint command for one file, or None when the file is not linted here or its tool is unavailable."""
    rel = _rel(path, root)
    if rel is None or not is_this_repo(root):
        return None
    if _is_python(rel):
        ruff = ruff_argv()
        if ruff is None:
            return None
        return [*ruff, "check", "--quiet", "--output-format", "concise", "--select", RUFF_RULES, str(path)]
    if _is_frontend(rel):
        eslint = _eslint(root)
        if not eslint.is_file():
            return None
        return ["node", str(eslint), "--max-warnings", "0", str(path)]
    return None


def unavailable(path: Path, root: Path) -> str | None:
    """Why a file that SHOULD be linted here cannot be (tool missing), else None."""
    rel = _rel(path, root)
    if rel is None or not is_this_repo(root):
        return None
    if _is_python(rel) and ruff_argv() is None:
        return "ruff is not installed"
    if _is_frontend(rel) and not _eslint(root).is_file():
        return "ESLint is not installed (frontend/node_modules missing)"
    return None


def _run(cmd: list[str], cwd: Path) -> tuple[int, str] | None:
    """Run ``cmd`` for at most TIMEOUT_S; (returncode, output) or None on timeout/OS error.

    Output goes to a temp file, not a pipe, so a grandchild that outlives the killed process cannot hold the call open.
    """
    with tempfile.TemporaryFile() as out:
        try:
            proc = subprocess.Popen(cmd, cwd=cwd, stdout=out, stderr=subprocess.STDOUT,  # noqa: S603 - fixed argv, no shell
                                    stdin=subprocess.DEVNULL)
        except OSError:
            return None
        try:
            proc.wait(timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=2)
            return None
        out.seek(0)
        return proc.returncode, out.read().decode("utf-8", errors="replace")


def lint(path: Path, root: Path) -> str:
    """Findings text for one file ('' when clean, unlinted, timed out, or the tool is unavailable)."""
    cmd = command_for(path, root)
    if cmd is None or not path.is_file():
        return ""
    cwd = root / "frontend" if cmd[0] == "node" else root
    result = _run(cmd, cwd)
    if result is None or result[0] == 0:
        return ""
    lines = [ln for ln in result[1].splitlines() if ln.strip()]
    if not lines:
        return ""
    shown = lines[:MAX_LINES] + ([f"... {len(lines) - MAX_LINES} more"] if len(lines) > MAX_LINES else [])
    return "\n".join(shown)


def _emit(text: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}))


def main() -> None:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
        file_path = (data.get("tool_input") or {}).get("file_path")
        if not file_path:
            return
        path = Path(file_path)
        root = repo_root(path) or Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".")
        if not is_this_repo(root):
            return
        missing = unavailable(path, root)
        if missing:
            _emit(f"edit_lint (REQ-075): linter unavailable ({missing}); {file_path} was not linted.")
            return
        found = lint(path, root)
        if found:
            _emit(f"edit_lint (REQ-075): {file_path} has lint findings - fix them now:\n{found}")
    except Exception:  # noqa: BLE001 - a lint hook must never break a session (fail open)
        return


if __name__ == "__main__":
    main()
    sys.exit(0)
