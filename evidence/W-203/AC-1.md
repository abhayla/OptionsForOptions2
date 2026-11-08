---
work_item: W-203
requirement: REQ-156
ac: AC-1
result: fail
verified_by: "independent verifier (Sonnet, GC-IC1 step 10 round 6)"
date: 2026-11-04
ac_fp: "50fc13a471c8"
commands: "git rev-parse HEAD (efebcba2); python -m pytest -q -p no:cacheprovider tests/adjustment/test_approach_compare.py (16 passed); cd frontend && npx vitest run tests/adjust-compare.test.js (25 passed); env -u TEST_DATABASE_URL -u TEST_ADMIN_DATABASE_URL -u ALEMBIC_DATABASE_URL python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_adjustment_approaches_route.py -k 'no_spot or req156' (5 passed); read compare.py, adjustment.py 440-630, AdjustCompare.vue, adjustCompare.js, adjustDrawer.js"
---
Part 1 holds: the route asks for all APPROACH_IDS, compare() orders No change first, refused builds stay out of the columns (compare() raises if one is passed). Part 2 holds on the backend: adjustment.py:468-477 returns approaches=[] and the spot text names all three source reasons. It does not hold on the page: AdjustCompare.vue:9-171 draws everything whenever a reply exists, so with no spot the page also shows the title, intro, 'Why detected' card, an empty chart, 'Showing 0 of 0' filters, an empty table and the prepare panel; 'Spot not available' is only a caption at :35, and :186-187 say No change stays in the table though no column exists. No vitest covers a spot-less reply.

Fix: when reply.spot.value is null render only the spot line with its reasons; add a vitest for that case.

Recorded by the orchestrator from the verifier's returned block.
