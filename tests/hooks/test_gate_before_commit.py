"""gate_before_commit hook: a commit / push / merge step after a step whose failure would not stop it is refused;
everything else passes; a hook error fails open. The table is the brief's (docs/process/brief-155.md)."""
import json
import pathlib
import subprocess
import sys

import pytest

HOOKS = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "hooks"
sys.path.insert(0, str(HOOKS))
import gate_before_commit as g  # noqa: E402

ALLOW = [
    'git commit -m "x"',
    'git add -A && git commit -q -m "a | b; c" && git log --oneline -1',
    'cd /c/x && git add -A && git commit -m "multi\nline"',
    "git push -q origin b 2>&1 | tail -1; git log --oneline -1",
    "python tools/merge_when_green.py 12",
    "set -euo pipefail; python check.py; git commit -m x",
    "pytest -q | tail -1",
    "cat > f <<'EOF'\nfoo | bar\nEOF\ngit status",
    "python check.py && git commit -m x",
    "$ErrorActionPreference = 'Stop'; python check.py; git commit -m x",
    'git commit -m "a\n; b || c"',
    "git add -A && git commit -m x 2>&1 | tail -1",
    "echo 'python check.py; git commit' ",
    "cat <<EOF\nx; y\nEOF",
]
REFUSE = [
    "python tools/ci_local.py | tail -3 && git push",
    "python check.py; git commit -m x",
    "python check.py\ngit add -A && git commit -m x",
    "pytest -q 2>&1 | tail -1 && git commit -m x",
    "make test || true && git push",
    "set -e; pytest | tail -1; git commit -m x",
    "python check.py; git push",
    "python check.py; python tools/merge_when_green.py 5",
    "cat > f <<'EOF'\nfoo\nEOF\npytest\ngit commit -m x",
    "pytest &\ngit -C /x commit -m x",
]


@pytest.mark.parametrize("cmd", ALLOW)
def test_allowed(cmd):
    assert g.decide(cmd)[0] is True


@pytest.mark.parametrize("cmd", REFUSE)
def test_refused_with_reason(cmd):
    allowed, reason = g.decide(cmd)
    assert allowed is False
    assert "own call" in reason and "read its result" in reason


def test_reason_names_the_earlier_step():
    assert "python check.py" in g.decide("python check.py; git commit -m x")[1]


def test_quoted_pipe_and_newline_are_not_separators():
    assert g.decide('git commit -m "a | b\nc; d"')[0]
    assert g.decide('python check.py && git commit -m "a | b\nc; d"')[0]


def test_set_e_does_not_excuse_a_piped_earlier_step():
    assert not g.decide("set -euo pipefail; pytest | tail -1; git commit -m x")[0]


def test_fails_open_when_the_scanner_crashes(monkeypatch):
    def boom(_):
        raise RuntimeError("bug")
    monkeypatch.setattr(g, "_scan", boom)
    assert g.decide("python check.py; git commit -m x") == (True, "")


@pytest.mark.parametrize("raw", ["", "not json", "[]", '{"tool_input": 5}', '{"tool_input": {"command": 7}}'])
def test_main_fails_open_on_odd_input(raw, monkeypatch, capsys):
    import io
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    assert g.main() == 0
    assert capsys.readouterr().err == ""


def _run(cmd):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    return subprocess.run([sys.executable, str(HOOKS / "gate_before_commit.py")], input=payload,
                          capture_output=True, text=True)


def test_stdin_round_trip_allow():
    r = _run("git add -A && git commit -m x")
    assert r.returncode == 0 and r.stderr == ""


def test_stdin_round_trip_refuse():
    r = _run("pytest | tail -1 && git push")
    assert r.returncode == 2 and "pytest" in r.stderr
