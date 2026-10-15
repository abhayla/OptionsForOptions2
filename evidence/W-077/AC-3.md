---
work_item: W-077
ac: AC-3
requirement: REQ-039
ac_fp: "d7a390072d2b"
result: pass
verified_by: "verifier (sonnet, fresh context; two runs: full check at fc446ff, honesty re-check at 2a7d4f7)"
builder: "builder (sonnet, worktree agent)"
date: '2026-10-16'
commands: "npm ci; npx vitest run; npm run lint; npm run build; python -m pytest -q -p no:cacheprovider tests/outcome tests/errors; db_run.py <v077> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_checked_at.py tests_app/test_outcome_route.py tests_app/test_outcome_no_provider_names.py tests_app/test_broker_instruments.py; scratch vitest with Date faked to 2031; builder test with answered_at stripped; re-check: git diff fc446ff 2a7d4f7 --stat -- frontend backend tests tests_app (0 lines); git diff fc446ff 2a7d4f7 -- spec/decisions/ADR-088.md work/W-077.md; python tools/ac_fp.py REQ-039 AC-3 --yaml"
---

AC: AC-3
result: pass
commands: as in the frontmatter
observed: At fc446ff: vitest 151/151, lint 0, build 0, domain 731 passed, app 30 passed. All four states render 'Checked at <IST>' from answered_at (outcome and planned-entry) or the HTTP Date header (error). Browser clock faked to 2031: NOT_CONNECTED and REFUSED still showed 'Checked at 16 Oct 2026, 09:20:05 IST' for answered_at 2026-10-16T03:50:05Z. Missing answered_at: 'Checked at Time not available'. First run FAILED AC-3 only because not connected uses the answer time while ADR-088 named the last connection attempt, unrecorded. At 2a7d4f7 (no code change since fc446ff, 0 lines in frontend/backend/tests/tests_app): ADR-088 clarified (not connected = answer time, the server keeps no attempt record; provenance orchestrator under the owner's overnight instruction, reversible, OQ-3) and the card lists each state's time; code matches (outcome.py answered_at, planned_entry.py, api.js mapError Date header, StrategyBuilderPage istTime(null) -> 'Time not available').
attack: Browser clock faked: shown time unchanged. answered_at removed: 3 builder tests red (not connected, refused, browser clock). Re-check: looked for drift between the clarified ADR and the code on the not-connected, error-without-Date and unpriced paths - none; no browser-clock fallback exists.

Two verifier runs (full check at fc446ff, honesty re-check at 2a7d4f7); W-072's AC-3 was delivered by W-077.

Recorded by the orchestrator from the verifier's returned block.
