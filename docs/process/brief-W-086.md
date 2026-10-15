# Builder brief: W-086 expiry-day entry warning and acknowledgement (Tier A)

Core: an entry leg SELL of a SENSEX contract expiring 2026-10-15, placed on 2026-10-15, requires the explicit
acknowledgement; a BUY of the same contract that day only warns, naming the extra expiry-day margin; the same legs one
day before expiry get neither.
Proof: step 1 is `tests/execution/test_expiry_day_entry.py` on real SENSEX contracts of 2026-10-15 from the recorded
catalogue fixtures (grep `tests/fixtures/`). Write it FIRST, red.

Tier: A (an execution risk gate). Model: sonnet (builder routing).
Budget: 40 min wall-clock, 44 tool calls. HARD: at call 40 stop, commit, push, report done / not done / next command.
Report: evidence-table, under ~250 words.
Copy from: none - a rule in this project's own pre-execution checks.

Read first: `docs/process/builder-brief.md`, `work/W-086.md`, `spec/decisions/ADR-083.md` (decision 2),
`spec/requirements/REQ-056.md` (AC-6), `spec/findings.md` F-20, `backend/ofo/execution/safety.py` (flags,
`requires_confirmation`, `confirmation_text`), `backend/ofo/execution/context.py`, `CLAUDE.md`.

## Spec basis
- ADR-083: "a SHORT leg expiring that day needs the explicit acknowledgement"
- REQ-056 AC-6: "Risk messages scale with risk: normal → explain; elevated → warn; exceptional → explicit acknowledgement"

## What to build
1. Expiry-day entry (REQ-056 AC-6): an entry/adjustment leg whose contract expires today -> elevated warning naming the
   extra expiry-day margin (F-20: extra 2% ELM on short options, no calendar benefit); a SHORT such leg -> the
   exceptional level: explicit acknowledgement required before execution (reuse the existing confirmation mechanism;
   no generic I-understand checkbox). Four-part catalogue messages, pins updated.


## Reviewer checklist (write first; each red when mutated)
- Expiry-day BUY leg -> warning only; expiry-day SELL leg -> acknowledgement required; next-day expiry -> neither.
- The trading date comes from the context clock (no wall clock), in IST.
- Exits are not affected (REQ-059 exit carve-out) - test it.
- Every guard has a killing test; list them.

## Rules
- Targeted tests: tests/execution, tests/errors separately. No database. Then your worktree's own atool `--no-tests`.
- Do not touch backend/ofo/execution/basket.py, backend/ofo/broker/, margin code, reconciliation code (W-085 runs in
  parallel) or the grouping module (W-083). Templates/pins: add entries only. No kit/`spec/`/`views/`/findings INDEX;
  never write `evidence/`.
- Commit, push `build/W-086-expiry-day-entry`. No PR.
