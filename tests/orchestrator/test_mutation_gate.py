"""mutation_gate.py: a script, not the builder's memory, runs every listed guard mutant and fails on a survivor.

Each case builds a tiny sample checkout (two guards, tests for them) in a tmp folder and runs the real gate as a
subprocess. Core: one mutant killed by its named test and one not -> exit 1 naming the survivor."""

import hashlib
import json
import pathlib
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.repo_scan  # tree_hash walks a whole sample checkout

REPO = pathlib.Path(__file__).resolve().parents[2]
GATE = REPO / "scripts" / "orchestrator" / "mutation_gate.py"
TIMEOUT_SECS = 3
SLACK_SECS = 10
RESULT_WAIT_SECS = 60

GUARDS = "def guard_a(x):\n    return x > 0\n\n\ndef guard_b(x):\n    return x < 100\n"
TESTS = (
    "from sample import guard_a, guard_b\n\n\n"
    "def test_a():\n    assert guard_a(1)\n    assert not guard_a(0)\n\n\n"
    "def test_b_weak():\n    assert guard_b(1)\n\n\n"
    "def test_b_strong():\n    assert guard_b(1)\n    assert not guard_b(100)\n"
)
HANG = "import time\n\n\ndef test_hang():\n    time.sleep(120)\n"


def make_checkout(root: pathlib.Path, extra: dict[str, str] | None = None) -> pathlib.Path:
    co = root / "co"
    co.mkdir()
    (co / "pytest.ini").write_text("[pytest]\npythonpath = .\naddopts = -p no:cacheprovider\n")
    (co / "sample.py").write_text(GUARDS)
    (co / "test_sample.py").write_text(TESTS)
    for name, text in (extra or {}).items():
        (co / name).write_text(text)
    return co


def mutant(mid: str, find: str, replace: str, test: str, file: str = "sample.py") -> dict:
    return {"id": mid, "file": file, "find": find, "replace": replace, "test": test}


A = mutant("a-flip", "x > 0", "x >= 0", "test_sample.py::test_a")
B_WEAK = mutant("b-weak", "x < 100", "x <= 100", "test_sample.py::test_b_weak")
B_STRONG = mutant("b-strong", "x < 100", "x <= 100", "test_sample.py::test_b_strong")


