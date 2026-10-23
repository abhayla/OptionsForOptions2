"""Finding ci-apt-mirror-stall: every job that installs Playwright first points apt at the Ubuntu archive directly.

The runner's mirror list (mirror+file:, the Azure mirror first for every file) stalled `playwright install-deps` past
its 12-minute cap three times on 2026-10-23. A step that rewrites the apt sources must run before any
`playwright install` step in the same job, and must fail when a mirror-list entry survives.
Reads ``.github/workflows/app-tests.yml``."""
import pathlib

import pytest
import yaml

pytestmark = pytest.mark.repo_scan

WORKFLOW = pathlib.Path(__file__).resolve().parents[1] / ".github" / "workflows" / "app-tests.yml"
INSTALL = "playwright install"
REWRITE = "mirror\\+file:/etc/apt/apt-mirrors"  # the sed pattern that removes the mirror list
PROVE = "! grep"  # the step fails when a mirror-list entry survives


def _jobs(text: str) -> dict:
    return yaml.safe_load(text)["jobs"]


def missing_direct_apt(text: str) -> list[str]:
    """Jobs whose first `playwright install` step has no earlier sources-rewrite step that proves itself."""
    bad = []
    for name, job in _jobs(text).items():
        runs = [str(s.get("run", "")) for s in job.get("steps", [])]
        installs = [i for i, r in enumerate(runs) if INSTALL in r]
        if not installs:
            continue
        rewrites = [i for i, r in enumerate(runs) if REWRITE in r and PROVE in r]
        if not rewrites or rewrites[0] > installs[0]:
            bad.append(name)
    return bad


def test_every_playwright_job_reads_the_archive_directly_first():
    assert missing_direct_apt(WORKFLOW.read_text(encoding="utf-8")) == []


def test_the_check_flags_a_job_without_the_rewrite():
    text = ("jobs:\n  e2e:\n    steps:\n      - run: npx playwright install-deps chromium\n"
            "  ok:\n    steps:\n      - run: \"sed -e 's#mirror\\\\+file:/etc/apt/apt-mirrors#x#' f; ! grep -q y f\"\n"
            "      - run: npx playwright install chromium\n")
    assert missing_direct_apt(text) == ["e2e"]


def test_the_check_flags_a_rewrite_that_comes_after_the_install():
    text = ("jobs:\n  late:\n    steps:\n      - run: npx playwright install chromium\n"
            "      - run: \"sed -e 's#mirror\\\\+file:/etc/apt/apt-mirrors#x#' f; ! grep -q y f\"\n")
    assert missing_direct_apt(text) == ["late"]
