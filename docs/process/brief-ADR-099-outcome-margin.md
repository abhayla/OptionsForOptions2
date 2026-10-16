# Builder brief: ADR-099 Zerodha margin on the outcome screen (Tier A: money shown to the user)

Core: with a live Kite session, the outcome answer carries a `margin` block with Zerodha's needed amount (the W-081
client's `required_total` = Kite basket figure + ADR-094 top-up, a closing basket counting as 0), the available funds,
and a Checked-at time; it is fetched once per change of the plan (legs / sides / quantities / planned prices), never
per tick; with no session the existing login text; if Zerodha cannot be read, a could-not-read text, never a made-up
figure.
Proof: an app test with a recorded real reply - `tests/fixtures/kite_margins/basket-2026-10-16-long-strangle-bump5.json`
(NIFTY, final 6409, required 7065.50) through a fake transport - gives needed 7065.50 and the given available
funds; a second call with the same plan makes NO new margin request; changing one quantity makes exactly one.

Model: opus.
Budget: 45 min wall-clock, 75 tool calls. At budget STOP and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 250 words, branch + head sha.
Copy from: none - this repo's `backend/ofo_app/kite_margin.py` (W-081, `fetch_basket_margin`, `fetch_available_funds`),
`backend/ofo/outcome/service.py` (`MARGIN` placeholder, `outcome_margin_pending`), `backend/ofo_app/routes/outcome.py`.
Findings checked: money-parsed-through-float, margin-gate-blocks-closing-basket, targeted-tests-miss-dependent-files
Tests: `python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/outcome tests/errors`
plus the app test files you touch and `tests_app/test_outcome_route.py` / `test_strategy_live_push.py` via
`scripts/orchestrator/db_run.py`; `npm run lint` + `npm run test:run` in frontend if you touch it (npm ci first if
node_modules is missing, output to a log); `python scripts/ruff_ratchet.py`; regenerate `docs/api/openapi.json` with
`python scripts/generate_openapi.py` if the response model changes and run `tests_app/test_openapi_drift.py`.

## Spec basis
ADR-099 (needed amount and available funds with a Checked-at time, refetched only on a plan change; read the file);
ADR-016 (Zerodha's figure decides); ADR-094; ADR-088 (Checked at); REQ-055.

## Must hold (reviewer checklist - test each first)
1. Money is Decimal end to end and leaves the API as a 2-decimal string; never float.
2. Cache key = the plan (instrument ids, sides, quantities, planned prices); a price TICK alone never refetches; a
   plan change refetches exactly once; cache per user, bounded size.
3. No session -> existing login text, no Kite call; Kite error/timeout -> a could-not-read text, outcome still
   COMPUTED for the rest (margin failure never blocks the P&L answer); the margin read never runs on the event loop
   thread synchronously (use to_thread like other Kite reads) and has a timeout.
4. Wording only through the error/explanation catalogue with unique codes (ADR-003 wording: information, not advice).
5. Frontend shows the block in the existing margin slot on desktop and mobile; e2e/unit tests for each state.
6. The hard gate is unchanged (REQ-055 check before the basket).
7. Mutation: refetch on every call; drop the session check; float conversion -> a test fails.

## Rules
- Your own worktree, branch `build/ADR-099-outcome-margin` from `origin/main`. No new duplicated literal; reuse the
  existing helper; ruff/mypy baselines must not rise; commit messages must not name the spec folder; commit and push; no PR;
  never write `evidence/`, `work/` or the spec. Never call the real Kite.
