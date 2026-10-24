"""REQ-133 AC-2 repo guard: a Playwright file that answers the strategy live socket itself must stamp every push.

Findings test-double-encodes-old-assumption and static-guard-scoped-by-name-text: the page drops a live push that lacks
the version it sent, and a Playwright file that plays the server itself kept sending pushes without it. The first cut
of this scan decided scope by the pattern's TEXT and judged each FILE once; both let real cases through. This one:

- SCOPE by what the pattern would match: every `routeWebSocket` pattern under `frontend/e2e` (`*.ts`, `*.js`, `*.mjs`
  and the other script suffixes) is translated with Playwright's glob rules (`**` any characters, `*` any except `/`,
  `?` one character, `{a,b}`; a `/.../` regex literal is searched) and tested against the live socket URL. A match =
  live-socket route. A pattern the scan cannot translate (variable, `${` template, `new RegExp(`, a call) fails closed.
- RULE per SEND (comments stripped, string text blanked first), in every file that routes the live socket and in every
  e2e file it imports (relative imports, transitively - a helper that does the sending is checked too). A `.send(` is
  allowed only when (a) ECHO: its argument is `<x>.stamp(...)` (optionally inside `JSON.stringify(...)`) of an object
  made by `echoSeq()` imported from `frontend/e2e/support/echoSeq` (import source; alias followed), (b) FORWARD: the
  argument is exactly the parameter of the enclosing `onMessage((m) =>` callback and the two sockets are the page's and
  a `connectToServer()` one, (c) SILENT: the file's live routes are all `() => {}` handlers, or (d) CLIENT: the send is
  on a `new WebSocket(` made in the file, outside every route handler. Anything else fails with file:line; a send the
  scan cannot attribute (`ws['send'](`, `ws.send?.(`, a bare `send(`) fails closed.

Out of reach (stated, not detected): a send through a computed property built at run time, a socket whose URL cannot
match the live one, a module imported through a non-relative specifier or a re-export, Vitest fakes under
frontend/tests (covered by the builder-brief standing item).
"""

from __future__ import annotations

import posixpath
import re
import shutil
from pathlib import Path
from typing import NamedTuple

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = Path(__file__).resolve().parent.parent
E2E = Path("frontend") / "e2e"
LIVE_PATH = "/api/strategies/live"
LIVE_URLS = (f"http://127.0.0.1:4173{LIVE_PATH}", f"ws://127.0.0.1:4173{LIVE_PATH}", LIVE_PATH)
SUFFIXES = (".ts", ".js", ".mjs", ".cjs", ".mts", ".cts", ".tsx", ".jsx")
ECHO_MODULE = "frontend/e2e/support/echoSeq.ts"
ECHO_NAME = "echoSeq"
REMEDY = "import { echoSeq } from './support/echoSeq' and stamp every push"
REGEX_PREV = "(,=:[!&|?{};"
ECHO_RULE, FORWARD_RULE, SILENT_RULE, CLIENT_RULE = "echo", "forward", "silent", "client"

ROUTE_CALL = re.compile(r"\brouteWebSocket\s*\(")
IMPORT_NAMED = re.compile(r"""\bimport\s+(?:type\s+)?\{([^}]*)\}\s*from\s*(['"])([^'"\n]+)\2""")
IMPORT_NS = re.compile(r"""\bimport\s+\*\s*as\s+(\w+)\s+from\s*(['"])([^'"\n]+)\2""")
IMPORT_ANY = re.compile(r"""(?:\bfrom\s*|\bimport\s*|\brequire\s*\(\s*|\bimport\s*\(\s*)(['"])(\.[^'"\n]*)\1""")
STAMP_ARG = re.compile(r"\s*(JSON\s*\.\s*stringify\s*\(\s*)?(\w+)\s*\.\s*stamp\s*\(")
ON_MESSAGE = re.compile(r"(\w+)\s*\??\s*\.\s*onMessage\s*\(\s*\(?\s*(\w+)\s*\)?\s*=>")
SILENT_HANDLER = re.compile(r"\s*,\s*(?:async\s*)?\(\s*\w*\s*\)\s*=>\s*\{\s*\}\s*,?\s*$")
SEND_WORD = re.compile(r"\bsend\b")
SEND_BRACKET = re.compile(r"""\[\s*(['"`])send\1\s*\]""")
OPEN_CALL = re.compile(r"\s*\(")
CONNECT = re.compile(r"(\w+)\s*=\s*[\w$.]+\s*\.\s*connectToServer\s*\(")


