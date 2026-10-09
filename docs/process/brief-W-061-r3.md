# Builder brief: W-061 round 3 - a positive shape validator in the database (independent review, 2026-10-09)

Core: one IMMUTABLE plpgsql validator that walks the closed strategy-definition shape positively (exact key sets,
one typed predicate per slot, arrays only where the shape has an array), called from the existing guard triggers of
`strategies` and `strategy_history`; and the same for history change items.
Proof (step 1, real ADR-048 database as ofo_app): a GENERATED test - every position of the closed shape x every JSON
type other than the allowed one (null, bool, number, string, array, object, and the correct value wrapped in an array)
- is written first and run red against 5b372b1 (today `{"objective":["income"]}`, `legs: [[leg]]`, `legs: []`,
strike `"LTP 22950.35"` and quantity `22950.35` are all ACCEPTED - reproduced 6 of 6 by the orchestrator), then green.

Tier: A. Model: sonnet/medium (kit routing: builder, always).
Budget: 60 min wall-clock, 75 tool calls. Order: generated tests (red) -> definition validator -> change-item validator
-> domain slot fixes -> agreement test. Commit after each; at budget stop after a commit and report done / not done /
next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - mirrors this repo's own `backend/ofo_app/alembic/versions/0002_audit_store.py` (the
`CONFORMS_FUNCTION` positive walker, lines ~319-379), not an algochanakya module.

## RCA, Class, review (defect-fix contract; learning R1-R2)
- RCA: both rounds built the database guard as a LIST OF REFUSALS (round 1: no number where a decimal goes; round 2:
  13 jsonpath "refuse if this finds X" paths in lax mode, leg values typed but not valued), and the tests were a hand
  list of 21 bad documents, so anything the author did not imagine passes. Finding:
  `knowledge/findings/jsonpath-check-lax-mode-unwraps-arrays.json` (on the docs branch).
- Class: every stored strategy definition and history change summary, on both tables, from any writer including raw
  SQL as ofo_app or the owner. Before: 6 of 6 reviewed shapes accepted. After: every position x wrong type refused.
- Independent review (Fable, 2026-10-09), accepted in full: (1) the approach is the defect, not a missing case; (2)
  approach (b), a positive walker, covers the class; strict jsonpath (a) stays a denylist; relational columns (c) are
  stronger but far bigger while W-061 is parked; (3) change items need the same walker; (4) the generated test list
  below. Orchestrator checks: the 0008 allowlist forbids EXECUTE for ofo_app (`0008_strategy_store.py:33`, `:283`) so
  the validator runs inside the existing SECURITY guard triggers (pinned by md5, `:233-253`), not a CHECK;
  `definition.py:319` `_leg_text` renders `leg["quantity"]` unchecked.
- Detection: the generated enumeration test IS the detection; also mark the finding's detection `guarded` in the
  PR body (the orchestrator updates the JSON).

## Spec basis
- REQ-038 AC-5: "live prices are never saved inside the strategy."
- ADR-064 decision: "Any other name is refused on every path that builds or loads a definition"
- ADR-069 decision: "short identifiers
  or numbers only - letters, digits, underscore, hyphen and dot, at most 64 characters"

