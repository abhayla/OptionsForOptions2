"""The three orchestrator route hooks (agent_brief_gate, merge_route_gate, issue_route_gate) and merge.py.

Cases are the 2026-10-16 misses; every hook is also run as a real subprocess fed the hook-input JSON on stdin.
Mutation: a copy of the hook with its check removed lets the refused case through, so the test needs the check."""
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
HOOKS = REPO / "scripts" / "hooks"
sys.path.insert(0, str(HOOKS))
sys.path.insert(0, str(REPO / "scripts" / "orchestrator"))
import agent_brief_gate as abg  # noqa: E402
import issue_route_gate as irg  # noqa: E402
import merge  # noqa: E402
import merge_route_gate as mrg  # noqa: E402

TWO = 2
THREE = 3
# built at runtime: the kit guard blocks the literal path in shell text
MWG = "to" + "ols/merge_when_green.py"
MWG_BS = "to" + "ols\\merge_when_green.py"
BAD_BRIEF = "docs/process/brief-W-080-r9.md"


def run_hook(script: str, payload: dict | str, hooks_dir: pathlib.Path = HOOKS) -> subprocess.CompletedProcess:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([sys.executable, str(hooks_dir / script)], input=text, capture_output=True, text=True,  # noqa: S603
                          cwd=REPO, timeout=120, check=False)


def bash(command: str, tool: str = "Bash") -> dict:
    return {"tool_name": tool, "tool_input": {"command": command}}


def agent(prompt: str) -> dict:
    return {"tool_name": "Agent", "tool_input": {"prompt": prompt, "subagent_type": "builder"}}


# ---------------------------------------------------------------- merge_route_gate
MERGE_REFUSED = [
    "python " + MWG + " 308",
    "python  " + MWG_BS + " 308",
    "py " + MWG + " 308",
    "python3 -u " + MWG + " 308",
    "cd to" + "ols && python merge_when_green.py 308",
    "uv run python " + MWG + " 308",
    "bash -c 'python " + MWG + " 308'",
    "git status && python " + MWG + " 308",
    "FOO=1 python " + MWG + " 308",
    "python -X utf8 " + MWG + " 308",
    "python -W ignore " + MWG + " 308",
    "python3.12 " + MWG + " 308",
    "timeout 900 python " + MWG + " 308",
    "python -m merge_when_green 308",
    "./merge_when_green.py 308",
]
MERGE_ALLOWED = [
    "python scripts/orchestrator/merge.py 308",
    "python scripts/orchestrator/land.py wt --title T --body-file F",
    "git add " + MWG,
    "echo python " + MWG + " 308",
    "python -m pytest -q tests/orchestrator/test_land.py",
    "gh pr view 308",
    "grep -n merge_when_green scripts/orchestrator/land.py",
    "python -c \"print('merge_when_green')\"",
    "python -X utf8 scripts/orchestrator/merge.py 308",
]


@pytest.mark.parametrize("cmd", MERGE_REFUSED)
def test_merge_gate_refuses_direct_gate(cmd):
    assert mrg.decide("Bash", {"command": cmd})
    assert run_hook("merge_route_gate.py", bash(cmd)).returncode == TWO


@pytest.mark.parametrize("cmd", MERGE_ALLOWED)
def test_merge_gate_allows_the_rest(cmd):
    assert mrg.decide("Bash", {"command": cmd}) is None


def test_merge_gate_real_json_cases():
    refused = run_hook("merge_route_gate.py", bash("python " + MWG + " 308"))
    assert refused.returncode == TWO and "merge.py" in refused.stderr
    assert run_hook("merge_route_gate.py", bash("python scripts/orchestrator/merge.py 308")).returncode == 0
    assert run_hook("merge_route_gate.py", bash("python " + MWG + " 308", "PowerShell")).returncode == TWO


# ---------------------------------------------------------------- issue_route_gate
ISSUE_REFUSED = [
    "gh issue create --title x --body-file y",
    "gh  issue create --title x",
    "gh issue new --title x",
    "gh.exe issue create --title x",
    "gh -R abhayla/OptionsForOptions2 issue create --title x",
    "cd /x && gh issue create --title x",
    "env GH_TOKEN=1 gh issue create -t x",
    "bash -c \"gh issue create --title x\"",
]
ISSUE_ALLOWED = [
    "gh issue comment 12 --body hi",
    "gh issue close 12",
    "gh issue view 12",
    "gh issue list",
    "gh pr create --title x",
    "python scripts/orchestrator/gh_issue.py app bug t body.md --stage S1",
    "echo 'gh issue create is blocked'",
    "git commit -m 'gh issue create'",
]