def _blank(segment: str) -> str:
    return re.sub(r"[^\n]", " ", segment)


def _skip_string(text: str, start: int) -> int:
    quote, at = text[start], start + 1
    while at < len(text):
        if text[at] == "\\":
            at += 2
        elif text[at] == quote:
            return at + 1
        elif text[at] == "\n" and quote != "`":
            return at
        else:
            at += 1
    return len(text)


def _regex_end(text: str, start: int) -> int | None:
    at, in_class = start + 1, False
    while at < len(text) and text[at] != "\n":
        ch = text[at]
        if ch == "\\":
            at += 1
        elif ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "/" and not in_class:
            at += 1
            while at < len(text) and text[at].isalpha():
                at += 1
            return at
        at += 1
    return None


def strip_comments(text: str) -> tuple[str, str]:
    """Return (text without comments, the same with string bodies blanked too); both keep every offset and newline."""
    plain: list[str] = []
    masked: list[str] = []
    at, prev = 0, ""
    while at < len(text):
        two = text[at : at + 2]
        char = text[at]
        if two in ("//", "/*"):
            found = text.find("\n", at) if two == "//" else text.find("*/", at + 2)
            end = len(text) if found < 0 else (found if two == "//" else found + 2)
            plain.append(_blank(text[at:end]))
            masked.append(_blank(text[at:end]))
            at = end
            continue
        literal_end = None
        if char in "'\"`":
            literal_end = _skip_string(text, at)
        elif char == "/" and (prev == "" or prev in REGEX_PREV):
            literal_end = _regex_end(text, at)
        if literal_end is not None:
            segment = text[at:literal_end]
            plain.append(segment)
            masked.append(segment[:1] + _blank(segment[1:-1]) + segment[-1:] if len(segment) > 1 else segment)
            prev, at = char, literal_end
            continue
        plain.append(char)
        masked.append(char)
        if not char.isspace():
            prev = char
        at += 1
    return "".join(plain), "".join(masked)


def _close(text: str, open_at: int) -> int:
    """Index of the bracket closing the one at `open_at` (strings in `text` are already blanked); -1 if none."""
    pairs = {"(": ")", "{": "}", "[": "]"}
    depth = 0
    for at in range(open_at, len(text)):
        if text[at] in pairs:
            depth += 1
        elif text[at] in pairs.values():
            depth -= 1
            if depth == 0:
                return at
    return -1


class Route(NamedTuple):
    start: int
    close: int
    live: bool
    silent: bool


class Facts(NamedTuple):
    echoes: set[str]
    servers: set[str]
    routes: list[Route]


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def glob_to_regex(glob: str) -> str | None:
    """Playwright's glob rules, widened where unsure (more matches = more in scope); None = cannot translate."""
    out: list[str] = []
    at, depth = 0, 0
    while at < len(glob):
        ch = glob[at]
        if glob.startswith("**/", at):
            out.append("(?:.*/)?")
            at += 3
            continue
        if ch == "*":
            star = glob.startswith("**", at)
            out.append(".*" if star else "[^/]*")
            at += 2 if star else 1
            continue
        if ch == "[":
            end = glob.find("]", at + 1)
            if end < 0:
                return None
            out.append(glob[at : end + 1])
            at = end + 1
            continue
        if ch == "\\":
            out.append(re.escape(glob[at + 1 : at + 2]))
            at += 2
            continue
        depth += {"{": 1, "}": -1}.get(ch, 0)
        out.append({"?": ".", "{": "(?:", "}": ")"}.get(ch) or ("|" if ch == "," and depth else re.escape(ch)))
        at += 1
    return None if depth != 0 else "".join(out)


