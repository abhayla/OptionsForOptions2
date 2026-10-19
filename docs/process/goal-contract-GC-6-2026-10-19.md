# Goal contract GC-6 (from Mon 2026-10-19 evening): build-out of every decided item and screen, nothing silent

Chain: `goal-chain.md` (rules; chain rules 1-2 amended by this PR to allow this ONE parallel-build lock). Rows:
`build-ahead-tracker.md`, contract column `GC-6`. Source: the owner-approved plan of 2026-10-19 (PM review of all pending
work, 3 independent reviews: broker-app expert (Opus), usability (Sonnet), delivery/platform (Sonnet), all GO WITH FIXES,
every finding accepted or rejected in the plan's review log, copied in section 9). Design basis for screens:
`docs/design/screens-research-2026-10-19.md` + `docs/design/screens-research-2026-10-19-part2.md`.
**Owner needed:** (1) every new issue raised at once (section 2); (2) Thu 2026-10-22 09:30-11:30 IST live order proof
(Kite login, typed go, Place on Kite's page); (3) accepting the status of any row that cannot be built (section 1).
**Cap: none (owner decision D1).** Heartbeat and stale rule in section 3.

Core: every API process sizes its DB pool from the `ofo_app` role's limit, so the parallel builders, a second API and a
13-card Live Strategies page never hit `TooManyConnectionsError`.
Proof: on CI's own PostgreSQL (the `app-tests.yml` database, role `ofo_app` with CONNECTION LIMIT 5, the same limit
that failed #427's e2e 4/4 - #370), a DB test builds the app's engine twice with the DEFAULT settings (two API
processes), drives concurrent load through the real connection paths (outcome rates load, token read, strategy list)
for 60 s, and asserts 0 `TooManyConnectionsError` and `pg_stat_activity` for `ofo_app` <= 5; the same test run against
the old defaults (5 + 10) must fail (discrimination). Not on ofo_dev: that PostgreSQL also serves IPODhan production,
and a load run there needs the owner's explicit OK per run (global rule "production hosts are not test benches"; the
first attempt was refused 2026-10-19 ~20:35 IST). Fails -> STOP, record the output, re-plan around it.

## 0. The owner's standing instructions for this run (verbatim, 2026-10-19)
- "the goal contract should implement a verification step for each and everything, so that nothing gets unbuilt,
  nothing gets left half unbuilt ... Everything should be properly tracked and ensured that everything which is
  covered in this plan should be properly built. Okay, and only then the goal contract should finish."
- "nothing which is part of the goal contract should remain uncompleted ... if there are any issues that come up
  later, that should be raised to me, should not be silently left alone."
- "It will track each and everything. Nothing should be left unfinished or should not assume something. Wherever you
  have questions, should have asked me."
How the run obeys them:
- **Never assume a business answer.** Anything about what a user sees, reads or pays, product scope, wording, money
  shown, or a gap the spec does not settle is ASKED with the question tool (one question per call, recommended option
  first, a `Business call:` line and a `Spec basis:` line), and the answer is written into the spec the same turn
  (spec-first R4). Two owner requirements that conflict are always asked, never decided by the run.
- **Technical calls** (code design, tests, tooling, CI, store shape, fix rounds, merge order) are decided by the fitting
  expert role, with an independent reviewer when complex, recorded on the row and in the PR body, and told to the
  owner as information in the next progress note - never asked, never hidden.
- **The owner away:** no question tool; the question goes to `docs/process/owner-questions-<date>.md` with a
  recommendation plus a push notification, the affected row waits (`blocked-owner`), every other row continues.

## 1. Finish rule (owner D1, tightened by the owner's no-silent rule)
- GC-6 is MET only when every row with contract `GC-6` is `closed` with evidence (merged + verified, its worktree removed),
  OR its blocked status (`blocked-owner`, `blocked-live`, `stage-5`) has been **explicitly accepted by the owner**, the
  acceptance written on the row with its date.
