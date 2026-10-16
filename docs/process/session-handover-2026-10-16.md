# Session handover 2026-10-16: night build (00:00-06:30 IST), Stage 4b core first

Owner brief (2026-10-16 ~00:00): build everything that needs no live market, test it offline, market tests from 09:15;
no questions while asleep (parked in `docs/process/owner-questions-2026-10-16.md`, OQ-1..OQ-9). Plan: core first
(ADR-087). Plan file: `C:\Users\itsab\.claude\plans\confirm-you-are-in-fluffy-hinton.md`.

## DONE (merged to main, CI green on every PR)
- Decisions: ADR-087 (4b built ahead of the 4a gate), ADR-088 ("Checked at"), ADR-089 (breakeven labels), ADR-090
  (REQ-073 approved, AC-5 aligned with ADR-060) - #251, #254.
- W-074 charges rate table + calculator (#261, migration 0012). W-076 freeze limit from the NSE contract file (#264,
  migration 0013, F-36). W-077 "Checked at" + #249/#244/#213, closes W-072 / REQ-039 AC-3 (#262). W-078 executable
  price, NRML/MIS product, circuit band (#267). W-082 breakeven labels from loss regions (#268). W-085 expiry
  settlement (#280). W-086 expiry-day entry warning + short-leg acknowledgement (#276).
- W-081 margin gate merged as a COMPONENT (#274): card BLOCKED, no AC claimed (needs basket #271, a live funds read,
  #273).
- W-083 PARTIAL (#277): AC-1, AC-4 verified; AC-2 waits on OQ-7.
- Fixes: #259 (#278); #237 Save Draft e2e now runs in CI (#282); #263 items 1-3 (#283); #279 items 2-3 (#284, REQ-060
  clarification + OQ-8); #275 all five items + unique error-code guard (#286); #279 item 1, settle before reconcile
  (#287, Tier A: 6,000-case differential, only fewer blocks); #285 MARKET_DATA_120 renumbered, guard without
  exceptions (#288).
- Mechanism: PR close-keyword check (#289 - see the status table in the final report; merges on green).
- Docs batches #252 #253 #256 #258 #260 #265 #266 #270 #272 #281 and this batch (F-37, OQ-9, two findings, briefs).

## PARKED (owner decisions waiting, each with a recommendation)
- W-075 (#269) charges in money sentences: verified except D5; sentence vs expiry table with STT on exercise = OQ-4.
  Branch held, not merged. ADR-082's "about Rs 221" example is wrong (correct 214.96); fixed with W-075.
- W-080 (#271) basket: AC-1/AC-2 pass; AC-4 failed 3 times (urllib door accepts a Unicode-dot host). Options:
  idna-normalise the host or refuse non-ASCII - owner call.
- #257 freeze-limit maximum age = OQ-9 (needs a trading calendar; recommend 4 calendar days now).
- OQ-1 price-protection split, OQ-2 #255 "never split", OQ-7 add-to-existing order-free (recommend a); OQ-3/5/6/8
  information only.

## STILL OPEN (deferred, not started)
#263 item 4 (plan version on the basket tag), #273 (margin check on the platform estimate - with #271), #279 item 4
(persist awaiting/settled/retired state - before any scheduler), #255, #107 (needs a host), REQ-025 (legal Q261),
#199/#234/#200.

## Morning (owner present)
1. F-37 is recorded: the token stopped at about 04:30 IST (not 6 AM). The watcher (PID 14884) exited after the first
   failure. Re-run it on two more nights before relying on the minute.
2. 09:10 API on 8765 from main against ofo_dev (`scripts/orchestrator/dev_run.py`, APP_ENV=development,
   LIVE_MARKET=1, run as a background task - Start-Process is blocked); send the login link; login in a PRIVATE
   window (redirect `http://127.0.0.1:8765/kite/callback`). ofo_dev is migrated to 0011; apply 0012/0013 to ofo_dev
   before the charges/freeze live proofs.
3. 4a gate re-run (harness `D:\Abhay\Ventures\ofo-kite-ticks\2026-10-15\gate4a\`): D8 incl. TOTAL rows, draft
   save/reopen, 8 screenshots, #232 item 1 -> `docs/research/gate4a-2026-10-16/` + verdict in
   `docs/process/gate-4a-review-2026-10-15.md`.
4. Live proofs: margin `/user/margins` + `/margins/basket` (W-081), depth limit (W-078), charges reply (W-074), freeze
   block on the live catalogue (W-076).

## Misses (recorded)
- Partial-fix PR bodies closed whole issues 3 times (#263, #275, #279; reopened) despite a memory - finding
  `pr-text-closes-issue-unintended`; mechanism #289. Even the mechanism's own PR body first quoted examples that would
  have re-closed #237 and #263; the checker caught it before push.
- Two templates shared one error code twice (221 across branches; MARKET_DATA_120 on main) - finding
  `identifier-unique-only-by-convention`, guarded (#286, #288).
- Targeted test runs missed guard tests twice - occurrence 5 on `targeted-tests-miss-dependent-files`; every landing
  now runs the FULL domain suite.
- Local Python 3.13 vs CI 3.12 - finding `local-python-differs-from-ci`.
- My brief errors: short futures limited to options (#275 round 1); ADR-082's example taken as correct (W-075);
  expected PR #282 to pass the close check (it correctly fails). Builders ran over budget several times.
- Two builder worktrees (W-086, W-074) are locked by this session's process and could not be removed; they go when the
  session ends (`agentwt.py <id> release` otherwise).