def run_gate(co, mutants, results, *extra, timeout=300):
    mf = results.parent / "mutants.json"
    mf.write_text(json.dumps(mutants))
    return subprocess.run(  # noqa: S603
        [sys.executable, str(GATE), str(co), str(mf), str(results), *extra],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def lines(results):
    return [json.loads(x) for x in results.read_text().splitlines() if x.strip()]


def tree_hash(root: pathlib.Path) -> str:
    h = hashlib.sha256()
    for p in sorted(x for x in root.rglob("*") if x.is_file() and "__pycache__" not in x.parts):
        h.update(str(p.relative_to(root)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def test_survivor_fails_gate_and_is_named(tmp_path):
    co = make_checkout(tmp_path)
    res = tmp_path / "r.jsonl"
    p = run_gate(co, [A, B_WEAK], res)
    assert p.returncode == 1
    assert "b-weak" in p.stdout + p.stderr
    by_id = {r["id"]: r for r in lines(res)}
    assert by_id["a-flip"]["result"] == "killed"
    assert by_id["b-weak"]["result"] == "survived"
    assert by_id["__clean__"]["result"] == "passed"


def test_all_killed_exits_zero(tmp_path):
    co = make_checkout(tmp_path)
    res = tmp_path / "r.jsonl"
    p = run_gate(co, [A, B_STRONG], res)
    assert p.returncode == 0, p.stdout + p.stderr
    assert [r["result"] for r in lines(res)] == ["killed", "killed", "passed"]


@pytest.mark.parametrize("find", ["no such text", "x"])  # 0 occurrences, and 2+ occurrences
def test_find_not_exactly_once_is_unresolved(tmp_path, find):
    co = make_checkout(tmp_path)
    res = tmp_path / "r.jsonl"
    p = run_gate(co, [mutant("bad-find", find, "y", "test_sample.py::test_a")], res)
    assert p.returncode == 1
    assert lines(res)[0]["result"] == "unresolved"
    assert "bad-find" in p.stdout + p.stderr


def test_unknown_file_and_escaping_path_are_unresolved(tmp_path):
    co = make_checkout(tmp_path)
    res = tmp_path / "r.jsonl"
    ms = [
        mutant("nofile", "a", "b", "test_sample.py", file="missing.py"),
        mutant("escape", "a", "b", "test_sample.py", file="../outside.py"),
    ]
    (tmp_path / "outside.py").write_text("a")
    p = run_gate(co, ms, res)
    assert p.returncode == 1
    assert [r["result"] for r in lines(res)[:2]] == ["unresolved", "unresolved"]
    assert (tmp_path / "outside.py").read_text() == "a"


def test_no_tests_collected_is_unresolved_not_killed(tmp_path):
    co = make_checkout(tmp_path)
    res = tmp_path / "r.jsonl"
    p = run_gate(co, [mutant("none", "x > 0", "x >= 0", "test_sample.py::test_missing")], res)
    assert p.returncode == 1
    assert lines(res)[0]["result"] == "unresolved"


def test_hanging_test_times_out_named_within_limit(tmp_path):
    co = make_checkout(tmp_path, {"test_hang.py": HANG})
    res = tmp_path / "r.jsonl"
    # the clean run of the same hanging test also times out: the whole gate must end within two timeouts plus slack,
    # enforced by the subprocess limit (TimeoutExpired fails the test), not by comparing a measured time
    budget = 2 * TIMEOUT_SECS + SLACK_SECS + 20
    p = run_gate(
        co, [mutant("hang", "x > 0", "x >= 0", "test_hang.py")], res, "--timeout", str(TIMEOUT_SECS), timeout=budget
    )
    assert p.returncode == 1
    assert lines(res)[0]["result"] == "timeout"
    assert "hang" in p.stdout + p.stderr


def test_checkout_is_byte_identical_after_run(tmp_path):
    co = make_checkout(tmp_path)
    before = tree_hash(co)
    run_gate(co, [A, B_WEAK], tmp_path / "r.jsonl")
    assert tree_hash(co) == before


def test_results_appended_as_each_mutant_finishes(tmp_path):
    co = make_checkout(tmp_path, {"test_hang.py": HANG})
    res = tmp_path / "r.jsonl"
    mf = tmp_path / "mutants.json"
    mf.write_text(json.dumps([A, mutant("hang", "x < 100", "x <= 100", "test_hang.py")]))
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, str(GATE), str(co), str(mf), str(res), "--timeout", "100"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + RESULT_WAIT_SECS
        while time.monotonic() < deadline and not (res.exists() and res.read_text().strip()):
            time.sleep(0.2)
    finally:
        proc.kill()
        proc.wait()
    got = lines(res)
    assert len(got) == 1 and got[0]["id"] == "a-flip" and got[0]["result"] == "killed"


def test_malformed_mutants_file_fails_closed(tmp_path):
    co = make_checkout(tmp_path)
    res = tmp_path / "r.jsonl"
    p = run_gate(co, [{"id": "x", "file": "sample.py", "find": "a"}], res)  # missing keys
    assert p.returncode == 1
    p = run_gate(co, [], res)  # an empty allow-list proves nothing
    assert p.returncode == 1


def test_launcher_prefix_is_used(tmp_path):
    co = make_checkout(tmp_path)
    marker = tmp_path / "launched.txt"
    shim = tmp_path / "shim.py"
    shim.write_text(
        "import subprocess, sys, pathlib\n"
        f"pathlib.Path({str(marker)!r}).write_text('x')\n"
        "sys.exit(subprocess.call(sys.argv[1:]))\n"
    )
    p = run_gate(co, [A], tmp_path / "r.jsonl", "--launcher", f'"{sys.executable}" "{shim}"')
    assert p.returncode == 0, p.stdout + p.stderr
    assert marker.exists()
