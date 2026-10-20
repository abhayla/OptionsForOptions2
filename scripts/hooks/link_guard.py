"""PreToolUse hook (Bash|PowerShell): refuse link creation into the main checkout and forced worktree removal.

Finding worktree-link-into-main-checkout (2026-10-19): a review agent junctioned the main checkout's
frontend/node_modules into its scratch checkout; `git worktree remove --force` then walked into the junction and deleted
packages from the main checkout. Refused here:
  1. a command that creates a link (mklink /J /D /H, `cmd /c mklink`,
     New-Item -ItemType Junction|SymbolicLink|HardLink, `ln -s`, `fsutil hardlink`,
     os.symlink / CreateJunction / symlink_to in inline code) whose TARGET is inside the main
     checkout (or the project dir);
  2. `git worktree remove` with `--force` / `-f` (any option cluster holding f).
Allow-list thinking, fail closed: when a link verb is present and the target cannot be identified or resolved (inline
code, a variable, a subshell) the command is refused if the main checkout path appears anywhere in it, or if the target
holds an unresolved variable. `npm ci`, mkdir, plain `git worktree remove`, links to targets outside the
checkout pass.
Exit 0 = allow, 2 = block. A bug in this hook allows (fail open).
`decide(tool_name, tool_input, roots=None, cwd=None)`.
"""

from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
MAX_LEN = 100_000

MESSAGE_LINK = (
    "BLOCKED by link_guard: {why}. On 2026-10-19 a junction into the main checkout's node_modules was "
    "followed by a forced worktree removal that deleted packages from main. Run `npm ci` inside the "
    "scratch checkout instead of linking."
)
MESSAGE_FORCE = (
    "BLOCKED by link_guard: `git worktree remove --force` is refused (2026-10-19: it followed a junction "
    "and deleted packages from the main checkout). Remove links as links first, then use a plain "
    "`git worktree remove`."
)

SEGMENT_SPLIT = re.compile(r"[;&|\n]+")
MKLINK = re.compile(r"\bmklink(\.exe)?\b", re.I)
NEWITEM = re.compile(r"\b(new-item|ni)\b", re.I)
LINK_TYPE = re.compile(r"junction|symbolic\s*link|hard\s*link|symboliclink|hardlink", re.I)
CODE_LINK = re.compile(
    r"symlink|createjunction|hardlink|os\.link\b|symlink_to|link_to|createsymboliclink|"
    r"fsutil\s+hardlink|\bjunction(\.exe)?\b",
    re.I,
)
GIT_WT_REMOVE = re.compile(r"\bgit\b[^\n]*?\bworktree\s+remove\b(?P<rest>[^\n]*)", re.I)
TOKEN_SPLIT = re.compile(r"""[\s"'`,()=]+""")
UNRESOLVED = re.compile(r"[$%`]|\$\(|~")


def _key(path: str) -> str:
    """One comparable form for D:\\x, /d/x, /mnt/d/x, /cygdrive/d/x: lower-case, forward slashes, drive as /d."""
    p = path.replace("\\", "/").rstrip("/").casefold()
    m = re.match(r"^([a-z]):(/|$)", p)
    if m:
        p = "/" + m.group(1) + p[2:]
    p = re.sub(r"^/(?:mnt|cygdrive)/([a-z])(?=/|$)", r"/\1", p)
    return re.sub(r"/+", "/", p)


def _inside(path: str, roots: list[str]) -> bool:
    k = _key(path)
    return any(k == r or k.startswith(r + "/") for r in roots)


def _resolve(token: str, cwd: str) -> list[str]:
    """Candidate absolute forms of a token (as written, normalised, real path when it exists)."""
    t = token.strip()
    if not t:
        return []
    absolute = bool(re.match(r"^[A-Za-z]:[\\/]", t)) or t.startswith(("/", "\\"))
    full = t if absolute else os.path.join(cwd, t)
    out = [full, os.path.normpath(full)]
    with contextlib.suppress(OSError):
        out.append(os.path.realpath(full))
    return out


