# Builder brief: W-104 The Execute screen - exact orders + full cost, the owner's two clicks, a basket-return landing page (Tier A front end: the order path)

Core: on a saved strategy, "Execute Strategy" opens a screen that (1) holds the strategy's live socket (W-065
`useStrategyLive`, which subscribes the legs in `full` mode on the server feed) BEFORE it calls
`POST /api/strategies/{id}/execute`, (2) shows the orders and the `cost` block exactly as the reply gives them
(strings, no arithmetic in the browser), (3) on the OWNER's click POSTs `basket.data` with `basket.api_key` to
`basket.url` as an HTML form in a new tab (`target="_blank"`, built from the reply's fields byte-for-byte, never a
client-rebuilt JSON), and (4) on the owner's "Check with Zerodha" click calls the return route and shows each
order's Zerodha state, the plan outcome and the reconciliation result. A separate page `/execution/returned` (where
Kite sends the browser back - F-41, W-105) shows only a "Check with Zerodha" action for the last executed strategy
and never calls the return route by itself.
Proof (the GC-2e contract core, Playwright in CI only): against W-101's Execute replay API, the screen shows BUY 65
NIFTY26O1923650CE LIMIT 3.35, the margin from the derived entry reply, net premium -217.75 and the charges string;
the click's intercepted request (route-intercepted with `page.route` on `https://kite.zerodha.com/**`, aborted - nothing
reaches Kite) carries `api_key` and `data` byte-equal to the reply; "Check with Zerodha" shows plan 1 filled, 0
mismatches.

Tier: A. Model: opus.
Budget: 75 min wall-clock, 76 tool calls. HARD limit: at call 72 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 300 words, `git status --short` empty.
Copy from: none for the screen (no legacy Execute screen meets ADR-054's read-only basket); reuse this repo's
`frontend/src/composables/useStrategyLive.js`, `frontend/src/services/api.js`, `frontend/src/lib/displayFormat.js`,
`components/common/ErrorMessage.vue`. Check `spec/technical-design/legacy-reuse.md` for a frontend row first and say
what you found.
Findings checked: money-value-computed-outside-engine, advice-wording-denylist-per-module, live-subscription-lost-on-release-reacquire, liveness-from-shared-subscribers, gate-output-read-by-eye, targeted-tests-miss-dependent-files
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- REQ-056 AC-1: "The user triggers execution with one 'Execute Strategy' action, which hands the plan's orders to Zerodha as a
    read-only basket the user places on Kite's own order page"
- REQ-073 AC-3: "When the user returns from Kite, the platform reads the actual order states and positions from Zerodha and
  reconciles them"
- ADR-097 (2): "no app code or assistant action sends an order" - the basket form is submitted only by the owner's click.
- ADR-003 wording: decision-support only - never "you should", "best trade", "guaranteed".

## Build
1. Route + page: the Execute screen reached from the saved strategy's actions (`StrategyActions.vue` gets the
   "Execute Strategy" button only when the strategy is saved; read how the builder page knows a saved id). ENTRY when
   nothing is held, EXIT button when the reply/state says held - if the API gives no held flag, show both actions and
   let the route refuse (its catalogue message is shown as-is via `ErrorMessage.vue`).
2. Live first: open the strategy's live socket and wait for its first push for every leg (or the socket's own "live"
   status) before the Execute call; if not live within its normal timeout, show the catalogue's not-live text and do
   not call Execute. A route refusal for a leg without a live frame is shown with the route's catalogue text (test it
   with a mocked 409 in Vitest).
3. Cost block: every field of `cost` from W-102 (`net_premium`, `charges` or `charges_note`, `funds_available`,
   `margin_required`, `figures_read_at`) shown as the strings given; label the platform's own margin estimate, if
   shown at all, "planning estimate" (REQ-055 AC-3). W-102's field names are fixed by its brief
   (`D:/Abhay/Ventures/OptionsForOptions2/docs/process/brief-W-102.md`); merge `origin/build/W-102-execute-cost` into
   your branch as soon as it exists (check with `git ls-remote origin build/W-102-execute-cost`).
4. The basket form: a hidden `<form method="post" action=basket.url target="_blank">` with two hidden inputs `api_key`
   and `data`, values set from the reply verbatim, submitted only inside the owner's click handler. Store the
   strategy id in `localStorage` (`ofo.lastExecutedStrategy`, wrapped in try/catch) for the landing page.
5. "Check with Zerodha": calls the return route (read `backend/ofo_app/routes/execution_return.py` for its path and
   reply), shows per-order Zerodha state, the plan outcome word and mismatches count, as given.
6. `/execution/returned` page: text "Your orders were handled on Kite's page." plus the "Check with Zerodha" button for
   the stored strategy (none stored -> a link back to the strategy list). Nothing runs on page load.
7. Tests: Vitest for the components (form fields verbatim, no submit without a click, refusal text shown, landing page
   makes no request on load); Playwright spec `frontend/e2e/execute-screen.spec.ts` against the Execute replay API
   from W-101 (merge `origin/build/W-101-execute-replay` when it exists; the CI step and port come from that branch's
   `.github/workflows/app-tests.yml` change - read it, edit it with the Edit tool to run your spec there).
8. Any layout, wording or state beyond REQ-073's example: build your recommended version and write the question with
   your recommendation to `docs/process/owner-questions-2026-10-17.md` (create it; one numbered item each).

## Reviewer checklist (attack cases first)
- Attack: the browser computes any money (grep the component for `*`, `+`, `parseFloat`, `Number(` on money fields).
- Attack: the form is submitted on mount / on Execute reply (must be the owner's click only).
- Attack: `api_key` / `data` differ from the reply by one byte (the e2e compares the intercepted body).
- Attack: the landing page calls the return route on load.
- Wording: no advice words (ADR-003); catalogue text for refusals.
- Every server started in a test is stopped.

## DB
Not the shared-DB holder; run no DB command. Frontend: `npm run lint`, `npm run test:run`, `npm run build` locally;
Playwright runs in CI only.

## Rules
- Branch `build/W-104-execute-screen` from origin/main. Work card `work/W-104.md` (frontmatter shape of
  `work/W-100.md`; requirement_ids [REQ-056, REQ-073]; tier A; depends_on [W-101, W-102, W-105]; tests_required
  ['AC-1: frontend/e2e/execute-screen.spec.ts', 'AC-3: frontend/e2e/execute-screen.spec.ts']) and `W-104: 4b` in
  `docs/process/coverage-stages.yaml`.
- Never copy .env; no PR. No kit or `spec/` edit, no `views/`, no `evidence/`. Common rules: `docs/process/builder-brief.md`.
