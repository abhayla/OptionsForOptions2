"""Every e2e stand-in of the strategy socket echoes the server's seq (finding e2e-stand-in-drifts-from-server).

Run 40083846807: the page began to drop a strategy-socket push whose `seq` is not the version it sent; two Playwright
specs that played the server themselves sent no seq and only the CI Playwright job noticed. frontend/e2e/support/echoSeq.ts
is the one place a spec copies the seq. This test reads, with plain text scanning (no node), every
`routeWebSocket(<url>, <handler>)` under frontend/e2e and asserts the handlers of the STRATEGY socket are safe.

The strategy socket URL is read from `export const LIVE_PATH = '...'` in frontend/src/composables/useStrategyLive.js,
the path the real client opens (never typed here).

Per routeWebSocket call, answer states:
- URL is a plain string literal that does not end with LIVE_PATH: another socket (chain, indices); not this test's concern.
- URL is not a plain literal (template with ${}, variable, concatenation): FAIL CLOSED, the socket cannot be identified.
- strategy socket, handler calls connectToServer(): a pass-through to the real server, which echoes seq itself; allowed.
- strategy socket, handler never sends (`.send(` absent): a silent socket (support/quiet-live.ts); allowed.
- strategy socket, handler sends AND uses echoSeq() with .stamp(...) AND the file imports echoSeq from support/echoSeq: allowed.
- strategy socket, handler sends but the helper is missing (or imported from elsewhere): FAIL.
LIVE_PATH not found / not a literal, or no e2e dir: FAIL CLOSED.

Measured on origin/main b7670e10 (step 1): 8 routeWebSocket calls; strategy socket: execute-screen and feed-reconnect
(fakes, both use echoSeq), live-strategies and strategy-live (connectToServer pass-through), support/quiet-live (silent);
other sockets: chain-selection (fake of /api/market/chain/live, not versioned in useChainLive.js), home and index-view
(pass-through of /api/market/indices/live). Fakes of the strategy socket without echoSeq: 0.

Known blind spots: a socket opened by a page-side `new WebSocket` override (addInitScript) instead of routeWebSocket; a
pass-through handler that rewrites the server's pushes; a handler that imports echoSeq but never stamps the push it sends
(only the presence of `.stamp(` in the handler is checked); a `//` after whitespace inside a string literal; a `//` inside a string literal that follows whitespace; a URL passed through a variable (fails closed, by design);
parentheses inside a regex literal in a handler (the balance scan skips quoted strings only). Presence check, not behaviour.
"""

import os
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan  # reads every frontend/e2e spec

ROOT = Path(os.environ.get("OFO_E2E_CHECK_ROOT") or Path(__file__).resolve().parents[1])
LIVE_FILE = "frontend/src/composables/useStrategyLive.js"
E2E_DIR = "frontend/e2e"
HELPER = "echoSeq.ts"
IMPORT_RE = re.compile(r"""import\s*\{[^}]*\bechoSeq\b[^}]*\}\s*from\s*['"](?:\./|\.\./)(?:support/)?echoSeq['"]""")


def strategy_path(source: str) -> str:
    m = re.search(r"""export\s+const\s+LIVE_PATH\s*=\s*(['"])([^'"`$]+)\1""", source)
    if not m:
        pytest.fail(f"LIVE_PATH is not a plain string literal in {LIVE_FILE}; cannot tell which socket is the strategy one")
    return m.group(2)


def _skip_string(text: str, i: int) -> int:
    q = text[i]
    i += 1
    while i < len(text) and text[i] != q:
        i += 2 if text[i] == "\\" else 1
    return i


def _call_args(text: str, open_idx: int) -> str:
    """The text between the parenthesis at open_idx and its match (quoted strings skipped). Fails closed if unbalanced."""
    depth = 0
    i = open_idx
    while i < len(text):
        c = text[i]
        if c in "'\"`":
            i = _skip_string(text, i)
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i]
        i += 1
    pytest.fail("unbalanced parentheses after routeWebSocket(")


def _strip_comments(text: str) -> str:
    """Blank `// ...` line comments and `/* */` blocks (an apostrophe in a comment would break the string skip)."""
    text = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
    return re.sub(r"(?m)(^|\s)//.*$", lambda m: m.group(1), text)


def socket_calls(text: str) -> list[tuple[str | None, str]]:
    """(literal URL or None when it is not a plain literal, whole argument text) for each routeWebSocket( call."""
    out = []
    text = _strip_comments(text)
    for m in re.finditer(r"\brouteWebSocket\s*\(", text):
        args = _call_args(text, m.end() - 1)
        lit = re.match(r"""\s*(['"`])([^'"`]*)\1\s*,""", args)
        url = lit.group(2) if lit and "${" not in lit.group(2) else None
        out.append((url, args))
    return out


