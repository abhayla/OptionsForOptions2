## A4 review 4 (2026-11-24): gate commits 8b3b21d7, aa6ea9fb, ef1b1093

Reviewer: fresh-context helper, read-only. Required: behaviour unchanged; the approved line still reads exactly as
ADR-317 gives it. Verdict: PASS (no CRITICAL, no MAJOR).

ADR-317 sentence (`spec/decisions/ADR-317.md:15`): "Not saved: the live price is already at or beyond this level, so
this exit would close the trade straight away. To close now, use Exit." Shipped copies: "Not saved: " +
`render("paper_trigger_already_crossed").what_happened` (`templates.py:1043`, `PaperStops.vue:44`), compared with `==`
in Python: match; `frontend/tests/paper-stops.test.js:130`: match; `tests_app/test_paper_triggers_routes.py:509`
`CE_SENTENCE`: match (read by eye); `template_pins.json`: hash only. No broker name in either crossed-level sentence.
The lower-case pin of ef1b1093 matches the ADR, where the sentence follows "Not saved: ".

aa6ea9fb: `safety._key is duplicate_leg.contract_key`; `duplicate_leg_failure` builds the same CheckFailure as before;
`paper_duplicate_leg` is identical; no importer of the old `safety.paper_duplicate_leg` remains. No check lost.

Findings:
1. MINOR `PaperStops.vue:44`, `frontend/tests/paper-stops.test.js:100,201`: 8b3b21d7 removed the lower-casing regex, so
   every other refusal after "Not saved: " now keeps its capital ("Not saved: That stop already fired.", also
   paper_trigger_nothing_open and paper_trigger_level_invalid). Compatible with ADR-317 (5) ("Not saved: <that
   reason>"); the tests were flipped to match and the commit message does not say so.
2. MINOR `backend/ofo/errors/templates.py:1043,1049`: the two crossed-level templates are lower-case in the API
   `what_happened`, correct only behind "Not saved: ". Only emitter: `routes/paper.py:1420`, called with saving=true.
3. MINOR `tests/errors/template_pins.json:4286-4293`: the "owner read 2026-11-23" label sits on a new hash; the leg
   sentence ("... this stop would close the leg straight away ...") is still `pending owner read` and is not in ADR-317.

Attacks run and passed: `pytest -k "template or pin"` over tests; tests/errors, tests/execution,
tests/strategy/test_builder_history.py; test_door_names_private, test_kite_http_guard, test_gates_import_no_flags;
vitest paper-stops (21 tests).

Behaviour unchanged: yes for the approved line and the duplicate-leg check; no for the first letter of other refusals
(finding 1, MINOR).
