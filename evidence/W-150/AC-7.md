---
work_item: W-150
ac: AC-7
requirement: REQ-034
ac_fp: "5250eb0c6b9d"
result: pass
verified_by: "independent verifiers (Opus row 22 check + round 2 on f5ab7f1e; Sonnet AC-1/5/7 re-check on bf4823e7; Sonnet 22b check on e928a3af)"
builder: "builders (Opus: row 22 d0a6049f, ATM-IV fix f5ab7f1e; Sonnet: 22b e928a3af)"
date: '2026-10-24'
commands: "same vitest run; mutants: details open by default, summary text changed (sed + restore); read frontend/e2e/strategy-table.spec.ts:139-144"
---

AC: AC-7
result: pass
commands: same vitest run; mutants: details open by default, summary text changed (sed + restore); read frontend/e2e/strategy-table.spec.ts:139-144
observed: sum-make / sum-lose / sum-start (server sentences) render above each number in SummaryCards.vue; the per-leg Bid/Ask block is a native details element, closed by default (summary 'Details: bid and ask per leg'), opens on a click; e2e asserts closed then open (CI only).
attack: details-open mutant: 3 failed; summary-text mutant: 2 failed. Not run: Playwright locally (CI); the closed state in a real browser is unverified until CI.

Recorded by the orchestrator from the verifier's returned block.
