# W-1xx builder brief (lane A5): Saved-strategy actions - delete with undo, private notes, share link, proposal Before/After

Common brief: docs/process/builder-brief.md
Core: every saved-strategy action (delete, note, share, copy a shared plan, propose a change) is a server call that reads the strategy through the signed-in user's reference, so no request can reach another user's strategy or notes.
Proof: step 1 is a DB test file on the real store (`strategy_store`, the limited `ofo_app` role): user A saves a strategy, adds a note, shares it; user B (a second user reference) opens the link and copies it; B's request for A's notes and A's strategy returns not found; A's note holding the text `<script>alert(1)</script>` reads back as plain text. Written before any screen.
Tier: A (new tables = migrations, ownership checks on every read, a link that carries a plan to another user).

## Work item
The orchestrator allocates the W-id, writes `work/W-1xx.md` (requirement_ids REQ-070, REQ-037, REQ-086, REQ-111) and its coverage-stages row; commit them unchanged. Depends on #393 (My Strategies, W-109) merged in Step 1. Migrations: take the next free alembic number AFTER lane A3's setting-table migration; one migration per table, each calling `op.*` directly.

## Spec basis (quoted; remaining ACs only)
REQ-070 AC-6: "Only a strategy that never sent a basket can be deleted"
REQ-070 AC-6: "the draft is hidden from every list and kept on the server with its history for audit"
REQ-037 AC-1: "a leg can never be traded as an unrelated standalone trade"
REQ-037 AC-2: "The proposal recalculates max profit/loss, breakevens, current P&L, margin, charges and risk."
REQ-037 AC-3: "A Before/After comparison is shown before any order is prepared."
REQ-037 AC-5: "Every modification creates a new strategy version; old versions are kept."
REQ-086 AC-1: "Share creates a link to a frozen copy of the plan as it is at that moment"
REQ-086 AC-2: "The link carries a random identifier of at least 128 bits, never the strategy id, and the sharer can revoke it at any time"
REQ-086 AC-3: "a signed-out visitor is sent to sign in and then to the plan"
REQ-086 AC-4: "creates a new draft owned by the viewer with the same legs and planned entries"
REQ-086 AC-5: "The shared copy holds no account data"
REQ-086 AC-6: "Shared plans are never listed, searched, counted, ranked or shown as popular anywhere in the product"
REQ-086 AC-7: "the platform posts nothing itself and the shared message text carries no performance or return wording"
REQ-111 AC-1: "adds a note of up to 2,000 characters of plain text"
REQ-111 AC-2: "Notes are not timeline entries"
REQ-111 AC-3: "a request for another user's strategy's notes is refused with not found, checked on the server"
REQ-111 AC-4: "markup or script in a note is shown as typed, never run"
REQ-111 AC-5: "Notes never leave the platform with an order"
REQ-111 AC-6: "a note written on version 2 is still shown on version 3 with the version it was written on"
Already verified, not re-briefed: REQ-070 AC-1..AC-5 (evidence/W-016, domain `ofo/strategy/builder_history.py`); REQ-037 AC-1, AC-2, AC-4, AC-5 in the domain (evidence/W-027); REQ-009 AC-1..AC-8 (evidence/W-054). REQ-037 AC-4 (adjustment orders prepared and executed) is out of scope (ADR-165: no order is sent).

## Copy from
Copy from: spec/technical-design/legacy-reuse.md strategy section, row `app/models/strategies.py` (57) (REFERENCE: leg shape with Decimal, needs versions and state) for the table shape idea only; frontend row `src/views/StrategyLibraryView.vue` is not used here. Notes, share link, soft delete: Copy from: none - no algochanakya row; Sensibull behaviour below is the model.

## Sensibull screens (study folder D:\Abhay\Ventures\competitors\sensibull\2026-10-21\; never copy a screenshot or account data into the repo)
- 115-119 and 218-224 (BUILDER PASS 2): '...' menu = Save / Save As / Share > (Facebook, Twitter, WhatsApp, Telegram, Copy Link); Saved Strategies tab with search, rename (pencil, max 20 chars), bin = 'Delete Saved Strategy' dialog that really archives (soft delete); loading a saved strategy restores the saved prices.
- 090-092: Draft Portfolios have a notes icon per strategy (the Notes idea).
- Differences kept on purpose: our share is a frozen copy opened only by signed-in users and never listed (REQ-086, ADR-055 (3)); our delete is refused once a basket was ever sent (ADR-118); Sensibull has neither rule.

