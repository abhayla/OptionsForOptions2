"""PreToolUse hook (Bash|PowerShell): refuse a commit / push / merge step that runs after a step whose failure would not stop it.

Finding pipe-masks-gate-exit-code (issue #155). A gate piped into a filter (`gate | tail`) takes the filter's exit
status, and a step after `;`, a newline or `||` runs whatever the step before returned, so a following commit, push or
merge goes ahead after a failed gate.

Allow-list: a commit/push/merge step is allowed only when (a) it is the first step, or (b) every earlier step is joined
to the next by `&&` and none is piped, or (c) the command starts with `set -e` (any flag cluster holding `e`, or
`-o errexit`) or sets `$ErrorActionPreference = 'Stop'`, and no earlier step is piped (or joined by `||` / `&`).
Quoted text and heredoc bodies are data, never split. Anything the scanner cannot read -> allow (fail open).
Exit 0 = allow, 2 = block (message on stderr). `decide(command)` is the module-level function the tests import.
"""
from __future__ import annotations

import json
import re
import sys

PS_STOP = re.compile(r"\$ErrorActionPreference\s*=\s*['\"]Stop['\"]", re.I)
PYTHONS = {"python", "python3", "py", "python.exe", "py.exe"}


def _scan(cmd: str) -> list[tuple[str, list[str], str]]:
    """Split into steps: (raw text, words with quotes removed, connector to the next step)."""
    steps: list[tuple[str, list[str], str]] = []
    words: list[str] = []
    cur: str | None = None
    start = 0
    pending: list[tuple[str, bool]] = []
    n = len(cmd)
    i = 0

    def end_word() -> None:
        nonlocal cur
        if cur is not None:
            words.append(cur)
            cur = None

    def end_step(conn: str, at: int, nxt: int) -> None:
        nonlocal words, start
        end_word()
        if words:
            steps.append((cmd[start:at].strip(), words, conn))
            words = []
        elif steps and conn in ("&&", "||", "|", "&"):
            raw, w, _ = steps[-1]
            steps[-1] = (raw, w, conn)
        start = nxt

    while i < n:
        c = cmd[i]
        if c == "\\" and i + 1 < n:
            if cmd[i + 1] == "\n":
                i += 2
                continue
            cur = (cur or "") + cmd[i + 1]
            i += 2
        elif c == "'":
            j = cmd.find("'", i + 1)
            if j < 0:
                j = n
            cur = (cur or "") + cmd[i + 1:j]
            i = j + 1
        elif c == '"':
            j = i + 1
            buf = []
            while j < n and cmd[j] != '"':
                if cmd[j] == "\\" and j + 1 < n:
                    j += 1
                buf.append(cmd[j])
                j += 1
            cur = (cur or "") + "".join(buf)
            i = j + 1
        elif c == "<" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            j = i + 2
            strip = j < n and cmd[j] == "-"
            if strip:
                j += 1
            while j < n and cmd[j] in " \t":
                j += 1
            m = re.match(r"""(['"]?)([^\s'";&|<>]+)\1""", cmd[j:])
            if m:
                pending.append((m.group(2), strip))
                j += m.end()
            end_word()
            i = j
        elif c == "\n":
            nl = i
            i += 1
            for delim, strip in pending:
                while i < n:
                    k = cmd.find("\n", i)
                    line = cmd[i:k if k >= 0 else n]
                    i = (k + 1) if k >= 0 else n
                    if (line.strip() if strip else line.rstrip("\r")) == delim:
                        break
            pending = []
            end_step("\n", nl, i)
        elif c in " \t\r":
            end_word()
            i += 1
        elif c == "#" and cur is None:
            k = cmd.find("\n", i)
            i = k if k >= 0 else n
        elif c == ";":
            end_step(";", i, i + 1)
            i += 1
        elif c == "&" and cmd.startswith("&&", i):
            end_step("&&", i, i + 2)
            i += 2
        elif c == "|" and cmd.startswith("||", i):
            end_step("||", i, i + 2)
            i += 2
        elif c == "|":
            end_step("|", i, i + 1)
            i += 1 + (1 if cmd.startswith("|&", i) else 0)
        elif c == "&" and not (i > 0 and cmd[i - 1] in "<>") and not cmd.startswith("&>", i):
            end_step("&", i, i + 1)
            i += 1
        else:
            cur = (cur or "") + c
            i += 1
    end_step("", n, n)
    return steps


def _is_gated_step(words: list[str]) -> bool:
    """True when the step is a git commit, git push or merge_when_green run."""
    w = list(words)
    while w and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w[0]):
        w.pop(0)
    if not w:
        return False
    head = re.split(r"[\\/]", w[0])[-1].lower()
    if head in ("git", "git.exe"):
        k = 1
        while k < len(w) and w[k].startswith("-"):
            k += 2 if w[k] in ("-C", "-c") else 1
        return k < len(w) and w[k] in ("commit", "push")
    if "merge_when_green" in head:
        return True
    return head in PYTHONS and any("merge_when_green" in x for x in w[1:3])


def _stops_on_error(steps: list[tuple[str, list[str], str]]) -> bool:
    raw, words, _ = steps[0]
    if PS_STOP.search(raw):
        return True
    if words and words[0] == "set":
        for x in words[1:]:
            if re.match(r"^-[A-Za-z]*e[A-Za-z]*$", x):
                return True
        if "errexit" in words:
            return True
    return False


def decide(command: str) -> tuple[bool, str]:
    """(allowed, reason). Fails open: any problem reading the command allows it."""
    try:
        steps = _scan(command or "")
        strict = _stops_on_error(steps) if steps else False
        for k, (raw, words, _) in enumerate(steps):
            if not _is_gated_step(words):
                continue
            for j in range(k):
                if strict and j == 0:
                    continue
                eraw, _, conn = steps[j]
                bad = conn in ("|", "||", "&") if strict else conn != "&&"
                if bad:
                    why = {"|": "is piped (the pipe's last command sets the exit status)",
                           "||": "is followed by ||", "&": "is run in the background",
                           ";": "is followed by ; (the next step runs whatever it returned)",
                           "\n": "is on its own line (the next line runs whatever it returned)"}.get(conn, "")
                    return False, (
                        f"BLOCKED by gate_before_commit: the step `{eraw[:120]}` {why} so a failure would not stop "
                        f"`{raw[:80]}`. Run the gate as its own call, read its result, then commit / push / merge.")
        return True, ""
    except Exception:  # noqa: BLE001 - the hook must never block on its own bug
        return True, ""


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        command = (data.get("tool_input") or {}).get("command")
        if not isinstance(command, str):
            return 0
        allowed, reason = decide(command)
    except Exception:  # noqa: BLE001
        return 0
    if allowed:
        return 0
    sys.stderr.write(reason + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