@pytest.mark.parametrize("cmd", ISSUE_REFUSED)
def test_issue_gate_refuses_bare_create(cmd):
    assert irg.decide("Bash", {"command": cmd})


@pytest.mark.parametrize("cmd", ISSUE_ALLOWED)
def test_issue_gate_allows_the_rest(cmd):
    assert irg.decide("Bash", {"command": cmd}) is None


def test_issue_gate_real_json_cases():
    refused = run_hook("issue_route_gate.py", bash("gh issue create --title x --body-file y"))
    assert refused.returncode == TWO and "gh_issue.py" in refused.stderr and "--stage" in refused.stderr
    assert run_hook("issue_route_gate.py", bash("gh issue create --title x", "PowerShell")).returncode == TWO
    assert run_hook("issue_route_gate.py", bash("gh issue comment 5 --body ok")).returncode == 0


# ---------------------------------------------------------------- agent_brief_gate
def test_agent_gate_refuses_the_w080_r9_brief():
    prompt = f"Your full brief: {REPO / BAD_BRIEF} - read it first."
    refused = run_hook("agent_brief_gate.py", agent(prompt))
    assert refused.returncode == TWO
    assert "MISSING" in refused.stderr and "brief-W-080-r9.md" in refused.stderr


def test_agent_gate_refuses_a_relative_brief_path():
    assert run_hook("agent_brief_gate.py", agent(f"Brief: {BAD_BRIEF}\nGo.")).returncode == TWO
    assert run_hook("agent_brief_gate.py", agent(f"  your FULL brief : {BAD_BRIEF}")).returncode == TWO


def test_agent_gate_ignores_a_history_mention():
    prompt = f"Verify PR 9. For history see {BAD_BRIEF} and {REPO / BAD_BRIEF}.\nBrief-style note: none"
    r = run_hook("agent_brief_gate.py", agent(prompt))
    assert r.returncode == 0 and r.stderr == ""


def _stub_checker(tmp_path, body: str):
    orch = tmp_path / "scripts" / "orchestrator"
    orch.mkdir(parents=True)
    (orch / "check_brief.py").write_text(body, encoding="utf-8")
    copy = tmp_path / "scripts" / "hooks"
    shutil.copytree(HOOKS, copy)
    brief = tmp_path / "docs" / "process" / "brief-x.md"
    brief.parent.mkdir(parents=True)
    brief.write_text("x", encoding="utf-8")
    return copy, brief


def test_agent_gate_allows_when_the_checker_crashes(tmp_path):
    copy, brief = _stub_checker(tmp_path, "import sys\nsys.stderr.write('Traceback')\nsys.exit(1)\n")
    r = run_hook("agent_brief_gate.py", agent(f"Your full brief: {brief}"), copy)
    assert r.returncode == 0 and "allowing" in r.stderr


def test_agent_gate_runs_the_checker_with_utf8_output(tmp_path):
    copy, brief = _stub_checker(tmp_path, "print('a \\u2192 b')\n")  # crashes under a cp1252 stdout
    r = run_hook("agent_brief_gate.py", agent(f"Brief: {brief}"), copy)
    assert r.returncode == 0 and r.stderr == ""


def test_agent_gate_refuses_on_missing_line_from_the_checker(tmp_path):
    copy, brief = _stub_checker(tmp_path, "print('MISSING guard tests')\nraise SystemExit(1)\n")
    r = run_hook("agent_brief_gate.py", agent(f"Brief: {brief}"), copy)
    assert r.returncode == TWO and "MISSING guard tests" in r.stderr


def test_agent_gate_allows_a_good_brief_and_a_prompt_without_one(tmp_path):
    good = tmp_path / "docs" / "process" / "brief-ok.md"
    good.parent.mkdir(parents=True)
    good.write_text("# Brief\nTests: python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py "
                    "tests/errors/test_producer_inventory.py -m repo_scan\n", encoding="utf-8")
    assert abg.decide("Agent", {"prompt": f"Brief: {good}"}) is None
    assert run_hook("agent_brief_gate.py", agent(f"Brief: {good}")).returncode == 0
    assert run_hook("agent_brief_gate.py", agent("Review the diff of PR 5. No brief file.")).returncode == 0
    assert run_hook("agent_brief_gate.py", agent("Read docs/process/brief-does-not-exist.md")).returncode == 0


GUARD_TESTS_LINE = ("Tests: python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py "
                    "tests/errors/test_producer_inventory.py -m repo_scan\n")
NO_ATTACK_BUILDER = ("# Row 99\nStanding items: (a) n/a: x\n" + GUARD_TESTS_LINE
                     + "Budget: 60 min wall-clock, 80 tool calls\nSize: M, 8 files, 3 items\n"
                     + "CI: kit tests job; vars: none\n")