## What to build
1. Migrations + stores (limited `ofo_app` role, owner role for migrations): `strategy` soft-delete marker (`deleted_at`, who, when) on the existing store (`ofo_app/strategy_store.py`, migration 0008 tables); `strategy_note` (strategy id, version id, user ref, text up to 2,000 chars, created_at, edited_at); `shared_plan` (random token of at least 128 bits from `secrets`, frozen definition JSON, created_by, show_name flag, revoked_at). Times from the database clock like the other stores (finding request-clock-for-database-stamped-fact).
2. Routes: `DELETE /strategies/{id}` + `POST /strategies/{id}/undelete` (Undo within the session), refused with 'Can't delete: orders were sent' when the execution-plan store has any row for it; `GET/POST/PUT/DELETE /strategies/{id}/notes`; `POST /strategies/{id}/share`, `DELETE /shares/{token}` (revoke), `GET /api/shared/{token}` (read-only plan; engine numbers computed for the viewer from the shared planned entries, At Expiry always, live only with the viewer's live data), `POST /api/shared/{token}/copy`. Every handler takes the user reference from the session (as `routes/strategies.py` does), never a body field.
3. Proposal: `POST /strategies/{id}/proposals` (changed legs) and `GET .../proposals/{n}` returning the engine's Before and After side by side (max profit, max loss, breakevens, current P&L, margin, charges) using the domain in `ofo/strategy/modification.py`; accepting a proposal writes a new strategy version and keeps old ones. The comparison view is built as a reusable component: lane D (REQ-046 Opportunity panel) reuses it, so keep its input a plain before / after pair.
4. Frontend: Delete + Undo and 'Can't delete: orders were sent' in My Strategies; Notes section on the strategy page (plain text only, `v-text`, never `v-html`); Share dialog (copy link / device share sheet, 'Show my name' off by default, revoke); shared-plan page (read-only, 'Copy to my strategies'); `components/strategy/BeforeAfter.vue` (new).
5. Share text carries no return or performance words (ADR-003 wording test with an allow-list of the share strings).
6. Regenerate `docs/api/openapi.json`; register new ApiModel classes in `tests_app/test_response_door.py`; add the new tables to the audit allow-list test if `audit_allowlist.py` requires it.

## AC status (main + evidence/)
| AC | Status |
|---|---|
| REQ-070 AC-1..AC-5 | exists, verified (evidence/W-016); API routes for history / restore exist (`routes/strategies.py:360`, `:372`); not re-briefed |
| REQ-070 AC-6 delete | missing |
| REQ-037 AC-1, AC-2, AC-4, AC-5 | exists, verified (evidence/W-027, domain only) |
| REQ-037 AC-3 Before/After | missing (no route, no component) |
| REQ-086 AC-1..AC-7 | missing |
| REQ-111 AC-1..AC-6 | missing |
| REQ-009 AC-1..AC-8 | exists, verified (evidence/W-054); only the Execute entry changes in Step 1 |

## Attack cases
Token guessed or truncated (not found, same answer as revoked, no timing difference); revoked link opened (four-part catalogue error 'This shared plan is no longer available'); shared strategy later edited (the copy does not change); shared strategy that was executed earlier (no fills, funds or P&L in the copy: test with an executed fixture); note of 2,001 characters (refused); note with markup (shown as typed); note for another user's strategy (not found, not 403); delete of a strategy with a basket row (refused); delete then Undo then list (appears once); signed-out visitor opening a link (redirect to sign in, then the plan); viewer copies twice (two drafts, owned by the viewer); shared copy opened with no live data (At Expiry numbers only, stated); two users' tests in one run (no leakage through a shared in-process cache).

Threat model: in scope another user's token, id or note id in a path or body (ownership checked on the server for every read and write), token enumeration, stored script in a note or plan name, a share body that tries to include account fields; out of scope a user who deliberately sends their own link to a stranger, and the transport security of the hosting (MR-140, later).

## Findings checked
Findings checked: caller-supplied-verdict-trusted, identifier-unique-only-by-convention, request-clock-for-database-stamped-fact, store-rule-enforced-per-call-site, sealed-object-mutable-after-seal, advice-wording-denylist-per-module, privilege-guard-as-denylist, guard-without-killing-test, branch-migration-tests-move-shared-db

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step gains an import; (c) applied: the ownership test enumerates every new route from the app's route table and fails when a new route is missing from the owner-checked list (fails closed on routes it cannot classify); (d) applied: answer states of the execution-plan store (no row, row, store unreadable) decide delete (allowed, refused, refused with the reason) and each has a test.
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Targeted tests: tests_app/test_strategy_delete.py, tests_app/test_strategy_notes.py, tests_app/test_shared_plan.py, tests_app/test_proposals_route.py (all new; the migration and store tests run as their own files because they are DB stores), tests_app/test_response_door.py, `python scripts/alembic_migration_guard.py`; frontend: `npx vitest run tests/notes.test.js tests/share.test.js tests/before-after.test.js`, `npm run lint`, `npm run build`.
Rules: no new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated files in the PR (the one exception is docs/api/openapi.json when an API model changes)
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table

## Open
Open: technical: 'signed-in' while login is not built (ADR-165 (8)). Proposal: the shared-link gate checks that the session carries a user reference; the one fixed owner has one today; tests use two references so adding users later needs no rewrite; the redirect target is the existing sign-in route placeholder.
Open: technical: REQ-037 AC-3 appears in lane A's list but its only screen consumer is REQ-046 in lane D. Proposal: build the API and component here (as above) and let lane D import it; if lane D starts first it builds `BeforeAfter.vue` and this PR drops item 3.
Open: business: none found. REQ-086 AC-5 shows the sharer's display name only if ticked; default is off per the AC.

## Legacy map rows (copy_from_check.py)
Rows of spec/technical-design/legacy-reuse.md that name this brief's requirements. Act on each:
COPY/ADAPT -> use it (provenance header) or write in the report why not; REFERENCE -> read before
designing; SKIP -> do not re-survey.

| `services/autopilot/{strike_finder_service,strategy_converter,template_service,suggestion_engine,position_sizing,position_leg_service,leg_actions_service,break_trade_service,staged_entry_service}.py` | REFERENCE | leg exit/add actions break ADR-002 | REQ-027, REQ-037 |
| `src/router/index.js` (234) | ADAPT | structure (lazy routes, meta flags, once-only auth guard); new route table; UX-only entitlement guard | REQ-009 |
| `src/components/layout/KiteLayout.vue` (80), `KiteHeader.vue` (715) | ADAPT | rename and restyle (not Zerodha's look); strip broker switching | REQ-009 |
