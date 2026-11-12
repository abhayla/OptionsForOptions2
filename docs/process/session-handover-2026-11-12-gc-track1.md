# Session handover 2026-11-12: GC-TRACK1

Contract: `docs/process/goal-contract-GC-TRACK1-2026-11-12.md`. Run log: `docs/process/gc-track1-run-log.md`.
Owner questions: `docs/process/owner-questions-2026-11-12.md` (A1 answered by the login; A2 open).
Status page: the one page (db collection `tasks`, rows k01..k32).

## DONE
- k01-k05: status rows, docs PR #698 (ADR-290/291, contract), worktree, CORE PROOF k04 PASS live (typed-in condor
  strategy 136 saved 10:44:58 with no page open, worker recomputed it every minute on FRESH reads), k05 cause found
  (fill facts skipped without a page socket: finding `entry-facts-skipped-when-the-api-holds-no-index-quote`).
- Stage B: k06 migration 0052 `strategy_held_entries` (Tier A review PASS), k07 held block + replies, k08 fill facts
  at save or 409 refusal, k09 broker changes via the existing forms.
- Stage C: k11-k15 held tracked like paper (tests), k16 re-check after a fresh margin read, k17 worker supervisor,
  k18 LIVE 30 min no screen (136 and 128 both 59 checks; alert T-03 record 263 at 11:45:01), k19 LIVE Compare on 136
  -> "Roll the untested spread toward spot" recorded at typed prices (call spread 25650/25750 -> 25550/25650).
- Stage D: k20 (no code: `order_path` switch already hides Execute; ADR-292 (6) names it), k21 triage, k22 cap
  exemption (live count), k23 first alert not a candle late, k24 day-rule text, k25 deleted strategies' alerts, k27
  open-leg count, k28 deferred issue #701.
- Stage E: k29 Tier B review (1 MAJOR found: restart count, see PARKED), k30 prepush TOTAL PASS on 51159d51, k31 PR #703
  merged 16:37 (main b2edf013), k32 this handover + the CI api limit 150 -> 180 min.

## PARKED
- k26 one order per contract and side (ADR-274): #699 (2 rounds broke ADR-274 (3) / sent an oversize exit).
- k22 remainder: the daily cap count restored on worker start includes watch/day records: #702 (round 2 broke
  `test_risk_exit_not_gated`; reverted). Cost: after a worker restart an automatic alert can be held early that day.

## Live state at hand-off
- ofo_dev is at 0052 (owner A2: "go with your recommendations", 15:10). k10 proven live on held condor strategy 137
  (typed in 15:14:31 with the held block): label, entry 15:00, "Rules start from 12 Nov 15:14", broker, record line;
  its fill facts row was stored with no page open (k08 live proof).
- Strategy 136 (core proof) has no held row: it was typed in before 0052; it is a typed-in paper condor.
- The live app runs from main again (restarted 16:38).

## DEFERRED (issues)
- #700 a changed plan waits one speed interval before its re-check. #701 remaining IC defects + DEPTH list.
- k29 MINOR: k08 refuses a typed basket when the index has no live quote in 3 s (by design); the 3 s wait sits in
  the fill transaction; scenario-clock CHECK can 500 in test-data mode; 3 new input labels for owner read
  ("Entry date and time", "Broker", "N open legs").

## Lessons (process)
- A night start with a [LIVE] core proof sat idle ~6 h; the owner's "don't sit idle" unlocked core-independent work
  (memory `night-start-live-core-idle`).
- Worktrees have no `.env`: DB tests run the MAIN checkout's `db_run_fresh.py` with the worktree as the run folder.
- The REST chain read is NOT_CONNECTED without a page socket by design; a spike reads the chain socket.
- An API started before the Kite login never picks the session up: restart it (by PID) after login.
- A request-model change also changes `docs/api/openapi.json`: put the regenerate + drift test in the brief.
- Four status stamps typed from memory were in the future: read `date` in the same step.

## NEXT
1. The owner types in his real held condor with the "Held at my broker" option, in market hours.
2. Worktree OptionsForOptions2-gc-track1-dadj keeps the parked k26 commits 51fdb62f / 6e843923 (#699), local only.
3. #702 (cap count on restart) with a leaf module outside the gate's import closure; #699 when real orders return.