def matches_live_socket(kind: str, value: str) -> bool | None:
    """Would this pattern match the live socket URL? None = the scan cannot tell."""
    try:
        if kind == "regex":
            return any(re.search(value, url) for url in LIVE_URLS)
        pattern = glob_to_regex(value)
        return None if pattern is None else any(re.fullmatch(pattern, url) for url in LIVE_URLS)
    except re.error:
        return None


def _literal_arg(plain: str, start: int, close: int) -> tuple[str, str, int] | None:
    """The first argument of a call as (kind, value, end offset) when it is a plain literal, else None."""
    at = start
    while at < close and plain[at].isspace():
        at += 1
    if at >= close:
        return None
    if plain[at] in "'\"`":
        end = _skip_string(plain, at)
        body = plain[at + 1 : end - 1]
        bad = "\\" in body or (plain[at] == "`" and "${" in body) or plain[end - 1 : end] != plain[at]
        kind, value = "glob", body
    elif plain[at] == "/":
        regex_end = _regex_end(plain, at)
        if regex_end is None:
            return None
        end, bad = regex_end, False
        kind, value = "regex", plain[at + 1 : plain.rfind("/", at + 1, end)]
    else:
        return None
    rest = plain[end:close].lstrip()
    if bad or (rest and rest[0] not in ",)"):
        return None
    return kind, value, end


def _route_calls(rel: str, plain: str, masked: str) -> tuple[list[Route], list[str]]:
    """Return (the route calls with live / silent flags, fail-closed problems) for one file."""
    calls: list[Route] = []
    problems: list[str] = []
    for found in ROUTE_CALL.finditer(masked):
        open_at = found.end() - 1
        close = _close(masked, open_at)
        literal = _literal_arg(plain, open_at + 1, close if close > 0 else len(plain))
        verdict = matches_live_socket(literal[0], literal[1]) if literal else None
        if literal is None or close < 0 or verdict is None:
            line = _line_of(plain, found.start())
            problems.append(f"{rel}:{line}: routeWebSocket pattern is not a literal the scan can translate")
            continue
        calls.append(Route(found.start(), close, verdict, bool(SILENT_HANDLER.match(plain[literal[2] : close]))))
    return calls, problems


def _resolve(root: Path, rel: str, specifier: str) -> str | None:
    """The e2e file a relative import names, as a posix path from `root`; None when it is not an e2e file."""
    base = posixpath.normpath(posixpath.join(posixpath.dirname(rel), specifier))
    if not base.startswith(E2E.as_posix() + "/"):
        return None
    options = [base, *(base + suffix for suffix in SUFFIXES), *(f"{base}/index{suffix}" for suffix in SUFFIXES)]
    return next((option for option in options if (root / option).is_file()), "")


def _echo_pattern(root: Path, rel: str, plain: str) -> re.Pattern[str] | None:
    """A pattern matching `x = <echoSeq as imported from the echoSeq module>(`, followed by import source."""
    names: list[str] = []
    for named in IMPORT_NAMED.finditer(plain):
        if _resolve(root, rel, named.group(3)) == ECHO_MODULE:
            parts = [part.split() for part in named.group(1).split(",")]
            names.extend(re.escape(words[-1]) for words in parts if words and words[0] == ECHO_NAME)
    names.extend(
        re.escape(ns.group(1)) + r"\s*\.\s*" + ECHO_NAME
        for ns in IMPORT_NS.finditer(plain)
        if _resolve(root, rel, ns.group(3)) == ECHO_MODULE
    )
    return re.compile(r"(\w+)\s*=\s*(?:" + "|".join(names) + r")\s*\(") if names else None


def _send_rule(masked: str, at: int, arg: str, receiver: str, facts: Facts) -> str | None:
    """Which rule a send meets (echo / forward / client), or None."""
    stamp = STAMP_ARG.match(arg)
    if stamp and stamp.group(2) in facts.echoes:
        tail = arg[_close(arg, stamp.end() - 1) + 1 :].strip()
        if tail == (")" if stamp.group(1) else ""):
            return ECHO_RULE
    if re.fullmatch(r"\w+", arg.strip()):
        for cb in ON_MESSAGE.finditer(masked):
            end = _close(masked, masked.index("(", cb.start(1) + len(cb.group(1))))
            if (
                cb.start() < at < end
                and cb.group(2) == arg.strip()
                and ((cb.group(1) in facts.servers) != (receiver in facts.servers))
            ):
                return FORWARD_RULE
    inside_route = any(route.start < at < route.close for route in facts.routes)
    declared = re.search(rf"\b{re.escape(receiver)}\s*=\s*new\s+WebSocket\s*\(", masked[:at])
    if declared and not inside_route:
        return CLIENT_RULE
    return None


