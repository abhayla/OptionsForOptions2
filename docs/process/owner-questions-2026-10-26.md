# Owner questions, 2026-10-26

## Q1: merge PR #556 (ADR-189, kit 1.14.0 lean process)?

Asked by the night guard's route (L17) at ~00:4x IST; PR #556 stays open and unmerged until answered.
Business call: you set the review and safety level for code that touches real-money orders; only you can accept less
local checking.
Spec basis: ADR-189 amends ADR-178 (3), ADR-181 (1), ADR-171 (8), ADR-112 and ADR-106 (2)(3)(11); each replaced text
is quoted in its SPEC CHANGE section.

Before -> after:
1. Always-loaded text: 23,863 -> 7,715 bytes (CLAUDE.md 17,826 -> 1,678; cap 8,192).
2. Local check before a push: `gate.py`, ~8 min (ruff ratchet, DB-free app tests, OpenAPI compare, frontend
   lint/format/Vitest) -> `tools/ci_local.py`, 57 s measured (kit ci.yml only). App and frontend breaks are now first
   seen in CI.
3. Mutation tests: every builder brief had to run `mutation_gate.py` (check_brief refused without it) -> Tier A guards
   only, at most 5 mutants, not a gate.
4. Reviews: Tier A verifier per PR, Tier B verified at requirement close, independent redesign after a round-2 MAJOR
   -> one checker per item (Opus A / Sonnet B / none C); after round 2 a Tier A CRITICAL/MAJOR parks, anything else
   ships with its findings listed.
5. Row review: 62 KB file (R1-R19, per-row table, meta review every 3rd row, enforced by a test) -> lessons L1-L19
   plus one log entry per item; the test is deleted.
6. ADR-178 tracker: 6.8 KB tracker, a SessionStart hook every session, 935 lines of measuring scripts ->
   `tools/measure_tokens.py` on demand.
7. Evidence: 3 project scripts -> the kit tool behind one wrapper (in-flight refusal kept).
8. Reverses item (3) of ADR-188 on the unmerged chunk-4 docs branch: "The local gate stays for every change, Tier B
   included (ADR-181 unchanged)".
9. Two departures from your message: numbered ADR-189 (188 was taken by the 10-25 speed-rules decision);
   `views/spec-digest.md` regenerated (3 lines) because CI refuses a stale digest.

Options:
- **Approve all, merge (Recommended).** Matches your 2026-10-26 approval; CI green is the last gate. Real case: row 30
  took 276 min, about half of it waiting on gates and reviews.
- Approve, keep local app tests: merge, plus a follow-up so the builder also runs select_app_tests' DB-free files
  before a push (catches app breaks before CI; a few minutes per push).
- Hold the PR: leave #556 open; say which item to change.

Answer: (pending)