def judge(rel: str, text: str, live_path: str) -> list[str]:
    """Problems with the strategy-socket stand-ins in one file (empty list = fine)."""
    problems = []
    code = _strip_comments(text)
    for url, args in socket_calls(text):
        if url is None:
            problems.append(f"{rel}: routeWebSocket URL is not a plain string literal; cannot tell if it is the strategy socket")
            continue
        if not url.endswith(live_path):
            continue
        if "connectToServer(" in args or ".send(" not in args:
            continue  # pass-through to the real server, or a silent socket
        if not (re.search(r"\bechoSeq\s*\(", args) and ".stamp(" in args and IMPORT_RE.search(code)):
            problems.append(f"{rel}: fakes the strategy socket {url} and sends pushes without the shared echoSeq helper")
    return problems


def _specs() -> list[Path]:
    d = ROOT / E2E_DIR
    if not d.is_dir():
        pytest.fail(f"cannot read {E2E_DIR} (under {ROOT})")
    files = sorted(p for p in d.rglob("*.ts") if p.name != HELPER)
    if not files:
        pytest.fail(f"no .ts files under {E2E_DIR}")
    return files


def _live_path() -> str:
    p = ROOT / LIVE_FILE
    if not p.is_file():
        pytest.fail(f"cannot read {LIVE_FILE} (under {ROOT})")
    return strategy_path(p.read_text(encoding="utf-8"))


def test_every_strategy_socket_stand_in_uses_the_shared_seq_helper():
    live_path = _live_path()
    assert live_path == "/api/strategies/live", live_path
    problems = []
    seen = 0
    for p in _specs():
        text = p.read_text(encoding="utf-8")
        seen += len(socket_calls(text))
        problems += judge(p.relative_to(ROOT).as_posix(), text, live_path)
    assert seen >= 1, "found no routeWebSocket call at all: the scan itself is broken"
    assert not problems, "\n".join(problems)


# parser answer states, on synthetic source
SRC_FAKE = "import { x } from './y'\nawait page.routeWebSocket('**/api/strategies/live', (ws) => { ws.onMessage(() => ws.send('{}')) })\n"
SRC_HELPER = (
    "import { echoSeq } from './support/echoSeq'\n"
    "await page.routeWebSocket('**/api/strategies/live', (ws) => {\n  const echo = echoSeq()\n"
    "  ws.onMessage((m) => { echo.remember(m); ws.send(JSON.stringify(echo.stamp({ a: 1 }))) })\n})\n"
)


def test_fake_without_helper_is_red_and_with_helper_is_green():
    assert judge("f.ts", SRC_FAKE, "/api/strategies/live")
    assert judge("f.ts", SRC_HELPER, "/api/strategies/live") == []
    # helper called but not imported from the shared file
    assert judge("f.ts", SRC_HELPER.replace("./support/echoSeq", "./mine"), "/api/strategies/live")
    # helper imported but never stamps
    assert judge("f.ts", SRC_HELPER.replace("echo.stamp({ a: 1 })", "{ a: 1 }"), "/api/strategies/live")


def test_pass_through_silent_and_other_sockets_are_allowed():
    through = "page.routeWebSocket('**/api/strategies/live', (ws) => { const s = ws.connectToServer(); ws.onMessage((m) => s.send(m)) })"
    silent = "page.routeWebSocket('**/api/strategies/live', () => {})"
    other = "page.routeWebSocket('**/api/market/chain/live', (ws) => { ws.send('{}') })"
    for src in (through, silent, other):
        assert judge("f.ts", src, "/api/strategies/live") == []


def test_computed_url_fails_closed():
    for src in (
        "page.routeWebSocket(URL, (ws) => { ws.send('{}') })",
        "page.routeWebSocket(`${base}/api/strategies/live`, (ws) => { ws.send('{}') })",
        "page.routeWebSocket('**' + PATH, (ws) => { ws.send('{}') })",
    ):
        assert judge("f.ts", src, "/api/strategies/live"), src


def test_live_path_unreadable_fails_closed():
    assert strategy_path("export const LIVE_PATH = '/api/strategies/live'\n") == "/api/strategies/live"
    for bad in ("const LIVE_PATH = '/x'\n", "export const LIVE_PATH = `/api/${x}`\n", "export const LIVE_PATH = BASE + '/x'\n"):
        with pytest.raises(pytest.fail.Exception):
            strategy_path(bad)
    with pytest.raises(pytest.fail.Exception):
        _call_args("routeWebSocket(('a'", len("routeWebSocket"))
