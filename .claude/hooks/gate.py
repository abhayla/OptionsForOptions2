#!/usr/bin/env python3
"""prod-gate gate: PreToolUse hook.

Intended matcher: Bash|PowerShell|Edit|Write|MultiEdit|NotebookEdit|SendMessage|RemoteTrigger|
Monitor|Workflow|Agent|Task|Skill|mcp__.*  (any wider matcher is also handled).

A SEATBELT against accidents, not a lock (OD-11): it reads text, so obfuscated input evades it.

In a governed project (one with .factory/authority.yaml above the hook's cwd):

  a. Edit/Write/MultiEdit/NotebookEdit into .factory/, the records dir, the ledger, the
     hook's own directory, or Claude settings files            -> deny
  b. Bash/PowerShell text that mentions any of those paths      -> deny
  c. Bash/PowerShell text matching a deploy pattern             -> allow only with an
     unused record for that exact release dated today AND fewer than
     max_deploys_per_day ledger entries today; on allow the record is consumed and
     a ledger line appended. Deploy-looking text that is not in canonical form -> deny.
  d. Anti-forge: shell text containing the authorize phrase, keystroke-injection APIs,
     or a Claude launch carrying the phrase; SendMessage/RemoteTrigger/other tools
     carrying the phrase                                        -> deny
  e. Internal error: deny if the input looks deploy/record related, else allow.

Ungoverned project -> allow. Allow = exit 0 with no output (the normal permission
flow still applies). Deny = exit code 2 with the reason on stderr (a JSON permissionDecision
"deny" at exit 0 can be overridden by another hook's "allow"; exit 2 cannot).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import site
import sys
import sysconfig
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common as c  # noqa: E402

SHELL_TOOLS = {"Bash", "PowerShell"}
FILE_WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
MESSAGE_TOOLS = {"SendMessage", "RemoteTrigger"}
PASS_TOOLS = {"Read", "Glob", "Grep", "LS", "WebFetch", "WebSearch", "TodoWrite", "ToolSearch"}
# run a command/script in-process: shell-like checks, never a deploy
COMMAND_TOOLS = {"Monitor", "Workflow"}
# start another Claude: the child's own tool calls are gated, but its prompt must not carry
# the phrase or a deploy, and a remote child runs without this machine's hooks
AGENT_TOOLS = {"Agent", "Task", "Skill"}
PATCH_CMD = re.compile(r"(?:^|[;&|(\n]\s*)(?:sudo\s+)?patch(?=\s|$)|\bgit\b[^;&|\n]*?\s(?:apply|am)(?=\s|$)",
                       re.IGNORECASE | re.MULTILINE)
TREE_PATHSPEC = {".", "./", ":/", "*", ":(top)", "-a", "--all"}
KEYSTROKE_TOKENS = ("sendkeys", "sendwait", "appactivate", "sendinput", "keybd_event",
                    "wscript.shell", "wscript", "xdotool", "autohotkey", "pyautogui", "pynput",
                    )
# "claude" in command position: line start, after ; & | ( or a launcher word, optionally with
# a directory prefix and quotes. Mentions inside arguments (git log --author claude) do not count.
CLAUDE_LAUNCH = re.compile(
    r"(?:^|[;&|(\n]|\b(?:npx|exec|call|nohup|env|time|start|cmd\s*/c)\b)\s*(?:\w+=\S*\s+)*"
    r"(?:[^\s;&|]*[/\\])?[\"'`]?(?:claude(?:\.exe|\.cmd|\.ps1)?|@anthropic-ai/claude-code)[\"'`]?"
    r"(?=$|[\s;&|)])",
    re.IGNORECASE | re.MULTILINE,
)
REGEX_META = set(".^$*+?{}[]|()")
DOT_GLOB = re.compile(r"(?:^|[\s/\\\"'=(])\.[\w-]*[*?\[]")
PRINT_FLAG = re.compile(r"(?:^|\s)(?:-p|--print)(?:\s|=|$)")
NEW_CONSOLE = ("start-process", "startprocess", "wt.exe", "conhost", "cmd/cstart",
               "cmd.exe/cstart", "mintty", "invoke-item", "saps")
CHILD_ESCAPE = re.compile(r"(?:^|[;&|(\s])(?:cd|pushd|chdir|set-location|sl)(?:\s|$)",
                          re.IGNORECASE | re.MULTILINE)
CHILD_ESCAPE_TOKENS = ("-workingdirectory", "--add-dir", "--settings", "--setting-sources",
                       "disableallhooks", "claude_config_dir", "--bare", "claude_project_dir")
CONTENT_KEYS = ("content", "new_string", "new_source", "text", "data")


class Deny(Exception):
    pass


# ----------------------------------------------------------------- output


def deny(reason: str) -> int:
    # exit 2 + reason on stderr: a JSON permissionDecision "deny" at exit 0 can be overridden by
    # another matching hook's "allow" (finding json-deny-overridden-by-another-hooks-allow); exit 2 cannot
    print("prod-gate: " + reason, file=sys.stderr)
    return 2


# ----------------------------------------------------------------- text helpers


def squash(text: str) -> str:
    """Remove shell quoting/escapes that split tokens: quotes, backticks, carets, backslashes."""
    t = re.sub(r"[\"'`^\\]", "", text)
    return re.sub(r"\s+", " ", t)


def nospace(text: str) -> str:
    return re.sub(r"[\s+]", "", squash(text)).lower()


def slashed(text: str) -> str:
    t = text.lower().replace("\\", "/")
    t = re.sub(r"[\"'`^]", "", t)
    return re.sub(r"/+", "/", t)


# ----------------------------------------------------------------- tokenizer (round 2)
# Checks that depend on WHICH command runs (patch, claude, globs) use tokens, not substrings:
# a word inside a commit message or an argument is data, not a command.

SEP_CHARS = set(";&|()\n")
WRAPPERS = {"sudo", "env", "nohup", "time", "exec", "command", "nice", "builtin", "$"}
CLAUDE_NAMES = {"claude", "@anthropic-ai/claude-code"}
GLOB_CH = set("*?[")
REGEXY = set("+^$(){}|")
CATCH_ALL = {"*", "**", ".*", "*.*"}
CATCH_ALL_RE = re.compile(r"^\*\.[\w-]+$")
ANCHOR_RE = re.compile(r"^(?:\$\{?(?:env:)?\w+\}?|%\w+%|~)(?=[\\/])", re.IGNORECASE)
MSG_SUBCMDS = {"commit", "tag", "notes", "merge", "revert", "stash"}
HEREDOC_GIT = re.compile(r"\bgit\b[^;&|\n]*\b(?:commit|tag|notes)\b[^;&|\n]*<<-?\s*(['\"]?)(\w+)\1")
PS_HERESTR_GIT = re.compile(r"\bgit\b[^;&|\n]*\b(?:commit|tag|notes)\b[^;&|\n]*@(['\"])\s*$")
CAT_HEREDOC_STUB = re.compile(r"\$\(\s*cat\s+<<-?\s*['\"]?\w+['\"]?\s*\)")


def tokenize(cmd: str, ps: bool = False) -> list[str] | None:
    """shlex tokens with ; & | ( ) < > and newlines as separate punctuation; None if unparseable."""
    import shlex
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>\n")
        lex.whitespace = " \t\r"
        lex.whitespace_split = True
        lex.commenters = ""
        if ps:
            lex.escape = "`"
        return list(lex)
    except ValueError:
        return None


def is_sep(tok: str) -> bool:
    return bool(tok) and all(ch in SEP_CHARS for ch in tok)


def is_redirect(tok: str) -> bool:
    return bool(tok) and all(ch in SEP_CHARS or ch in "<>" for ch in tok) and ("<" in tok or ">" in tok)


def segments(cmd: str, ps: bool = False) -> list[list[str]] | None:
    toks = tokenize(cmd, ps)
    if toks is None:
        return None
    segs, cur = [], []
    for t in toks:
        if is_sep(t):
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append(t)
    if cur:
        segs.append(cur)
    return segs


def split_seg(seg: list[str]) -> tuple[str, list[str], list[str]]:
    """(command name, args, stdin redirect targets) for one simple command."""
    words, stdin, i = [], [], 0
    while i < len(seg):
        t = seg[i]
        if is_redirect(t):
            if i + 1 < len(seg):
                if "<" in t:
                    stdin.append(seg[i + 1])
                i += 2
                continue
        words.append(t)
        i += 1
    j = 0
    while j < len(words) and (words[j].lower() in WRAPPERS or re.match(r"^\w+=", words[j])):
        j += 1
    if j >= len(words):
        return "", [], stdin
    name = re.split(r"[\\/]", words[j])[-1].lower() if "@anthropic-ai" not in words[j] else "@anthropic-ai/claude-code"
    name = re.sub(r"\.(exe|cmd|ps1|bat)$", "", name)
    if name == "npx" and j + 1 < len(words):
        return split_seg(words[j + 1:] + [x for s in stdin for x in ("<", s)])
    return name, words[j + 1:], stdin


def git_sub(args: list[str]) -> tuple[str, list[str]]:
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"):
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        return a.lower(), args[i + 1:]
    return "", []


def strip_heredocs(cmd: str) -> str:
    """Drop heredoc / here-string bodies that are the message of a git commit/tag/notes."""
    lines = cmd.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = HEREDOC_GIT.search(line)
        p = PS_HERESTR_GIT.search(line) if not m else None
        if m or p:
            end = (lambda s: s.strip() == m.group(2)) if m else (lambda s: s.lstrip().startswith(p.group(1) + "@"))
            j = i + 1
            while j < len(lines) and not end(lines[j]):
                j += 1
            if j < len(lines):  # only strip a terminated body
                out.append(lines[j])
                i = j + 1
                continue
        i += 1
    return "\n".join(out)


def executes(t: str) -> bool:
    """A message containing a command substitution runs code (except a bare $(cat <<EOF))."""
    live = CAT_HEREDOC_STUB.sub("", t)
    return "$(" in live or "`" in live


def data_view(cmd: str, ps: bool = False) -> str:
    """The command with git commit/tag messages removed (they are data, not commands).
    A message that runs a command substitution is kept: that part does execute."""
    text = strip_heredocs(cmd)
    segs = segments(text, ps)
    if segs is None:
        return text
    changed = text != cmd
    rebuilt = []
    for seg in segs:
        name, args, _ = split_seg(seg)
        sub, _rest = git_sub(args) if name == "git" else ("", [])
        if sub not in MSG_SUBCMDS:
            rebuilt.append(seg)
            continue
        keep, skip = [], False
        for t in seg:
            if skip:
                skip = False
                if executes(t):
                    keep.append(t)
                else:
                    changed = True
                continue
            if t in ("-m", "--message", "-F", "--file") or re.fullmatch(r"-[a-zA-Z]*m", t):
                keep.append(t)
                skip = True
                continue
            if t.startswith("--message=") or (t.startswith("-m") and len(t) > 2):
                if executes(t):
                    keep.append(t)
                else:
                    changed = True
                continue
            keep.append(t)
        rebuilt.append(keep)
    if not changed:
        return cmd
    return " ;\n".join(" ".join(s) for s in rebuilt)


def literal_prefix(pattern: str) -> str:
    out, i = [], 0
    p = pattern.lstrip("^")
    while i < len(p):
        ch = p[i]
        if ch == "\\":
            nxt = p[i + 1] if i + 1 < len(p) else ""
            if nxt == "s":
                out.append(" ")
            elif nxt and not nxt.isalnum():
                out.append(nxt)
            else:
                break
            i += 2
            continue
        if ch in REGEX_META:
            break
        out.append(ch)
        i += 1
    return "".join(out).strip()


def deploy_keywords(cfg: dict) -> list[str]:
    kws = [k for k in cfg["deploy_keywords"] if k.strip()]
    for pat in cfg["deploy_patterns"]:
        pre = literal_prefix(pat)
        if len(pre) >= 4:
            kws.append(pre)
        first = pre.split(" ")[0] if pre else ""
        if len(first) >= 4:
            kws.append(first)
    return [re.sub(r"\s+", "", k).lower() for k in kws]


def protected_tokens(cfg: dict) -> list[str]:
    toks = {".factory", "authority.yaml", ".claude/settings", "sitecustomize", "usercustomize",
            c.STATE_APP, slashed(c.state_base())}
    for key in ("records_dir", "ledger"):
        if not cfg[key]:
            continue
        rel = slashed(cfg[key]).strip("/")
        toks.add(rel)
        base = rel.rsplit("/", 1)[-1]
        if len(base) >= 6:
            toks.add(base)
    toks.add(slashed(c.HOOK_DIR))
    hook_name = os.path.basename(c.HOOK_DIR).lower()
    if len(hook_name) >= 6:
        toks.add(hook_name)
    for p in cfg["protected_paths"]:
        if p.strip():
            toks.add(slashed(p).strip("/"))
    return [t for t in toks if t]


def protected_roots(cfg: dict) -> list[str]:
    root = cfg["_root"]
    home = os.path.expanduser("~")
    paths = [
        os.path.join(root, ".factory"),
        c.state_base(),
        cfg["_records_abs"],
        cfg["_ledger_abs"],
        c.HOOK_DIR,
        os.path.join(root, ".claude", "settings.json"),
        os.path.join(root, ".claude", "settings.local.json"),
        os.path.join(home, ".claude", "settings.json"),
        os.path.join(home, ".claude", "settings.local.json"),
    ]
    for p in cfg["protected_paths"]:
        paths.append(p if os.path.isabs(p) else os.path.join(root, p))
    paths.extend(python_import_dirs())
    return [canon(p) for p in paths]


def python_import_dirs() -> list[str]:
    """Where a planted module (sitecustomize.py, a fake yaml) would change the gate itself."""
    dirs = set()
    for key in ("purelib", "platlib", "stdlib", "platstdlib"):
        try:
            dirs.add(sysconfig.get_paths()[key])
        except Exception:
            pass
    try:
        dirs.add(site.getusersitepackages())
    except Exception:
        pass
    return [d for d in dirs if d]


def canon(path: str) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def under(path: str, roots: list[str]) -> bool:
    return any(path == r or path.startswith(r.rstrip(os.sep) + os.sep) for r in roots)


def all_strings(obj) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in all_strings(v)]
    if isinstance(obj, (list, tuple)):
        return [s for v in obj for s in all_strings(v)]
    return []


# ----------------------------------------------------------------- checks


def check_file_write(tin: dict, cfg: dict, cwd: str) -> None:
    roots = protected_roots(cfg)
    for key in ("file_path", "notebook_path", "path"):
        p = tin.get(key)
        if not isinstance(p, str) or not p.strip():
            continue
        full = canon(p if os.path.isabs(p) else os.path.join(cwd, p))
        parts = [x.lower() for x in re.split(r"[\\/]+", full)]
        if under(full, roots) or ".factory" in parts:
            raise Deny(f"writes to {p} are blocked: authorization records, the deploy ledger, "
                       "authority.yaml, the gate's own files, Claude settings and Python's "
                       "import directories are owner-only.")
    texts = [tin.get(k) for k in CONTENT_KEYS]
    for e in tin.get("edits") or []:
        if isinstance(e, dict):
            texts.append(e.get("new_string"))
    for t in texts:
        if isinstance(t, str):
            check_content(t, cfg, "file content")


def check_content(t: str, cfg: dict, via: str) -> None:
    """Text that will later be executed or applied (a script, a patch, a slash command)."""
    if mentions_deploy(t, cfg):
        raise Deny(f"{via} contains the production deploy command; writing it into a "
                   "script would run the deploy outside the gate. The owner edits deploy "
                   "scripts in a governed project.")
    check_forge(t, cfg, via)
    check_keystrokes(t)
    check_protected_tokens(t, cfg, via)


def mentions_deploy(text: str, cfg: dict) -> bool:
    ns = nospace(text)
    if any(k and k in ns for k in deploy_keywords(cfg)):
        return True
    return any(rx.search(text) or rx.search(squash(text)) for rx in cfg["_compiled"])


def check_protected_mention(text: str, cfg: dict, cwd: str | None = None, ps: bool = False) -> None:
    check_globs(text, cfg, cwd or cfg["_root"], ps)
    check_protected_tokens(text, cfg, "command")


def glob_roots(cfg: dict) -> list[tuple[str, bool]]:
    """(path, strict): strict roots (the state dir) deny even a catch-all wildcard reaching them."""
    root = cfg["_root"]
    home = os.path.expanduser("~")
    strict = [c.state_base(), cfg["_records_abs"], cfg["_ledger_abs"]]
    loose = [os.path.join(root, ".factory"), c.HOOK_DIR, os.path.join(root, ".claude", "settings.json"),
             os.path.join(home, ".claude", "settings.json")]
    loose += [p if os.path.isabs(p) else os.path.join(root, p) for p in cfg["protected_paths"]]
    return [(canon(p), True) for p in strict] + [(canon(p), False) for p in loose]


def expand_anchor(first: str) -> str | None:
    """Resolve the first path component of a glob: ~, $env:X, %X%, $X, ${X}, or a drive."""
    if first == "~":
        return os.path.expanduser("~")
    m = (re.fullmatch(r"\$(?:env:)?\{?(\w+)\}?", first, re.IGNORECASE)
         or re.fullmatch(r"\$\{env:(\w+)\}", first, re.IGNORECASE) or re.fullmatch(r"%(\w+)%", first))
    if m:
        return os.environ.get(m.group(1)) or os.environ.get(m.group(1).upper())
    if re.fullmatch(r"[A-Za-z]:", first):
        return first + os.sep
    return None


def check_glob_path(tok: str, roots: list[tuple[str, bool]], cwd: str) -> None:
    comps = tok.replace("\\", "/").split("/")
    if comps and comps[0] == "":
        prefix, comps = os.path.abspath(os.sep), comps[1:]
    else:
        anchor = expand_anchor(comps[0]) if comps else None
        if anchor is not None:
            prefix, comps = anchor, comps[1:]
        elif comps and comps[0].startswith(("$", "%")):
            return  # unknown variable: cannot resolve (OD-11 accepted gap)
        else:
            prefix = cwd
    for comp in comps:
        if comp in ("", "."):
            continue
        if comp == "..":
            prefix = os.path.dirname(prefix)
            continue
        if not GLOB_CH & set(comp):
            prefix = os.path.join(prefix, comp)
            continue
        base = canon(prefix)
        catch_all = comp in CATCH_ALL or bool(CATCH_ALL_RE.match(comp))
        for r, strict in roots:
            try:
                rel = os.path.relpath(r, base)
            except ValueError:
                continue
            if rel == "." or rel.startswith(".."):
                continue
            parts = rel.split(os.sep)
            if not fnmatch.fnmatchcase(parts[0].lower(), comp.lower()):
                continue
            if not catch_all or (strict and len(parts) == 1):
                raise Deny(f"wildcard '{tok}' can reach the protected path {r}; name the files "
                           "you mean instead (seatbelt, OD-11).")
        return  # nothing after a wildcard can be resolved


def check_globs(text: str, cfg: dict, cwd: str, ps: bool = False) -> None:
    segs = segments(text, ps)
    if segs is None:
        if DOT_GLOB.search(text):
            raise Deny("wildcards on dot-directories (e.g. '.f*') are blocked in a governed "
                       "project: they can reach the protected .factory folder without naming it.")
        return
    roots = glob_roots(cfg)
    for seg in segs:
        for tok in seg:
            for cand in {tok, tok.split("=", 1)[-1]}:
                body = ANCHOR_RE.sub("", cand, count=1)  # a $env:X / %X% / ~ anchor is not regex
                if GLOB_CH & set(body) and not REGEXY & set(body):
                    check_glob_path(cand, roots, cwd)


def check_protected_tokens(text: str, cfg: dict, via: str) -> None:
    s = slashed(text)
    sq = slashed(squash(text))
    for tok in protected_tokens(cfg):
        if tok in s or tok in sq:
            raise Deny(f"{via} mentions protected path '{tok}'. Authorization records, the "
                       "deploy ledger, authority.yaml, the gate's files and Claude settings "
                       "cannot be touched from a shell, a script or a patch (use the Read tool "
                       "to inspect them).")


def check_git_destroy(text: str) -> None:
    """git operations that delete untracked files or revert the whole tree."""
    for seg in (squash(x).lower() for x in re.split(r"[;&|\n]+", text)):
        if not re.search(r"\bgit\b", seg):
            continue
        words = seg.split()
        if re.search(r"\bgit\b.*\sclean(\s|$)", seg) and not re.search(
                r"\s(-[a-z]*n[a-z]*|--dry-run)(\s|$)", seg):
            raise Deny("'git clean' (without -n) is blocked in a governed project: it deletes "
                       "untracked files such as authority.yaml.")
        if re.search(r"\bgit\b.*\sstash(\s|$)", seg) and re.search(
                r"\s(-[a-z]*[ua][a-z]*|--include-untracked|--all)(\s|$)", seg):
            raise Deny("'git stash -u/--all' is blocked in a governed project: it removes "
                       "untracked files such as authority.yaml.")
        if re.search(r"\bgit\b.*\sreset(\s|$)", seg) and "--hard" in words:
            raise Deny("'git reset --hard' is blocked in a governed project: it can revert "
                       "the gate's config and files. The owner runs it.")
        unstage_only = (re.search(r"\bgit\b.*\srestore(\s|$)", seg) and
                        ({"--staged", "-s"} & set(words)) and not ({"--worktree", "-w"} & set(words)))
        if (re.search(r"\bgit\b.*\s(checkout|restore)(\s|$)", seg) and TREE_PATHSPEC & set(words)
                and not unstage_only):
            raise Deny("whole-tree 'git checkout/restore' is blocked in a governed project: it "
                       "can revert the gate's config and files. Name the files instead.")


AM_CONTROL = {"--abort", "--continue", "--skip", "--quit", "--resolved", "-r",
              "--show-current-patch", "--retry"}
APPLY_READONLY = {"--check", "--stat", "--numstat", "--summary"}


def patch_targets(seg: list[str]) -> list[str] | None:
    """Files a patch command would apply, [] for stdin, None if the segment applies nothing."""
    name, args, stdin = split_seg(seg)
    if name == "git":
        sub, rest = git_sub(args)
        if sub == "apply":
            if APPLY_READONLY & set(rest) and "--apply" not in rest:
                return None
        elif sub == "am":
            if AM_CONTROL & set(rest):
                return None
        else:
            return None
        files = [a for a in rest if not a.startswith("-")]
    elif name == "patch":
        files, i = [], 0
        while i < len(args):
            a = args[i]
            if a in ("-i", "--input") and i + 1 < len(args):
                files.append(args[i + 1])
                i += 2
                continue
            if a.startswith("--input="):
                files.append(a.split("=", 1)[1])
            elif not a.startswith("-"):
                files.append(a)
            i += 1
    else:
        return None
    return files + stdin


def check_patch_apply(cmd: str, cfg: dict, cwd: str, ps: bool = False) -> None:
    """git apply / git am / patch: inspect every patch file named; stdin patches are denied."""
    segs = segments(cmd, ps)
    if segs is None:
        if PATCH_CMD.search(cmd) or PATCH_CMD.search(squash(cmd)):
            raise Deny("a command that may apply a patch could not be parsed; its patch cannot "
                       "be checked in a governed project.")
        return
    for seg in segs:
        files = patch_targets(seg)
        if files is None:
            continue
        seen = 0
        for tok in files:
            path = tok if os.path.isabs(tok) else os.path.join(cwd, tok)
            try:
                if not os.path.isfile(path) or os.path.getsize(path) > 5_000_000:
                    continue
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    body = fh.read()
            except OSError:
                continue
            seen += 1
            check_content(body, cfg, f"patch file {tok}")
        if not seen:
            raise Deny("applying a patch whose file cannot be read (stdin, missing file) is "
                       "blocked in a governed project: its content cannot be checked.")


def check_forge(text: str, cfg: dict, via: str) -> None:
    phrase = nospace(cfg["authorize_phrase"])
    ns = nospace(text)
    if phrase in ns:
        if CLAUDE_LAUNCH.search(text):
            raise Deny(f"{via} launches Claude with '{cfg['authorize_phrase']}': a scripted "
                       "prompt can never authorize production. Only the owner can, by typing it.")
        raise Deny(f"{via} contains '{cfg['authorize_phrase']}'. Only the owner can authorize "
                   "production, by typing it in an attended session.")


CLAUDE_INFO_FLAGS = {"--version", "-v", "--help", "-h"}


def is_claude_management(args: list[str]) -> bool:
    """claude --version / --help / mcp list / mcp get X / doctor: start no session."""
    if args and all(a.lower() in CLAUDE_INFO_FLAGS for a in args):
        return True
    low = [a.lower() for a in args]
    if low[:2] == ["mcp", "list"] and len(low) == 2:
        return True
    if low[:2] == ["mcp", "get"] and len(low) == 3:
        return True
    if low == ["doctor"] or (low[:1] == ["mcp"] and low[1:] and all(a in CLAUDE_INFO_FLAGS for a in low[1:])):
        return True
    return False


def claude_management_only(text: str, ps: bool = False) -> bool:
    """True when every Claude launch in `text` is a management call (no session starts)."""
    segs = segments(text, ps)
    if segs is None:
        return False
    mgmt = 0
    for seg in segs:
        name, args, _ = split_seg(seg)
        if name in CLAUDE_NAMES:
            if not is_claude_management(args):
                return False
            mgmt += 1
    hits = len(CLAUDE_LAUNCH.findall(text))
    return mgmt > 0 and hits <= mgmt


def check_claude_launch(text: str, cwd_inside: bool = True, ps: bool = False) -> None:
    sq = squash(text)
    ns = nospace(text)
    if (not any(t in ns for t in NEW_CONSOLE)) and claude_management_only(text, ps):
        return
    if "claude" in ns and any(t in ns for t in NEW_CONSOLE):
        raise Deny("starting Claude in a new console is blocked in a governed project (an "
                   "attended-looking session could carry a forged authorization).")
    if not (CLAUDE_LAUNCH.search(text) or CLAUDE_LAUNCH.search(sq)):
        return
    if not PRINT_FLAG.search(sq):
        raise Deny("only headless 'claude -p' launches are allowed from a shell in a governed "
                   "project; an interactive Claude would look attended.")
    if not cwd_inside:
        raise Deny("Claude may not be launched from a directory outside the governed project: "
                   "the child would not load this project's hooks.")
    if CHILD_ESCAPE.search(sq) or any(t in ns for t in CHILD_ESCAPE_TOKENS):
        raise Deny("a Claude child may not change directory, add directories, or replace its "
                   "settings/config dir: it could run without this project's prod-gate hooks.")


def check_keystrokes(text: str) -> None:
    low = nospace(text)
    for tok in KEYSTROKE_TOKENS:
        if tok.replace(" ", "") in low:
            raise Deny(f"keystroke/window-injection API '{tok}' is blocked in a governed project "
                       "(it could type a forged authorization into an attended session).")


def find_deploy(cmd: str, cfg: dict) -> str | None:
    """Return the release a deploy command targets, None if it is not a deploy; raise Deny
    for deploy-looking text that cannot be safely attributed to exactly one release."""
    forms = [cmd, squash(cmd)]
    counts, releases = [], []
    for form in forms:
        n = 0
        starts = set()
        for rx in cfg["_compiled"]:
            # overlapping scan: a permissive pattern ending in .* must not swallow a 2nd deploy
            pos = 0
            while pos <= len(form):
                m = rx.search(form, pos)
                if not m:
                    break
                starts.add(m.start())
                releases.append(m.group("release"))
                pos = m.start() + 1
        n = len(starts)
        counts.append(n)
    ns = nospace(cmd)
    kws = deploy_keywords(cfg)
    kw_hit = any(k and k in ns for k in kws)
    kw_max = max([ns.count(k) for k in kws if k] or [0])
    if not releases:
        if kw_hit:
            raise Deny("command looks like a production deploy but is not in the canonical form "
                       "declared in authority.yaml (literal release id required, no variables, "
                       "quoting tricks or indirection).")
        return None
    if any(r is None or not re.fullmatch(c.RELEASE_RE, r) for r in releases):
        raise Deny("deploy command has no literal release id (R-###); cannot be authorized.")
    if len(set(releases)) > 1:
        raise Deny(f"one command targets several releases {sorted(set(releases))}; deploy one at a time.")
    if max(counts) > 1 or kw_max > 1:
        raise Deny("one command runs the production deploy more than once; one deploy per command.")
    if not any(rx.fullmatch(cmd.strip()) for rx in cfg["_compiled"]):
        raise Deny("a production deploy must be run alone, exactly in the form declared in "
                   "authority.yaml: nothing chained before or after it, no loops, no wrappers.")
    return releases[0]


class Lock:
    def __init__(self, directory: str):
        self.path = os.path.join(directory, ".prod-gate.lock")
        self.fd = None

    def __enter__(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        for _ in range(100):
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(self.path) > 30:
                        os.remove(self.path)
                        continue
                except OSError:
                    pass
                time.sleep(0.05)
        raise RuntimeError("could not take the prod-gate lock")

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
            try:
                os.remove(self.path)
            except OSError:
                pass


def ledger_today(cfg: dict, date: str) -> int:
    path = cfg["_ledger_abs"]
    if not os.path.exists(path):
        return 0
    n = 0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                n += 1  # unreadable line counts against the cap (fail closed)
                continue
            if not isinstance(entry, dict) or entry.get("date") == date:
                n += 1
    return n


def authorize(release: str, cfg: dict, data: dict, cmd: str) -> None:
    phrase = cfg["authorize_phrase"]
    date = c.today()
    with Lock(cfg["_records_abs"]):
        path = c.record_path(cfg, date, release)
        if not os.path.isfile(path):
            raise Deny(f"no owner authorization for {release} today ({date}). The owner must "
                       f"type '{phrase} {release}' in an attended Claude session first.")
        with open(path, "r", encoding="utf-8") as fh:
            rec = json.load(fh)
        if not isinstance(rec, dict) or rec.get("release") != release or rec.get("date") != date:
            raise Deny(f"authorization record for {release} is malformed or not for today; "
                       f"the owner must type '{phrase} {release}' again.")
        if rec.get("used") is not False:
            raise Deny(f"authorization for {release} today was already used; the owner must "
                       f"authorize again tomorrow.")
        done = ledger_today(cfg, date)
        if done >= cfg["max_deploys_per_day"]:
            raise Deny(f"production already deployed {done} time(s) today (max "
                       f"{cfg['max_deploys_per_day']}/day).")
        entry = {"date": date, "release": release, "session_id": data.get("session_id"),
                 "command": cmd, "at": c.now_iso()}
        os.makedirs(os.path.dirname(cfg["_ledger_abs"]), exist_ok=True)
        with open(cfg["_ledger_abs"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        rec.update({"used": True, "used_at": entry["at"], "used_by_session": data.get("session_id"),
                    "command": cmd})
        c.write_json_atomic(path, rec)


def authorize_tool(tool: str, cfg: dict, data: dict) -> None:
    """A deploy-like tool call (deploy_tools): consume ANY unused record dated today."""
    phrase = cfg["authorize_phrase"]
    date = c.today()
    with Lock(cfg["_records_abs"]):
        chosen = None
        d = cfg["_records_abs"]
        names = sorted(os.listdir(d)) if os.path.isdir(d) else []
        for n in names:
            if not (n.startswith(date + "-") and n.endswith(".json")):
                continue
            try:
                with open(os.path.join(d, n), "r", encoding="utf-8") as fh:
                    rec = json.load(fh)
            except (OSError, ValueError):
                continue
            rel = n[len(date) + 1:-5]
            if (isinstance(rec, dict) and rec.get("used") is False and rec.get("date") == date
                    and rec.get("release") == rel):
                chosen = (os.path.join(d, n), rec)
                break
        if chosen is None:
            raise Deny(f"tool {tool} deploys/restarts production (deploy_tools) and there is no "
                       f"unused owner authorization today ({date}). The owner must type "
                       f"'{phrase} R-###' in an attended Claude session first.")
        done = ledger_today(cfg, date)
        if done >= cfg["max_deploys_per_day"]:
            raise Deny(f"production already deployed {done} time(s) today (max "
                       f"{cfg['max_deploys_per_day']}/day); tool {tool} counts as a deploy.")
        path, rec = chosen
        entry = {"date": date, "release": rec["release"], "session_id": data.get("session_id"),
                 "tool": tool, "command": json.dumps(data.get("tool_input"), default=str)[:2000],
                 "at": c.now_iso()}
        os.makedirs(os.path.dirname(cfg["_ledger_abs"]), exist_ok=True)
        with open(cfg["_ledger_abs"], "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        rec.update({"used": True, "used_at": entry["at"], "used_by_session": data.get("session_id"),
                    "command": f"tool {tool}"})
        c.write_json_atomic(path, rec)


def is_deploy_tool(tool: str, cfg: dict) -> bool:
    return any(rx.fullmatch(tool) for rx in cfg["_deploy_tools"])


# ----------------------------------------------------------------- evaluation


def evaluate(data: dict, cfg: dict):
    """Raise Deny, or return None / ("release", R-###) / ("tool", name) still to authorize."""
    tool = data.get("tool_name") or ""
    tin = data.get("tool_input") or {}
    if not isinstance(tin, dict):
        tin = {"value": tin}
    cwd = data.get("cwd") or os.getcwd()

    if tool in PASS_TOOLS:
        return None
    if tool in FILE_WRITE_TOOLS:
        check_file_write(tin, cfg, cwd)
        return None
    if tool in SHELL_TOOLS:
        cmd = tin.get("command")
        if not isinstance(cmd, str):
            raise Deny("shell tool call without a command string")
        ps = tool == "PowerShell"
        cwd_c = canon(cwd)
        parts = [x.lower() for x in re.split(r"[\\/]+", cwd_c)]
        if ".factory" in parts or under(cwd_c, protected_roots(cfg)):
            raise Deny("shell commands may not run from inside a protected directory.")
        view = data_view(cmd, ps)  # git commit/tag messages removed: data, not commands
        check_protected_mention(view, cfg, cwd, ps)
        check_git_destroy(view)
        check_patch_apply(view, cfg, cwd, ps)
        check_keystrokes(cmd)
        check_forge(cmd, cfg, "command")
        check_claude_launch(view, under(cwd_c, [canon(cfg["_root"])]), ps)
        release = find_deploy(view, cfg)
        return ("release", release) if release is not None else None
    # SendMessage / RemoteTrigger / Monitor / Workflow / Agent / Skill / MCP and any other tool
    text = "\n".join(all_strings(tin))
    via = "message" if tool in MESSAGE_TOOLS else f"tool {tool}"
    check_forge(text, cfg, via)
    if tool in AGENT_TOOLS:
        if str(tin.get("isolation", "")).lower() == "remote":
            raise Deny(f"{tool} with remote isolation is blocked in a governed project: a remote "
                       "agent runs without this machine's prod-gate hooks.")
        if mentions_deploy(text, cfg):
            raise Deny(f"{tool} input carries the production deploy command; only the owner's "
                       "attended session runs a deploy, through Bash/PowerShell under the gate.")
        return None
    if tool in COMMAND_TOOLS:
        check_git_destroy(text)
        check_claude_launch(text)
    if tool not in MESSAGE_TOOLS:
        check_keystrokes(text)
        check_protected_mention(text, cfg, cwd)
        try:
            release = find_deploy(text, cfg)
        except Deny:
            release = "?"
        if release is not None:
            raise Deny(f"production deploys may run only through Bash/PowerShell under the gate, "
                       f"not through {tool}.")
    if tool not in MESSAGE_TOOLS and tool not in COMMAND_TOOLS and is_deploy_tool(tool, cfg):
        return ("tool", tool)
    return None


CD_WORDS = {"cd", "pushd", "chdir", "set-location", "sl"}


def norm_sep(path: str) -> str:
    """Normalize a possibly-Windows-style path to use '/' as separator.

    PowerShell/Windows-style arguments (cd targets, path args) can contain backslashes
    regardless of the host OS the hook itself runs on: a transcript replayed from a
    Windows session, or a PowerShell command captured verbatim, still uses '\\'. On a
    POSIX host, os.path.join/os.path.abspath treat '\\' as an ordinary filename
    character (not a separator), so a target like '..\\proj' never resolves to the
    parent's sibling 'proj' and a governed sibling project goes undetected. Convert
    backslashes to '/' before any join/resolve so path handling matches Windows
    behaviour on every host. A drive letter ('C:\\...') keeps its colon; only the
    backslashes become slashes ('C:/...'), which every OS's path functions accept.
    """
    return path.replace("\\", "/")


def candidate_dirs(data: dict) -> list[str]:
    """Every place whose project rules apply: cwd, CLAUDE_PROJECT_DIR, cd targets, path args."""
    cwd = data.get("cwd") or os.getcwd()
    out = [cwd]
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        out.append(os.environ["CLAUDE_PROJECT_DIR"])
    tin = data.get("tool_input")
    tool = data.get("tool_name") or ""
    strings = all_strings(tin) if isinstance(tin, (dict, list)) else []
    words: list[str] = []
    for text in strings:
        if len(text) > 200_000:
            continue
        segs = segments(text, tool == "PowerShell") if tool in SHELL_TOOLS or tool in COMMAND_TOOLS else None
        if segs is not None:
            for seg in segs:
                name, args, stdin = split_seg(seg)
                words.extend(args + stdin)
                if name in CD_WORDS:
                    words.extend(a for a in args if not a.startswith("-"))
                words.extend(seg)
        elif "\n" not in text:
            words.append(text)
    here = norm_sep(cwd)
    for w in words:
        w = w.split("=", 1)[-1] if w.startswith("-") else w
        w = w.strip().strip("\"'")
        if not w or len(w) > 1024 or not re.search(r"[\\/]", w) or "://" in w:
            continue
        w = norm_sep(os.path.expanduser(w))
        out.append(w if os.path.isabs(w) or re.match(r"^[A-Za-z]:", w) else os.path.join(here, w))
    return out


def governed_roots(data: dict) -> tuple[list[str], list[str]]:
    """(roots with authority.yaml, once-governed roots whose authority.yaml is gone)."""
    roots, lost = [], []
    for d in candidate_dirs(data):
        r = c.find_project_root(d)
        if r is not None:
            if canon(r) not in {canon(x) for x in roots}:
                roots.append(r)
            continue
        try:
            m = c.find_governed_marker(d)
        except Exception:
            m = None
        if m and m not in lost:
            lost.append(m)
    return roots, lost


def looks_sensitive(blob: str) -> bool:
    low = blob.lower()
    return any(t in low for t in ("deploy", "authoriz", ".factory", "prod", "release", "claude"))


def main() -> int:
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw) if raw.strip() else {}
        if not isinstance(data, dict):
            raise ValueError("hook input is not an object")
    except Exception as exc:
        if looks_sensitive(raw):
            return deny(f"unreadable hook input ({exc}); failing closed.")
        return 0
    tool = data.get("tool_name") or ""
    if tool in PASS_TOOLS:
        return 0
    # the rules of EVERY involved project apply: the tool's cwd, the session's project dir (a
    # shell that cd'ed out is still governed), and any project a cd target or path arg lands in
    try:
        roots, lost = governed_roots(data)
    except Exception as exc:
        if looks_sensitive(json.dumps(data.get("tool_input"), default=str)):
            return deny(f"could not resolve the projects involved ({exc}); failing closed.")
        return 0
    for gone in lost:
        if gone and tool not in PASS_TOOLS:
            return deny(f"{gone} was a governed project but its .factory/authority.yaml is gone "
                        "(deleted, stashed, cleaned or checked out away); every shell/write call "
                        "is blocked until the owner restores it or removes the governed marker "
                        f"at {os.path.join(c.state_dir(gone), c.GOVERNED_MARK)}.")
    pending = []
    for root in roots:
        try:
            cfg = c.load_config(root)
        except c.ConfigError as exc:
            return deny(f"authority.yaml of {root} is unusable ({exc}); every shell/write call "
                        "is blocked in this project until the owner fixes it.")
        try:
            c.mark_governed(root)
        except Exception as exc:
            print(f"prod-gate: could not write governed marker: {exc}", file=sys.stderr)
        try:
            got = evaluate(data, cfg)
        except Deny as d:
            return deny(str(d) if len(roots) == 1 else f"[{root}] {d}")
        except Exception as exc:
            if looks_sensitive(json.dumps(data.get("tool_input"), default=str)):
                return deny(f"internal error while checking a possibly production-related call "
                            f"({type(exc).__name__}: {exc}); failing closed.")
            print(f"prod-gate: internal error on an unrelated call, allowing: {exc}", file=sys.stderr)
            continue
        if got is not None:
            pending.append((got, cfg))
    # authorize only after every project allowed, so a later deny never wastes a record
    for (kind, value), cfg in pending:
        try:
            if kind == "release":
                authorize(value, cfg, data, data.get("tool_input", {}).get("command", ""))
            else:
                authorize_tool(value, cfg, data)
        except Deny as d:
            return deny(str(d))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # last resort: fail closed
        sys.exit(deny(f"unexpected gate failure ({exc}); failing closed."))