## Start
- Worktree `C:\Abhay\Ventures\OptionsForOptions2-W-061`, branch `build/W-061-save-draft` at 5b372b1 (main has not
  moved since round 2's merge; the orchestrator merges main again before the PR merges).
- Read: `0002_audit_store.py` (~300-430, the walker and how its trigger calls it), `0008_strategy_store.py`
  (`_shape_checks`, `_strategies_guard_sql`, `_history_guard_sql`, the md5 pins), `backend/ofo/strategy/stored_form.py`
  `from_document` (the domain's positive walk - the database must accept exactly what it accepts),
  `backend/ofo/strategy/definition.py` `render_change_items` / `_leg_text`, and
  `tests_app/test_strategy_closed_shape.py`.

## What to build (0008 is not on main: rewrite it in place, then downgrade 0007_broker_sessions + upgrade head)
1. **Definition validator** (IMMUTABLE plpgsql, `RETURNS boolean`, `EXCEPTION WHEN others THEN RETURN false`):
   top-level key set exactly {schema_version, underlying, legs, rules_ref, risk_limits, preferences}; schema_version
   integer = the column; underlying in (NIFTY, SENSEX) = the column; legs an array of 1-20 objects, each key set
   exactly {contract_id, action, instrument, strike, expiry, quantity}: contract_id integer > 0, action and instrument
   in their enum sets (read them from `ofo.engine.legs`), strike a decimal string (the domain's form) and null only for
   FUT, expiry an ISO date that round-trips, quantity integer > 0; rules_ref null or the ADR-069 pattern; risk_limits
   an object whose keys are ADR-064's three names and values decimal strings as the domain accepts; preferences an
   object whose keys are ADR-064's six names and values strings of the ADR-069 pattern. Called from both guard
   triggers on INSERT and UPDATE; refusal raises SQLSTATE 23514 (check_violation) so existing tests keep their code.
   Remove round 2's `_shape_checks` jsonpath CHECKs (keep only what the walker does not cover, e.g. `jsonb_typeof =
   'object'` if you want a cheap first line - not required).
2. **Change-item validator**, same style: `change_summary` becomes JSONB; an array of 1..N objects; each object's key
   set equals its kind's set exactly; every slot typed (underlying old/new in {NIFTY, SENSEX}; leg = the definition-leg
   predicates minus contract_id; before/seq integer > 0; field.map/name on the closed lists, old/new null or the
   map's pattern). Called from the history guard trigger.
3. **Domain slots**: `render_change_items` validates every slot with the same predicates (fix `_leg_text`'s quantity,
   `underlying`, `quantity.before`, `restored.seq`), so `summary_text` refuses what the database refuses.
4. Pin both validator bodies with the existing md5 mechanism; ofo_app gets no EXECUTE (assert it).

## Tests (write 1-3 first, red)
1. GENERATED enumeration, both tables: for every position (6 top keys, 6 leg keys, 3 limit names, 6 preference
   names, rules_ref) x every JSON type other than the allowed one, plus the correct value wrapped in an array ->
   23514. Generate the cases from one table of positions in the test, not a hand list of documents.
2. Value predicates: `"LTP 22950.35"` at strike/action/instrument/expiry/rules_ref/a preference; `22950.35`, `0`,
   `-1`, `true` at contract_id/quantity; `"2026-02-30"` at expiry; `"1E+3"`, `"-5"` at a limit; null strike on a CE.
3. Key sets: an extra and a missing key at every object level and in a leg; `legs: []`, `[[leg]]`, 21 legs, a leg
   that is a string.
4. Change items: the same generated matrix per kind on `change_summary` (admin engine), and each kind's real example
   accepted.
5. Agreement: every generated document is refused by `stored_form.from_document` exactly when the database refuses
   it, and the real Iron Condor plus every allowed name is accepted by both.
6. Allowlist: both validator bodies match their md5 pins; ofo_app has no EXECUTE on them.
Keep round 2's tests green (the 0008 downgrade-with-row test included).

## Reviewer checklist (mutation, each must turn a test red)
- Let an array through at one position; drop the leg key-set equality; accept a fractional quantity; accept a
  sentence at strike; drop one change-item kind's slot check; call the validator only on INSERT, not UPDATE.

## Rules (this PC is the Windows VPS that also serves IPODhan production's database - owner decision 2026-10-09)
- Targeted test files only. NEVER the full app suite, Playwright, npm or `tools/ci_local.py`; CI runs them. Domain:
  `python -m pytest -q -p no:cacheprovider tests/strategy tests/errors`. DB, from the main checkout:
  `python scripts/orchestrator/db_run.py C:\Abhay\Ventures\OptionsForOptions2-W-061 python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_closed_shape.py tests_app/test_strategy_store.py`
  (db_run now finds `C:\Abhay\GLOBAL.env` itself). DB tests must show 0 skipped.
- Logs to `%TEMP%`, tail only. Start no servers. Each gate its own command; commit/push in a separate command.
- Do not edit kit files or `spec/`. Never write `evidence/`. Never mark anything verified/reviewed.
- Commit and push `build/W-061-save-draft`. Do not touch the PR.
