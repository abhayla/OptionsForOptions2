"""PreToolUse hook (Bash|PowerShell): refuse a commit / push / merge step that runs after a step whose failure would not stop it.

Finding pipe-masks-gate-exit-code (issue #155). A gate piped into a filter (`gate | tail`) takes the filter's exit
status, and a step after `;`, a newline or `||` runs whatever the step before returned, so a following commit, push or
merge goes ahead after a failed gate.

Gated steps: `git commit`, `git push` (git global options allowed before the subcommand), `merge_when_green` (also
behind python / uv run / poetry run ...), `gh pr merge`; found behind `env`, `time`, `if/then`, `( )`, `{ }` and inside
`bash -c "..."` / `sh -c` / `pwsh -Command` (judged recursively).
Allow-list: a gated step is allowed only when (a) every earlier step is harmless setup (`cd`, `pushd`, `popd`, a bare
assignment, `export`, `set -x` style, `<step> || exit N`), or (b) joined to the next by `&&` with no pipe, or (c) the
command starts with `set -e` (a flag cluster holding `e`, or `-o errexit`) and no earlier step is piped, `||`-joined
or backgrounded. PowerShell's `$ErrorActionPreference = 'Stop'` does NOT stop on a failing native program, so it
excuses nothing; PowerShell 7 `&&` chaining works as in bash.
Quoted text and heredoc bodies are data, never split. Anything unreadable, or longer than 100 KB -> allow (fail open).
Exit 0 = allow, 2 = block (message on stderr, names only the earlier step's command word). `decide(command)` is the
module-level function the tests import.
"""
from __future__ import annotations

import json
import re
import sys

MAX_LEN = 100_000
PYTHONS = {"python", "python3", "py"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
PS_SHELLS = {"pwsh", "powershell"}
RUNNERS = {"uv", "poetry", "pipenv", "pdm", "hatch", "rye", "pipx", "npx"}
PREFIX = {"time", "command", "exec", "nohup", "sudo", "builtin", "nice"}
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "{", "}", "(", ")", "fi", "done", "esac"}
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
HEREDOC_DELIM = re.compile(r"""(['"]?)([^\s'";&|<>]+)\1""")
GIT_ARG_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}
SET_NAMES = {"pipefail", "errexit", "nounset", "xtrace", "noglob", "noclobber", "allexport"}
Step = tuple[list[str], str]


def _scan(cmd: str, ps: bool = False) -> tuple[list[Step], bool]:
    """Split into steps: (words with quotes removed, connector to the next step). Linear time.
    Returns (steps, unterminated_quote). ps=True: a backslash inside double quotes is literal (PowerShell)."""
    steps: list[Step] = []
    words: list[str] = []
    cur: list[str] | None = None
    pending: list[tuple[str, bool]] = []
    n = len(cmd)
    i = 0
    sub = 0
    bt = False
    unterminated = False

    def add(s: str) -> None:
        nonlocal cur
        if cur is None:
            cur = []
        cur.append(s)

    def end_word() -> None:
        nonlocal cur
        if cur is not None:
            words.append("".join(cur))
            cur = None

    def end_step(conn: str) -> None:
        nonlocal words
        end_word()
        if words:
            steps.append((words, conn))
            words = []
        elif steps and conn in ("&&", "||", "|", "&"):
            steps[-1] = (steps[-1][0], conn)

    while i < n:
        c = cmd[i]
        if (sub > 0 or bt) and c not in "'\"\\":
            if c == "(":
                sub += 1
            elif c == ")":
                sub -= 1
            elif c == "`":
                bt = False
            add(c)
            i += 1
        elif c == "\\" and not ps and i + 1 < n:
            if cmd[i + 1] == "\n":
                i += 2
                continue
            add(cmd[i + 1])
            i += 2
        elif c == "`" and ps and i + 1 < n:
            add(cmd[i + 1])
            i += 2
        elif c == "`":
            bt = True
            add(c)
            i += 1
        elif c == "'":
            j = cmd.find("'", i + 1)
            if j < 0:
                j = n
                unterminated = True
            add(cmd[i + 1:j])
            i = j + 1
        elif c == '"':
            j = i + 1
            start = j
            buf: list[str] = []
            closed = False
            while j < n:
                d = cmd[j]
                if d == '"':
                    closed = True
                    break
                if ps and d == "`" and j + 1 < n:
                    buf.append(cmd[start:j])
                    j += 1
                    start = j
                    j += 1
                    continue
                if not ps and d == "\\" and j + 1 < n:
                    buf.append(cmd[start:j])
                    j += 1
                    start = j
                j += 1
            buf.append(cmd[start:min(j, n)])
            if not closed:
                unterminated = True
            add("".join(buf))
            i = j + 1
        elif c == "$" and cmd.startswith("$(", i):
            add("$(")
            sub = 1
            i += 2
        elif c == "<" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            j = i + 2
            strip = j < n and cmd[j] == "-"
            if strip:
                j += 1
            while j < n and cmd[j] in " \t":
                j += 1
            m = HEREDOC_DELIM.match(cmd, j)
            if m:
                pending.append((m.group(2), strip))
                j = m.end()
            end_word()
            i = j
        elif c == "\n":
            i += 1
            for delim, strip in pending:
                while i < n:
                    k = cmd.find("\n", i)
                    line = cmd[i:k if k >= 0 else n]
                    i = (k + 1) if k >= 0 else n
                    if (line.strip() if strip else line.rstrip("\r")) == delim:
                        break
            pending = []
            end_step("\n")
        elif c in " \t\r":
            end_word()
            i += 1
        elif c == "#" and cur is None:
            k = cmd.find("\n", i)
            i = k if k >= 0 else n
        elif c == ";":
            end_step(";")
            i += 1
        elif c == "(" or c == ")":
            end_step(c)
            i += 1
        elif c == "&" and cmd.startswith("&&", i):
            end_step("&&")
            i += 2
        elif c == "|" and cmd.startswith("||", i):
            end_step("||")
            i += 2
        elif c == "|":
            end_step("|")
            i += 2 if cmd.startswith("|&", i) else 1
        elif c == "&" and not (i > 0 and cmd[i - 1] in "<>") and not cmd.startswith("&>", i):
            if cur is None and not words:
                i += 1  # PowerShell call operator at the start of a step
            else:
                end_step("&")
                i += 1
        else:
            add(c)
            i += 1
    end_step("")
    return steps, unterminated


