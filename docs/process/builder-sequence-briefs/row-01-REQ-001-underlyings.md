# Row 1: REQ-001 V1 scope (W-129, builder sequence chunk 1, Tier B, size S)

Common brief: docs/process/builder-brief.md (this brief overrides it where they differ: see the section Where you work).

Core: one home module owns the supported underlyings, and every route that takes an underlying refuses any other value
with the same plain catalogue message.
Proof: step 1 is a failing test that posts `BANKNIFTY` and `nifty` to the outcome route and gets the generic
USER_INPUT_002 today (verifier, 2026-10-22: "any other symbol gets the generic USER_INPUT_002"); it then gets
`gate_underlying_unsupported`.

Spec basis: REQ-001 AC-1: "Only NIFTY, BANKNIFTY and FINNIFTY (NSE) and SENSEX (BSE) can be selected as underlyings in
V1; no stock option, stock screener or heatmap exists (ADR-157)." (the BANKNIFTY/FINNIFTY part is deferred to row 46,
REQ-090, by the contract: today only NIFTY and SENSEX are selectable). REQ-001 AC-2: "A strategy leg is one of exactly
six types". REQ-001 AC-4: "The exchange of each underlying is recorded (NIFTY, BANKNIFTY, FINNIFTY → NSE; SENSEX → BSE)
and the data model allows more exchanges later."
Copy from: none - the map has no REQ-001 row (copy_from_check.py finds none); the change is local wiring.

## Where you work
Worktree `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs`, branch `build/seq-chunk-1` (checked out). Commit on it
as you go; do NOT push; no PR. Scratch: `C:\Users\itsab\AppData\Local\Temp\claude\D--Abhay-Ventures-OptionsForOptions2\cdc8b776-da99-4858-844d-ba9899512551\scratchpad\row01`.

## Verifier findings to fix (2026-10-22, main 235e1793)
1. AC-1: only the catalogue route answers an unsupported underlying with `gate_underlying_unsupported` ("BANKNIFTY is
   not supported. Supported underlyings: NIFTY, SENSEX."); chain, outcome, save, planned entry, tracking, ready-made and
   the strategy socket answer the generic USER_INPUT_002 because they type the field `Literal['NIFTY','SENSEX']`
   (chain.py:75, strategies.py:82, outcome.py:161, tracking.py:75, planned_entry.py:42, ...). Lower-case `nifty` gets
   USER_INPUT_002 even on the catalogue route (catalogue.py:30 regex is upper-case only).
2. AC-4: the NSE/BSE pairing has one home (`SUPPORTED_UNDERLYINGS`, catalogue.py:48, migration copy 0003:98 checked by
   test_catalogue_store.py:151), but the underlying SET is retyped in about 20 places (route Literals, chain_push.py,
   index_push.py:34/38/58, replay_mode.py:183, `routes/catalogue.py:29`, 2 frontend lists, kite_margin.py:44) with no
   test tying them to the home: adding an index means 20 edits and nothing fails if one is missed.
3. AC-2 (unverified by the verifier, check it): a catalogue INDEX row id used as a leg reaches `Instrument('INDEX')`
   (strategy_store.py:125, outcome/service.py:211) and probably answers a 500, not a refusal.

## What to build
- One alias, structural (run-discipline C8: a structural guarantee over a detector): the home module exports the set
  and one `Underlying` type built from it; every route/push model imports that type (no retyped Literal). A repo test
  (marked `repo_scan`) is the second layer: no `Literal[` naming an underlying string outside the home, and the
  frontend's lists come from one module whose values a vitest asserts equal to the server's (read
  `/api/catalogue`'s expiries contract or a shared constant; your call, recorded in the report).
- One refusal: any underlying value outside the set, including wrong case, answers `gate_underlying_unsupported` with
  the symbol shown only when it matches the symbol shape (the catalogue route's existing rule: a non-symbol stays the
  fixed input error, never echoed) on every route and on the socket's refusal frame. Decision (orchestrator,
  technical): lower case is refused, not normalised (no silent substitution).
- An index row id (or any catalogue row whose type is outside CE/PE/FUT) used as a leg is refused with a catalogue
  message on save and outcome, never a 500; test both.
- AC-4: keep the pairing data-driven in the home (it already is); add the test that the route set equals the home set.

Standing items: (a) n/a: no time-budgeted job; (b) n/a: no CI step changes; (c) the repo test discovers files from the
tree and fails closed on a file it cannot parse; it names the home by import source; (d) n/a: no other system's answer.
Reviewer checklist: every route that takes an underlying has a BANKNIFTY test and a `nifty` test answering the same
code; the socket too; index-id leg -> refusal not 500; no `Literal["NIFTY"` left outside the home; openapi regenerated
if a model's schema text changed; every guard has a test that dies without it (mutation list in the report); no new
duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no regenerated
files in the PR (except openapi.json, the builder-brief exception).

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus the changed files' tests: app files through `python scripts/orchestrator/db_run.py . python -m pytest -q -rs -p
no:cacheprovider -c pytest-app.ini tests_app/<file>.py` (use `python scripts/orchestrator/select_app_tests.py <worktree>`
to find them), `tests_app/test_response_door.py`, vitest for changed frontend files, and `python scripts/ruff_ratchet.py`.
Budget: 30 min wall-clock, 40 tool calls
Report: evidence-table
