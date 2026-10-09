---
work_item: W-061
ac: AC-5
requirement: REQ-038
ac_fp: "c6cee64b494e"
result: pass
verified_by: "verifier (opus, fresh context, 2026-10-09 re-check at d454da6)"
builder: "builder (sonnet; rounds 2-4 2026-10-09, round 1 opus)"
date: '2026-10-09'
commands: "git worktree add --detach <scratch>/verify/W-061b origin/build/W-061-save-draft (d454da6); python tools/ac_fp.py REQ-038 AC-5 --yaml --root <wt>; python -m pytest -q -p no:cacheprovider tests/strategy tests/errors; python scripts/orchestrator/db_run.py <wt> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_store.py tests_app/test_strategy_closed_shape.py tests_app/test_strategy_shape_matrix.py; db_run.py <wt> ... tests_app/test_zz_verifier_w061.py (throwaway test file, run as ofo_app); db_run.py <wt> ... test_zz_verifier_w061.py test_strategy_store.py -k 'round_trip or core_proof'; git diff 3f14653 d454da6 --stat -- evidence"
---

AC: AC-5
result: pass
commands: git worktree add --detach <scratch>/verify/W-061b origin/build/W-061-save-draft (d454da6); python tools/ac_fp.py REQ-038 AC-5 --yaml --root <wt>; python -m pytest -q -p no:cacheprovider tests/strategy tests/errors; python scripts/orchestrator/db_run.py <wt> python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_strategy_store.py tests_app/test_strategy_closed_shape.py tests_app/test_strategy_shape_matrix.py; db_run.py <wt> ... tests_app/test_zz_verifier_w061.py (throwaway test file, run as ofo_app); db_run.py <wt> ... test_zz_verifier_w061.py test_strategy_store.py -k 'round_trip or core_proof'; git diff 3f14653 d454da6 --stat -- evidence
observed: domain 970 passed; DB 132 passed, 0 skipped; core proof with all 3 limits, 6 preferences and rules_ref passes twice through a new engine; my own history round trip (0.05 / 1234567.890 / 0, range-bound, rules-set_1.v2) through a new engine: hist[0].saved == first, stored text keeps 1234567.890; my later assertions did not run because I assumed the limits keep the order I typed (the store sorts them by name); evidence diff shows only W-064/AC-3.md and AC-5.md; no builder commit touches work/ or evidence/
attack: 59 cases as ofo_app, all rolled back: 30 bad definition inserts (array-wrapped preference/limit/rules_ref, legs [[leg]], empty legs, strike/action sentence, quantity 22950.35/65.5/'65', top-level ltp/LTP, preference keys ltp/last_price, leg last_price/ltp, trailing newline/space, empty, 65 chars, nested, null, underlying sentence, expiry with time, contract_id as string, schema_version 1.5, other object, duplicate key where the last one wins) all 23514; 14 bad change summaries (field/underlying sentence, extra ltp key, a plain sentence, array of sentences, array-wrapped old value, string seq, leg_added with last_price, fractional before, empty, extra note, limit sentence, name ltp, strike sentence) all 23514; 4 UPDATEs to a bad definition after a valid history entry all 23514; 6 privilege attacks (disable trigger, replica role, replace or drop the validator, UPDATE history, DELETE) all 42501; 4 domain cases (sentence, array, float limit, 65.5 quantity) all StoredFormError; the good control insert was accepted. 0 accepted.

Recorded by the orchestrator from the verifier's returned block.
Recorded 2026-10-09 at PR #134 head d454da6; replaces the 2026-10-08 record (18ff326), which a later Tier A
verification failed (issue #165). Since then: round 2 (ADR-069 value type, typed history items; DB CHECK still open,
6 of 6 live-price shapes reproduced), independent review (Fable: the refusal-list approach was the defect), round 3
(positive plpgsql validators in the guard triggers, generated matrix) with a Tier A adversarial review "covers the
class: yes" (63 value attacks, privilege probes, mutations M1-M6 all red), round 4 (filled limits/preferences round
trip; the 2026-10-08 coverage gap of issue #138). Review minors deferred: issue #167.
