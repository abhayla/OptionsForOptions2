"""PreToolUse hook (Bash|PowerShell): refuse a shell command that stops processes by NAME.

Finding process-kill-by-name-hits-others (third occurrence, 2026-10-23 09:47): `taskkill //F //IM python.exe`, run by a
process agent, killed the owner's live API. This hook is an ALLOW-LIST of process-stop forms; every other stop is refused:
  taskkill   only with /PID <digits> (one or more) plus /F /T, never /IM or /FI
  Stop-Process  only with -Id <digits[,digits]> (plus -Force -PassThru -WhatIf -Confirm -Verbose -ErrorAction)
  kill       only with literal digit PIDs (signal flags allowed)
  pkill, killall, pskill, tskill, `wmic process ... delete|terminate`, `.Kill()` / Terminate on a Get-Process result:
  always refused.
The command is parsed quote-aware: quoted text and heredoc bodies are data (`grep taskkill`, `git commit -m '...pkill'`
pass), while `;` `&&` `||` `|` newlines, braces, `$( )`, backticks, `bash -c` / `cmd /c` / `powershell -Command` strings and
-EncodedCommand payloads are all judged. Out of scope: a script file that kills by name (the prose rule still applies).
Exit 0 = allow, 2 = block. A crash, a missing helper or malformed input allows (fail open); a stop command the parser
cannot judge (nesting deeper than MAX_DEPTH) is refused.
`decide(tool_name, tool_input)`.
"""

from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
MAX_LEN = 100_000
MAX_DEPTH = 4

REASON = (
    "BLOCKED by kill_by_name_guard: {why}; stop only the PIDs you started (kill by PID; finding "
    "process-kill-by-name-hits-others). On 2026-10-23 `taskkill //F //IM python.exe` killed the owner's live API. "
    "Record the PID of every process you start and run `taskkill /PID <pid> /F` or `Stop-Process -Id <pid>`."
)

ALWAYS_REFUSED = frozenset({"pkill", "killall", "pskill", "tskill", "skill"})
STOP_VERBS = ALWAYS_REFUSED | {"taskkill", "stop-process", "spps", "kill", "wmic"}
CARRIERS = frozenset({"bash", "sh", "zsh", "dash", "cmd", "powershell", "pwsh", "eval", "iex", "invoke-expression",
                      "ssh", "wsl", "su", "runas"})
WRAPPERS = frozenset({"sudo", "env", "time", "nohup", "exec", "command", "call", "start", "xargs", "builtin", "timeout",
                      "nice", "setsid"} | CARRIERS)
EXEC_FLAGS = frozenset({"-exec", "-execdir", "-ok"})
ASSIGN = re.compile(r"^[A-Za-z_]\w*=")
DIGITS = re.compile(r"\d+")
PID_LIST = re.compile(r"\d+(?:,\d+)*")
KILL_FLAG = re.compile(r"-(?:[A-Za-z]\w*|\d+)")
SWITCH = re.compile(r"(?://|/|-)([A-Za-z]+)(?::(.*))?", re.S)
PS_SWITCH = re.compile(r"-([A-Za-z]+)(?::(.*))?", re.S)
ENC_FLAG = re.compile(r"-e(?:nc(?:odedcommand)?)?", re.I)
METHOD_KILL = re.compile(r"\.\s*kill\s*\(|\.\s*terminate\s*\(|-methodname\s+terminate", re.I)
PROCESS_SOURCE = re.compile(r"get-process|\bgps\b|get-wmiobject|get-ciminstance|win32_process", re.I)
PS_FLAGS_NO_VALUE = frozenset({"force", "passthru", "whatif", "verbose", "confirm"})
PS_FLAGS_VALUE = frozenset({"erroraction", "ea"})
KILL_VALUE_FLAGS = frozenset({"-s", "-n", "-signal"})


def _matching_paren(text: str, start: int) -> int:
    """Index just past the `)` closing the `(` at start - 1 (end of text when unbalanced)."""
    depth = 1
    i = start
    while i < len(text) and depth:
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        i += 1
    return i


