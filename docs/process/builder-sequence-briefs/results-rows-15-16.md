# Verifier results: rows 15-16 start check (REQ-028, REQ-038), 2026-10-23 - for recording evidence at their close

Opus verifier, fresh context, head 0e574b58 (brief `verify-rows-15-16.md`). Scratch (may be gone later; this file is
the record): `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\7a0c81e3-1fa0-4c0c-ab2b-6ae5a07ae075\scratchpad\verify-15-16`.
Suites: tests/strategy + tests/reconciliation 690 passed; guard tests 1399 passed; repo_scan 1231 passed + 1 file-lock
flake (passed alone). Mutation gate: 7 killed, M7 and M9 survived (second guards behind a working first guard).

| Row | REQ | AC | Result | Observed (file:line) / attack |
|---|---|---|---|---|
| 15 | REQ-028 | AC-1 | pass | 6 legs, all six leg types, 2 expiries: built, valid StrategyDefinition, labelled Custom Strategy; 5 legs over 3 expiries -> Custom |
| 15 | REQ-028 | AC-2 | NOT CHECKED | tests/strategy/test_modification*.py pass; no attack run within budget - needs a short check |
| 15 | REQ-028 | AC-3 | pass | a new template added as data only matches (22 templates load; 25050/25200/25350 -> 'Call Ladder Scratch' k=1 w=3); a duplicate shape is refused at load; mutant M8 (loader overlap check) killed |
| 15 | REQ-028 | AC-4 | pass | matching.py:132 returns Custom when nothing fits |
| 15 | REQ-028 | AC-5 | pass | no per-strategy branch in backend (only underlying-name compares in execution/safety.py, send_guard.py); M9 (matching.py:130) survived, minor |
| 16 | REQ-038 | AC-1 | pass | definition and live-state field sets do not overlap; 'ltp' on a leg -> unknown_key; M6 killed |
| 16 | REQ-038 | AC-2 | FAIL (MAJOR) | domain only: PUT /strategies/{id} -> strategy_store.update (strategy_store.py:221) had no execution check; migration 0008 status 'draft' only; no versions table. Built in row 16 (migration 0022, b5855c17) - re-verify |
| 16 | REQ-038 | AC-3 | FAIL (MAJOR) | the app never called propose_execution/confirm/apply_result. Built in row 16 - re-verify |
| 16 | REQ-038 | AC-4 | pass | versions.py:486-490 recorded actual = broker position; M2 killed by 9 tests |
| 16 | REQ-038 | AC-5 | partial (DB part) | dumps/loads exact ('44.90', '+05:30'); float price refused; ADR-085 text verbatim (legPicker.js:10, explanations.py:945); M5 killed; DB part = CI #525 |