def _check_file(
    root: Path, rel: str, cleaned: tuple[str, str, list[Route]], is_live: bool
) -> tuple[list[tuple[str, int, str]], list[str]]:
    """Return ([(file, line, rule)], problems) for every send in one file."""
    plain, masked, routes = cleaned
    sends: list[tuple[str, int, str]] = []
    problems: list[str] = []
    live_routes = [route for route in routes if route.live]
    silent_file = is_live and bool(live_routes) and all(route.silent for route in live_routes)
    echo_re = _echo_pattern(root, rel, plain)
    echoes = {m.group(1) for m in echo_re.finditer(masked)} if echo_re else set()
    facts = Facts(echoes, {m.group(1) for m in CONNECT.finditer(masked)}, routes)
    problems.extend(
        f"{rel}:{_line_of(plain, b.start())}: send through a computed property; the scan cannot attribute it"
        for b in SEND_BRACKET.finditer(plain)
    )
    for word in SEND_WORD.finditer(masked):
        line = _line_of(masked, word.start())
        before = masked[: word.start()].rstrip()
        call = OPEN_CALL.match(masked, word.end())
        if not (before.endswith(".") and not before.endswith("?.") and call):
            problems.append(f"{rel}:{line}: send is not a plain `<socket>.send(` call; the scan cannot attribute it")
            continue
        receiver = re.search(r"(\w+)\s*\??\s*$", before[:-1])
        arg = masked[call.end() : _close(masked, call.end() - 1)]
        rule = _send_rule(masked, word.start(), arg, receiver.group(1) if receiver else "", facts)
        if rule is None and silent_file:
            rule = SILENT_RULE
        if rule is None:
            problems.append(f"{rel}:{line}: send is not an echoSeq stamp, a pure forward or a client socket; {REMEDY}")
        else:
            sends.append((rel, line, rule))
    return sends, problems


def scan(root: Path) -> tuple[dict[str, list[str]], list[tuple[str, int, str]], list[str]]:
    """Return ({live-socket file: rules its sends meet}, [(file, line, rule)] for every send checked, problems)."""
    e2e = root / E2E
    if not e2e.is_dir():
        return {}, [], [f"{E2E.as_posix()} is missing"]
    problems: list[str] = []
    cleaned: dict[str, tuple[str, str, list[Route]]] = {}
    for path in sorted(p for p in e2e.rglob("*") if p.is_file() and p.suffix in SUFFIXES):
        rel = path.relative_to(root).as_posix()
        plain, masked = strip_comments(path.read_text(encoding="utf-8"))
        routes, route_problems = _route_calls(rel, plain, masked)
        problems.extend(route_problems)
        cleaned[rel] = (plain, masked, routes)
    live = sorted(rel for rel, (_, _, routes) in cleaned.items() if any(route.live for route in routes))
    queue, checked = list(live), set(live)
    while queue:
        rel = queue.pop()
        for imp in IMPORT_ANY.finditer(cleaned[rel][0]):
            target = _resolve(root, rel, imp.group(2))
            if target == "":
                line = _line_of(cleaned[rel][0], imp.start())
                problems.append(f"{rel}:{line}: import {imp.group(2)} does not resolve to an e2e file")
            elif target and target not in checked:
                checked.add(target)
                queue.append(target)
    rules: dict[str, list[str]] = {rel: [] for rel in live}
    report: list[tuple[str, int, str]] = []
    for rel in sorted(checked):
        sends, send_problems = _check_file(root, rel, cleaned[rel], rel in live)
        report.extend(sends)
        problems.extend(send_problems)
        if rel in rules:
            rules[rel] = sorted({rule for _, _, rule in sends})
    return rules, report, sorted(problems)


