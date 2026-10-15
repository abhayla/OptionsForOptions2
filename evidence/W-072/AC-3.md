---
work_item: W-072
ac: AC-3
requirement: REQ-039
ac_fp: "d7a390072d2b"
result: pass
verified_by: "verifier (sonnet, fresh context) - the W-077 verification of REQ-039 AC-3 at fc446ff / 2a7d4f7"
builder: "builder (sonnet, worktree agent) - W-072 and W-077"
date: '2026-10-16'
commands: "npx vitest run (151, incl. frontend/tests/display-format.test.js and frontend/tests/error-parts.test.js); npm run lint; npm run build; python -m pytest -q -p no:cacheprovider tests/outcome tests/errors; db_run.py tests_app/test_outcome_checked_at.py tests_app/test_outcome_route.py tests_app/test_outcome_no_provider_names.py tests_app/test_broker_instruments.py; python tools/ac_fp.py REQ-039 AC-3 --yaml"
---

AC: AC-3
result: pass
commands: as in the frontmatter
observed: W-072's AC-3 verification failed on 2026-10-15 only because four non-normal states showed no "when" (#245). W-077 (ADR-088) added "Checked at <server answer time, IST>" to those states on top of W-072's code; the W-077 verifier ran the whole vitest suite (151 passed, including W-072's display-format and error-parts tests), lint, build, domain 731 and the targeted app tests, and passed REQ-039 AC-3 (see evidence/W-077/AC-3.md). W-072's e2e spec frontend/e2e/strategy-display-format.spec.ts is run by CI's Playwright job on the merging PR, not by the verifier.
attack: see evidence/W-077/AC-3.md (browser clock faked to 2031; answered_at stripped; ADR/code drift check).

Two verifier runs (full check at fc446ff, honesty re-check at 2a7d4f7); W-072's AC-3 was delivered by W-077.

Recorded by the orchestrator from the verifier's returned block.