- "Buildable" = a row with no `blocked-*` flag whose `depends_on` rows are all closed. Chain rule 4b here reads: no
  close-out while any buildable row has a next step.
- No row is dropped, merged into another, or narrowed without the owner's OK through the question tool. New defects found
  while building become NEW GC-6 rows with an issue, never "deferred to later" unless the owner says so.
- Rows still `deferred #N` in GC-6 (#409, #411, #422) are put to the owner at start, one question each with a
  recommendation; the answer is written on the row (`todo`, or `owner-accepted <date>` deferred). #423, #435, #433,
  #434 and #439 are GC-6 work (`todo` with their depends_on); #442 stays GC-3F's.
- Every GC-6 row carries a `verify:` line. A carried row's line names a test file pattern; the builder brief records
  the exact file on the row before it moves to `building`, and `tracker_check.py` refuses a `building` row without it.

## 2. Nothing silent (owner, 2026-10-19)
Raised the moment it happens: a blocked row, a failed proof, a second red of one class, a business conflict, a new defect
outside a row, a reviewer MAJOR not fixed, any defer or park. Owner present: one question-tool question per issue with a
recommendation, a `Business call:` line when it is one, and a `Spec basis:` line. Owner away: a dated entry in
`docs/process/owner-questions-<date>.md` plus a push notification; asked again when the owner returns. Every progress note
and the close-out list every open row with its reason and next step.

## 3. Lock, heartbeat, lease, merges
- Lock `lock/gc-6` (parallel-build lock, chain rule 1b). It never blocks a main-line contract (GC-3F checks main-line
  locks only). Heartbeat: at each merge and at least every 2 h the session pushes a new lock commit
  (`OLD=$(git ls-remote origin refs/heads/lock/gc-6 | cut -f1); NOW=$(TZ='IST-5:30' date '+%Y-%m-%d %H:%M IST');
  C=$(git commit-tree origin/main^{tree} -p origin/main -m "lock GC-6 session <id> start <start IST> cap none (D1)
  heartbeat $NOW"); git push --force-with-lease=lock/gc-6:$OLD origin $C:refs/heads/lock/gc-6`).
  The IST stamp is read with `TZ='IST-5:30' date` or PowerShell `Get-Date`: Git Bash ignores `TZ=Asia/Kolkata` and
  prints UTC (the first GC-6 lock commit said "14:46 IST" at 20:16 IST; lessons.md).
  Stale = no heartbeat for 6 h; only the owner clears a stale lock. Resume prompt: the one prompt with GC-6 named, plus
  "take lock/gc-6 only if the owner cleared it as stale".
- **ofo_dev lease:** marker file `D:\Abhay\Ventures\.ofo-dev-lease` holding `<session id> <builder/item> <IST start>`.
  Only the holder starts an API process or runs a DB test (role limit 5; that PostgreSQL also serves IPODhan
  production). Everyone else runs targeted non-DB tests; DB tests run in CI. The holder deletes the marker when done.
- **Migration numbers** are allocated on the tracker row before a builder starts (0019 is #419's).
- **Merges:** docs PRs and frontend-only PRs merge when they pass review. PRs touching `backend/**`, a migration, or any
  Tier A path wait until GC-3F's item 1 and its held-PR merges finish (about Wed 2026-10-21 11:00 IST); GC-3F pins its
  proof to the main sha it starts on. Screens are one stacked chain, so main is merged in once. Every merge:
  `python scripts/orchestrator/merge.py N --reviewed-sha <full sha>` then `merge_audit.py`.
- During GC-3F's live window (Wed 09:15-~11:00) GC-6 starts no API and runs no DB test.

## 4. Order of work (rows in `build-ahead-tracker.md`; up to 3 builders at once: one order/money Tier A, one
## durability/safety Tier A, one screens)
1. **S0** this docs PR (research note part 2, decision rows ADR-116..120, findings, contract, tracker, GC-3F delta).
2. **O0** CI-SPLIT (split `app-tests.yml` into frontend and API jobs with their own path filters), HARVEST-DRAFT (kit issue:
   draft filter for the kit's `ci.yml`), TRACKER-CHECK-PLAN (extend `tracker_check.py` from held #417: plan ids <-> rows <->
   evidence files on main).
3. **O1** POOL-BUDGET (core, above); review rounds of held #421 and #424 (GC-3F merges them).
4. **O1.5 safety rails** KILL-SWITCH, MKT-HOURS (ADR-119), INSTR-FRESH, TOKEN-RETURN, DUP-TAG.
5. **O2 order path**, stacked on the held branches (never rebuilt): #313, #380-2, #380-3 (with ADR-116), #390 (ADR-117
   two baskets, rules a-g), #389, #263, #115, #423, EXIT-FREEZE-MSG (ADR-092 block, "exit the rest on Kite"), #279.
6. **O3 money** #240, #400, OUTCOME-500, #45, #273.
7. **O4 durability/security** #352-2, #401 (interim: owner check + CSRF token), #191, #148, #353-verify (in #418).
8. **ORDER-LIVE-THU** blocked-live: Thu 2026-10-22 09:30-11:30, one 2-leg spread through two baskets, then an exit, 0
   mismatches, holdings unchanged, pnl_equal, audit chain verified.
9. **Screens** in journey order: S1 BUILDER-WIRE; S2 W-118-sel; S3 CREATE-GUIDED; S5 EXECUTE-REVIEW; S6 ORDERS-SCREEN;
   S7 POSITIONS (W-111 part 2 after #400, W-083 AC-2 adopt path per ADR-096); S4 MY-STRAT-HISTORY + DRAFT-DELETE (on held
   #393); S9 ALERTS-THREAD with REQ-041/042/043/062/064/#107 (4c rows stay `blocked` until the 4b rows close, ADR-112);
   LIVE-POS-TAB (#434); S10 ADJUST; S8 ZERODHA-CONN (on held #397); S11 #433, MARKET-CTX, LEARN (#435 content), F-47;
   S12 LANDING; S13 BILLING-SHELL (ADR-055: shells only).
   Shared-state rows built once and used everywhere: ST-MKT-CLOSED, ST-SESSION, ST-TWO-BASKET, ST-RETURN, ST-EMPTY.
   Close-out gate: E2E-J1 (journey 1 at 390 px: Home -> Create Strategy -> Builder -> Execute -> return page -> Orders).
10. **Carried from the superseded GC-3G / GC-4 / GC-5T** (same rows, contract changed to GC-6): #234, #404, #199, #220,
    #297, #126, #344, #318, #247, IDX-FLAT (blocked-live), DRAFT-LABEL; #200 stays `parked #200` (independent redesign
    allowed as its next step).
Out of this contract by owner decision D6: platform sign-in/sign-out and the identity screens (stage-5 rows), #129, #112.

## 5. Verification per row (nothing half built)
1. Builder: failing test first on the real function, then code; targeted tests only; `Report: evidence-table`.
2. Tier A (orders, money, reconciliation, DB, security, hooks/workflows, the Execute route): a fresh Opus reviewer,
   hands-on attacks first, at most 2 rounds; then an independent redesign; a third red -> second independent reviewer +
   re-plan, owner told (section 2). **Review rounds run as a READ-ONLY `general-purpose` agent with `model: opus`, never
   as the `verifier` agent type:** a running `verifier` arms the in-flight gate, which refuses EVERY builder's git writes
   in the session (2026-10-19: the #313 builder spent its whole budget on refused writes). The `verifier` type runs only
   for the final evidence pass of a requirement (it writes the evidence blocks), dispatched when no builder is mid-write.
   A stopped verifier's leftover snapshot files are removed by the session that ran it (run-discipline E2).
3. Tier B (screens computing no money): Sonnet diff review; every screen also: `data-testid="page-title"`, Vitest,
   Playwright e2e on the recordings or `OUTCOME_REPLAY=1`, screenshots at 1280 px and 390 px read back, an ADR-003 grep.
4. The orchestrator re-runs the row's `verify:` command itself (a worker's word is never relayed) before `closed`;
   evidence via `record_evidence.py` under `evidence/<W-id>/`; a requirement whose ACs are all met gets a verifier pass,
   then `trace_check.py`.
5. Completeness audit before close-out: `tracker_check.py` (plan ids <-> rows <-> evidence on main) first; then a fresh
   Opus auditor that built nothing reads only the gaps the script lists. Each gap goes back to work. Still red after 3
   audit rounds -> a second independent reviewer + re-plan, owner told. The close-out carries a table of ALL GC-6 rows.

## 6. CI and token rules
- A branch stays local in its worktree until the fast local checks pass and it is review-ready: one push per review
  round (CI runs on every PR push, drafts included). Same-area items in one stack; main merged in once before the gate.
  Two docs PRs in the contract (this one, the close-out). Red CI: `gh run view <id> --log-failed`, fix, push once.
- Sonnet builds Tier B, docs, and Tier A with a tight brief (O0, O1, O1.5, #263, #115, #401 interim); Opus builds only
  D3/#390, #380-2/3, #313, #400 (each brief: `Why Opus:`); the fresh-Opus verifier stays on every Tier A PR.
- Briefs: `docs/process/builder-brief.md` + item part only, `Design basis:` section only, `check_brief.py`, `Budget:`,
  reports under ~300 words, logs to files. Reuse: W-113 card, `useIndexAnswer`, the Builder components, the legacy-reuse
  map (`Copy from:`). No recurring cron; one Monitor per CI wait.
- Worktrees: one per row (`OptionsForOptions2-<row>`; review checkouts in the scratchpad), removed when its PR is pushed
  via `agentwt.py release`; tracked-file and package counts of the main checkout compared before/after (F4).

## 7. Stops (genuine only)
The core proof fails; every remaining row is blocked on the owner, the live market or ADR-055 and the owner has not yet
answered; a destructive or production step. Never a status report.

## 8. Owner decisions this contract builds on (2026-10-19, question tool)
D1 finish rule; D2 shared-contract flat lift (ADR-116); D3 two baskets (ADR-117); D4 no what-if sliders in V1 and D7 no
guessed next-day fills (ADR-120); D5 draft delete (ADR-118); D6 sign-in out of this plan; D8 Execute only in market hours
(ADR-119). Already decided earlier, cited not re-asked: ADR-080 (3) + ADR-095 price protection (OQ-1); ADR-096 adopt path
(OQ-7); ADR-055 billing hold; REQ-012 AC-1 Google sign-in.

## 9. Review log (independent reviews of the plan, 2026-10-19)
Accepted: expert C1-C4, M1-M5, minors; usability C1-C4, M1-M4, M6, minors; delivery #1, #2, #4-#11. Partly: usability
M7 (deep-link to Orders after Kite; bottom bar unchanged), delivery #3 (buildable defined, audit escalates after 3
rounds). Rejected: usability M5 rename of "Check with Zerodha" (REQ-073 wording; a gloss instead); delivery #3's "close
PARTIAL after 3 audits" (contradicts D1 and the owner's no-silent rule). Full table: the approved plan's "Review log".
**Chain rule 3 review of this contract (fresh Opus, 2026-10-19 ~20:30 IST): GO WITH FIXES, 0 CRITICAL / 7 MAJOR / 7
MINOR, all accepted and applied in this PR:** M1 partial fill vs "COMPLETE" (ADR-117 (2)(a) + REQ-056 AC-4 now: final
at Zerodha with a fill > 0, sells capped); M2 REQ-073 AC-1 / REQ-056 AC-1 per entry step; M3 chain rule 2 lock check;
M4 "main-line" defined, GC-6 status "RUNNING (parallel, rule 1b)"; M5 rows POSITIONS, REVIEW-421, REVIEW-424,
#353-VERIFY, HOME-NEW, IDENTITY-SCREENS added; M6 #423/#435/#433/#434/#439 set to `todo`; M7 runnable verify lines on
every GC-6 row (order/money rows specific); m1-m3 refinements marked in ADR-117/119 and every basket build gated by
ADR-119; m4 owner acceptance checked by TRACKER-CHECK-PLAN; m5 #411/#422 contract aligned; m6 DB-CONNLIMIT closes
with POOL-BUDGET; m7 heartbeat written out in full.

## 10. Resume state (handover 2026-10-19 night; the owner clears the session and runs the goal prompt below)
The first session (a47e05b8) ran 20:16-~22:30 IST and released `lock/gc-6` at handover; the next session takes it
fresh (chain rule 2, parallel lock). Every worktree it created is removed; every branch below is pushed. The truth is
the tracker rows (contract `GC-6`), not this list; this list is the starting point:
- **Closed:** S0 (#446), HARVEST-DRAFT (Startup-Factory#152). BUILDER-WIRE: PR #447 (see its row for merged/CI).
- **Held, reviewed PASS:** POOL-BUDGET draft PR #448 (core proof = its CI api job; read it first).
- **Built, review findings to fix (round 2):** MKT-HOURS (gc6/mkt-hours), CI-SPLIT (gc6/ci-split, round-2 review only).
- **Built, not yet reviewed:** CREATE-GUIDED (gc6/create-guided; apply ADR-121 (1) first), #313a (gc6/313a-migration).
- **Next to start:** #313b, KILL-SWITCH (on gc6/mkt-hours), INSTR-FRESH, TOKEN-RETURN, DUP-TAG, W-083-AC2, then the O2
  order rows, O3 money rows, and the screens in section 4's order.
- **Wednesday 2026-10-21:** GC-3F (main line, owner present) runs item 1 at 09:30; GC-6 starts no API and runs no DB
  test in its live window and holds every backend/Tier A merge until GC-3F's held merges finish (~11:00).
- **Thursday 2026-10-22 09:30-11:30:** ORDER-LIVE-THU needs the owner (Kite login, typed go, Place on Kite).
- **Owner answers since the plan:** ADR-121 (range reading; "Wed 21 Oct"). Information already given to the owner:
  REQ-024 moved to Approved under ADR-114 + the GC-6 plan; the core proof runs on CI's PostgreSQL, not ofo_dev.

## The goal prompt for this contract
> Run GC-6 for this repo: git pull main, read docs/process/goal-chain.md, docs/process/goal-contract-GC-6-2026-10-19.md
> (sections 0-10 in full, section 0 first) and the GC-6 rows of docs/process/build-ahead-tracker.md, and run the contract
> under its rules from its section 10 resume state. Take lock/gc-6 (chain rule 1b; refuse if it exists and the owner has
> not cleared it as stale). Obey section 0 at every step: never assume a business answer - ask the owner with the
> question tool (one question per call, recommendation first, Business call and Spec basis lines) and write the answer
> into the spec the same turn; decide technical calls by role and tell the owner as information; raise every issue the
> moment it happens; never drop, merge or narrow a row without the owner's OK. Every row needs its verify command re-run
> by you before it is closed. Review rounds use a read-only general-purpose Opus agent, never the verifier type
> (section 5). The goal is MET only when the transcript shows: (1) every GC-6 row in build-ahead-tracker.md `closed`
> with evidence, or its blocked status accepted by the owner and dated on the row; (2) the completeness audit clean;
> (3) the close-out PR merged with the next contract written and checked; (4) a final message with the all-rows table,
> the scorecard and the evidence table; (5) lock/gc-6 deleted. IMPOSSIBLE only when every remaining row waits on the
> owner, the live market or ADR-055 and the owner has been asked. Never stop for a status report.