EXPECTED = {
    "frontend/e2e/execute-screen.spec.ts": [ECHO_RULE],
    "frontend/e2e/feed-reconnect.spec.ts": [ECHO_RULE],
    "frontend/e2e/strategy-live.spec.ts": [CLIENT_RULE, FORWARD_RULE],
    "frontend/e2e/live-strategies.spec.ts": [FORWARD_RULE],
    "frontend/e2e/support/quiet-live.ts": [],
}
LIVE_ROUTE = "await page.routeWebSocket('**/api/strategies/live', (ws) => {\n  %s\n})\n"


def _copy_tree(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / E2E, tmp_path / E2E)
    return tmp_path


def _edit(root: Path, name: str, old: str, new: str) -> None:
    path = root / E2E / name
    text = path.read_text(encoding="utf-8")
    assert text.count(old) >= 1, f"{old!r} not in {name}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def _add(root: Path, name: str, body: str) -> None:
    (root / E2E / name).write_text(body, encoding="utf-8")


def _problems(root: Path) -> list[str]:
    return scan(root)[2]


def test_real_tree_every_live_socket_send_meets_the_rule() -> None:
    """AC-2: today's e2e tree has no send on the strategy live socket that is unstamped."""
    assert _problems(ROOT) == []


def test_report_lists_each_live_socket_file_and_the_rule_each_send_met(capsys: pytest.CaptureFixture[str]) -> None:
    """AC-2: the live-socket files today are exactly the five known ones, with the rule each send met."""
    rules, report, _ = scan(ROOT)
    with capsys.disabled():
        for rel, line, rule in report:
            print(f"{rule:8} {rel}:{line}")
        for rel in rules:
            print(f"live     {rel}")
    assert rules == EXPECTED


def test_echo_file_without_the_echoseq_import_is_refused(tmp_path: Path) -> None:
    """AC-2: execute-screen.spec.ts with its echoSeq import removed is refused."""
    root = _copy_tree(tmp_path)
    _edit(root, "execute-screen.spec.ts", "import { echoSeq } from './support/echoSeq'\n", "")
    problems = _problems(root)
    assert len(problems) == 1 and problems[0].startswith("frontend/e2e/execute-screen.spec.ts:")


def test_echo_file_that_imports_but_never_stamps_is_refused(tmp_path: Path) -> None:
    """AC-2: an ECHO file that imports echoSeq but never stamps a push is refused."""
    root = _copy_tree(tmp_path)
    _edit(root, "feed-reconnect.spec.ts", ".stamp(", ".restamp(")
    problems = _problems(root)
    assert len(problems) == 1 and problems[0].startswith("frontend/e2e/feed-reconnect.spec.ts:")


def test_forward_that_stopped_forwarding_from_a_real_server_is_refused(tmp_path: Path) -> None:
    """AC-2: a forward file whose server socket is no longer a connectToServer() one is refused."""
    root = _copy_tree(tmp_path)
    _edit(root, "strategy-live.spec.ts", "connectToServer(", "connectElsewhere(")
    problems = _problems(root)
    assert problems and all(p.startswith("frontend/e2e/strategy-live.spec.ts:") for p in problems)


def test_new_file_sending_its_own_live_pushes_is_refused(tmp_path: Path) -> None:
    """AC-2: a new file that sends on the live route with no echoSeq is refused with the remedy."""
    root = _copy_tree(tmp_path)
    _add(root, "new-live.spec.ts", LIVE_ROUTE % "ws.send('{}')")
    problems = _problems(root)
    assert len(problems) == 1 and problems[0].startswith("frontend/e2e/new-live.spec.ts:") and REMEDY in problems[0]


def test_one_unstamped_send_in_an_otherwise_stamped_file_is_refused(tmp_path: Path) -> None:
    """AC-2 (A3): an ECHO file with one extra unstamped send is refused at that send."""
    root = _copy_tree(tmp_path)
    _edit(
        root,
        "execute-screen.spec.ts",
        "const echo = echoSeq()",
        "const echo = echoSeq(); ws.send(JSON.stringify({ legs: [] }))",
    )
    problems = _problems(root)
    assert len(problems) == 1 and problems[0].startswith("frontend/e2e/execute-screen.spec.ts:")


