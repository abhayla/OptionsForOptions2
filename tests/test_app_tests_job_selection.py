"""Per-job selection in the App tests workflow (GC-6 CI-SPLIT, finding F-53; REQ-075 AC-6/AC-7, ADR-093).

Class: workflow-level path filters start EVERY job for any listed path, so a frontend-only change ran the API job.
The `changes` job (dorny/paths-filter) now picks the jobs per pull request. This test parses the workflow, evaluates
its filter globs offline (picomatch rules: `**` crosses slashes, `*` does not, dotfiles match) and asserts which jobs
each change set selects, that nothing the old workflow ran goes untested, and that the wiring fails toward testing.
"""
from __future__ import annotations

import pathlib
import re

import pytest
import yaml

pytestmark = pytest.mark.repo_scan

ROOT = pathlib.Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "app-tests.yml"
JOB_FOR_OUTPUT = {"api": "api", "frontend": "frontend", "e2e": "execute-screen-e2e"}


def _doc() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _filters() -> dict[str, list[str]]:
    step = _doc()["jobs"]["changes"]["steps"][0]
    return yaml.safe_load(step["with"]["filters"])


def _outer_paths(event: str) -> list[str]:
    doc = _doc()
    return (doc.get(True) or doc["on"])[event]["paths"]


def _glob_to_regex(glob: str) -> re.Pattern[str]:
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif glob.startswith("**", i):
            out += ".*"
            i += 2
        elif glob[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(glob[i])
            i += 1
    return re.compile(out + r"\Z")


def _matches(globs: list[str], path: str) -> bool:
    assert not any(g.startswith("!") for g in globs), "negations are not evaluated here; keep filters positive"
    return any(_glob_to_regex(g).match(path) for g in globs)


def _selected(paths: list[str]) -> set[str]:
    """The job outputs a pull request touching `paths` turns on, given the workflow starts at all."""
    filters = _filters()
    return {name for name, globs in filters.items() if any(_matches(globs, p) for p in paths)}


def _starts_workflow(path: str) -> bool:
    return _matches(_outer_paths("pull_request"), path)


@pytest.mark.parametrize(
    ("changed", "expected"),
    [
        ("frontend/src/x.vue", {"frontend", "e2e"}),
        ("backend/ofo_app/routes/x.py", {"api", "e2e"}),
        ("backend/ofo/engine/x.py", {"api", "frontend", "e2e"}),
        ("requirements-app.txt", {"api", "frontend", "e2e"}),
        ("tests/fixtures/kite_ws/x.csv", {"api", "frontend", "e2e"}),
        ("tests_app/test_x.py", {"api"}),
        ("frontend/package-lock.json", {"frontend", "e2e"}),
        ("docs/api/openapi.json", {"api", "frontend", "e2e"}),
        ("pytest-app.ini", {"api"}),
        ("ruff.toml", {"api"}),
        ("requirements-dev.txt", {"api"}),
        ("scripts/ruff_baseline.json", {"api"}),
        (".github/workflows/app-tests.yml", {"api", "frontend", "e2e"}),
    ],
)
def test_a_change_selects_exactly_the_jobs_that_read_it(changed: str, expected: set[str]) -> None:
    assert _starts_workflow(changed), f"{changed} would not even start the workflow"
    assert _selected([changed]) == expected


def test_frontend_only_starts_no_api_job_and_backend_api_only_starts_no_frontend_job() -> None:
    assert "api" not in _selected(["frontend/src/x.vue", "frontend/package-lock.json"])
    assert "frontend" not in _selected(["backend/ofo_app/routes/x.py", "tests_app/test_x.py"])
    assert "e2e" in _selected(["backend/ofo_app/routes/x.py"])  # the Execute screen e2e runs the real API


@pytest.mark.parametrize(
    "changed",
    ["docs/process/x.md", "spec/decisions/ADR-001.md", "knowledge/findings/x.json", "evidence/W-001/AC-1.md"],
)
def test_a_docs_spec_knowledge_or_evidence_change_starts_nothing(changed: str) -> None:
    assert not _starts_workflow(changed)
    assert _selected([changed]) == set()


def test_every_path_that_started_the_workflow_still_selects_at_least_one_job() -> None:
    """Under-testing guard: each outer-gate glob, probed with a sample file, must select a job (nothing starts a
    workflow whose jobs all skip, and nothing that used to run tests now runs none)."""
    probes = {
        "backend/ofo/**": "backend/ofo/engine/x.py",
        "tests/fixtures/**": "tests/fixtures/kite_ws/x.csv",
        "backend/ofo_app/**": "backend/ofo_app/main.py",
        "tests_app/**": "tests_app/test_x.py",
        "requirements-app.txt": "requirements-app.txt",
        "pytest-app.ini": "pytest-app.ini",
        "scripts/alembic_migration_guard.py": "scripts/alembic_migration_guard.py",
        "scripts/generate_openapi.py": "scripts/generate_openapi.py",
        "frontend/**": "frontend/src/x.vue",
        "docs/api/**": "docs/api/openapi.json",
        "docs/research/kite-proof-2026-10-07/**": "docs/research/kite-proof-2026-10-07/rest-2026-10-15/basket.json",
        ".github/workflows/app-tests.yml": ".github/workflows/app-tests.yml",
        "tests/**": "tests/engine/test_x.py",
        "ruff.toml": "ruff.toml",
        "requirements-dev.txt": "requirements-dev.txt",
        "scripts/ruff_ratchet.py": "scripts/ruff_ratchet.py",
        "scripts/ruff_baseline.json": "scripts/ruff_baseline.json",
    }
    for event in ("push", "pull_request"):
        assert set(_outer_paths(event)) == set(probes), f"{event}: outer paths changed; extend the probes"
    for glob, sample in probes.items():
        assert _matches([glob], sample), glob
        assert _selected([sample]), f"{sample} (outer gate {glob}) would start the workflow and run no job"


def test_tests_dir_is_in_the_api_filter_for_the_ruff_ratchet() -> None:
    assert _matches(_filters()["api"], "tests/anything/deep/x.py")


def test_each_job_waits_for_changes_and_fails_toward_testing() -> None:
    jobs = _doc()["jobs"]
    assert "changes" in jobs and jobs["changes"]["if"] == "github.event_name == 'pull_request'"
    for output, job in JOB_FOR_OUTPUT.items():
        assert jobs[job]["needs"] == "changes", job
        cond = jobs[job]["if"]
        assert "!cancelled()" in cond, f"{job}: without it a failed `changes` skips the job silently"
        assert "github.event_name != 'pull_request'" in cond, f"{job}: a push to main must run every job"
        assert "needs.changes.result != 'success'" in cond, f"{job}: a failed filter must run the job"
        assert f"needs.changes.outputs.{output} == 'true'" in cond, job
    assert set(JOB_FOR_OUTPUT) == set(jobs["changes"]["outputs"])


def test_job_names_are_unchanged_and_the_filter_action_is_pinned_to_a_full_sha() -> None:
    jobs = _doc()["jobs"]
    assert {"api", "frontend", "execute-screen-e2e"} <= set(jobs)
    assert all("name" not in jobs[j] for j in JOB_FOR_OUTPUT.values())  # check names stay the job ids
    uses = _doc()["jobs"]["changes"]["steps"][0]["uses"]
    assert re.fullmatch(r"dorny/paths-filter@[0-9a-f]{40}", uses), uses
    assert jobs["changes"]["permissions"]["pull-requests"] == "read"
