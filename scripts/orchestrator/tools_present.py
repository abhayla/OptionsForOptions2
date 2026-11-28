"""tools_present.py: the gate's first step. Names every tool the gate needs that is missing, with the exact command that
installs it, before any stage runs (a fresh cloud container lost a full gate run to a missing ruff, four times in one
night). Takes well under 5 seconds. Checks only what the gate itself runs: it removes and weakens nothing.

  python scripts/orchestrator/tools_present.py [--frontend]     exit 0 = all present, 1 = something missing (listed)

The ruff check is exact: the gate calls ``python -m ruff`` and the ratchet baseline was counted with the version pinned
in requirements-dev.txt, so a ruff binary on PATH (any version) does NOT count; only the pinned one inside this Python.
"""
import importlib.util
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INSTALL_PY = "python -m pip install -r requirements-dev.txt -r requirements-app.txt"
MODULES = ("pytest", "mypy", "fastapi", "sqlalchemy")


def pinned(repo: str, name: str) -> str | None:
    try:
        with open(os.path.join(repo, "requirements-dev.txt"), encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    m = re.search(rf"^{re.escape(name)}==([^\s#]+)", text, re.MULTILINE)
    return m.group(1) if m else None


def ruff_version() -> str | None:
    try:
        proc = subprocess.run([sys.executable, "-m", "ruff", "--version"],
                              capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"ruff (\S+)", proc.stdout) if proc.returncode == 0 else None
    return m.group(1) if m else None


def check(repo: str, need_frontend: bool = False, which=shutil.which, find_spec=importlib.util.find_spec,
          ruff_ver=ruff_version) -> list[tuple[str, str]]:
    """(problem, exact fix) per missing tool. Empty list = ready."""
    out: list[tuple[str, str]] = []
    want = pinned(repo, "ruff")
    have = ruff_ver()
    if have is None:
        out.append(("ruff is not importable by this Python (the gate runs `python -m ruff`; a PATH ruff is not used)",
                    INSTALL_PY))
    elif want is not None and have != want:
        out.append((f"ruff {have} in this Python, the ratchet baseline needs the pinned {want}",
                    f"python -m pip install ruff=={want}"))
    out.extend((f"python module {mod} is missing", INSTALL_PY) for mod in MODULES if find_spec(mod) is None)
    if which("git") is None:
        out.append(("git is not on PATH", "install git"))
    if need_frontend:
        if which("node") is None or which("npm") is None:
            out.append(("node/npm is not on PATH (a frontend step is planned)",
                        "install Node 22 (the cloud image has /opt/node22/bin)"))
        elif not os.path.isdir(os.path.join(repo, "frontend", "node_modules")):
            out.append(("frontend/node_modules is missing (a frontend step is planned)", "cd frontend && npm ci"))
    return out


def report(problems) -> str:
    lines = [f"TOOLS MISSING ({len(problems)}): the gate did not start; nothing was run"]
    lines += [f"  - {problem}\n      fix: {fix}" for problem, fix in problems]
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    problems = check(ROOT, need_frontend="--frontend" in argv)
    if problems:
        print(report(problems))
        return 1
    print("tools present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
