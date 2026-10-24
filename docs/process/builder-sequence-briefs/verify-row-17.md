# Verifier brief: row 17 (W-145) - UX levels removed, one full screen for everyone (Tier A checker)

Common brief: docs/process/builder-brief.md (checker part). Fresh context, adversarial, read-only: edit no file,
commit nothing. Copy files to your scratch folder for every mutation. No database over the tunnel.
Why Opus: `backend/ofo/table/columns.py` is in the safety set (SAFETY_SET in scripts/orchestrator/measure_process.py).

Spec basis: ADR-168 (4) "the three UX levels (Guided, Standard, Advanced) are removed; there is one level for
everyone" and "every rule that shows or hides something by level is rewritten to one level"; ADR-168 (5) "The one level
shows everyone the full builder" and "Guided creation (REQ-024) stays as its own Create Strategy screen, not a level".
REQ-006 and REQ-007 are Superseded, so their old criteria are NOT checked; this row is checked against ADR-168 (4)(5).
Reference: screens 010, 011, 012, 014, 015, 168, 206 - copy the one full builder with no level switch; open RD-122, RD-123, RD-124, RD-125 (RD-124/125 belong to REQ-035, row 18: not checked here)

What was built (branch `build/seq-chunk-2`, worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`; diff from
cf30134e): spec parts A1-A3 (decisions, vision, invariants, registers, 13 requirements, re-pins; REQ-035 back to
Approved), backend B1a (table and outcome take no level, one column set) and B1b (outcome route ignores a stray
`ux_level`, other unknown keys still 422; `advanced_details` renamed `leg_quotes`, sent for every live answer, absent
when not connected / not live), frontend B2a/B2b (no level switch, no `?ux=`, no `ux_level` in any request, details
block read from `leg_quotes`).

For EVERY check say which screen or route shows it and whether you exercised it THERE (finding
verified-on-a-module-the-product-does-not-call). Hands-on attacks first.

## Checks (one verdict block each: pass / fail / partial, with the command and its output line)
1. Spec: Grep `spec/` for `Guided|Standard|Advanced|UX level|ux_level`: every hit is a difficulty label (Q117/ADR-032),
   the guided creation path (REQ-024/069, ADR-005/006), the phrase Standard deviation, a superseded REQ-006/007/011, or a
   note saying the level clause was rewritten or removed. Safety clauses (ADR-004 Q32, ADR-029, invariant 19,
   REQ-036, REQ-063) still forbid the bypass for every user. No open question was answered (Q264 still open).
2. One column set: the outcome route `POST /strategies/outcome` (TestClient, DB-free, or the tests_app files that need
   no database) returns every column (IV, Greeks, % return, breakevens) in the locked order - compare the order with the
   Advanced list at cf30134e (`git show cf30134e:backend/ofo/table/columns.py`).
3. Request handling: a body with `ux_level: "guided"` returns the same outcome as one without it; a body with another
   unknown key returns 422; the response has no `ux_level` key.
4. `leg_quotes`: present with Bid/Ask for a live computed answer, absent for not connected and not live; the
   not-connected / not-live / stale responses are otherwise unchanged from cf30134e (same fields, same sentences).
5. Builder screen (`/strategy/builder`, `frontend/src/pages/StrategyBuilderPage.vue`): mount it in vitest with the
   level-free fixtures - no Guided/Standard/Advanced control; the details block renders from `leg_quotes`; an old
   `?ux=guided` link opens the same full screen; the outcome request body has no `ux_level`. Grep `frontend/` for
   `ux_level|uxLevel|data-ux|advanced_details|advancedDetails|\?ux=` -> nothing outside deliberate negative tests.
6. Create Strategy (`/strategy/create`): the guided path opens the builder with the drafted legs and only a `draft`
   query; the manual path key `'advanced'` still opens an empty builder (REQ-024).
7. Execute page and live card payloads carry no `ux_level`.
8. Mutation (Tier A): on scratch copies, (a) re-hide one column from the one set, (b) send `leg_quotes` when not live,
   (c) refuse a request carrying `ux_level` again, (d) frontend: read `advanced_details` instead of `leg_quotes` - each
   must be killed by a test; quote which.
9. Gates: `python -m pytest -q -p no:cacheprovider tests/table tests/outcome`, the guard tests line below, `python
   scripts/orchestrator/reach_check.py` (exit 0), and in `frontend/` `npx vitest run` on strategy-table, strategy-live,
   create-strategy, feed-reconnect, leg-picker (node_modules: `D:\Abhay\Ventures\OptionsForOptions2-row17b2\frontend`
   has them; run the frontend checks there after confirming its HEAD equals the chunk head you check, or say it does not).

Threat model: in scope - a column or the details block still hidden for anyone, a level still read or sent anywhere, a
safety clause weakened, a not-live state changed, an open question answered; out of scope - row 18's table criteria
(REQ-035 is re-verified at row 18), Playwright e2e (CI runs it on draft PR #531).
Findings checked: verified-on-a-module-the-product-does-not-call, brief-rule-from-memory

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table - one block per check 1-9 (verdict, screen/route, exercised there yes/no, command, output line),
then numbered findings CRITICAL / MAJOR / MINOR with file:line. Under 500 words.