def _substitutions(text: str) -> list[str]:
    """Inner command text of every `$( )` and backtick pair inside a double-quoted string."""
    found: list[str] = []
    i = 0
    while i < len(text):
        if text.startswith("$(", i):
            end = _matching_paren(text, i + 2)
            found.append(text[i + 2 : end - 1])
            i = end
        elif text[i] == "`":
            end = text.find("`", i + 1)
            end = len(text) if end < 0 else end
            found.append(text[i + 1 : end])
            i = end + 1
        else:
            i += 1
    return found


def _skip_heredocs(cmd: str, i: int, delimiters: list[str]) -> int:
    """After a newline at i - 1: skip each pending heredoc body up to its closing delimiter line."""
    for delim in delimiters:
        while i < len(cmd):
            end = cmd.find("\n", i)
            end = len(cmd) if end < 0 else end
            line = cmd[i:end].strip()
            i = min(end + 1, len(cmd))
            if line == delim:
                break
    delimiters.clear()
    return i


class _Scan:
    """Quote-aware split of a command into steps (word lists). Quoted text is one word of data; nested command text
    ($( ), backticks, unterminated quotes) is scanned too and its steps are added."""

    def __init__(self, cmd: str, depth: int) -> None:
        self.cmd, self.depth = cmd, depth
        self.steps: list[list[str]] = []
        self.words: list[str] = []
        self.cur: list[str] = []
        self.has = False
        self.heredocs: list[str] = []

    def end_word(self) -> None:
        if self.has:
            self.words.append("".join(self.cur))
        self.cur, self.has = [], False

    def end_step(self) -> None:
        self.end_word()
        if self.words:
            self.steps.append(self.words)
        self.words = []

    def nested(self, text: str) -> None:
        self.steps.extend(_Scan(text, self.depth + 1).run())

    def run(self) -> list[list[str]]:
        cmd, n, i = self.cmd, len(self.cmd), 0
        while i < n:
            c = cmd[i]
            if c == "'":
                j = cmd.find("'", i + 1)
                if j < 0:  # unterminated: the rest is judged as command text (fail closed)
                    self.nested(cmd[i + 1 :])
                    break
                self.cur.append(cmd[i + 1 : j])
                self.has, i = True, j + 1
            elif c == '"':
                j = i + 1
                while j < n and cmd[j] != '"':
                    j += 2 if cmd[j] in "\\`" and j + 1 < n and cmd[j + 1] in '"`$\\' else 1
                inner = cmd[i + 1 : j]
                for sub in _substitutions(inner):
                    self.nested(sub)
                self.cur.append(inner)
                self.has, i = True, j + 1
            elif c == "`":
                j = cmd.find("`", i + 1)
                j = n if j < 0 else j
                self.end_word()
                self.nested(cmd[i + 1 : j])
                i = j + 1
            elif c in ";&|\n" or c in "{}()":
                self.end_step()
                i += 1
                if c == "\n" and self.heredocs:
                    i = _skip_heredocs(cmd, i, self.heredocs)
            elif c.isspace():
                self.end_word()
                i += 1
            elif c == "#" and not self.has:
                j = cmd.find("\n", i)
                i = n if j < 0 else j
            elif cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
                m = re.match(r"<<-?\s*(['\"]?)([^\s'\";&|]+)\1", cmd[i:])
                if m:
                    self.heredocs.append(m.group(2))
                    i += m.end()
                else:
                    i += 2
            else:
                self.cur.append(c)
                self.has, i = True, i + 1
        self.end_step()
        return self.steps


def _base(word: str) -> str:
    name = re.split(r"[\\/]", word.strip("'\""))[-1].lower()
    return re.sub(r"\.(?:exe|com|cmd|bat|ps1)$", "", name)


def _wrapperish(word: str) -> bool:
    """A word that may sit before the command actually run: env assignment, wrapper/launcher, option, number."""
    w = word.lower()
    return bool(ASSIGN.match(word) or _base(w) in WRAPPERS or w.startswith(("-", "/")) or DIGITS.fullmatch(w))


def _taskkill(args: list[str]) -> str | None:
    pids, j = 0, 0
    while j < len(args):
        m = SWITCH.fullmatch(args[j])
        name = m.group(1).lower() if m else ""
        if m and name in ("f", "t") and m.group(2) is None:
            j += 1
        elif m and name == "pid":
            value = m.group(2) if m.group(2) is not None else (args[j + 1] if j + 1 < len(args) else "")
            if not DIGITS.fullmatch(value):
                return "`taskkill /PID` needs literal digits"
            pids += 1
            j += 1 if m.group(2) is not None else 2
        else:
            return f"`taskkill {args[j]}` is not a PID-based form (name or filter selection)"
    return None if pids else "`taskkill` without /PID <digits>"


