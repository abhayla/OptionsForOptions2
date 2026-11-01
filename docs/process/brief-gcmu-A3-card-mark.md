# Brief: GC-MU A3 - ADR-230 (2): the Live Strategies card shows "N adjustment opportunities", linking to that strategy's inbox row

Core: the count of a strategy's open adjustment opportunities, read from the existing suggestion records, reaches its Live Strategies card; dismissing the last one in the inbox makes the mark go.
Proof: step 1 of this brief - a route/store test on scenario ADJ-02 with a recorded opportunity: the count read for that strategy is 1; after the dismiss route runs, it is 0.
Budget: 40 min wall-clock, 55 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Spec quote: ADR-230 "dismissing the row there clears the mark"
Sensibull: n/a - the reference product has no adjustment-opportunity inbox (searched the study for opportunity, alert badge).
Reference: none - searched adjustment opportunities, card badge (no such screen in the study); open records: RD-096 (shape detection, not touched)
Copy from: none - the inbox (REQ-112, REQ-162) was built new in GC-ADJ2.
Tier: B.

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-mark`, branch `build/gcmu-mark` (from `build/gcmu`). Commit there only, never push. `frontend/node_modules` is a junction: never delete it, never run `npm ci`/`npm install`. Do NOT edit `backend/ofo_app/playbook_store.py` (shared with another session): read through its existing functions; if a new query is unavoidable, put it in a NEW module and report it.

## The decision (spec/decisions/ADR-230.md decision (2))
The card shows "N adjustment opportunities", linking to that strategy's row in Positions > Adjustment opportunities; dismissing the row there clears the mark. Count from the existing suggestion records (REQ-112, REQ-162). No mark when N is 0. Wording through the catalogue (`backend/ofo/errors/templates.py` / `explanations.py`, pins updated), decision support only (ADR-003); singular for N = 1.

## Do, in order
1. CORE: a server read of open-opportunity counts per strategy for the user (what the inbox route `backend/ofo_app/routes/adjustment_opportunities.py` counts as open; same definition, one function reused, never a second rule). Test on ADJ-02: 1 before dismiss, 0 after `POST /api/adjustment-opportunities/{id}/dismiss`.
2. Serve it with the data the Live Strategies page already loads (find the route that lists live strategies; add a field there through the declared reply model in `backend/ofo_app/api_models.py` - an undeclared reply field makes the route answer 500, as A2 round 1 showed). Route test asserts the field.
3. `frontend/src/pages/LiveStrategiesPage.vue`: the mark on the card, a link to the inbox row for that strategy (`AdjustmentOpportunitiesPage.vue`; add a query or hash anchor so the page scrolls to that strategy's group). vitest for the mark (0 hidden, 1 singular, 3 plural) and the link target.
4. DB tests through the main checkout's runner, one file at a time (the worktree has no `.env`; the shared DB host serves production): `python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run_fresh.py D:/Abhay/Ventures/OptionsForOptions2-gcmu-mark python -m pytest -c pytest-app.ini tests_app/<file>.py -q -rs`. Run in full every changed route test file this way, plus `tests_app/test_response_door.py tests_app/test_api_models.py`, `tests/strategy/test_templates.py`, `python scripts/ruff_ratchet.py`, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, and `npx vitest run <changed specs>`. Logs to a file, tail only.

## Standing items
- Answer states for the count: open records present, all dismissed, all acted on, a record found false, strategy not tracked, count read failed (the card shows no mark and the page still loads; log it).
- A shown-value change greps every test tree (e2e included) for the card text it touches.
- Test files that import `ofo_app` go under `tests_app/`, not `tests/`.
- No new duplicated literal; ruff baselines must not rise; no regenerated files except pins by the repo's process.
- REPORT every shared-list file changed with line ranges (`frontend/src/router/nav.js`, `backend/ofo/errors/templates.py`, `backend/ofo/errors/explanations.py`, `tests/errors/template_pins.json`, `backend/ofo_app/api_models.py`).
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcmu-mark.
