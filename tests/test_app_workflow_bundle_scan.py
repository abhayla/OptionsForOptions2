"""REQ-048 AC-5 (W-134, standing item b): the bundle scan runs in CI on the built bundle.

The scan reads ``frontend/dist``, so the CI step must come after the frontend build, and after the step that installs
pytest (``requirements-app.txt``) in the same job. Reads ``.github/workflows/app-tests.yml`` (project-owned)."""
import pathlib

import pytest
import yaml

pytestmark = pytest.mark.repo_scan

WORKFLOW = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows" / "app-tests.yml"
SCAN_COMMAND = "tests/test_bundle_secret_scan.py"


def _steps() -> list[dict]:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return doc["jobs"]["frontend"]["steps"]


def _index(steps: list[dict], needle: str, key: str = "run") -> int:
    hits = [i for i, s in enumerate(steps) if needle in str(s.get(key, ""))]
    assert hits, f"no frontend step with {needle!r} in {key}"
    return hits[0]


def test_the_scan_step_runs_in_the_frontend_job_after_the_build_and_after_the_pytest_install():
    steps = _steps()
    scan = _index(steps, SCAN_COMMAND)
    assert scan > _index(steps, "npm run build")
    assert scan > _index(steps, "pip install -r requirements-app.txt")
    assert "pytest" in str(steps[scan]["run"]) and "if" not in steps[scan], "the scan step must be unconditional"
    assert "continue-on-error" not in steps[scan]


def test_pytest_is_in_the_requirements_the_frontend_job_installs():
    reqs = (WORKFLOW.parents[2] / "requirements-app.txt").read_text(encoding="utf-8")
    assert any(line.strip().lower().startswith("pytest==") for line in reqs.splitlines())


def test_a_change_to_the_scan_files_starts_the_frontend_job():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "- 'tests/test_bundle_secret_scan.py'" in text and "- 'tests/test_app_workflow_bundle_scan.py'" in text