def main_roots(project_dir: str) -> list[str]:
    """Comparable keys for the project dir and the main checkout (parent of the git common dir)."""
    paths = [project_dir]
    try:
        for args in (["--show-toplevel"], ["--git-common-dir"]):
            r = subprocess.run(  # noqa: S603
                ["git", "-C", project_dir, "rev-parse", *args],  # noqa: S607
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            line = r.stdout.strip().splitlines()[0] if r.returncode == 0 and r.stdout.strip() else ""
            if line:
                p = os.path.join(project_dir, line)
                paths.append(os.path.dirname(os.path.normpath(p)) if args[0] == "--git-common-dir" else p)
    except (OSError, subprocess.SubprocessError):
        pass
    keys: list[str] = []
    for p in paths:
        for cand in (p, os.path.normpath(p), os.path.realpath(p)):
            k = _key(cand)
            if k and k not in keys:
                keys.append(k)
    return keys


def _tokens(text: str) -> list[str]:
    return [t for t in TOKEN_SPLIT.split(text) if t]


def _is_path_like(t: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:", t)) or "/" in t or "\\" in t or t.startswith(".") or not t.startswith("-")


LAUNCHERS = {
    "sudo",
    "command",
    "env",
    "time",
    "exec",
    "nohup",
    "bash",
    "sh",
    "zsh",
    "dash",
    "cmd",
    "cmd.exe",
    "wsl",
    "start",
    "call",
    "-c",
    "-lc",
    "-ec",
    "/c",
    "/k",
    "/s",
    "pwsh",
    "powershell",
    "-command",
    "-noprofile",
}
INTERPRETERS = re.compile(
    r"^(python|py|pypy|node|perl|ruby|pwsh|powershell)[\d.]*(\.exe)?$|^(fsutil|junction)(\.exe)?$", re.I
)
ASSIGN = re.compile(r"^[A-Za-z_]\w*=")


def _at_command_position(low: list[str], i: int) -> bool:
    """True when every word before index i is a launcher/prefix (word i is then the command run)."""
    return all(w in LAUNCHERS or ASSIGN.match(w) for w in low[:i])


def _targets(seg: str) -> tuple[list[str] | None, bool]:
    """(target tokens of the link-creating verb in this segment or None when unidentifiable, verb_seen)."""
    toks = _tokens(seg)
    low = [t.lower() for t in toks]
    for i, t in enumerate(low):
        if MKLINK.fullmatch(t) and _at_command_position(low, i):  # mklink [/D|/H|/J] link target
            rest = [x for x in toks[i + 1 :] if not re.fullmatch(r"/[dhj]", x, re.I)]
            return (rest[1:2] if len(rest) > 1 else None), True
        if (
            t in ("ln", "ln.exe")
            and _at_command_position(low, i)
            and any(re.fullmatch(r"-[a-z]*s[a-z]*|--symbolic", x, re.I) for x in toks[i + 1 :])
        ):
            rest = [x for x in toks[i + 1 :] if not x.startswith("-")]  # ln -s TARGET [LINK]
            return (rest[:1] if rest else None), True
    if NEWITEM.search(seg) and LINK_TYPE.search(seg):
        for i, t in enumerate(low):
            if t in ("-target", "-value", "-tar", "-val", "-v") and i + 1 < len(toks):
                return [toks[i + 1]], True
        return None, True
    return None, bool(CODE_LINK.search(seg)) and any(INTERPRETERS.match(t) for t in toks)


def _link_refusal(command: str, roots: list[str], cwd: str) -> str | None:
    # inline code keeps its own `;` / `|`, so the whole command is judged as one more segment
    for seg in [*SEGMENT_SPLIT.split(command), command]:
        targets, verb = _targets(seg)
        if not verb:
            continue
        if targets is not None:
            for tgt in targets:
                if UNRESOLVED.search(tgt):
                    return MESSAGE_LINK.format(
                        why="a link target holding a variable cannot be checked against the main checkout"
                    )
                if any(_inside(c, roots) for c in _resolve(tgt, cwd)):
                    return MESSAGE_LINK.format(why=f"a link whose target `{tgt}` is inside the main checkout")
            continue
        # verb present, target not identifiable: refuse when the main checkout shows up anywhere in the segment
        for tok in _tokens(seg):
            if _is_path_like(tok) and any(_inside(c, roots) for c in _resolve(tok, cwd)):
                return MESSAGE_LINK.format(
                    why=f"a link command naming the main checkout (`{tok}`) with a target that cannot be read"
                )
        if re.search(r"[$%]", seg):
            return MESSAGE_LINK.format(why="a link command with a variable target that cannot be checked")
    return None


def _force_refusal(command: str) -> str | None:
    for seg in re.split(r"[;&|\n]+", command):
        m = GIT_WT_REMOVE.search(seg)
        if not m:
            continue
        for w in _tokens(m.group("rest")):
            if w == "--force" or re.fullmatch(r"-[A-Za-z]*f[A-Za-z]*", w) or w.startswith("--force="):
                return MESSAGE_FORCE
    return None


def decide(tool_name: str, tool_input: dict, roots: list[str] | None = None, cwd: str | None = None) -> str | None:
    if tool_name.lower() not in ("bash", "powershell"):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command or len(command) > MAX_LEN:
        return None
    forced = _force_refusal(command)
    if forced:
        return forced
    if roots is None:
        roots = main_roots(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    return _link_refusal(command, roots, cwd or os.getcwd())


def main() -> int:
    try:
        from _route_common import run_hook  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - a missing helper module fails open, silently
        return 0
    return run_hook(decide)


if __name__ == "__main__":
    sys.exit(main())
