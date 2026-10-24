"""REQ-133 AC-2 repo guard: a Playwright spec that answers the strategy live socket itself must stamp its pushes.

Finding test-double-encodes-old-assumption (row 24): the page drops a live push that lacks the version it sent, and two
Playwright specs that play the server themselves kept sending pushes without it. This scan reads every `*.ts` file under
`frontend/e2e/` as plain text. A file is IN SCOPE when it contains `routeWebSocket(`; each call's first argument must be
a string literal (anything else fails closed, naming file:line). A call whose literal contains `strategies/live` makes
the file a live-socket fake, and such a file is allowed only as one of three named categories (an allow-list):

- ECHO: imports the shared helper from `./support/echoSeq` or `./echoSeq` and calls `.stamp(`.
- FORWARD: listed in FORWARD_ONLY (with a reason) and still calls `connectToServer(`, so the real replay server's own
  seq echo reaches the page.
- SILENT: contains no `.send(` at all.

Out of scope (stated, not detected): a FORWARD file that also injects its own `.send(` with something other than the
forwarded message; sockets other than the strategy live one; Vitest fakes under frontend/tests (covered by the
builder-brief standing item).
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

pytestmark = pytest.mark.repo_scan

ROOT = Path(__file__).resolve().parent.parent
E2E = Path("frontend") / "e2e"
LIVE_MARK = "strategies/live"
ROUTE_CALL = "routeWebSocket("
HELPER_SOURCES = ("./support/echoSeq", "./echoSeq")
LITERAL_ARG = re.compile(r"""routeWebSocket\(\s*(['"`])([^'"`$\n]*)\1""")
IMPORT_LINE = re.compile(r"""^\s*import\b[^;\n]*\bfrom\s+['"]([^'"]+)['"]""", re.MULTILINE)
REMEDY = "import { echoSeq } from './support/echoSeq' and stamp every push"

ECHO, FORWARD, SILENT = "ECHO", "FORWARD", "SILENT"
FORWARD_ONLY = {
    "frontend/e2e/strategy-live.spec.ts": "forwards the real replay server frames so its seq echo reaches the page",
    "frontend/e2e/live-strategies.spec.ts": "forwards the real replay server frames so its seq echo reaches the page",
}
EXPECTED = {
    "frontend/e2e/execute-screen.spec.ts": ECHO,
    "frontend/e2e/feed-reconnect.spec.ts": ECHO,
    "frontend/e2e/strategy-live.spec.ts": FORWARD,
    "frontend/e2e/live-strategies.spec.ts": FORWARD,
    "frontend/e2e/support/quiet-live.ts": SILENT,
}


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def scan(root: Path) -> tuple[dict[str, str], list[str]]:
    """Return ({live-fake file: category}, problems) for the e2e tree under `root`."""
    found: dict[str, str] = {}
    problems: list[str] = []
    e2e = root / E2E
    if not e2e.is_dir():
        return found, [f"{E2E.as_posix()} is missing"]
    for path in sorted(e2e.rglob("*.ts")):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        if ROUTE_CALL not in text:
            continue
        literals = {m.start(): m.group(2) for m in LITERAL_ARG.finditer(text)}
        live = False
        for m in re.finditer(re.escape(ROUTE_CALL), text):
            if m.start() not in literals:
                problems.append(f"{rel}:{_line_of(text, m.start())}: routeWebSocket pattern is not a string literal")
            elif LIVE_MARK in literals[m.start()]:
                live = True
        if not live:
            continue
        imports = IMPORT_LINE.findall(text)
        if rel in FORWARD_ONLY:
            found[rel] = FORWARD
            if "connectToServer(" not in text:
                problems.append(f"{rel}: pinned as forward-only but no longer calls connectToServer(")
        elif any(src in HELPER_SOURCES for src in imports) and ".stamp(" in text:
            found[rel] = ECHO
        elif ".send(" not in text:
            found[rel] = SILENT
        else:
            problems.append(f"{rel}: answers {LIVE_MARK} itself without echoing the page's seq; {REMEDY}")
    for pinned in FORWARD_ONLY:
        if pinned not in found:
            problems.append(f"{pinned}: pinned as forward-only but it is no longer a strategy live-socket fake")
    return found, problems


def _copy_tree(tmp_path: Path) -> Path:
    shutil.copytree(ROOT / E2E, tmp_path / E2E)
    return tmp_path


def _edit(root: Path, name: str, old: str, new: str) -> None:
    path = root / E2E / name
    text = path.read_text(encoding="utf-8")
    assert text.count(old) >= 1, f"{old!r} not in {name}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_real_tree_every_live_socket_fake_is_allowed() -> None:
    """AC-2: today's e2e tree has no strategy live-socket fake that sends unstamped pushes."""
    _, problems = scan(ROOT)
    assert problems == []


def test_report_lists_the_five_live_socket_files(capsys: pytest.CaptureFixture[str]) -> None:
    """AC-2: the live-socket files today are exactly the five known ones, each in its category."""
    found, _ = scan(ROOT)
    with capsys.disabled():
        for rel, category in found.items():
            print(f"{category:8} {rel}")
    assert found == EXPECTED


def test_forward_only_pins_are_exact_reasoned_and_exist() -> None:
    """AC-2: the pin dict is the two known paths, each with a reason of 4+ words, each file existing."""
    assert set(FORWARD_ONLY) == {"frontend/e2e/strategy-live.spec.ts", "frontend/e2e/live-strategies.spec.ts"}
    for rel, reason in FORWARD_ONLY.items():
        assert len(reason.split()) >= 4, rel
        assert (ROOT / rel).is_file(), rel


def test_echo_spec_without_the_echoseq_import_is_refused(tmp_path: Path) -> None:
    """AC-2: execute-screen.spec.ts with its echoSeq import removed is refused."""
    root = _copy_tree(tmp_path)
    _edit(root, "execute-screen.spec.ts", "import { echoSeq } from './support/echoSeq'\n", "")
    _, problems = scan(root)
    assert len(problems) == 1 and problems[0].startswith("frontend/e2e/execute-screen.spec.ts:")


def test_echo_spec_that_imports_but_never_stamps_is_refused(tmp_path: Path) -> None:
    """AC-2: an ECHO spec that imports echoSeq but never stamps a push is refused."""
    root = _copy_tree(tmp_path)
    _edit(root, "feed-reconnect.spec.ts", ".stamp(", ".restamp(")
    _, problems = scan(root)
    assert len(problems) == 1 and problems[0].startswith("frontend/e2e/feed-reconnect.spec.ts:")


def test_forward_pin_that_stopped_forwarding_is_refused(tmp_path: Path) -> None:
    """AC-2: a pinned forward-only file that no longer calls connectToServer is refused."""
    root = _copy_tree(tmp_path)
    _edit(root, "strategy-live.spec.ts", "connectToServer(", "connectElsewhere(")
    _, problems = scan(root)
    assert len(problems) == 1 and "no longer calls connectToServer(" in problems[0]


def test_forward_pin_that_is_no_longer_a_live_fake_is_refused(tmp_path: Path) -> None:
    """AC-2: a stale pin (the file now routes another socket) is refused, not silently ignored."""
    root = _copy_tree(tmp_path)
    _edit(root, "live-strategies.spec.ts", "**/api/strategies/live", "**/api/other/feed")
    _, problems = scan(root)
    assert problems == [
        "frontend/e2e/live-strategies.spec.ts: pinned as forward-only but it is no longer a strategy live-socket fake"
    ]


def test_new_spec_sending_its_own_live_pushes_is_refused(tmp_path: Path) -> None:
    """AC-2: a new spec that sends on the live route with no echoSeq and no pin is refused."""
    root = _copy_tree(tmp_path)
    (root / E2E / "new-live.spec.ts").write_text(
        "await page.routeWebSocket('**/api/strategies/live', (ws) => {\n  ws.send('{}')\n})\n", encoding="utf-8"
    )
    _, problems = scan(root)
    assert len(problems) == 1 and problems[0].startswith("frontend/e2e/new-live.spec.ts:")
    assert REMEDY in problems[0]


def test_non_literal_route_pattern_fails_closed(tmp_path: Path) -> None:
    """AC-2: a routeWebSocket call whose pattern is a variable or a template with ${ is refused with file:line."""
    root = _copy_tree(tmp_path)
    (root / E2E / "var.spec.ts").write_text(
        "const p = '**/api/strategies/live'\nawait page.routeWebSocket(p, (ws) => {})\n", encoding="utf-8"
    )
    (root / E2E / "tpl.spec.ts").write_text(
        "await page.routeWebSocket(`**/api/${x}/live`, (ws) => {})\n", encoding="utf-8"
    )
    _, problems = scan(root)
    assert sorted(problems) == [
        "frontend/e2e/tpl.spec.ts:1: routeWebSocket pattern is not a string literal",
        "frontend/e2e/var.spec.ts:2: routeWebSocket pattern is not a string literal",
    ]
