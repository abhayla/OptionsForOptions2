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
| 1 | Orchestrator context diet (audit change 1) | orchestrator context tokens per turn, per session (session-end script) | < 250k average | missed (chunk-1 conformance check 2026-10-24, measure_process.py --sessions 5 --chunk-start 3ccc8439: 13 MISS / 16 OK / 2 UNMEASURED: sessions b9b5cb32 538k, 0c676935 286k, 5db71e90 456k per turn; 7a0c81e3 236k passes) |
| 2 | Fresh session about every 3 rows (change 1a) | rows closed per orchestrator session | <= 3 | followed (chunk-1 conformance check 2026-10-24, measure_process.py --sessions 5 --chunk-start 3ccc8439: 13 MISS / 16 OK / 2 UNMEASURED: at most 3 rows closed per session) |
| 3 | No tables / logs / diffs read into the orchestrator (change 1b, 1d) | 63-row table prints per session | 0 (one per chunk report) | missed (chunk-1 conformance check 2026-10-24, measure_process.py --sessions 5 --chunk-start 3ccc8439: 13 MISS / 16 OK / 2 UNMEASURED: 3 table prints in session b9b5cb32) |
| 4 | Checker model by changed file (change 2) | Opus dispatches whose prompt or brief names no safety-set file (session-end list of every Opus dispatch + its files) | 0 without a `Why Opus:` line naming a safety-set file | missed (chunk-1 conformance check 2026-10-24, measure_process.py --sessions 5 --chunk-start 3ccc8439: 13 MISS / 16 OK / 2 UNMEASURED: 2 + 3 Opus dispatches with no Why Opus line, sessions b9b5cb32 and 0c676935) |
| 5 | Findings-only round 2 (change 3, ADR-178 (1)) | minutes per round-2 verify (transcript first-last time) | <= 15 | open (unmeasured, chunk-1 conformance check 2026-10-24, measure_process.py --sessions 5 --chunk-start 3ccc8439: 13 MISS / 16 OK / 2 UNMEASURED: no round-2 checker transcript in the window) |
| 6 | DB tests in CI, not the tunnel (change 5) | local database runs per session (fresh_launch / db_run commands) | <= rows closed in the session (one per row) | missed (chunk-1 conformance check 2026-10-24, measure_process.py --sessions 5 --chunk-start 3ccc8439: 13 MISS / 16 OK / 2 UNMEASURED: 11, 3 and 5 local database runs in sessions b9b5cb32, 7a0c81e3, 5db71e90) |
| 7 | Process-tool freeze (change 6) | commits touching scripts/orchestrator or scripts/hooks per chunk | <= 1, and none before the chunk-1 PR except the generator and the script | missed (chunk-1 conformance check 2026-10-24, measure_process.py --sessions 5 --chunk-start 3ccc8439: 13 MISS / 16 OK / 2 UNMEASURED: 27 process-tool commits in chunk 1, mostly CI fixes) |
| 8 | Draft chunk PR open from the chunk's first row (change 5) | `gh pr list --state open --draft` names the chunk branch | present | missed (2026-10-24: PR #525 opened 2026-10-23T10:01Z, about 29 h after row 1's first commit; chunk 2 opens its draft PR at its first row) |
| 9 | Brief generator (change 4) | briefs made by `make_brief.py` / all row briefs since it landed | 100% | missed (2026-10-24, grep proxy: 3 of 16 briefs added after make_brief.py landed name it) |
| 10 | A small row-ahead fix is verified when built (change 7) | minutes between a fix commit and its verifier dispatch | <= 15 | missed (chunk-1 conformance check 2026-10-24, measure_process.py --sessions 5 --chunk-start 3ccc8439: 13 MISS / 16 OK / 2 UNMEASURED: worst fix-to-checker gaps 108, 43 and 31 min) |
| 11 | Reference-product COPY gaps per chunk (change 8, ADR-178 (2)) | `reference_register.py --close-check` over the chunk's requirements at chunk close | exit 0 (spec_change records excluded) | followed (2026-10-24: --close-check over chunk 1's requirements names 4 records, RD-035/065/066/114, all spec_change true - excluded by this row's limit and ADR-178 (2); they wait for Q282) |
| 12 | Paperwork per chunk (change 9, ADR-178 (3)) | full reports per chunk; deferred issues per chunk | 1 full report per chunk (+1 per row > 50% over); 1 deferred issue per chunk | missed (2026-10-24: 17 deferred issues created in chunk 1 against 1; full-report count unmeasured) |

Not enforceable by any script - judgement calls, stated plainly (auditor, section C):
- Whether the orchestrator reads a log or diff into its context: only row 1's number shows it, after the fact.
- Whether a "display" file quietly feeds money: covered by the repo guard tests (one engine, Decimal boundary, write
  allow-list) and the chunk-level Opus review.
- The quality of a findings-only round 2: the chunk-level Opus review is the backstop.

Unchanged safety core (audit section 6) is enforced by existing tests and is not tracked here: order-path guards,
money maths with hand-computed values, injected-clock liveness tests, auth checks, independent verifiers, the
chunk-level Opus review, CI full suites.
