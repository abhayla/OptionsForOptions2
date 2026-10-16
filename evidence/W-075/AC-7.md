---
work_item: W-075
ac: AC-7
requirement: REQ-034
ac_fp: "5250eb0c6b9d"
result: pass
verified_by: "verifier (Sonnet, independent, Tier B, 2026-10-16 GC-2a)"
builder: "builder (Opus, PR #311, 2026-10-16)"
date: '2026-10-16'
commands: "git worktree add --detach <SCRATCH>/verify/W-075 origin/main (901d3ee); python -m pytest -q -p no:cacheprovider tests/outcome/test_charges_in_sentences.py tests/scenario/test_expiry_values_with_charges.py; python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py; python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_charges_wiring.py; independent hand computation of the 8 orders from the migration 0012 rates; to_paise_up attacks; _summary_of_legs on replay frames (sold put only, bought call only, condor, bull put; with and without rates); python tools/ac_fp.py REQ-034 AC-7 --yaml"
---

AC: AC-7
result: pass
commands: git worktree add --detach <SCRATCH>/verify/W-075 origin/main (901d3ee); python -m pytest -q -p no:cacheprovider tests/outcome/test_charges_in_sentences.py tests/scenario/test_expiry_values_with_charges.py; python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py; python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_outcome_charges_wiring.py; independent hand computation of the 8 orders from the migration 0012 rates; to_paise_up attacks; _summary_of_legs on replay frames (sold put only, bought call only, condor, bull put; with and without rates); python tools/ac_fp.py REQ-034 AC-7 --yaml
observed: 27 passed; 715 passed, 1 skipped; 5 passed (app wiring). Hand round trip 214.95956479500, rounded up 214.96; max loss 8,635.25 + 214.96 = 8,850.21; max profit 4,364.75 - 214.96 = 4,149.79; code round_trip_charges = 214.96 (Decimal). Condor sentence 'At most ₹8,850.21 at expiry, including about ₹214.96 of charges and taxes.' followed by the owner's OQ-4 (a) line, verbatim in backend/ofo/errors/explanations.py (summary_lose_exercise_stt_note). ac_fp 5250eb0c6b9d
attack: to_paise_up(0.001)=0.01, (0.0100)=0.01, (214.95956479500)=214.96, (-0.001)=-0.00, (-0.011)=-0.01, (214.96)=214.96, (0.009999)=0.01, all Decimal, no float in the module. OQ-4 line absent for sold-only, futures-only (ChargesNotComputable -> ADR-071 phrase), unlimited loss and the no-rates fallback; present for condor, bought call, bull put. Gaps (not AC-7 defects): no tests_app test asserts the line text; issue 269 D5 narrowed, not closed (the line gives no figure: exercise STT on the long 23350 call is 648.38 at NIFTY 30,000). Covers the class: yes.

Recorded by the orchestrator from the verifier's returned block.