def test_forward_file_injecting_its_own_push_is_refused(tmp_path: Path) -> None:
    """AC-2 (A9): a forward file that also sends its own frame to the page is refused."""
    root = _copy_tree(tmp_path)
    _edit(
        root,
        "strategy-live.spec.ts",
        "ws.onMessage((m) => server.send(m))",
        "ws.onMessage((m) => server.send(m)); ws.send('{}')",
    )
    assert len(_problems(root)) == 1


def test_loopback_of_the_pages_own_message_is_not_a_forward(tmp_path: Path) -> None:
    """AC-2: ws.onMessage((m) => ws.send(m)) sends the page's follow message back to it; it is not a server forward."""
    root = _copy_tree(tmp_path)
    _add(root, "loop.spec.ts", LIVE_ROUTE % "ws.onMessage((m) => ws.send(m))")
    assert len(_problems(root)) == 1


def test_support_helper_that_sends_unstamped_is_refused(tmp_path: Path) -> None:
    """AC-2 (A4): a page file whose handler is imported from a support file that sends unstamped is refused there."""
    root = _copy_tree(tmp_path)
    _add(
        root,
        "support/fakeLive.ts",
        "export const fakeLive = (ws: any) => { ws.onMessage(() => ws.send(JSON.stringify({ legs: [] }))) }\n",
    )
    _add(
        root,
        "helper.spec.ts",
        "import { fakeLive } from './support/fakeLive'\n"
        "await page.routeWebSocket('**/api/strategies/live', fakeLive)\n",
    )
    problems = _problems(root)
    assert len(problems) == 1 and problems[0].startswith("frontend/e2e/support/fakeLive.ts:1:")


def test_support_helper_not_imported_by_a_live_file_is_out_of_scope(tmp_path: Path) -> None:
    """AC-2: a file that sends but is neither a live-socket file nor imported by one is not this guard's business."""
    root = _copy_tree(tmp_path)
    _add(root, "support/other.ts", "export const other = (ws: any) => ws.send('{}')\n")
    assert _problems(root) == []


@pytest.mark.parametrize(
    "pattern",
    ["**/live", "**/api/strategies/*", "**/strategies/**", "**/api/{strategies,other}/live", "/api/strategies/live"],
)
def test_patterns_that_match_the_live_socket_are_in_scope(tmp_path: Path, pattern: str) -> None:
    """AC-2 (A5, A5b): a glob that matches the live socket URL without naming it is in scope; its send fails."""
    root = _copy_tree(tmp_path)
    _add(root, "broad.spec.ts", f"await page.routeWebSocket('{pattern}', (ws) => {{ ws.send('{{}}') }})\n")
    assert len(_problems(root)) == 1


def test_regex_literal_pattern_is_evaluated(tmp_path: Path) -> None:
    """AC-2: a /regex/ pattern that matches the live socket URL is in scope; one that does not is left alone."""
    root = _copy_tree(tmp_path)
    _add(root, "re1.spec.ts", "await page.routeWebSocket(/strategies\\/live/, (ws) => { ws.send('{}') })\n")
    _add(root, "re2.spec.ts", "await page.routeWebSocket(/market\\/chain/, (ws) => { ws.send('{}') })\n")
    problems = _problems(root)
    assert len(problems) == 1 and problems[0].startswith("frontend/e2e/re1.spec.ts:")


def test_patterns_that_cannot_match_the_live_socket_are_out_of_scope(tmp_path: Path) -> None:
    """AC-2: other sockets (chain, indices) send what they like; only a live-matching pattern is scanned."""
    root = _copy_tree(tmp_path)
    _add(root, "chain.spec.ts", "await page.routeWebSocket('**/api/market/chain/live', (ws) => { ws.send('{}') })\n")
    _add(root, "idx.spec.ts", "await page.routeWebSocket('**/api/market/indices/live', (ws) => { ws.send('{}') })\n")
    assert _problems(root) == []


