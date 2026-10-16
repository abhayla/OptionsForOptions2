# GC-2c contract: independent review record (chain rule 3)

Reviewer: fresh Opus agent, read-only (Explore type), not the author; run 2026-10-17 ~03:50 IST on the draft in the
GC-2b close-out branch. Raw output below, verbatim, then the orchestrator's decision on each finding.

## Reviewer output (verbatim)

1. **MAJOR: the Core/Proof cannot match tags as written.** The Proof says to "POST Execute on the strategy of the 2026-10-16 order" (contract:15-17) and match by tag. The recorded orders carry `OFS1V1L0` for entry and `OFS1V2L0` for exit (`tests/fixtures/kite_replies/orders-151006.json:38,79`). So the test has to create strategy id 1 at version 1, and version 2 for the exit. A database-assigned id will not match. The contract also has no Execute step for the exit. Fix: name how the test seeds strategy 1 v1/v2, or how tags are mapped.

2. **MAJOR: the time plan does not fit 6 h.** Items 1-2 are Tier A, about 1-1.5 h each, so about 3 h. Add the 1.5 h tail and 4.5 h is gone. Item 5b runs "before item 3 if 1 h + tail remain" (contract:55-56), and item 3 needs "2 h + tail" (contract:44). Both cannot fit. Item 5b is also missing from the give-way order (contract:8), and it is unclear whether "item 5" includes 5b. Fix: put 5b in the give-way order explicitly, and state that items 3-4 will realistically park.

3. **MAJOR: item 3's migration handling is unsafe.** It runs "its one DB test file locally through `db_run.py`" (contract:45-46) but does not name `branch-migration-tests-move-shared-db`. That finding's fix is to check `alembic current` afterwards and restore main's head, or use a throwaway database (`wt-2bdocs/knowledge/findings/branch-migration-tests-move-shared-db.json:11`). The finding is not on main yet: it exists only in the docs worktree. Also, #313 requires the fills and adopted holdings to be stored "in the same transaction as the strategy version", but the contract item omits that (`gh issue view 313`).

4. **MINOR: "offline" is overstated.** The route-level Proof needs the strategy store (`backend/ofo_app/routes/strategies.py:42`), so it is a database test. It is runnable through `db_run.py`, but under the fast-delivery rule it belongs in CI.

5. **MINOR: "audited" is in the title (contract:1) and the chain row ("-> audit", `goal-chain.md:27`), but no item covers it** (REQ-064 is the audit log). Either add an item or drop the word.

6. **MINOR: item 4 does not point to the owner-questions file itself.** The screen layout and the return view go beyond REQ-073's single example (`REQ-073.md:53-54`). Repeat the Stops line inside item 4, plus the ADR-003 wording rule.

7. **MINOR: the named functions exist and fit their roles, but some names are imprecise.**
   - `fresh_registry` is "W-092's function" (`origin/main:eligibility_from_zerodha.py:82`); name it.
   - `checked_basket` needs an exact `KiteMargin` client and a `freeze_check` (`checked_basket.py:59-60`). The offline funds fixture exists (`tests_app/test_checked_basket.py:32`); the brief should name it and the freeze source.
   - The local main checkout (`d61fcfb`) is behind `origin/main` (`a16212b`) and lacks `eligibility_from_zerodha.py`. The `git pull` in chain rule 2 fixes this.

Verdict: READY WITH CHANGES

## Decisions (orchestrator)

| # | Decision | Applied as |
|---|---|---|
| 1 MAJOR | ACCEPTED | The proof seeds strategy id 1 at versions 1 and 2 (tags OFS1V1L0 / OFS1V2L0) and has an Execute step for the exit (v2). |
| 2 MAJOR | ACCEPTED | Give-way order: 5b, then 5, then 4, then 3; items 3 and 4 stated as expected to park. |
| 3 MAJOR | ACCEPTED | Item 3 names the finding (check `alembic current` and restore main's head after any local replay; prefer CI), requires a real downgrade, and states #313's same-transaction rule. The finding lands on main with the GC-2b close-out PR. |
| 4 MINOR | ACCEPTED | The proof is named a DB test proven by CI; locally only that one file through `db_run.py`. |
| 5 MINOR | ACCEPTED | "audited" dropped from the title; a line says REQ-064 audit events are a later item. (The chain row is rewritten with GC-2c's NEXT marking.) |
| 6 MINOR | ACCEPTED | Item 4 repeats the owner-questions rule and ADR-003's wording rule, and takes W-081's AC-3 labelling caveat. |
| 7 MINOR | ACCEPTED | `fresh_registry` and `checked_basket` named exactly with their inputs (exact `KiteMargin` client, the funds fixture of `tests_app/test_checked_basket.py`, a named freeze-limit source). The pull is already chain rule 2. |
