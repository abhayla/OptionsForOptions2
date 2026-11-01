# Session handover - GC-MU, 2026-11-01

Contract: `docs/process/goal-contract-GC-MU-2026-11-01.md`. Branch: `build/gcmu` (run tree
`D:\Abhay\Ventures\OptionsForOptions2-gcmu`). It ran beside GC-SET (`build/settings`) under
`D:\Abhay\Ventures\OptionsForOptions2-coord\PROTOCOL.md`. Nothing went to main, no PR was opened, no order was placed,
nothing was deployed. GC-SET had NOT merged into `feature/adjustments` at close, so `feature/adjustments` was not touched.

Final head and gate: see "Close" at the end.

## DONE (merged into build/gcmu)

| Item | Merge | Proof (recorded in this run) | Review |
|---|---|---|---|
| Step 1: #519 shared-compute keys built from the engine call | 33df89e4 | key = exact engine arguments; mutants killed (Tier A PASS, 2 MINOR) | Tier A |
| Step 1 T1: frontend money-arithmetic scan | f160a2cd | five shapes pinned red | Tier B |
| Step 1 T2: range rule | 4a2bde2b (docs) | F-90: `readingFromRange` lives only in the browser (REQ-063 AC-2); deferred #625 | - |
| Step 2: #517 REQ-048 AC-5 redesign (reply inventory + value canaries) | 65fe3b69, inventory 14991922 | 6/6 registration mutants killed (1b2 killed by a test added at close: 5c0f2679) | Tier A (round 1 REVISE; round 2 verifier ran no attack, so the orchestrator ran the mutants) |
| Step 3: W-137 / #520 MINORs + `liveprices` role | 1430742e | round-1 MAJORs fixed; M1/M2/M3/M5 killed; 300 s skew window pinned at both edges | Tier A |
| Step 4: background role (REQ-115/165/166) | 02a00755 | core: ADJ-02, no client, one record 0.40-0.61 s after the price; state via the screen's `state_of`; 6 + 5 mutants killed; loop failures contained | Tier A (read-only review: MAJOR found + fixed) |
| Step 4b: background wanted-token key unioned by the feed | 0bcd8700 | 9 new tests + 8 feed test files green | orchestrator |
| A1: liquidity limits (ADR-230 (1)) | 5f9da8b5 | remainder parked #624 | Tier B |
| A2: Compare cost rows + charge breakdown | b6c1957f | API on ADJ-13: "Cost as % of premium left" 2.28 % / 3.53 % / 1.72 %, "Change in max profit", per-charge breakdown (brokerage, STT, exchange ...) on the cost cell | Tier B |
| A3: card mark "N adjustment opportunities" (+ round 2: Dismiss on the inbox row, c4869ef6) | 431f56a0 | API on ADJ-02: card 72 reads "3 adjustment opportunities" -> 2 after one dismiss -> no mark after all three | Tier B |
| A4: two stops = whichever comes first | 4e25e9cf | plan sheet + summary tests | Tier B |
| A5: "Adjustments used" from the history count | a2d8cefc | API on ADJ-13 reads "2 used" - correct for the stored orders, which hold 2 adjustments because the SEED is wrong (#628) | Tier C |

Every shared-file change has a line in `coord/overlaps/GC-MU.md`.

## PENDING

- **T3** (ADR-220 (4) Greeks comparison on one real NIFTY chain): needs market hours and the owner's Kite login. First
  session: Mon 2026-11-03 09:15 IST. Not parked; blocks nothing.
- **Step 4c** (the worker writes its legs' tokens to the 4b key): DONE, merged fa6f3646 (7 answer-state tests; the
  `_serve` Redis wiring is `pragma: no cover`, not run against a real Redis - first real proof is with the feed on a
  market day, together with T3).

## Screen proofs (owner's Chrome, 2026-11-01 08:13-08:50 IST, after the owner connected Chrome)

- **A2:** ADJ-13, `/strategy/builder?adjust=73`. "Cost as % of premium left" reads 2.28 / 3.53 / 1.72 / 5.10 / 3.34 %,
  and Exit reads "-" with "no premium is left to earn". "Change in max profit" renders. The charge breakdown opens on
  tap and adds up: for the roll toward spot, Rs 114.35 in charges + Rs 91.00 bid-ask = Rs 205.35.
- **A5:** the "Adjustments used" row renders "2 used" / "3 used". That count is the stored orders' count, which is
  wrong because of the seed (#628).
- **A1:** the liquidity row renders, with "Tightest spreads" marked as the leader.
- **A3:** ADJ-03, strategy 76. The card read "3 adjustment opportunities" and linked to `?strategy=76`. The inbox had
  no Dismiss, which is a gap against ADR-230 (2), so A3 round 2 added Dismiss to the inbox row (merge c4869ef6). One
  click then dismissed all 3, and the card mark was gone.
- **390 px** (a 390 px frame, because the window was maximized): the Compare scrolled 159 px sideways, the editor
  27 px and the inbox 300 px. All three were fixed in 44cbcb25. After the fix, all four page states measure 372 = 372
  with no sideways scroll. The screenshots are local, in the Chrome screenshot temp folder (`claude-chrome-screenshots-*`).
- **Found during the proofs:** #630 (a "no current price" dash, seen once, not reproduced); #631 (a dropped DB
  connection gives a 500); old inbox rows stored before 10-31 still show raw trigger codes ("T-01: 0.3416").
- **No detection change** for the 390 px class: jsdom has no layout, so the guard is a real-browser check at 390 px
  (an e2e step).

## BLOCKED

- Nothing.

## PARKED / DEFERRED (issues)

- #624 parked: A1 remainder (an unreadable playbook fails open; the drawer has no strike flags).
- #627 parked: step 4 remainder.
  - The background never reads margin, so T-16 is not checked with no screen open.
  - T-13 has no open-price reader.
  - There is no restart service and no heartbeat alert (the Notifier part of REQ-115 AC-6).
  - The screen does not read the worker's result (REQ-165 AC-6).
  - The valuation time differs from the screen's by about one tick.
  - REQ-050 AC-3 recompute count.
- #623 deferred: the Compare low-OI cell's 64-character slot.
- #625 deferred: F-90, the range-reading rule lives only in the browser.
- #626 deferred: no Content-Security-Policy `connect-src 'self'` (step 2 D3).
- #628 deferred: `seed_scenario.py` batches a scenario's trade wrongly (ADJ-13 seeds 2 adjustments, the scenario has 1).
- #630 deferred: the Compare showed "no current price" for a current leg once in scenario mode; not reproduced.
- #631 deferred: the DB pool has no pre-ping, so a dropped connection turns the next request into a 500.
- Step 3 MINOR (not filed separately): after expiry the status reads `phase: live` with `ended: True`.

## Owner answers (owner back 2026-11-01 ~08:00 IST)

- Q-MU-1 -> ADR-231: the roll debit limit is the HIGHER of Rs 500 and 10% of max profit (as built in A1).
- Q-MU-2 -> ADR-232: the card counts open conditions, not inbox rows (as built in A3).
- The 25 GC-MU texts (A1 6, A2 15 + 2 label lists, A3 2): approved as recommended, so the pins are marked owner read
  (3a8073c1).
- The other 461 pending catalogue texts: an independent wording check runs first, then the owner reads only the
  flags (#629). This is a separate task after GC-MU.
- Kite: the owner logs in on Mon 2026-11-03 at 09:15 IST or later for T3. A login today does not help, because the
  market is closed and the token expires at 06:00.
- These records are on `build/gcmu-docs` (9890e0f0, 3a8073c1, plus this file), merged into `build/gcmu` after the backup
  push.

## MERGE-SWAPs left for the integration (GC-SET stand-ins)

- `backend/ofo_app/calc_speeds.py`: speeds and safety-valve limits. Read from the settings store with GC-SET's reserved
  keys: `speeds.per_option_seconds`, `speeds.background_check_seconds`, `speeds.valve_step_seconds.1/.2/.3`, and
  `speeds.open_strategy_seconds` (read only). GC-SET's step 6 guard fails on a registry key with no reader, so add the
  keys WITH their readers at merge.
- `backend/ofo/adjustment/compare.py` `cost_pct()`: ADR-221 one cost function.

## What GC-SET was told (coord inbox, both directions in coord/log.md)

- Step 3 merged.
- The reserved speed keys are used as given, and `adjustment_check.py` was not touched; GC-SET fixes `condition_line`
  T-10b.
- Each verifier start, because a verifier blocks git writes in every worktree.
- #626 filed.

## Lessons (process)

- **Verifiers ran out of budget three times** (step 3: 1 h 40 min against a 20 min cap; step 2: 25 min with 0 mutants
  run). Each one tried to set up a database scratch copy inside a ~200k-token context. What worked: the orchestrator runs
  the mutants itself (a cheap script, restored by bytes, never git from a script), and the verifier is given a
  READ-ONLY brief with concrete questions. That read is what found step 4's MAJOR.
- **Step 4 round 1 copied the screen's state builder,** and the copy dropped five fields. The builder brief should
  carry "reuse the screen's state function; never a copy" (C3 structural guarantee).
- **A test that feeds prices directly hid that no price would arrive in real use** (the feed subscribes only the API's
  wanted set). The core proof must name the real input path.
- **Proving on the real seeded data found #628** (A5 count) that every fixture test passed.
- **An unbounded in-memory list in a long-running role** (step 4 `checks` / `errors`) got past every review; it was
  capped at close.

## NEXT

1. **Integration, after GC-SET merges into `feature/adjustments`:** merge it into `build/gcmu`, resolve with both
   overlap ledgers, swap every MERGE-SWAP above, regenerate the reply inventory (`python scripts/reply_inventory.py`,
   review every UNREVIEWED), run the tests of every overlap file, run `prepush.py --full` (heavy slot), then merge
   `--no-ff build/gcmu` into local `feature/adjustments` and push it as backup. No PR; nothing to main without the
   owner's explicit OK.
2. **T3,** at the first market session with the owner present (Mon 2026-11-03 09:15 IST earliest).
4. **#628** before any further screen proof on ADJ-13.
5. **Foundation steps 5-7** after sign-in.
6. **#629:** the wording check of the 461 pending texts, then the owner reads the flags (after the integration, so the texts are final).

## Close (step 9, GC-SET not merged branch)

- The commit that adds this file is the final head of `build/gcmu`. `python scripts/orchestrator/prepush.py --full`
  runs on it under the heavy slot, and its marker is in `<git-common-dir>/ofo-prepush/<sha>.json`. The pass or fail
  line and the sha are in the run's final report and in the memory note `gcmu-contract-2026-11-01.md`.
- On TOTAL PASS, `build/gcmu` is pushed to origin as backup only. No PR; `feature/adjustments` and `main` are not
  touched.
- The worktrees whose use ended are removed with `wt-rm.ps1` after the push, with counts printed: gcmu-key, gcmu-liq,
  gcmu-feed, gcmu-door, gcmu-stops, gcmu-t1, gcmu-cmp, gcmu-mark, gcmu-used, gcmu-bg, gcmu-want, gcmu-wire, gcmu-inbox, gcmu-docs. The run tree
  `OptionsForOptions2-gcmu` stays, for the integration.
