# ADR-178 tracker: every audit change, the one number that shows it is followed

Source: `process-audit-2026-10-23.md` (sections 4-6) and the auditor's enforcement verdict (2026-10-23, after ADR-178).
Owner, 2026-10-23: "Nothing get missed, nothing get assumed. Make sure everything is strictly followed."

How it is enforced (built 2026-10-23 on `build/seq-process`):
- **Every session end:** `python scripts/orchestrator/measure_process.py --chunk-start <sha>` (rows 1-7 and 10) prints
  each counter against its limit, MISS lines first, exit 1 on any miss. A MISS is a finding the same turn; the Status
  column below is updated from the output only, never typed. The baseline rows below were measured on the three
  sessions BEFORE ADR-178 (the audit's numbers); the first session under ADR-178 replaces them.
- **Every session start:** the project hook `scripts/hooks/adr178_start.py` prints the rows still `open` or `missed`.
- **Every chunk end:** a fresh Sonnet conformance check (`builder-sequence-briefs/conformance-check-chunk.md`, 15 min /
  25 calls, never the orchestrator) re-runs the script, measures rows 8, 9, 11, 12 by their commands, marks each row
  followed / missed with its evidence, and the misses are fixed before the next chunk.
- Status values: `open` (not built or not yet measured), `followed` (last measurement within the limit, with the date),
  `missed` (over the limit; names the finding).

| # | Audit change | Counter (how we know) | Limit | Status |
|---|---|---|---|---|
| 1 | Orchestrator context diet (audit change 1) | orchestrator context tokens per turn, per session (session-end script) | < 250k average | missed (chunk 3 session A a43256ae, measured 2026-10-25 by `measure_process.py --session a43256ae --chunk-start 038e7889 --since 2026-10-24` after the #532 F fix (chunk 4 process item): avg context 363k/turn over 627 turns vs < 250k); chunk 2: unmeasured (#532 F); chunk 1: missed |
| 2 | Fresh session about every 3 rows (change 1a) | rows closed per orchestrator session | <= 3 | followed (chunk 3 session A a43256ae, measured 2026-10-25 by `measure_process.py --session a43256ae --chunk-start 038e7889 --since 2026-10-24` after the #532 F fix (chunk 4 process item): 3 rows closed - 27, 28, 29 - from the row-review headings); chunk 2: missed (f1b75d11 closed 4) |
| 3 | No tables / logs / diffs read into the orchestrator (change 1b, 1d) | 63-row table prints per session | 0 (one per chunk report) | followed (chunk 3 session A a43256ae, measured 2026-10-25 by `measure_process.py --session a43256ae --chunk-start 038e7889 --since 2026-10-24` after the #532 F fix (chunk 4 process item): 0 table prints); chunk 2: unmeasured (#532 F); chunk 1: missed |
| 4 | Checker model by changed file (change 2) | Opus dispatches whose prompt or brief names no safety-set file (session-end list of every Opus dispatch + its files) | 0 without a `Why Opus:` line naming a safety-set file | missed (chunk 3 session A a43256ae, measured 2026-10-25 by `measure_process.py --session a43256ae --chunk-start 038e7889 --since 2026-10-24` after the #532 F fix (chunk 4 process item): 7 Opus dispatches with no safety-set file and no `Why Opus:` line naming one - mostly process-gate checks citing ADR-181); chunk 1: missed |
| 5 | Findings-only round 2 (change 3, ADR-178 (1)) | minutes per round-2 verify (transcript first-last time) | <= 15 | missed (chunk 3 session A a43256ae, measured 2026-10-25 by `measure_process.py --session a43256ae --chunk-start 038e7889 --since 2026-10-24` after the #532 F fix (chunk 4 process item): 5 round-2 checkers - 8, 9, 15, 17, 36 min; 3 over the limit by the script's rounding) |
| 6 | DB tests in CI, not the tunnel (change 5) | local database runs per session (fresh_launch / db_run commands) | <= rows closed in the session (one per row) | missed (chunk 3 session A a43256ae, measured 2026-10-25 by `measure_process.py --session a43256ae --chunk-start 038e7889 --since 2026-10-24` after the #532 F fix (chunk 4 process item): 4 local database runs vs 3 rows closed - the 52-file DB run over the tunnel among them; DB tests now go to CI through an early draft PR); chunk 1: missed |
| 7 | Process-tool freeze (change 6) | commits touching scripts/orchestrator or scripts/hooks per chunk | <= 1, and none before the chunk-1 PR except the generator and the script; chunk 3: <= 2, the gate command and the dispatch command (ADR-181) | missed (chunk-2 conformance check 2026-10-24, measure_process.py --sessions 2 --chunk-start 9d885bda: 10 process-tool commits vs <= 1 - reach_check.py 2 (the chunk's one approved process item) + reach_check_baseline.json 8 (data entries); the copy builder's reference_register.py change was reverted before merge, 0 commits); chunk 1: 27 |
| 8 | Draft chunk PR open from the chunk's first row (change 5) | `gh pr list --state open --draft` names the chunk branch | present | followed (chunk-2 conformance check 2026-10-24, measure_process.py --sessions 2 --chunk-start 9d885bda: draft PR #531 opened 2026-10-23T19:05Z, one minute after the chunk's first commit cf30134e) |
| 9 | Brief generator (change 4) | briefs made by `make_brief.py` / all row briefs since it landed | 100% | missed (chunk-2 conformance check 2026-10-24, measure_process.py --sessions 2 --chunk-start 9d885bda: 0 of 28 brief files name make_brief - row briefs were rendered through make_brief.render via a scratch helper, every fix/round-2 brief was hand-written; the measure cannot see the render path) |
| 10 | A small row-ahead fix is verified when built (change 7) | minutes between a fix commit and its verifier dispatch | <= 15 | missed (chunk 3 session A a43256ae, measured 2026-10-25 by `measure_process.py --session a43256ae --chunk-start 038e7889 --since 2026-10-24` after the #532 F fix (chunk 4 process item): worst 52 min, fix c1 round 1 commit 16:55Z -> check 17:48Z; 29b 27 min; 2 of 6 fixes measured, 4 had no check after them - c2 r1, 28f r1-r3) |
| 11 | Reference-product COPY gaps per chunk (change 8, ADR-178 (2)) | `reference_register.py --close-check` over the chunk's requirements at chunk close | exit 0 (spec_change records excluded) | missed (chunk-2 conformance check 2026-10-24, measure_process.py --sessions 2 --chunk-start 9d885bda: --close-check exit 1, 11 records - 5 spec_change excluded (RD-124/133/147/149/154); 6 not: RD-032 (Q211), RD-141 (REQ-138), RD-148 (owner-pending RD-149), RD-153 (row 37), RD-097 and RD-132 (built, not verified) - now deferred with owners in #532 E) |
| 12 | Paperwork per chunk (change 9, ADR-178 (3)) | full reports per chunk; deferred issues per chunk | 1 full report per chunk (+1 per row > 50% over); 1 deferred issue per chunk | followed (chunk-2 conformance check 2026-10-24, measure_process.py --sessions 2 --chunk-start 9d885bda: 1 deferred issue, #532; full reports: row-review entries only, prose for no row >50% over - full-report count by commit subject 0) |

Not enforceable by any script - judgement calls, stated plainly (auditor, section C):
- Whether the orchestrator reads a log or diff into its context: only row 1's number shows it, after the fact.
- Whether a "display" file quietly feeds money: covered by the repo guard tests (one engine, Decimal boundary, write
  allow-list) and the chunk-level Opus review.
- The quality of a findings-only round 2: the chunk-level Opus review is the backstop.

Unchanged safety core (audit section 6) is enforced by existing tests and is not tracked here: order-path guards,
money maths with hand-computed values, injected-clock liveness tests, auth checks, independent verifiers, the
chunk-level Opus review, CI full suites.
