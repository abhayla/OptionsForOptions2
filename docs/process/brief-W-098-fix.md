# Fix brief: W-098 red CI on PR #355 - the producer-inventory scan (Tier A item, fix round 1)

Core: `tests/errors/test_producer_inventory.py::test_every_producer_in_scope_is_routed_through_render` fails on PR #355
(CI run 38989215685): `execution/basket.py:136 'build it again'`, `execution/margin_gate.py:40 'call check_margin...
try_from_list or apply_margin_refusals'`, `instruments/eligibility.py:169 'build it again from the list'` - the new
`SealedTuple` subclass declarations carry sentence-shaped refusal text, which the scan reads as user-facing text built
outside `render()`.
Proof: that test red on the branch now, green after the fix, run locally (it needs no database).

RCA: the seal's refusal text moved from method bodies into class-definition keywords at module level, where the
producer scan looks for user-facing sentences.
Class: every developer-facing refusal string that W-098 placed at module/class level in `backend/ofo/` (the three
above; grep the branch diff for any other) - before: 3 flagged, after: 0.
Proof: `python -m pytest -q -p no:cacheprovider tests/errors/` all green.

Tier: A item, fix round. Model: sonnet.
Budget: 20 min wall-clock, 24 tool calls. HARD limit: at call 22 commit, push, report.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under 200 words.
Copy from: none - a fix inside this project's own W-098 code.
Findings checked: guard-as-forbidden-list, targeted-tests-miss-dependent-files
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py

## Spec basis
- REQ-065 / ADR-086 (one catalogue for user-facing text; the scan enforces it). The seal's messages are developer
  errors (TypeError for a forged construction), not user text.

## What to do
1. Read `tests/errors/test_producer_inventory.py` to learn exactly what the scan treats as a producer and what it
   exempts (how did `KiteBasket`'s refusal text pass before W-098? - follow that same shape: e.g. the text inside the
   raising function in `sealed.py`, built from the class name, not a sentence literal at module level). Do NOT add an
   exemption to the scan and do not edit the test.
2. Fix the three sites (and any other the diff shows) so the scan passes and every seal refusal still raises with a
   message naming the type. `tests/test_sealed_proof_objects.py` stays green unchanged except for message text it
   asserts, if any (say which).
3. Run: `python -m pytest -q -p no:cacheprovider tests/errors/ tests/test_sealed_proof_objects.py tests/execution/test_kite_basket.py tests/execution/test_margin_gate.py tests/test_*.py`
   and `python scripts/ruff_ratchet.py` (no rule may rise). Commit, push `build/W-098-sealed-proofs`. No PR (it exists:
   #355).

## Rules
- Work in a fresh worktree of branch `build/W-098-sealed-proofs` from origin (it is pushed; the old agent worktree is
  gone). No kit or `spec/` edit, no `views/`, no regenerated files, no `evidence/`.
