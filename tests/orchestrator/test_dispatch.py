"""dispatch.py (ADR-181 item 2): a Measure JSON becomes a checked brief only when every step passes, a row's third fix
round is refused, and each accepted dispatch is recorded so the round count survives a new session.

Core: the real children run on the recorded Measure JSON of row 24 (tests/orchestrator/fixtures/measure-24.json) and
the stale JSON is refused at make-brief with no ledger line. Every other case injects the child runner."""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "orchestrator"))
import dispatch  # noqa: E402

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "measure-24.json"
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t.invalid"]
SCRIPT_ORDER = ["make_brief.py", "check_brief.py", "copy_from_check.py", "overlap_gate.py"]
STEP_OF = {"make_brief.py": "make-brief", "check_brief.py": "check-brief", "copy_from_check.py": "copy-from",
           "overlap_gate.py": "overlap"}
PLANNED = ["backend/a.py", "tests/test_a.py"]
CHANGED = ["backend/b.py"]


def _git(cwd: pathlib.Path, *args: str) -> None:
    subprocess.run([*GIT, "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture(scope="module")
def repo_pair(tmp_path_factory):
    """A real git repo on main and a builder worktree on build/t (built once: `git worktree add` is slow)."""
    base = tmp_path_factory.mktemp("dispatch-repo")
    root = base / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    (root / "f.txt").write_text("x")
    _git(root, "add", "f.txt")
    _git(root, "commit", "-m", "init")
    wt = base / "wt"
    _git(root, "worktree", "add", "-b", "build/t", str(wt))
    return root, wt


@pytest.fixture
def env(tmp_path, repo_pair):
    """The repo pair with frontend/node_modules present, a Measure JSON, and per-test ledger and brief paths."""
    root, wt = repo_pair
    (wt / "frontend" / "node_modules").mkdir(parents=True, exist_ok=True)
    measure = tmp_path / "measure.json"
    measure.write_text(json.dumps({"row": "21c", "files": PLANNED, "changed_files": CHANGED}))
    return {"root": root, "wt": wt, "measure": measure, "ledger": tmp_path / "ledger.jsonl",
            "out": tmp_path / "brief.md", "tmp": tmp_path}


class Fake:
    """Injected child runner: records argv, answers per script, writes the brief like make_brief does."""

    def __init__(self, answers: dict[str, object] | None = None):
        self.calls: list[list[str]] = []
        self.answers = answers or {}
        self.lists: list[str] = []

    def __call__(self, argv: list[str]) -> int:
        self.calls.append(argv)
        name = pathlib.Path(argv[1]).name
        if name == "overlap_gate.py":
            self.lists.append(pathlib.Path(argv[-1]).read_text(encoding="utf-8"))
        answer = self.answers.get(name, 0)
        if isinstance(answer, BaseException):
            raise answer
        if name == "make_brief.py" and answer == 0:
            pathlib.Path(argv[argv.index("--out") + 1]).write_bytes(b"# brief\n")
        return answer  # type: ignore[return-value]

    @property
    def scripts(self) -> list[str]:
        return [pathlib.Path(c[1]).name for c in self.calls]


def run(env, row="21c", kind="build", fake=None, extra=None, in_flight=("--no-in-flight",), wt=None, measure=None):
    argv = [row, str(measure or env["measure"]), "--kind", kind, "--out", str(env["out"]),
            "--worktree", str(wt or env["wt"]), "--ledger", str(env["ledger"]), "--root", str(env["root"]),
            *in_flight, *(extra or [])]
    fake = fake or Fake()
    return dispatch.main(argv, runner=fake), fake


def ledger_lines(env) -> list[dict]:
    if not env["ledger"].exists():
        return []
    return [json.loads(line) for line in env["ledger"].read_text(encoding="utf-8").splitlines()]


def test_steps_are_this_exact_ordered_list():
    assert dispatch.STEPS == ("round-limit", "worktree-ready", "make-brief", "check-brief", "copy-from", "overlap",
                              "ledger")


def test_accepted_dispatch_runs_children_in_order_and_writes_one_ledger_line(env, capsys, monkeypatch):
    monkeypatch.setenv("CLAUDE_SESSION_ID", "sess-9")
    code, fake = run(env, in_flight=("--in-flight", f"{env['tmp'] / 'other'}=abc123"))
    out = capsys.readouterr().out
    assert code == 0
    assert fake.scripts == SCRIPT_ORDER
    assert f"DISPATCH OK row 21c build round 1 brief {env['out']}" in out
    [line] = ledger_lines(env)
    assert list(line) == list(dispatch.LEDGER_KEYS)
    assert (line["row"], line["kind"], line["round"], line["brief"], line["session"]) == (
        "21c", "build", 1, str(env["out"]), "sess-9")
    assert line["brief_sha256"] == hashlib.sha256(b"# brief\n").hexdigest()
    assert line["at"].endswith("+00:00")


def test_session_is_unknown_without_the_env_variable(env, monkeypatch):
    monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)
    run(env)
    assert ledger_lines(env)[0]["session"] == "unknown"


def test_make_brief_gets_the_documented_argv(env):
    _, fake = run(env, kind="fix")
    assert fake.calls[0][2:] == ["21c", str(env["measure"]), "--kind", "fix", "--out", str(env["out"]),
                                 "--root", str(env["root"].resolve())]
    assert fake.calls[1][2:] == [str(env["out"]), "--root", str(env["root"].resolve())]
    assert fake.calls[2][2:] == [str(env["root"].resolve()), str(env["out"])]


def test_third_fix_round_refused_first_and_second_accepted(env, capsys):
    codes = [run(env, kind="fix")[0] for _ in range(3)]
    out = capsys.readouterr().out
    assert codes == [0, 0, 1]
    assert "DISPATCH REFUSED row 21c: third fix round - park it (run-discipline B1)" in out
    assert [e["round"] for e in ledger_lines(env)] == [1, 2]


def test_refused_third_round_runs_no_child(env):
    run(env, kind="fix")
    run(env, kind="fix")
    code, fake = run(env, kind="fix")
    assert (code, fake.calls) == (1, [])


def test_build_and_verify_r2_are_never_counted_as_fix_rounds(env):
    for kind in ("build", "build", "build", "verify-r2", "verify-r2"):
        assert run(env, kind=kind)[0] == 0
    assert [run(env, kind="fix")[0] for _ in range(3)] == [0, 0, 1]
    rounds = [(e["kind"], e["round"]) for e in ledger_lines(env)]
    assert rounds == [("build", 1), ("build", 2), ("build", 3), ("verify-r2", 1), ("verify-r2", 2),
                      ("fix", 1), ("fix", 2)]


def test_row_key_in_other_case_and_spacing_is_the_same_row(env):
    assert [run(env, row=r, kind="fix")[0] for r in ("21c", " 21C", "21C ")] == [0, 0, 1]


def test_other_rows_have_their_own_count(env):
    run(env, kind="fix")
    run(env, kind="fix")
    assert run(env, row="22", kind="fix")[0] == 0


def test_ledger_entry_with_odd_kind_spelling_counts_as_fix(env):
    env["ledger"].write_text("".join(json.dumps({"row": "21C ", "kind": k}) + "\n" for k in ("FIX", " fix")))
    code, _ = run(env, kind="fix")
    assert code == 1


def test_round_limit_is_re_checked_when_recording(env):
    """Another session dispatched between our first look and our write: the second look refuses."""
    fake = Fake()
    real_call = fake.__call__

    def racing(argv):
        if pathlib.Path(argv[1]).name == "copy_from_check.py":
            env["ledger"].write_text("".join(json.dumps({"row": "21c", "kind": "fix"}) + "\n" for _ in range(2)))
        return real_call(argv)

    code = dispatch.main(["21c", str(env["measure"]), "--kind", "fix", "--out", str(env["out"]), "--worktree",
                          str(env["wt"]), "--ledger", str(env["ledger"]), "--root", str(env["root"]),
                          "--no-in-flight"], runner=racing)
    assert code == 1
    assert len(ledger_lines(env)) == 2


FAILURES = [1, 2, 3, 127, -9, FileNotFoundError("no python"), PermissionError("denied")]


@pytest.mark.parametrize("script", SCRIPT_ORDER)
@pytest.mark.parametrize("answer", FAILURES, ids=repr)
def test_each_child_failing_stops_the_run_and_writes_no_ledger_line(env, capsys, script, answer):
    in_flight = ("--in-flight", f"{env['tmp'] / 'other'}=abc123")
    code, fake = run(env, fake=Fake({script: answer}), in_flight=in_flight)
    out = capsys.readouterr().out
    assert code == 1
    assert fake.scripts == SCRIPT_ORDER[: SCRIPT_ORDER.index(script) + 1]  # nothing after the failed step ran
    assert f"DISPATCH REFUSED row 21c: step {STEP_OF[script]}" in out
    assert "DISPATCH OK" not in out
    assert ledger_lines(env) == []


def test_second_in_flight_row_failing_refuses(env):
    class Second(Fake):
        def __call__(self, argv):
            code = super().__call__(argv)
            return 1 if pathlib.Path(argv[1]).name == "overlap_gate.py" and argv[2].endswith("two") else code

    code, fake = run(env, fake=Second(), in_flight=("--in-flight", "one=r1", "--in-flight", "two=r2"))
    assert (code, fake.scripts.count("overlap_gate.py")) == (1, 2)
    assert ledger_lines(env) == []


def test_overlap_args_and_planned_list(env):
    _, fake = run(env, in_flight=("--in-flight", "otherwt=ref1"))
    overlap = fake.calls[-1]
    assert overlap[2:5] == ["otherwt", "ref1", str(env["wt"].resolve())]
    assert fake.lists == ["\n".join(PLANNED) + "\n"]


def test_verify_r2_overlap_uses_changed_files(env):
    _, fake = run(env, kind="verify-r2", in_flight=("--in-flight", "otherwt=ref1"))
    assert fake.lists == ["\n".join(CHANGED) + "\n"]


@pytest.mark.parametrize("body", ["{}", "[]", '{"files": []}', '{"files": "a.py"}', '{"files": [1]}', "not json"])
def test_overlap_without_a_usable_file_list_refuses(env, body):
    env["measure"].write_text(body)
    code, _ = run(env, in_flight=("--in-flight", "otherwt=ref1"))
    assert code == 1
    assert ledger_lines(env) == []


def test_in_flight_value_may_hold_a_drive_letter_path(env):
    _, fake = run(env, in_flight=("--in-flight", "D:\\x\\y=origin/main",))
    assert fake.calls[-1][2:4] == ["D:\\x\\y", "origin/main"]


@pytest.mark.parametrize("flags", [(), ("--no-in-flight", "--in-flight", "w=r"), ("--in-flight", "no-equals"),
                                   ("--in-flight", "=ref"), ("--in-flight", "w=")])
def test_in_flight_flags_must_be_explicit_and_well_formed(env, flags):
    fake = Fake()
    with pytest.raises(SystemExit) as exc:
        dispatch.main(["21c", str(env["measure"]), "--kind", "build", "--out", str(env["out"]), "--worktree",
                       str(env["wt"]), "--ledger", str(env["ledger"]), "--root", str(env["root"]), *flags],
                      runner=fake)
    assert exc.value.code == 2
    assert fake.calls == [] and ledger_lines(env) == []


def test_unknown_kind_is_a_usage_error(env):
    with pytest.raises(SystemExit) as exc:
        run(env, kind="deploy")
    assert exc.value.code == 2


def test_missing_worktree_is_exit_4_with_setup_steps(env, capsys):
    code, fake = run(env, wt=env["tmp"] / "nowhere")
    out = capsys.readouterr().out
    assert code == 4 and fake.calls == [] and ledger_lines(env) == []
    assert "wt-new.ps1" in out and "npm ci" in out and "scripts/orchestrator/gate.py" in out


def test_worktree_on_main_is_exit_4(env, capsys):
    code, fake = run(env, wt=env["root"])
    assert code == 4 and fake.calls == []
    assert "not a builder branch" in capsys.readouterr().out


def test_worktree_without_node_modules_is_exit_4(env, capsys):
    (env["wt"] / "frontend" / "node_modules").rmdir()
    code, fake = run(env)
    out = capsys.readouterr().out
    assert code == 4 and fake.calls == []
    assert "no frontend/node_modules" in out and "frontend && npm ci" in out


def test_plain_folder_is_not_a_worktree(env):
    plain = env["tmp"] / "plain"
    (plain / "frontend" / "node_modules").mkdir(parents=True)
    assert run(env, wt=plain)[0] == 4


def test_setup_steps_are_printed_on_success_too(env, capsys):
    run(env)
    out = capsys.readouterr().out
    assert "wt-new.ps1" in out and "-Name wt -Branch build/wt -Base origin/main -Purpose row-21c-build" in out
    assert "frontend && npm ci" in out and "python scripts/orchestrator/gate.py" in out


CORRUPT = ["not json\n", "[1, 2]\n", '{"row": "21c"}\n', '{"row": 21, "kind": "fix"}\n',
           '{"row": "21c", "kind": "fix"}\n{"row": "21c", "kind": "fix"\n']


@pytest.mark.parametrize("text", CORRUPT)
def test_corrupt_ledger_refuses_instead_of_reading_as_empty(env, capsys, text):
    env["ledger"].write_text(text)
    code, fake = run(env, kind="build")
    assert code == 1 and fake.calls == []
    assert "DISPATCH REFUSED row 21c: ledger" in capsys.readouterr().out
    assert env["ledger"].read_text() == text


def test_ledger_with_blank_lines_is_still_counted(env):
    env["ledger"].write_text('\n{"row": "21c", "kind": "fix"}\n\n{"row": "21c", "kind": "fix"}\n')
    assert run(env, kind="fix")[0] == 1


def test_default_ledger_lives_in_the_shared_git_common_dir(env):
    argv = ["21c", str(env["measure"]), "--kind", "build", "--out", str(env["out"]), "--worktree", str(env["wt"]),
            "--root", str(env["wt"]), "--no-in-flight"]
    assert dispatch.main(argv, runner=Fake()) == 0
    shared = env["root"] / ".git" / dispatch.LEDGER_NAME
    assert json.loads(shared.read_text())["row"] == "21c"


def test_real_children_refuse_the_recorded_row_24_measure_json_and_write_no_ledger(env, capsys):
    """Core: the real make_brief/check_brief/copy_from_check run on the recorded JSON. It was recorded before
    REQ-049's open reference records and legacy map rows applied to a row-24 brief, so the gate must refuse it."""
    argv = ["24", str(FIXTURE), "--kind", "build", "--out", str(env["out"]), "--worktree", str(env["wt"]),
            "--ledger", str(env["ledger"]), "--root", str(REPO), "--no-in-flight"]
    assert dispatch.main(argv) == 1
    assert "DISPATCH REFUSED row 24: step make-brief exited 1" in capsys.readouterr().out
    assert ledger_lines(env) == []