def _base(word: str) -> str:
    b = re.split(r"[\\/]", word)[-1].lower()
    return b[:-4] if b.endswith(".exe") else b


def _core(words: list[str]) -> list[str]:
    """Strip assignments, control keywords and prefix wrappers: the words from the real command on."""
    w = list(words)
    for _ in range(10):
        while w and (ASSIGN.match(w[0]) or w[0] in KEYWORDS):
            w.pop(0)
        if not w:
            return w
        head = _base(w[0])
        if head == "env":
            w = w[1:]
            while w and (w[0].startswith("-") or ASSIGN.match(w[0])):
                w = w[2:] if w[0] == "-u" else w[1:]
            continue
        if head in PREFIX:
            w = w[1:]
            while w and w[0].startswith("-"):
                w = w[1:]
            continue
        if head in RUNNERS:
            w = w[1:]
            if w and w[0] in ("run", "exec"):
                w = w[1:]
            while w and w[0].startswith("-"):
                w = w[1:]
            continue
        return w
    return w


def _shell_inner(words: list[str]) -> tuple[str, bool] | None:
    """For `bash -c "..."` / `pwsh -Command ...`: (inner text, is_powershell)."""
    w = _core(words)
    if not w:
        return None
    head = _base(w[0])
    if head in SHELLS:
        for k in range(1, len(w) - 1):
            if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", w[k]):
                return w[k + 1], False
    elif head in PS_SHELLS:
        for k in range(1, len(w) - 1):
            if w[k].lower() in ("-c", "-command", "-com", "-co"):
                return " ".join(w[k + 1:]), True
    return None


def _is_gated_step(words: list[str], depth: int = 0) -> bool:
    """True when the step is a git commit / git push / merge_when_green / gh pr merge run (through wrappers)."""
    w = _core(words)
    if not w:
        return False
    head = _base(w[0])
    if head == "git":
        k = 1
        while k < len(w) and w[k].startswith("-"):
            k += 2 if w[k] in GIT_ARG_OPTS else 1
        return k < len(w) and w[k] in ("commit", "push")
    if head == "gh":
        rest = [x for x in w[1:] if not x.startswith("-")]
        return rest[:2] == ["pr", "merge"]
    if "merge_when_green" in head:
        return True
    if head in PYTHONS and any("merge_when_green" in _base(x) for x in w[1:4]):
        return True
    if depth < 3:
        inner = _shell_inner(words)
        if inner is not None:
            return _has_gated(inner[0], inner[1], depth + 1)
    return False