def _stop_process(args: list[str]) -> str | None:
    id_seen, j = False, 0
    while j < len(args):
        m = PS_SWITCH.fullmatch(args[j])
        name = m.group(1).lower() if m else ""
        if m and name in ("id", "pid"):
            value = m.group(2) if m.group(2) is not None else (args[j + 1] if j + 1 < len(args) else "")
            if not PID_LIST.fullmatch(value):
                return "`Stop-Process -Id` needs literal digits"
            id_seen = True
            j += 1 if m.group(2) is not None else 2
        elif m and name in PS_FLAGS_NO_VALUE and (m.group(2) is None or name == "confirm"):
            j += 1
        elif m and name in PS_FLAGS_VALUE:
            j += 1 if m.group(2) is not None else 2
        else:
            return f"`Stop-Process {args[j]}` is not a PID-based form (name or object selection)"
    return None if id_seen else "`Stop-Process` without -Id <digits>"


def _kill(args: list[str]) -> str | None:
    pids, j = [], 0
    while j < len(args):
        a = args[j]
        if a.lower() in KILL_VALUE_FLAGS:
            j += 2
        elif KILL_FLAG.fullmatch(a):
            j += 1
        else:
            pids.append(a)
            j += 1
    if pids and all(DIGITS.fullmatch(p) for p in pids):
        return None
    return "`kill` needs literal digit PIDs (no job names, variables or empty list)"


def _wmic(args: list[str]) -> str | None:
    text = " ".join(args).lower()
    if "process" in text and re.search(r"delete|terminate", text):
        return "`wmic process ... delete/terminate` selects processes by query"
    return None


def _check_step(words: list[str], depth: int) -> str | None:
    low = [w.lower() for w in words]
    for i, word in enumerate(words):
        at_command = all(_wrapperish(w) for w in words[:i]) or (i > 0 and low[i - 1] in EXEC_FLAGS)
        if not at_command:
            continue
        base = _base(word)
        args = words[i + 1 :]
        if base in ALWAYS_REFUSED:
            return f"`{base}` stops processes by name"
        if base == "taskkill":
            return _taskkill(args)
        if base in ("stop-process", "spps"):
            return _stop_process(args)
        if base == "kill":
            return _kill(args)
        if base == "wmic":
            return _wmic(args)
        if base in CARRIERS:
            return _check_carried(args, depth)
    return None


def _check_carried(args: list[str], depth: int) -> str | None:
    """The words after a shell launcher are command text: each word, all of them joined, and -EncodedCommand payloads."""
    candidates = [" ".join(args), *args]
    for j, a in enumerate(args[:-1]):
        if ENC_FLAG.fullmatch(a):
            try:
                candidates.append(base64.b64decode(args[j + 1], validate=True).decode("utf-16-le"))
            except (ValueError, UnicodeDecodeError):
                pass
    for text in candidates:
        if text.strip():
            why = _judge(text, depth + 1)
            if why:
                return why
    return None


def _judge(command: str, depth: int) -> str | None:
    if depth > MAX_DEPTH:
        return "a command nested too deeply to be read (fail closed)"
    for words in _Scan(command, depth).run():
        why = _check_step(words, depth)
        if why:
            return why
    return None


def decide(tool_name: str, tool_input: dict) -> str | None:
    if tool_name.lower() not in ("bash", "powershell"):
        return None
    command = tool_input.get("command")
    if not isinstance(command, str) or not command or len(command) > MAX_LEN:
        return None
    if METHOD_KILL.search(command) and PROCESS_SOURCE.search(command):
        return REASON.format(why="a process object's Kill()/Terminate() on a Get-Process or WMI selection")
    why = _judge(command, 0)
    return REASON.format(why=why) if why else None


def main() -> int:
    try:
        from _route_common import run_hook  # noqa: PLC0415
    except Exception:  # noqa: BLE001 - a missing helper module fails open, silently
        return 0
    return run_hook(decide)


if __name__ == "__main__":
    sys.exit(main())
