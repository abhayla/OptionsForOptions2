---
work_item: W-024
ac: AC-2
requirement: REQ-065
ac_fp: "d1023ce348f1"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus, rounds 1-10)"
date: '2026-10-08'
commands: "python -m pytest -q -p no:cacheprovider tests/errors; ad-hoc script: render 101 templates, find_advice_wording over 119 templates x 4 parts, missing/empty slot, UserFacingError(), TestClient through ofo_app.errors.install (raising route, bad query value, unknown route)"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/errors; ad-hoc script: render 101 templates, find_advice_wording over 119 templates x 4 parts, missing/empty slot, UserFacingError(), TestClient through ofo_app.errors.install (raising route, bad query value, unknown route)
observed: All 4 parts non-empty for 101 rendered templates; advice-wording hits 0 ('you should', 'best', 'guaranteed' each flagged by the checker); missing slot and empty slot -> ValueError; UserFacingError() -> TypeError. HTTP: RuntimeError('SECRET you should buy; best; guaranteed') -> 500 INTERNAL_SYSTEM_002 four-part body without the text; bad query -> 422 USER_INPUT_002; unknown route -> 404 USER_INPUT_003; every body four parts, external_text null.
attack: Exception text with banned words reached the handler: body was the fixed internal template, no leak. Empty/missing slots fail closed. tests_app boundary tests were run under the root pytest.ini (no asyncio mode) so they did not execute there; the handler check is manual over 3 routes. Out of scope by owner decision 2026-10-08: the Tier A review's MAJORs, issue #148.

Recorded by the orchestrator from the verifier's returned block.