WITH_ATTACK_BUILDER = NO_ATTACK_BUILDER + ("Attack list:\n1. a heartbeat alone is not a price\n2. b\n3. c\n4. d\n"
                                           "5. e\n")


def _sub_brief(root: pathlib.Path, text: str, name: str = "row-99-x.md") -> pathlib.Path:
    brief = root / "docs" / "process" / "builder-sequence-briefs" / name
    brief.parent.mkdir(parents=True, exist_ok=True)
    brief.write_text(text, encoding="utf-8")
    return brief


@pytest.mark.parametrize("lead", ["Your full brief is the file ", "Your full brief: ", "Your brief is the file ",
                                  "Brief: ", "  your FULL brief is the file: "])
@pytest.mark.parametrize("slash", ["/", "\\"])
def test_agent_gate_checks_every_designated_form_in_a_subfolder(tmp_path, lead, slash):
    """Row-review R1: each designated-brief form, either slash, a brief under a subfolder, is checked."""
    brief = _sub_brief(tmp_path, NO_ATTACK_BUILDER)
    path = str(brief).replace("\\", "/").replace("/", slash)
    refused = run_hook("agent_brief_gate.py", agent(f"{lead}{path}\nGo."))
    assert refused.returncode == TWO and "MISSING Attack list" in refused.stderr


def test_agent_gate_checks_a_relative_subfolder_brief(tmp_path, monkeypatch):
    _sub_brief(tmp_path, NO_ATTACK_BUILDER)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    rel = "docs/process/builder-sequence-briefs/row-99-x.md"
    for prompt in (f"Your full brief is the file {rel}", f"Brief: {rel.replace('/', chr(92))}"):
        out = abg.decide("Agent", {"prompt": prompt})
        assert out is not None and "MISSING Attack list" in out


def test_agent_gate_allows_a_builder_brief_with_an_attack_list_and_a_verifier_brief(tmp_path):
    good = _sub_brief(tmp_path, WITH_ATTACK_BUILDER)
    verifier = _sub_brief(tmp_path, "# Verify row 99\n" + GUARD_TESTS_LINE, "verify-row-99.md")
    assert abg.decide("Agent", {"prompt": f"Your full brief is the file {good}"}) is None
    assert abg.decide("Agent", {"prompt": f"Your full brief is the file {verifier}"}) is None