def _has_gated(text: str, ps: bool, depth: int) -> bool:
    steps, unterm = _scan(text, ps)
    if unterm and not ps:
        steps, _ = _scan(text, True)
    return any(_is_gated_step(w, depth) for w, _ in steps)


def _is_setup(words: list[str]) -> bool:
    """Harmless setup line: cd/pushd/popd, bare assignment, export, set -x style, PowerShell $var = value."""
    if not words:
        return True
    h = words[0]
    if h.lower() in ("cd", "pushd", "popd", "set-location", "push-location", "pop-location", "sl"):
        return True
    if all(ASSIGN.match(x) for x in words):
        return True
    if h == "export":
        return all(re.match(r"^[A-Za-z_][A-Za-z0-9_]*(=|$)", x) for x in words[1:])
    if h.startswith("$") and ("=" in h or (len(words) > 1 and words[1].startswith("="))):
        return True
    if h == "set":
        return all(re.match(r"^[-+][A-Za-z]+$", x) or x in SET_NAMES for x in words[1:])
    return False


def _normalize(steps: list[Step]) -> list[Step]:
    """`if cond; then X` / `while cond; do X`: X runs only when cond succeeded, so the cond step counts as `&&`."""
    out = [(list(w), c) for w, c in steps]
    for k in range(len(out) - 1):
        w, c = out[k]
        nxt = out[k + 1][0]
        if c in (";", "\n") and w and w[0] in ("if", "elif", "while", "until") and nxt and nxt[0] in ("then", "do"):
            out[k] = (w, "&&")
        if nxt and nxt[0] in ("}", "fi", "done", "esac") and len(nxt) == 1 and c in (";", "\n"):
            out[k] = (w, out[k + 1][1])
    return out


def _stops_on_error(steps: list[Step]) -> bool:
    words = steps[0][0] if steps else []
    if words and words[0] == "set":
        for x in words[1:]:
            if re.match(r"^-[A-Za-z]*e[A-Za-z]*$", x):
                return True
        if "errexit" in words:
            return True
    return False


def _cmd_word(words: list[str]) -> str:
    w = _core(words)
    word = _base(w[0]) if w else "a command"
    return re.sub(r"[^\w.\-]", "?", word)[:40]


def _judge(cmd: str, ps: bool, depth: int) -> str | None:
    """None = allowed, else the refusal message."""
    steps, unterm = _scan(cmd, ps)
    if unterm and not ps:
        steps, _ = _scan(cmd, True)  # `"C:\a\"` in PowerShell is not an escape
    steps = _normalize(steps)
    if depth < 3:
        for words, _ in steps:
            inner = _shell_inner(words)
            if inner is not None:
                r = _judge(inner[0], inner[1], depth + 1)
                if r:
                    return r
    strict = _stops_on_error(steps)
    harmless = [_is_setup(w) for w, _ in steps]
    for j in range(len(steps) - 1):
        if steps[j][1] == "||" and (_core(steps[j + 1][0]) or [""])[0] in ("exit", "return"):
            harmless[j] = harmless[j + 1] = True
    for k, (words, _) in enumerate(steps):
        if not _is_gated_step(words, depth):
            continue
        for j in range(k):
            if harmless[j] or (strict and j == 0):
                continue
            ewords, conn = steps[j]
            if (conn in ("|", "||", "&")) if strict else (conn != "&&"):
                why = {"|": "is piped (the pipe's last command sets the exit status)",
                       "||": "is followed by ||", "&": "is run in the background",
                       ";": "is followed by ; (the next step runs whatever it returned)",
                       "\n": "is on its own line (the next line runs whatever it returned)"}.get(
                    conn, "can be followed by the next step after a failure")
                return (f"BLOCKED by gate_before_commit: an earlier step (`{_cmd_word(ewords)}`) {why}, so a failure "
                        f"would not stop the commit / push / merge step after it. Run that step as its own call, "
                        f"read its result, then commit / push / merge.")
    return None


def decide(command: str, powershell: bool = False) -> tuple[bool, str]:
    """(allowed, reason). Fails open: any problem reading the command allows it."""
    try:
        if not command or len(command) > MAX_LEN:
            return True, ""
        r = _judge(command, powershell, 0)
        return (True, "") if r is None else (False, r)
    except Exception:  # noqa: BLE001 - the hook must never block on its own bug
        return True, ""


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        command = (data.get("tool_input") or {}).get("command")
        if not isinstance(command, str):
            return 0
        allowed, reason = decide(command, str(data.get("tool_name", "")).lower() == "powershell")
    except Exception:  # noqa: BLE001
        return 0
    if allowed:
        return 0
    sys.stderr.write(reason + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
