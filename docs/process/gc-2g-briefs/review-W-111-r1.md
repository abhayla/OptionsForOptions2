# Review brief: W-111 Positions part 1 round 1 (PR #410, head 23881c7, stacked on #398) - Tier A, fresh, narrow

Common brief: docs/process/builder-brief.md (review task: read-only; hands-on attacks first)
Core: GET /api/positions passes Zerodha's order book to W-108 and shows a pending contract exactly as ADR-110 says;
no own/outside split for it, the strategy blocked, a link to its Execute screen; no client input can change a verdict.
Proof: each finding cites path:line and a command run this turn.
Spec basis: ADR-110; ADR-109 (2), (5); REQ-044 AC-3; REQ-060 AC-7; ADR-027.

ADR-110: "makes no own/outside split for it"
ADR-110: "Order placed - waiting for Check with Zerodha"
Copy from: none - a review.
Findings checked: caller-supplied-verdict-trusted, verified-on-a-module-the-product-does-not-call, test-asserts-implementation-output, state-with-no-working-exit
Threat model: in scope - the two Zerodha reads (positions, orders) and every failure of each, the answer model (pending rows, null not 0, blocked flags), the page text and links, no browser arithmetic; out of scope - W-108's attribution logic (reviewed, PASS at 05ae2c5), P&L/risk (part 2), route wiring of Execute/return (GC-3F).
Why Opus: Tier A review of a route that reads Zerodha positions and orders and shows position quantities.
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table

Checkout (read-only; scratch scripts in a NEW folder under the same scratchpad):
C:/Users/itsab/AppData/Local/Temp/claude/D--Abhay-Ventures-OptionsForOptions2/6e6d07e9-9c28-471b-b352-b399378b3504/scratchpad/w111
Read: docs/process/gc-2g-briefs/brief-W-111-rebase.md (main checkout), then `git diff origin/build/W-108-attribution
HEAD -- backend frontend/src frontend/tests frontend/e2e tests_app` in the checkout.

Attacks:
1. Orders read fails / raises / returns a non-list / returns [] while a plan is open: does the route refuse (409) or
   pass an empty book? Is an EMPTY list (a real day with no orders) treated correctly (absent rows -> pending for an
   open plan, which is ADR-110's answer)?
2. A pending row: does any field read 0 for own/outside (JSON or page)? Is the strategy's link present on BOTH views
   (current and linked)? Is a second holder on a pending contract shown blocked (`blocked_strategy_ids`)?
3. Is `blocked_strategy_ids` derived only from `Attribution.blocked` and the contract's holders - can it name a
   strategy of another user or a strategy not on that contract?
4. Any query/body/header that changes pending or blocked? Any arithmetic in the Vue page?
5. Old blocked text gone from every tree (grep `holds fewer units`).
6. The e2e test for the pending row: does it exercise the real route or only a browser mock? If only a mock, say what
   is unproven end to end.
7. Run the route tests through `python scripts/orchestrator/db_run.py <checkout> python -m pytest -q -p no:cacheprovider -p no:metadata -c pytest-app.ini tests_app/test_positions_route.py` (that one file only: the VPS PostgreSQL also serves IPODhan production) and, in frontend/, `npx vitest run tests/positions-page.test.js` if node_modules is present.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests (reviewer: only the files named in attack 7)
Report (under 300 words): verdict PASS / REVISE, findings (CRITICAL/MAJOR/MINOR, path:line, one-line fix), covers the
class (every Zerodha read state x every attribution state shown on the page): yes/no, evidence table.