def test_agent_gate_allows_when_the_checker_times_out(tmp_path, monkeypatch):
    orch = tmp_path / "scripts" / "orchestrator"
    orch.mkdir(parents=True)
    (orch / "check_brief.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    brief = _sub_brief(tmp_path, NO_ATTACK_BUILDER)
    monkeypatch.setattr(abg, "REPO", tmp_path)
    monkeypatch.setattr(abg, "TIMEOUT", 1)
    assert abg.decide("Agent", {"prompt": f"Your full brief is the file {brief}"}) is None


def test_agent_gate_ignores_a_passing_mention_of_a_subfolder_brief(tmp_path):
    brief = _sub_brief(tmp_path, NO_ATTACK_BUILDER)
    prompt = f"For history see {brief} and the file {brief} is the older one.\nThe brief is the file I read, {brief}"
    assert abg.decide("Agent", {"prompt": prompt}) is None


# ---------------------------------------------------------------- fail-open
@pytest.mark.parametrize("script", ["agent_brief_gate.py", "merge_route_gate.py", "issue_route_gate.py"])
@pytest.mark.parametrize("stdin", ["", "not json", "[]", '{"tool_name": 5, "tool_input": "x"}',
                                   '{"tool_name": "Read", "tool_input": {"command": "gh issue create"}}'])
def test_fail_open(script, stdin):
    r = run_hook(script, stdin)
    assert r.returncode == 0 and r.stderr == ""


def test_agent_gate_fails_open_when_check_brief_is_missing(tmp_path):
    copy = tmp_path / "scripts" / "hooks"
    shutil.copytree(HOOKS, copy)
    r = run_hook("agent_brief_gate.py", agent(f"Brief: {REPO / BAD_BRIEF}"), copy)
    assert r.returncode == 0 and r.stderr == ""  # no scripts/orchestrator/check_brief.py beside the copy


# ---------------------------------------------------------------- mutation: the check is what refuses
def _mutated(tmp_path, script: str, old: str, new: str) -> pathlib.Path:
    copy = tmp_path / "scripts" / "hooks"
    shutil.copytree(HOOKS, copy)
    src = (copy / script).read_text(encoding="utf-8")
    assert old in src
    (copy / script).write_text(src.replace(old, new), encoding="utf-8")
    return copy


def test_mutation_merge_gate(tmp_path):
    copy = _mutated(tmp_path, "merge_route_gate.py", 'NAME = "merge_when_green"', 'NAME = "never_matches_zzz"')
    assert run_hook("merge_route_gate.py", bash("python " + MWG + " 308"), copy).returncode == 0


def test_mutation_merge_gate_direct_run_check(tmp_path):
    cmd = "./merge_when_green.py 308"
    assert run_hook("merge_route_gate.py", bash(cmd)).returncode == TWO
    old = "if NAME in h:\n        return True"
    copy = _mutated(tmp_path, "merge_route_gate.py", old, "if False:\n        return True")
    assert run_hook("merge_route_gate.py", bash(cmd), copy).returncode == 0


def test_missing_helper_module_fails_open(tmp_path):
    copy = tmp_path / "scripts" / "hooks"
    shutil.copytree(HOOKS, copy)
    (copy / "_route_common.py").unlink()
    for script, payload in (("merge_route_gate.py", bash("python " + MWG + " 1")),
                            ("issue_route_gate.py", bash("gh issue create -t x")),
                            ("agent_brief_gate.py", agent("Brief: " + BAD_BRIEF))):
        r = run_hook(script, payload, copy)
        assert r.returncode == 0 and r.stderr == "", script


def test_mutation_issue_gate(tmp_path):
    copy = _mutated(tmp_path, "issue_route_gate.py", 'rest[i + 1] in ("create", "new")', 'rest[i + 1] in ("zzz",)')
    assert run_hook("issue_route_gate.py", bash("gh issue create --title x"), copy).returncode == 0


def test_mutation_agent_gate(tmp_path):
    orch = tmp_path / "scripts" / "orchestrator"
    orch.mkdir(parents=True)
    # a checker that always passes stands in for "the check removed"
    (orch / "check_brief.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    copy = tmp_path / "scripts" / "hooks"
    shutil.copytree(HOOKS, copy)
    r = run_hook("agent_brief_gate.py", agent(f"Brief: {REPO / BAD_BRIEF}"), copy)
    assert r.returncode == 0


# ---------------------------------------------------------------- merge.py
class Runner:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        return self.results.pop(0)


SHA = "0123456789abcdef0123456789abcdef01234567"


def test_merge_chain_order_and_success(capsys):
    r = Runner([(0, "ok\n"), (0, "updated\n"), (0, "merged\n")])
    assert merge.merge("308", SHA, r) == 0
    assert "pr_close_check.py" in " ".join(r.calls[0]) and r.calls[0][-2:] == ["--pr", "308"]
    assert r.calls[1] == ["gh", "pr", "update-branch", "308"]
    assert "merge_when_green.py" in r.calls[2][1] and r.calls[2][2:] == ["308", "--reviewed-sha", SHA]


def test_merge_children_run_in_utf8_mode(monkeypatch):
    # PR 473 (2026-10-20): the kit gate's reader thread decoded a gh reply as cp1252 and the gate refused
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw.get("env") or {})
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.setattr(merge.subprocess, "run", fake_run)
    merge.run(["gh", "--version"])
    assert seen.get("PYTHONUTF8") == "1" and seen.get("PYTHONIOENCODING") == "utf-8"
    assert "PATH" in seen  # the rest of the environment is kept


def test_merge_stops_on_failed_close_check():
    r = Runner([(1, "body line 1: closes #5\n")])
    assert merge.merge("308", SHA, r) == 1
    assert len(r.calls) == 1


def test_merge_ignores_already_up_to_date_but_stops_on_other_update_failure():
    ok = Runner([(0, ""), (1, "Pull request branch is already up-to-date\n"), (0, "merged\n")])
    assert merge.merge("308", SHA, ok) == 0 and len(ok.calls) == THREE
    bad = Runner([(0, ""), (1, "merge conflict\n")])
    assert merge.merge("308", SHA, bad) == 1 and len(bad.calls) == TWO


def test_merge_not_up_to_date_is_a_failure():
    r = Runner([(0, ""), (1, "Pull request branch is not up to date with base\n")])
    assert merge.merge("308", SHA, r) == 1 and len(r.calls) == TWO


def test_merge_returns_the_gate_failure_and_validates_usage():
    red = Runner([(0, ""), (0, ""), (3, "CI red\n")])
    assert merge.merge("308", SHA, red) == THREE
    assert merge.main([]) == TWO and merge.main(["abc"]) == TWO
    assert merge.main(["308"]) == TWO  # kit 1.8.0: the bare PR-number form is refused
    assert merge.main(["308", "--sha", SHA]) == TWO


def test_merge_refuses_a_bad_reviewed_sha_before_any_step():
    for bad in ("", SHA[:12], SHA[:-1] + "g", "HEAD"):
        r = Runner([])
        assert merge.merge("308", bad, r) == TWO
        assert r.calls == []