def test_space_before_the_bracket_is_seen(tmp_path: Path) -> None:
    """AC-2 (A7): `routeWebSocket (` with a space is still a route call."""
    root = _copy_tree(tmp_path)
    _add(root, "ws.spec.ts", "await page.routeWebSocket ('**/api/strategies/live', (ws) => { ws.send('{}') })\n")
    assert len(_problems(root)) == 1


def test_stamp_in_a_comment_does_not_count(tmp_path: Path) -> None:
    """AC-2 (A8): `.stamp(` only in a // or /* */ comment, or in a string, does not stamp the send."""
    root = _copy_tree(tmp_path)
    _add(
        root,
        "cmt.spec.ts",
        "import { echoSeq } from './support/echoSeq'\n// echo.stamp( later\n/* echo.stamp( */\n"
        "const echo = echoSeq()\n"
        "await page.routeWebSocket('**/api/strategies/live', (ws) => { ws.send('echo.stamp(') })\n",
    )
    assert len(_problems(root)) == 1


def test_text_in_comments_is_not_code(tmp_path: Path) -> None:
    """AC-2 (A8): a send or a route call that exists only in a comment is neither flagged nor counted."""
    root = _copy_tree(tmp_path)
    _add(
        root,
        "doc.spec.ts",
        "// await page.routeWebSocket(pattern, (ws) => ws.send('{}'))\n"
        "/* ws.send('{}') */\n" + LIVE_ROUTE % "// ws.send('{}')\n  ws.close()",
    )
    assert _problems(root) == []


def test_a_js_file_is_scanned(tmp_path: Path) -> None:
    """AC-2 (A10): a .js file under frontend/e2e is scanned like a .ts one."""
    root = _copy_tree(tmp_path)
    _add(root, "x.spec.js", LIVE_ROUTE % "ws.send('{}')")
    problems = _problems(root)
    assert len(problems) == 1 and problems[0].startswith("frontend/e2e/x.spec.js:")


def test_alias_import_of_echoseq_is_followed(tmp_path: Path) -> None:
    """AC-2: `import { echoSeq as e }` and a namespace import both count as the helper (import source)."""
    root = _copy_tree(tmp_path)
    _add(
        root,
        "alias.spec.ts",
        "import { echoSeq as e } from './support/echoSeq'\n"
        + LIVE_ROUTE % "const s = e(); ws.send(JSON.stringify(s.stamp({})))",
    )
    _add(
        root,
        "ns.spec.ts",
        "import * as E from './support/echoSeq'\n" + LIVE_ROUTE % "const s = E.echoSeq(); ws.send(s.stamp({}))",
    )
    assert _problems(root) == []


def test_same_named_local_function_is_not_the_helper(tmp_path: Path) -> None:
    """AC-2: a local `echoSeq`, or one imported from another module, is not the helper."""
    root = _copy_tree(tmp_path)
    _add(
        root,
        "local.spec.ts",
        "const echoSeq = () => ({ stamp: (x) => x })\n"
        + LIVE_ROUTE % "const s = echoSeq(); ws.send(JSON.stringify(s.stamp({})))",
    )
    _add(
        root,
        "other.spec.ts",
        "import { echoSeq } from './clipping-check'\n"
        + LIVE_ROUTE % "const s = echoSeq(); ws.send(JSON.stringify(s.stamp({})))",
    )
    assert sorted(p.split(":")[0] for p in _problems(root)) == [
        "frontend/e2e/local.spec.ts",
        "frontend/e2e/other.spec.ts",
    ]


def test_a_stamp_followed_by_other_content_is_refused(tmp_path: Path) -> None:
    """AC-2: `JSON.stringify(s.stamp({})) + junk` sends something other than the stamped frame."""
    root = _copy_tree(tmp_path)
    _add(
        root,
        "tail.spec.ts",
        "import { echoSeq } from './support/echoSeq'\n"
        + LIVE_ROUTE % "const s = echoSeq(); ws.send(JSON.stringify(s.stamp({})) + 'x')",
    )
    assert len(_problems(root)) == 1


