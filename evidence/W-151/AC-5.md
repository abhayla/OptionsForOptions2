---
work_item: W-151
ac: AC-5
requirement: REQ-119
ac_fp: "ffe6e48e6db1"
result: pass
verified_by: "independent verifiers (Opus 23a check, round 2, redesign check; Opus 23b check, round 2)"
builder: "builders (Opus: 23a 3d57accf/e724981b + orchestrator lint 8ca82154, Sonnet fix 220923e9, Opus independent redesign c2e921bd; Sonnet: 23b 00b8ecba, fix f7445753)"
date: '2026-10-24'
commands: "pytest -c pytest-app.ini tests_app/test_execute_revision.py (DB-free core) unmutated and with the revision check moved after _execute (2 failed); 23b: vitest tests/execute-screen.test.js (409 -> re-read -> next prepare sends revision+1)"
---

AC: AC-5
result: pass
commands: pytest -c pytest-app.ini tests_app/test_execute_revision.py (DB-free core) unmutated and with the revision check moved after _execute (2 failed); 23b: vitest tests/execute-screen.test.js (409 -> re-read -> next prepare sends revision+1)
observed: The Execute review carries seq and the revision it was built from; a revision other than the stored one is refused 409 'Your plan changed - review it again.' (backend/ofo/errors/templates.py) before any broker read or plan write (routes/execute.py: load, revision check, then session, then _execute); after the 409 the page re-reads the saved strategy once and the next prepare sends the new revision.
attack: check moved after the broker/plan-reservation call: caught by test_core_db_free_a_stale_revision_never_reaches_the_broker_or_the_plan_store; re-read removed: 3 failed. DB cases run in CI only. MINOR: any 409 triggers the re-read (the error code is not passed to the page).

Recorded by the orchestrator from the verifier's returned block.
