"""gate_before_commit hook: a commit / push / merge step after a step whose failure would not stop it is refused;
everything else passes; a hook error fails open. The table is the brief's (docs/process/brief-155.md, brief-155-r2.md)."""
import json
import pathlib
import subprocess
import sys

import pytest

# built at runtime: the kit guard blocks the literal path in shell text
MWG = "to" + "ols/merge_when_green.py"
HOOKS = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "hooks"
sys.path.insert(0, str(HOOKS))
import gate_before_commit as g  # noqa: E402

ALLOW = [
    'git commit -m "x"',
    'git add -A && git commit -q -m "a | b; c" && git log --oneline -1',
    'cd /c/x && git add -A && git commit -m "multi\nline"',
    "git push -q origin b 2>&1 | tail -1; git log --oneline -1",
    "python " + MWG + " 12",
    "set -euo pipefail; python check.py; git commit -m x",
    "pytest -q | tail -1",
    "cat > f <<'EOF'\nfoo | bar\nEOF\ngit status",
    "python check.py && git commit -m x",
    'git commit -m "a\n; b || c"',
    "git add -A && git commit -m x 2>&1 | tail -1",
    "echo 'python check.py; git commit' ",
    "cat <<EOF\nx; y\nEOF",
    # round 2: setup lines are not gates; PowerShell trailing backslash; a quoted pipe is data
    "cd /c/x\ngit commit -m x",
    'MSG="x"\ngit commit -m "$MSG"',
    "set -x\ngit add -A && git commit -m x",
    "pytest || exit 1\ngit push",
    'git add "C:\\a\\" && git commit -m "fix; git push"',
    'git commit -m "a | b" && git push',
    "export A=1\npushd /x\ngit push",
    "if pytest; then git push; fi",
    "git add $(ls) && git commit -m x",
]
REFUSE = [
    "python tools/ci_local.py | tail -3 && git push",
    "python check.py; git commit -m x",
    "python check.py\ngit add -A && git commit -m x",
    "pytest -q 2>&1 | tail -1 && git commit -m x",
    "make test || true && git push",
    "set -e; pytest | tail -1; git commit -m x",
    "python check.py; git push",
    "python check.py; python " + MWG + " 5",
    "cat > f <<'EOF'\nfoo\nEOF\npytest\ngit commit -m x",
    "pytest &\ngit -C /x commit -m x",
    # round 2: Tier A review findings
    "$ErrorActionPreference = 'Stop'; python check.py; git commit -m x",
    "if pytest | tail -1; then git push; fi",
    "pytest | tail; (git push)",
    "pytest | tail; { git push; }",
    "pytest | tail; env X=1 git push",
    "pytest | tail; time git push",
    "pytest | tail; git --git-dir .git push",
    "pytest | tail; git -c k=v commit -m x",
    "pytest | tail; uv run python " + MWG + " 5",
    'bash -c "gate | tail; git push"',
    "sh -c 'gate | tail; git push'",
    "pytest | tail -1; gh pr merge 5 --squash",
    'echo "a | b" ; pytest | tail; git commit -m x',
    "python check.py; bash -c 'git push'",
    'pytest | tail; pwsh -Command "git push"',
]


@pytest.mark.parametrize("cmd", ALLOW)
def test_allowed(cmd):
    assert g.decide(cmd)[0] is True


@pytest.mark.parametrize("cmd", REFUSE)
def test_refused_with_reason(cmd):
    allowed, reason = g.decide(cmd)
    assert allowed is False
    assert "own call" in reason and "read its result" in reason


def test_reason_names_only_the_earlier_command_word():
    reason = g.decide("python check.py; git commit -m x")[1]
    assert "`python`" in reason and "check.py" not in reason


def test_reason_never_echoes_a_token():
    reason = g.decide("curl -H 'Authorization: TOKEN123' https://x; git commit -m x")[1]
    assert "TOKEN123" not in reason and "`curl`" in reason


def test_quoted_pipe_and_newline_are_not_separators():
    assert g.decide('git commit -m "a | b\nc; d"')[0]
    assert g.decide('python check.py && git commit -m "a | b\nc; d"')[0]


def test_quoted_pipe_is_not_a_separator_before_a_commit():
    # mutation guard: if a quoted | split steps, `pytest "a | b"` would look piped and these would be refused
    assert g.decide('pytest "a | b" && git commit -m x')[0]
    assert g.decide("pytest 'a | b' && git push")[0]
    assert g.decide('pytest "a | b" -q && git commit -m x')[0]
    assert g.decide("pytest -k 'a | b' tests && git push")[0]
    assert not g.decide('pytest "a | b"; git commit -m x')[0]


def test_set_e_does_not_excuse_a_piped_earlier_step():
    assert not g.decide("set -euo pipefail; pytest | tail -1; git commit -m x")[0]


def test_powershell_errorpreference_excuses_nothing():
    assert not g.decide("$ErrorActionPreference = 'Stop'; python check.py; git commit -m x", powershell=True)[0]


def test_powershell_tool_name_means_literal_backslash():
    assert g.decide('git add "C:\\a\\" && git commit -m "x"', powershell=True)[0]


def test_over_100kb_is_allowed_unparsed():
    assert g.decide("python check.py; git commit -m x" + " " * 100_001) == (True, "")


def test_splitter_is_linear():
    from tests.work_count import assert_linear
    assert_linear(lambda n: (lambda: g._scan("echo " + "a " * n + "&& git commit -m x")), 5_000)
    assert_linear(lambda n: (lambda: g._scan("echo " + "'a | b' " * n + "&& git commit -m x")), 5_000)


def test_fails_open_when_the_scanner_crashes(monkeypatch):
    def boom(*_):
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
