# Builder brief: W-111 Positions part 1 on the redesigned W-108 (pending contracts per ADR-110) - GC-2g item 2, Tier A

Common brief: docs/process/builder-brief.md
Core: GET /api/positions passes Zerodha's order book to W-108 and shows a pending contract exactly as ADR-110 says;
no own/outside split for it, the strategy blocked, a link to the strategy's Execute screen.
Proof: tests_app/test_positions_route.py on the recorded replies (tests/fixtures/kite_replies/ orders-122104 +
positions-122104): plan 1 OPEN with its order row status rewritten to OPEN -> the contract row is pending, Zerodha's
65 marked not yet confirmed, own and outside absent, strategy 1 blocked; the same plan OPEN with the real COMPLETE row
-> own 65, outside 0, not blocked; the existing route tests still pass.
Spec basis: ADR-110; ADR-109 (2), (5); REQ-044 AC-3; REQ-060 AC-7; ADR-027.

ADR-110: "makes no own/outside split for it"
ADR-110: "Order placed - waiting for Check with Zerodha"
ADR-110: "not yet confirmed"
Copy from: none - the W-111 route and page already exist on build/W-111-positions; this rebases them.
Findings checked: caller-supplied-verdict-trusted, verified-on-a-module-the-product-does-not-call, state-with-no-working-exit, test-asserts-implementation-output
Tier: A (reads feeding a position quantity; any module the routes import). Branch: build/W-111-positions (head
ebd84fe, stacked on build/W-108-attribution). In your worktree: `git fetch origin`, `git checkout -B
build/W-111-positions origin/build/W-111-positions`, then `git rebase origin/build/W-108-attribution` (W-108 is now at
5747818 or later: read `git log origin/build/W-108-attribution -3`), resolve, and `git push --force-with-lease origin
build/W-111-positions`. Do not open a PR (the orchestrator opens a draft).
Budget: 90 min wall-clock, 80 tool calls
Report: evidence-table

## What to change
1. Route (backend/ofo_app/routes/positions.py): read Zerodha's orders too (`session.reads.fetch_orders()` +
   `kite_replies.orders_from_reply`) and pass them as W-108's `order_book`; an unreadable orders reply is the same
   409 refusal as an unreadable positions reply (never an empty book: an empty book would make every open plan read
   pending for the wrong reason, or worse be taken as final). Use `result.blocked` (W-108's set) for every blocked
   flag, not compare's mismatches alone.
2. Answer model: a contract row gets `pending: bool` and, when pending, the pending plans (strategy id, plan number),
   with `own` empty and `own_units` / `outside_units` absent or null - not 0 (0 would read as a split). Regenerate
   docs/api/openapi.json (`python scripts/generate_openapi.py`; the one allowed regenerated file).
3. Page (frontend/src/pages/PositionsPage.vue), both views: a pending row shows the two ADR-110 phrases quoted above
   (the waiting line; Zerodha's quantity marked as not yet confirmed), no own/outside split, and a link to
   `/strategy/{id}/execute`. Also fix the blocked text `(blocked: Zerodha holds fewer units than the strategy)`: it is
   wrong for an opposite outside trade and for two strategies on one contract; say only that the strategy is blocked
   until its position matches Zerodha (the text the page header already uses). Grep `frontend/tests/` and
   `frontend/e2e/` for the old text first and update every hit.
4. Tests: route cases above plus: orders reply unreadable -> 409; two strategies on one contract, one pending -> both
   blocked and that row pending; a pending strategy's other contract shows its normal row but blocked. Vitest:
   pending row text, link, no split. e2e positions.spec.ts: the pending row if the replay can serve it, else say why.

## Attack cases the reviewer will run
1. The route passes an empty or partial order book (a failed orders read) -> must refuse, never pending-for-all.
2. A pending row shows 0 own / 0 outside anywhere (route JSON or page) -> fail.
3. A client query/body can influence pending or blocked -> none exists.
4. The page computes any number (sum, difference) -> the browser does no arithmetic.
5. Old blocked text still in any test tree.

## B4 standing items
(a) no time-budgeted job; (b) no new CI import; (c) not a detector; (d) the answer states of both Zerodha reads
(positions: present / absent / flat / unreadable; orders: present final / present not final / absent / unreadable /
empty list) each with a test and a stated result.

Rules: no new duplicated literal (user-visible text has one home: if the page's messages live in a catalogue, put
the two ADR-110 phrases there); reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no
regenerated files except openapi.json. No money figure on this page (part 2). Windows local pytest: `-p no:metadata`.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus: tests_app/test_positions_route.py and tests_app/test_reconcile_attribution.py with -c pytest-app.ini (if the
route test needs the database, through scripts/orchestrator/db_run.py, that file only - the VPS PostgreSQL also serves
IPODhan production); in frontend/: `npm run lint`, `npx vitest run tests/positions-page.test.js`.
