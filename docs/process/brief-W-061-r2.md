# Builder brief: W-061 round 2 - three Tier A defects (issue #165), branch brought onto main

Core: one value type for settings values that every path (API body, `build_from_catalogue`, `strategy_store.save_draft`/
`update`, load) goes through, plus a database CHECK that refuses a definition outside the closed key shape.
Proof (step 1, real ADR-048 database as ofo_app): a raw INSERT, as `ofo_app`, of a definition holding `ltp`, `Spot`
and a nested `last_price` is REFUSED by PostgreSQL (today it is accepted - measured 2026-10-09, issue #165), and
`strategy_store.save_draft` with preference value `"LTP is 22950.35 buy now"` raises the ADR-069 refusal. Write both
tests first, run them red against 3f14653, then fix.

Tier: A. Model: sonnet/medium (kit routing: builder, always).
Budget: 60 min wall-clock, 75 tool calls. Order: merge, defect 2 (DB), defect 1, defect 3. Commit after each defect; at budget stop after a commit and report done /
not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - fixes inside W-061's own new modules; no algochanakya module covers a closed JSON shape check.

## RCA and Class (defect-fix contract)
- RCA: each rule was enforced at one door (the API body for ADR-069, the loader for the key shape, a text check for
  summaries), so any other path that writes the same data skips it.
- Class: every path that writes a strategy definition or a history summary: the API routes, `build_from_catalogue`,
  `strategy_store.save_draft`, `update`, `restore`, and a raw SQL write as `ofo_app`. Before: 1 of these paths
  refuses a sentence value; 0 refuse a live-price key at the database. After: all of them, and the database itself.
- Proof: the two step-1 tests above, run against the real `ofo_test` database (not skipped), red before and green after.
- Detection: the database CHECK and the domain value type ARE the detection (structural, not a list of bad words).

## Spec basis
- REQ-038 AC-5: "live prices are never saved inside the strategy."
- ADR-069 decision: "short identifiers
  or numbers only - letters, digits, underscore, hyphen and dot, at most 64 characters"
- ADR-069 decision: "is refused on save with the
  fixed input error (HTTP 422) and is never echoed back."
- ADR-064 decision: "Any other name is refused on every path that builds or loads a definition"

## Start
- Worktree `C:\Abhay\Ventures\OptionsForOptions2-W-061`, branch `build/W-061-save-draft` (at 3f14653). Work only there.
- FIRST `git merge origin/main` (main is 12 commits ahead: W-058, W-064, #164 and status batches). Keep both sides
  in `docs/process/coverage-stages.yaml`, `coverage-register.md`, `tests/errors/template_pins.json`,
  `backend/ofo_app/main.py`, `backend/ofo/errors/templates.py`; regenerate generated files, never hand-merge them
  (`python tools/build_findings_index.py .`, the spec digest via `python tools/ci_local.py` PIN lines). Commit the
  merge alone, then run `python scripts/orchestrator/merge_audit.py . 3f14653 origin/main HEAD` and paste its result.
- Read `backend/ofo/strategy/definition.py` (`_named`, `_limit_value`, `_preference_value`, `render_change_items`),
  `backend/ofo/strategy/stored_form.py` (`to_document`, `build_from_catalogue`, `summary_text`, `render_summary`),
  `backend/ofo_app/strategy_store.py`, `backend/ofo_app/routes/strategies.py`, migration
  `backend/ofo_app/alembic/versions/0008_strategy_store.py`. Issue #165 (`gh issue view 165`) has the measurements.

## What to fix
1. **ADR-069 in the domain value type.** One stdlib type/validator in `backend/ofo/strategy/` for a settings value
   (`^[A-Za-z0-9_.-]{1,64}$`, or a finite Decimal for risk limits) used by `_preference_value`, `_limit_value` and the
   rules reference, so the API, `build_from_catalogue`, the store and load all inherit it. Remove the API-only check
   (one door). The API answers the fixed input error 422 without echoing the value. Tests: domain (`tests/strategy/`)
   for each path, and `tests_app` asserting the API 422 body does not contain the sent value.
2. **Database CHECK for the closed shape** (edit 0008 in place - it is not on main yet). On both `strategies` and
   `strategy_history`: top-level keys exactly schema_version, underlying, legs, rules_ref, risk_limits, preferences;
   each leg exactly contract_id, action, instrument, strike, expiry, quantity; `risk_limits` keys only ADR-064's three
   names with decimal-string values; `preferences` keys only ADR-064's six names with values matching the ADR-069
   pattern; `rules_ref` null or the pattern. Use jsonpath (`keyvalue()`, `like_regex`) or an IMMUTABLE SQL function.
   Real-database tests as `ofo_app`, one per refused case: top-level `ltp`, `Spot` in preferences, nested `last_price`
   in a leg, an unknown risk-limit name, a sentence value; and the real Iron Condor still inserts.
   Then on the DB: `alembic downgrade 0007_broker_sessions` and `upgrade head`, plus a new real-database test of
   downgrade-then-upgrade WITH a row present (the open item in #165).
3. **Typed history summaries, never repr.** A `field` change item carries `map` (risk_limits | preferences |
   rules_ref), `name` (closed list) and `old`/`new` as the step-1 value type (absent = null), one item per changed
   name; it renders through a catalogue template in `backend/ofo/errors/templates.py` (pin it in
   `tests/errors/template_pins.json`). `summary_text` refuses free text in any slot. Test: the real summary that today
   shows `risk_limits "(('max_loss', Decimal('9000.50')),)" -> ...` now renders from the template with `9000.50`, and a
   field item with `"LTP is 22950.35 buy now"` is refused on write and shows the fixed unreadable line on read.
   List every new template line in `docs/process/w024-templates-for-owner.md` (owner reads them).

## Reviewer checklist (write these first; each must turn a test red when mutated)
- Mutation: drop the value-type call from `build_from_catalogue`; widen the pattern to allow a space; remove the
  leg-keys part of the CHECK; remove the preferences-value part of the CHECK; render a field item with `repr`.
- Every path in the Class list refuses a sentence value; the API 422 never contains the sent text.
- Fail closed: a refused update stores nothing (one transaction); history is unchanged.
- Expected values from the real fixture and the spec, never from running the code.

## Rules (this PC is the Windows VPS that also serves IPODhan production's database - owner decision 2026-10-09)
- Targeted test files only. NEVER run the full app suite, Playwright, `npm run build` or `ci_local.py` here; CI runs
  them. Domain: `python -m pytest -q -p no:cacheprovider tests/strategy tests/errors`. DB: from the main checkout,
  `OFO_GLOBAL_ENV='C:\Abhay\GLOBAL.env' python scripts/orchestrator/db_run.py C:\Abhay\Ventures\OptionsForOptions2-W-061 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_store.py`
  (and the other tests_app files you touch). DB tests must show 0 skipped.
- Output to a log file under `%TEMP%`, tail only. Start no servers; stop any process you start.
- Never chain a commit/push after a gate on the same line; run each gate as its own command.
- Do not edit kit files or `spec/`. Never write `evidence/`. Never mark anything verified or reviewed.
- Commit and push `build/W-061-save-draft`. Do not open, edit or merge the PR.