def test_a_stamp_that_does_not_wrap_the_frame_is_refused(tmp_path: Path) -> None:
    """AC-2: stamping something beside the frame is not stamping the frame."""
    root = _copy_tree(tmp_path)
    _add(
        root,
        "side.spec.ts",
        "import { echoSeq } from './support/echoSeq'\n"
        + LIVE_ROUTE % "const s = echoSeq(); ws.send(JSON.stringify({ a: s.stamp({}) }))",
    )
    assert len(_problems(root)) == 1


@pytest.mark.parametrize(
    "body",
    [
        "ws['send']('{}')",
        'ws["send"]("{}")',
        "ws.send?.('{}')",
        "const { send } = ws; send('{}')",
        "const f = ws.send",
    ],
)
def test_send_the_scan_cannot_attribute_fails_closed(tmp_path: Path, body: str) -> None:
    """AC-2: a send through a computed property, an optional call, a bare call or a bare reference fails closed."""
    root = _copy_tree(tmp_path)
    _add(root, "comp.spec.ts", LIVE_ROUTE % body)
    assert _problems(root) != []


def test_non_literal_route_pattern_fails_closed(tmp_path: Path) -> None:
    """AC-2: a routeWebSocket pattern that is a variable, a ${ template, new RegExp, a call or a sum fails closed."""
    root = _copy_tree(tmp_path)
    _add(root, "var.spec.ts", "const p = '**/api/strategies/live'\nawait page.routeWebSocket(p, (ws) => {})\n")
    _add(root, "tpl.spec.ts", "await page.routeWebSocket(`**/api/${x}/live`, (ws) => {})\n")
    _add(root, "rx.spec.ts", "await page.routeWebSocket(new RegExp('strategies/live'), (ws) => {})\n")
    _add(root, "call.spec.ts", "await page.routeWebSocket(livePattern(), (ws) => {})\n")
    _add(root, "cat.spec.ts", "await page.routeWebSocket('**/api/' + name, (ws) => {})\n")
    prefix = "routeWebSocket pattern is not a literal the scan can translate"
    assert _problems(root) == [
        f"frontend/e2e/call.spec.ts:1: {prefix}",
        f"frontend/e2e/cat.spec.ts:1: {prefix}",
        f"frontend/e2e/rx.spec.ts:1: {prefix}",
        f"frontend/e2e/tpl.spec.ts:1: {prefix}",
        f"frontend/e2e/var.spec.ts:2: {prefix}",
    ]


def test_client_socket_inside_a_route_handler_is_not_a_client_send(tmp_path: Path) -> None:
    """AC-2: `new WebSocket(` outside a route handler is a client; inside the live handler it is refused."""
    root = _copy_tree(tmp_path)
    _add(root, "client.spec.ts", LIVE_ROUTE % "const w = new WebSocket('ws://x'); w.send('{}')")
    assert len(_problems(root)) == 1


def test_silent_live_route_file_may_send_on_another_socket(tmp_path: Path) -> None:
    """AC-2: a file whose live routes are all `() => {}` may send on other sockets; a non-silent one ends it."""
    root = _copy_tree(tmp_path)
    other = "await page.routeWebSocket('**/api/market/chain/live', (ws) => { ws.send('{}') })\n"
    _add(root, "q1.spec.ts", "await page.routeWebSocket('**/api/strategies/live', () => {})\n" + other)
    assert _problems(root) == []
    _add(root, "q2.spec.ts", "await page.routeWebSocket('**/api/strategies/live', (ws) => { ws.close() })\n" + other)
    assert len(_problems(root)) == 1


def test_glob_translation_follows_playwright_rules() -> None:
    """AC-2: `*` stops at `/`, `**` does not, `?` is one character, braces alternate, a bad brace is untranslatable."""
    assert matches_live_socket("glob", "**/api/strategies/live") is True
    assert matches_live_socket("glob", "**/api/strategies/*") is True
    assert matches_live_socket("glob", "*/live") is False
    assert matches_live_socket("glob", "**/api/strategies/liv?") is True
    assert matches_live_socket("glob", "**/api/market/chain/live") is False
    assert matches_live_socket("glob", "**/api/{other,strategies}/live") is True
    assert matches_live_socket("glob", "**/api/{strategies/live") is None
    assert matches_live_socket("regex", "strategies/(") is None
