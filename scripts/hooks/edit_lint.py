"""PostToolUse hook (Write|Edit|MultiEdit): lint the one file just written and tell the session what is wrong.

REQ-075 AC-8, ADR-093. A slip is reported the moment it is made, not at PR time. Python files get ruff with the
hard-error rules only (F, E9, B, DTZ, BLE: undefined names and syntax, bug patterns, naive datetimes, broad except);
``.vue``/``.js`` under ``frontend/src`` get the project's ESLint config. Measured cost: ruff ~0.2 s, ESLint ~1 s per
file (``node .../eslint.js``, never ``npx``, which is twice as slow).

Never blocks: always exits 0. Findings go back as ``additionalContext`` (at most 20 lines). Missing tool, missing file,
a timeout or any error = silent no-op (fail open).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

RUFF_RULES = "F,E9,B,DTZ,BLE"
MAX_LINES = 20
TIMEOUT_S = 10


def repo_root(path: Path) -> Path | None:
    """The checkout holding ``path`` (main or a worktree: the nearest folder with a ``.git`` entry)."""
    for folder in path.resolve().parents:
        if (folder / ".git").exists():
            return folder
    return None


def command_for(path: Path, root: Path) -> list[str] | None:
    """The lint command for one file, or None when the file is not linted here."""
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    if rel.endswith(".py") and not rel.startswith("backend/ofo_app/alembic/versions/"):
        return [sys.executable, "-m", "ruff", "check", "--quiet", "--output-format", "concise",
                "--select", RUFF_RULES, str(path)]
    if rel.startswith("frontend/src/") and rel.endswith((".vue", ".js")):
        eslint = root / "frontend" / "node_modules" / "eslint" / "bin" / "eslint.js"
        if not eslint.is_file():
            return None
        return ["node", str(eslint), "--max-warnings", "0", str(path)]
    return None


def lint(path: Path, root: Path) -> str:
    """Findings text for one file ('' when clean, unlinted, or the tool is unavailable)."""
    cmd = command_for(path, root)
    if cmd is None or not path.is_file():
        return ""
    cwd = root / "frontend" if cmd[0] == "node" else root
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",  # noqa: S603 - fixed argv, no shell
                           timeout=TIMEOUT_S, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if r.returncode == 0:
        return ""
    lines = [ln for ln in (r.stdout + r.stderr).splitlines() if ln.strip()]
    if not lines or "No module named ruff" in lines[0]:
        return ""
    shown = lines[:MAX_LINES] + ([f"... {len(lines) - MAX_LINES} more"] if len(lines) > MAX_LINES else [])
    return "\n".join(shown)


def main() -> None:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
        file_path = (data.get("tool_input") or {}).get("file_path")
        if not file_path:
            return
        path = Path(file_path)
        root = repo_root(path) or Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".")
        found = lint(path, root)
        if found:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": f"edit_lint (REQ-075): {file_path} has lint findings - fix them now:\n{found}"}}))
    except Exception:  # noqa: BLE001 - a lint hook must never break a session (fail open)
        return


if __name__ == "__main__":
    main()
    sys.exit(0)
