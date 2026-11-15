# Iron condor user test, 13 Nov 2026: issues, tasks and the goal contract

## Context

On 13 Nov the iron condor flow was tested on live prices in Chrome, like a user: 10 practice trades, 6 kinds of
adjustment, about 190 raw notes, merged into 43 problems and checked against the written requirements.
**The arithmetic underneath is sound (every hand check of money matched). The faults are in what the screens show and
in settings that are saved but not acted on.**

This plan turns the problems into issues with a severity and a priority, splits every issue into tasks of at most
15 minutes, names the common tasks that repair several issues at once, and ends with a goal contract (GC-ICFIX) to be
run in a fresh session. Nothing goes to the live servers. Critical (P0) first, then P1, P2, P3.

Private source notes on this PC: `D:\Abhay\scratch\ic-uitest-2026-11-13\` (`ISSUES.md` raw, `SORTED.md` merged,
`SPEC-SCREEN.md` checked against the requirements).

## Your answers in this planning session (13 Nov evening); the run writes them as decision rows first

| Id | Your answer | What it means for the work |
|---|---|---|
| T | Tracker: "do not remove the existing task, just add these" | Old rows stay. New rows are added. An old row is marked done only if ALL of it gets done here. |
| D1 | Profit target = **before charges** | The target rule keeps comparing profit before charges. The alert must say which figure it used. A target can fire on a trade that loses after closing costs (143: +61.75 before, -218.85 after). |
| D2 | A trade **may have no plan, but the page must say so** | Nothing is saved for the user. The page shows "No plan saved yet: default rules apply", the default target and stop, and a "Set plan" button. |
| D3 | After the user adjusts a stopped trade, the stop **goes quiet until it crosses again** | Grey "Already true after adjustment N" line; no red warning until the loss clears the line and crosses again (144 went 2.4% to 9.7% quietly under this rule). |
| D4 | At the adjustment limit: **exit and reduce only** | The offer screen says "Adjustment limit reached (2 of 2)"; rolls, shifts, conversions are listed as not offered with the reason. |
| D5 | **Practice behaves exactly like a real trade** | "Not enough funds" stays on practice trades. Rule for every task: practice shows what real would show. My reading: it stays a message and does not refuse the practice order (your account shows about Rs 400 free). |
| D6 | Status words: **Draft / Running / Completed** | "Tracked" and "Waiting to start" go; the Paper or Zerodha tag stays beside the word. |

Decided by me under your standing rules (strategy and technical calls are mine); change any at approval:
- Guided builder: a condor that breaks the entry guide (138: delta 0.46) is shown with a plain warning line, not hidden.
- The offer screen shows every approach that applies (already written: ADR-214); the side-panel ticks only preselect.
- "Take profit" uses the same basis as D1 (before charges) and always shows the after-charges result beside it.
- The pop-up alert names the trade and opens that trade's offer screen (already written: REQ-162 AC-1, ADR-260).
- Time exit: no rule change (ADR-238: expiry day only). The plan screen gets the words "on expiry day".

## How the work is delivered: one branch, one push, one pull request, one CI run

Planned in the role of a **release lead**: the person whose job is to get many repairs out with the least waiting.

**Your instruction (13 Nov):** no pull request and CI run per repair; work on one branch; push everything together
when all the work is complete.

**What cost your time before, measured in this project:** each pull request waits about 26 minutes for CI, the full
pre-merge check takes 45-65 minutes on this PC, and merging one pull request puts the next one behind main so its CI
runs again. Ten small pull requests is roughly a working day of waiting. One pull request is about 1.5 hours.

**The plan:**
1. **One branch for everything:** `fix/gc-icfix`, in its own folder beside the project. Every repair lands there.
   Builders still work in their own scratch folders; their checked work is merged into the one branch on this PC.
2. **Nothing is pushed while the work runs.** No pull request, no CI, no merge to main during phases 1 to 5.
3. **Quality is kept by local checks, which cost machine time but none of yours:** a failing test first and an
   independent checker per issue; the fast local checks at every issue; the full local pre-merge check ONCE at the
   end of each priority (P0, P1, P2, P3), left running unattended.
4. **Screen proof runs from the branch.** The app on this PC is started from the branch folder, so every repair is
   seen in Chrome before anything is pushed.
5. **At the very end, on your word: one push, one pull request, one CI run, one merge.** The run stops at "ready to
   push" and tells you. Nothing leaves this PC before that.

**What this trades away, said plainly:**
- **One big pull request is harder to review and a red CI is harder to trace.** Covered by: the per-priority full
  local check (the same checks CI runs), and a list in the pull request of every issue with its test and proof.
- **Until the push, the work exists only on this PC.** Covered by: a backup file of the branch written to
  `D:\Abhay\scratch\gc-icfix-backup\` at the end of every priority (a single file that can restore the whole branch).
- **Main does not get any repair until the end.** If you want P0 on main early, say so and that priority gets its own
  push: at most 4 pushes in total, never one per repair.
- **Other work merged to main meanwhile must be pulled into the branch.** Done at the start of each priority, so
  the final merge is small.

## Severity and priority

**Severity:** Critical = the user acts on wrong money or relies on protection that is not there. Major = blocked, or
not told something needed. Minor = clumsy or confusing.
**Priority:** P0 first, then P1, P2, P3, in that order, as you asked.

## Common tasks: one repair that clears several issues

| Common task | What is built once | Issues it clears or shrinks |
|---|---|---|
| **CT-A One profit figure, after charges, labelled** | Every screen reads profit from the one engine and says "(after charges)"; the frozen panel refreshes | 3, 4, 16, 19, 24 |
| **CT-B A panel never shows nothing when its data fails** | One shared "could not load, retry" state, used by every panel on the trade page | 2, 18, 19 |
| **CT-C One alert record that names its trade and rule** | Pop-up, bell and Alerts list all read the same record: trade name, rule, value, time | 8, 12, 19 |
| **CT-D One dialog frame that scrolls with its buttons pinned** | Order review, exit confirm and plan box share it | 6 |
| **CT-E One place that decides a trade's state** | Draft / Running / Completed from one function, used by every list and card | 16, 25 |
| **CT-F "The value in force" for every plan field** | Plan, else playbook, else system default, and every alert names the value it used | 1, 7, 15, 22 |
| **CT-G Speed under load** | Find and remove the cause of the 12-18 s answers | 2, 9, 26 |

## Issues and their tasks (each task at most 15 minutes)

Task ids are the tracker row ids. "Check" = an independent checker that did not build it. "Screen" = done in Chrome
on a practice trade, like a user.

### P0, the critical ones (work on these first)

**Issue 1. The plan's Target is saved but never acted on** (Critical). 141: target 1%, profit Rs 32-49, nothing fired.

| Id | Task | Done when |
|---|---|---|
| u101 | Independent check of the repair built today (commit 5ecab208), incl. the background watcher path | verdict with the re-run test counts |
| u102 | Correct what the check finds (one round) | tests green, or parked with evidence |
| u103 | The target alert names the value and basis it used ("before charges", D1) | test |
| u104 | Screen: plan target 1% on a practice trade fires at its own value | screenshot + tracker line |

**Issue 2. Plan box fails after placing; no retry; plan card vanishes; trade runs on rules the user cannot see** (Critical). 4 of 8 trades.

| Id | Task | Done when |
|---|---|---|
| u111 | CT-B: failing tests: plan card and plan box with a failed read | tests red |
| u112 | CT-B: shared "could not load, retry" state; plan card and plan box use it; 30 s limit for this one request | tests green |
| u113 | D2: no-plan state: "No plan saved yet: default rules apply", defaults listed, "Set plan" | test |
| u114 | New on-screen words through the wording catalogue | catalogue test green |
| u115 | Check of u111-u114 | verdict |
| u116 | Screen: force a slow answer; retry works; a no-plan trade says so and can be given a plan | screenshots |

**Issue 3. Profit shown before charges, unlabelled** (Critical). 141: -32.50 shown, -435.95 real.
**Issue 4. Three different profit figures on one screen; one panel frozen** (Critical). 138: +29.25, +22.75, +58.50.

| Id | Task | Done when |
|---|---|---|
| u121 | CT-A design (Opus): list every place a profit figure is shown and where each reads from | list of screens with file names |
| u122 | CT-A: failing tests from the real cases (141, 143 closed; 138 three figures) | tests red |
| u123 | Trade page totals read the engine's after-charges figure and carry "(after charges)" | tests green |
| u124 | "Profit left / Loss left" built from the live figure, never above max profit | test |
| u125 | Completed list row: final P&L, charges, net after charges (ADR-259) | test |
| u126 | Frozen panel: second round on this morning's repair (the timing test that failed under load) | that test green 5 runs in a row |
| u127 | Before-charges figure and the charges breakdown one tap away (ADR-263) | test |
| u128 | Requirement wording: REQ-109 AC-10 brought in line with ADR-263 | file changed |
| u129 | Check by Opus (money): every figure, both real cases, hand arithmetic | verdict |
| u130 | Screen: on one practice trade the three figures agree, say "(after charges)", and match a hand sum | screenshot + sum |

**Issue 5. Stop warning freezes and gives no rupees** (Critical). 144: 2.07% shown for 5 min, real 7.46%.

| Id | Task | Done when |
|---|---|---|
| u141 | Failing test: warning value must follow the live figure | test red |
| u142 | Warning refreshes with the tracker; shows loss and stop line in rupees and percent, and the time it fired | tests green |
| u143 | D3: after an adjustment the stop shows the grey "Already true after adjustment N" line until it clears and crosses again | test |
| u144 | Check of u141-u143 | verdict |
| u145 | Screen: lopsided practice trade, stop 1%: live value moves; goes grey after an adjustment | screenshots |

**Issue 6. Confirm button unreachable on a large adjustment** (Major). 8-order review box on a 639-px page.

| Id | Task | Done when |
|---|---|---|
| u151 | CT-D: failing test on the shared dialog frame (body scrolls, buttons outside the scrolling part, height bound to the window) | test red |
| u152 | CT-D: repair in the shared frame; order review, exit confirm, plan box use it | tests green |
| u153 | Check, incl. whether a real-order dialog shares the frame (layout only, behaviour untouched) | verdict |
| u154 | Screen: iron butterfly conversion (8 orders) confirmed on this laptop; legs and money match the promise | screenshot + hand sum |

**Issue 7. "Customise triggers" edits the shared rules for every iron condor** (Critical).

| Id | Task | Done when |
|---|---|---|
| u161 | Read how the plan box opens the editor today; failing test: a system playbook is never opened for editing from a trade | test red |
| u162 | "Customise triggers" opens a personal copy for this trade (REQ-045, REQ-158 AC-6) | tests green |
| u163 | Alerts and history show the value actually used (143: 0.5% shown, 0.25% set) (ADR-245) | test |
| u164 | Check of u161-u163 | verdict |
| u165 | Screen: customise on one trade; a second trade's rules are unchanged | screenshots |

**P0 close (no push, no pull request, no CI)**

| Id | Task | Done when |
|---|---|---|
| u171 | All checked P0 work is on the one branch `fix/gc-icfix`; fast local checks | `ci_local` result line |
| u172 | Full local pre-merge check on the branch, started under Desktop Commander, watched by a script | TOTAL PASS line |
| u173 | Backup file of the branch written to `D:\Abhay\scratch\gc-icfix-backup\` | file name + size |
| u174 | App on this PC restarted from the branch folder; health check | health 200 + commit id served |
| u175 | Record the lasting findings (6 classes) in the findings folder, on the branch | files listed |
| u176 | Handover note for P0, on the branch | file path |

### P1: the user is not told, or is not protected

| Issue | Sev. | Tasks (ids u2xx) |
|---|---|---|
| **8. Alerts do not name the trade or rule; bell leads nowhere** | Major | u201 CT-C failing tests (pop-up, bell, Alerts list from one record) · u202 pop-up names trade and rule, opens that trade's offer · u203 bell count = open items of Alerts > Active (ADR-260); the "Alerts is coming" page replaced by the list · u204 check · u205 screen with two trades open |
| **9. Risk alerts arrive minutes late** | Major | u211 measure where the 2-4.5 min goes (watcher interval, candle wait, pop-up poll) · u212 stop alerts skip the candle wait (REQ-170 AC-5) · u213 check · u214 screen: stop to pop-up under 30 s |
| **10. No warning when a protective leg is removed** | Critical | u221 failing test from 139 · u222 warning line on every exit confirm list: before and after max loss and margin (ADR-256) · u223 check · u224 screen |
| **11. "Take profit" on a losing trade, same as Exit** | Major | u231 failing test from 141 · u232 refused with its reason when not in profit; shows the after-charges result (ADR-238 (6), D1) · u233 check |
| **12. Fired rules invisible on the trade's page** | Major | u241 a rules line on the trade page: each fired rule, its value, limit and time; "not being checked" shown as such · u242 check · u243 screen |
| **13. Rules flip on and off on noise** | Major | u251 read the stored starting point and re-arm margin for 142; failing test · u252 repair so one crossing gives one record (REQ-170 AC-1, AC-2) · u253 check |
| **14. Offer screen shows 1 of 8, ignores ticks** | Major | u261 default = every approach that applies, "Showing N of M" (ADR-214) · u262 check + screen |
| **15. Typing a Target resets other fields; same-day trade defaults to slow alert speed** | Major | u271 failing tests · u272 repair; a "refilled from playbook" note when a playbook is picked · u273 check |
| **16. Closed trades stay on Live Strategies with old legs** | Major | u281 CT-E failing tests · u282 one function for Draft / Running / Completed (D6); closed trades leave Live Strategies (ADR-259) · u283 cards read current legs and figures · u284 check + screen |
| **17. Two-expiry trade drawn with a capped loss** | Major | u291 graph shows no curve and the reason when max loss cannot be estimated · u292 check + screen on a diagonal roll |
| **18. Screen breaks after placing orders** | Major | u301 reproduce "could not refresh" and the empty builder; failing test · u302 repair with CT-B's shared state; builder reopens on the Paper tab · u303 check + screen |
| **19. At the close: stop warning and plan card vanish; stale figure; raw label as an alert** | Major | u311 plan card and last warning stay visible, marked "as of 15:30" · u312 the weekend reminder gets its sentence or is not raised (ADR-267) · u313 offer screen cannot prepare orders on stale prices · u314 check |
| **D4. Adjustment limit: exit and reduce only** | Major | u321 failing test at 2 of 2 · u322 sentence + only closing approaches offered; others listed as not offered · u323 check + screen |
| **P1 close (no push)** | | u331 pull main into the branch; fast checks · u332 full local pre-merge check · u333 backup file of the branch · u334 restart from the branch, health · u335 findings + handover |

### P2

| Issue | Sev. | Tasks (ids u4xx) |
|---|---|---|
| **20. Practice trades cannot be deleted** | Major | u401 this morning's repair (built) rebased on main, tests · u402 check · u403 screen: delete 3 practice trades, Undo one · u404 remove the old practice trades from the screen (about 70; Haiku) |
| **21. Adjustment history unreadable after close; entries unnamed** | Major | u411 history names the approach and shows on Completed trades · u412 check + screen |
| **22. Clock alert offers no action; plan accepts a time on any day** | Major | u421 plan screen and card say "Time exit (on expiry day)" · u422 clock alert before expiry day is not raised without an action · u423 check |
| **23. Rule already true at entry: 142/143 alerted at once, 138 silent** | Major | u431 read the stored starting points of 142, 143 · u432 repair or record why it is correct (ADR-258, ADR-283) · u433 check |
| **24. One contract with no price blanks the whole practice total** | Major | u441 failing test · u442 total shown for what has a price, the rest named · u443 check |
| **25. Status words disagree** | Minor | covered by u282 (CT-E); u451 screen check on every list |
| **26. App slow under load** | Major | u461 measure with the old trades cleared (after u404) · u462 profile the plan and rule-check answers · u463 remove the top cause · u464 re-measure: plan answer under 3 s with 6 open trades |
| **Guided builder too close** | Major | u471 warning line when sold strikes break the entry guide (ADR-216) · u472 check |
| **P2 close (no push)** | | u481 pull main into the branch; fast checks · u482 full local pre-merge check · u483 backup file of the branch · u484 restart from the branch + handover |

### P3 rough edges (one task each unless noted; ids u5xx)

u501 wording and number formats (one style for dates, grouping, dashes) · u502 Save button shows saved / unsaved;
stale "saved" message · u503 strategy name editable in place or not styled as editable · u504 placeholder pages
("Home / Strategies / Positions is coming") given a real link or removed from the menu · u505 layout jumps on the
strike controls · u506 pop-up no longer covers the Search box · u507 Greeks carry units and 2 decimals · u508 fill
price shown beside the "about" price after an exit · u509 approach names match what they do ("roll out" that keeps
the expiry; butterfly that moves wings) · u510 expiry labels: year on far expiries; Monday 23 Nov checked against the
exchange calendar · u511 adjustment-opportunities list: paging, plain text · u512 brokerage rate confirmed against
the broker's page · u513 "4 pending changes" with no edits · u514 check of u501-u513 · u515 pull main into the
branch, full local pre-merge check, backup file, handover (no push).

### Tests that live prices could not reach (run on generated market data, then live on Monday)

| Id | Task | Done when |
|---|---|---|
| u601 | Start test-data mode from the handover's commands; prove ONE rule fires in the background on generated prices | tracker line with the rule flagged |
| u602 | If u601 cannot fire a background rule: record the gap, move u603-u608 to Monday live | gap note |
| u603 | Breakeven crossing | flag + screen |
| u604 | Cheapest sold option nearly worthless | flag + screen |
| u605 | Loss against margin (switched on in a personal playbook copy) | flag + screen |
| u606 | Premium left small against adjustment cost; stale prices | flags + screen |
| u607 | Expiry-day time exit at 14:30, with its action | flag + offer |
| u608 | Stop fires, recovers, fires again | two records |
| u609 | Monday 09:15 [LIVE, needs your Kite login]: opening-gap rule; then re-run of the 13 Nov flow on everything merged | notes file + screenshots |
| u610 | Final report: every one of the 26 issues marked repaired / parked / open, with its proof; the branch is READY TO PUSH; stop and tell the owner | report file |
| u611 | **Only on the owner's word "push":** pull main into the branch, one push, ONE pull request listing every issue with its test and proof, ONE CI run, one merge, app restarted from main, branch folder removed | merge commit on main |

Counts: 7 P0 issues, 46 tasks. 13 P1 groups, 49 tasks. 8 P2 groups, 27 tasks. P3 15 tasks. Tests and close 11.
Setup 6. About 154 tasks, roughly 38 hours of task time, spread over several sessions.
Pushes: 1. Pull requests: 1. CI runs: 1 (more only if that one is red). Full local checks: 4, unattended.

## Verification (how each repair is proven)

- A failing test first, from the real case in the tables (trade number and figures), then the repair.
- An independent checker per issue; Opus for the money display (issues 3, 4).
- One full LOCAL pre-merge check per priority (45-65 min on this PC, unattended). CI runs once, at the very end.
- After each issue lands on the branch, the same steps in Chrome on a practice trade, with the app running from the
  branch, with a screenshot and a hand sum where money is shown.
- The tracker row is closed only with the command or screenshot and its result line.

---

# Goal contract GC-ICFIX: repair what the 13 Nov iron condor user test found (2026-11-13)

**Status:** scope and order approved by the owner in the planning session of 13 Nov 2026 (answers T, D1-D6 above).
Never run before.
**Executor:** `/goal` in a FRESH session of this project. One phase per session: a session finds the first phase
with open rows, runs it to its close, writes its handover and stops. Run the same contract again for the next phase.
**Standing direction:** read `docs/process/standing-direction.md` first and name its step in the run log. This run is
defect repair from an owner-run test, ordered by the owner's words of 13 Nov ("first let's work on the critical
ones ... P0. After that P1, then P2 and P3"); it adds no new approach, trigger or guide content.
**Written against:** main `8b0e0a8a`, 13 Nov 2026 evening.
**Task 0 of phase 1** copies this contract from the plan file
`C:\Users\itsab\.claude\plans\dreamy-mapping-sunbeam.md` into
`docs/process/goal-contract-GC-ICFIX-2026-11-13.md` ON THE BRANCH `fix/gc-icfix` (the whole plan file: the owner
answers, the delivery section, the issue and task tables and this contract) and commits it there with the decision
rows. No pull request for it.
**Delivery rule (owner, 13 Nov): ONE branch, ONE push, ONE pull request, ONE CI run, at the very end and only on the
owner's word.** Until then nothing is pushed.

**Mission, in plain words:** every issue in the tables above is repaired in priority order (P0, P1, P2, P3) on one
local branch, each proven by a failing test first, an independent check, and the same steps repeated in Chrome on a
practice trade with the app running from that branch; the rules live prices could not reach are tested on generated
market data; the run ends with the branch READY TO PUSH and waits for the owner; nothing is deployed to any server.

**Core:** a setting the user saves in a trade's plan is the value the background watcher acts on.
**Proof (task u101-u104, before any other P0 code):** on the running app on this PC, a practice iron condor with plan
Target 1% raises the target alert when profit before charges passes 1% of max profit, and the alert names "1%" and
"before charges". Read back: the rule-check answer for that trade (rule T-07, value, threshold 1) and the screenshot.
If the watcher still uses the playbook value, that cause is fixed before any other P0 task; HALT only if the plan
value cannot be read by the watcher at all.

## §0 Run rules

1. **Idempotent start.** First read: this contract; `docs/process/standing-direction.md`; the newest
   `docs/process/session-handover-*.md`; `docs/process/runbook.md`; `.claude/kit/GUIDE.md`; `git log --oneline -40`
   on main; tracker rows `u*`. A row whose "done when" already holds on main is marked done with that evidence and
   skipped. Never redo finished work.
2. **One branch, one folder.** The integration branch is `fix/gc-icfix`, cut from main, in the worktree
   `D:\Abhay\Ventures\OptionsForOptions2-gc-icfix` made ONCE with `~/.claude/tools/wt-new.ps1` (purpose "GC-ICFIX:
   all 13 Nov user-test repairs, one push at the end"; state the long life as the owner's reason, since it outlives
   the 48 h default: "owner 13 Nov: one branch until all work is complete"). A later session finds that folder and
   branch and continues on it; it never cuts a second integration branch. Builders work in their own short-lived
   agent worktrees cut FROM `fix/gc-icfix`; their checked commit is merged into `fix/gc-icfix` locally by sha after
   a diff read, and the agent worktree is removed with `~/.claude/tools/wt-rm.ps1`. No mutating git in the main
   checkout at all until u611. NO `git push`, NO pull request, NO CI trigger before u611.
3. **Existing work to reuse, not rebuild** (verify each sha exists first):
   - `5ecab208bf88b54d5319157706afafb01c35523b`, branch `worktree-agent-a1ccad3f243c6f4bc`: plan Target read at
     evaluation time (`with_plan_target` in the rule-check route; test `tests_app/test_plan_target_in_force.py`).
     Built, NOT independently checked. Known gaps to check in u101: the background watcher path; a Target above the
     last-stage value; T-07 switched off.
   - `be14b64e43dcbe4a3493912a6c248ecf4852ca5a`, branch `fix/ic-uitest-bundle-2026-11-13`, worktree
     `D:\Abhay\Ventures\OptionsForOptions2-uitest-bundle`: delete of practice trades (ADR-293) + live refresh of the
     practice panel. Full check failed once on `frontend/tests/builder-drafts-mode.test.js` ("Confirm posts the
     orders ONCE ...", expected 3 to be 2) under load; passes alone. The panel half goes into issue 4 (u126); the
     delete half into issue 20 (u401). Merge main into the branch before any new round.
   - The main checkout has uncommitted edits (`CLAUDE.md`, `spec/requirements/REQ-070.md`) and an untracked
     `spec/decisions/ADR-293.md`; the same content is committed on `be14b64e`. Task u002 brings them onto
     `fix/gc-icfix` by merging `be14b64e`'s docs commits (compare each file with the main checkout's copy first and
     record that they match). The main checkout's copies are left exactly as they are until u611; never discard
     them without that recorded match.
4. **Decision rows first (u001).** Write D1-D6 and the three "decided by me" lines as decision rows `ADR-294`
   onward (run `python tools/spec_similar.py . "<text>"` before each; read the body of any match; extend or cite, do
   not duplicate), each with its section text, quoting the owner's answer and the real case from the table above.
   D2 answers the open question in ADR-214 consequences / REQ-161 Why: update both. D3 extends ADR-258 to the stop.
   D4 turns the catalogue's "exit/reduce only" into a decision. D5 states the practice-equals-real rule and that
   ADR-202 (4) applies unchanged. D6 names the status words. Also correct the stale wording: REQ-109 AC-10 ("not
   subtracted") against ADR-263; "Start tracking" in REQ-161 and REQ-109 against ADR-207 (1). Add stage rows for the
   new ADRs in `docs/process/coverage-stages.yaml` (a missing row fails the pre-merge check).
5. **No orders, no servers.** No real order, no Kite order page, no click inside a real-order panel, never open
   kite.zerodha.com. No production or VPS work. No deploy. Margin, funds and the Kite client id never go into any
   file, commit, issue or tracker row (public repo).
6. **Practice equals real (D5).** No task may make a practice screen kinder or looser than the real one.
7. **Tracker.** https://claude.ai/artifact/LcMTSr5xx8LvAYVniotkxK, db collection `tasks`. Load the `ArtifactData`
   tool. NOTHING is removed or rewritten: rows `c*`, `k*`, `n*`, `o*` stay. Task u003 ADDS rows `u001..u610` with the
   same fields as the existing rows (`kind: "task"`, `order` from 401 upward in the order of the tables, `stage` =
   the priority and issue title, e.g. "P0 · 1. Plan Target is acted on", `title` in plain words, `detail`, `est: 15`,
   `doneline`, `state: "todo"`, empty `start`, `finish`, `actual`, `evidence`). Read one existing row first
   (e.g. `k22`) and copy its shape and state words exactly; if the page does not show the new stage names, republish
   the page from an Artifact read of the live page, changing only what is needed. One write at a task's START and
   one at its FINISH (state, clock time from `date` in the same step, minutes, evidence line), `if_version` pinned,
   never mid-task, never on a timer. An OLD row (`c25`, `c40`, `c56`, `k26`, any `n*`, `o*`) is marked done only if
   this run completes ALL of it; a partly completed old row is left untouched.
8. **Who does the work** (`~/.claude/rules/model-routing.md`). The main session only splits, briefs, verifies one
   result per claim and reports. Builders `model: sonnet`. Repeat clicks, lookups, renames `model: haiku`. Opus only
   for u121 (design) and u129 (check) with `Tier: A` and `Why Opus:` lines. Every brief carries: `model`;
   `Budget: <N> min wall-clock, <M> tool calls` (builder at most 80 calls, verifier at most 32: the hook refuses
   more); `Core:` / `Proof:` or, for a repair, `RCA`, `Class:` and `Proof:`; `Spec basis:`;
   `Report: evidence-table`; the `.claude/kit/builder-brief.md` standing items; a `Reuse:` line from a grep done
   before the brief; every answer state (stated, absent, not found, failed, empty, ambiguous) and what each does.
   Merge a builder's reported sha after reading its diff, never a branch by name.
9. **Shell guard.** Shell commands may not contain the words `spec`, `.claude`, `views`, `factory`: use the Read,
   Grep, Glob, Edit and Write tools for such paths; a worktree under `.claude\worktrees` is driven with relative
   paths from inside it.
10. **Tests.** Failing test first on the real function, from the real case in the tables. Targeted files only.
    DB tests one file at a time through the MAIN checkout's runner:
    `python scripts/orchestrator/db_run_fresh.py . python -m pytest -c pytest-app.ini tests_app/<file>.py`.
    Frontend: `npx vitest run <files>` from `frontend/`. Response-model changes also run the reply-inventory test;
    wording changes also run the wording and name-guard tests. Long output to a log outside the repo; read the tail.
11. **Long runs.** The full pre-merge check `python scripts/orchestrator/prepush.py` (45-65 min on this PC), the app
    servers, and any command over about 10 minutes start under Desktop Commander `start_process`
    (`cmd /c "cd /d <tree> && python -u scripts\orchestrator\prepush.py > <log> 2>&1"`) and are watched with a
    Monitor script on the process id; never a Bash background shell, never a helper kept waiting. Before a full
    check, close open practice trades from the screen to cut load. Stop only process ids this run started; never
    select a process by its command line.
12. **Integration, without pushing.** Per issue: the builder's checked commit is merged into `fix/gc-icfix` by sha;
    `python tools/ci_local.py` runs on the branch after each issue lands. Per phase close: `git merge origin/main`
    into the branch after a `git fetch` (fetch only; nothing is pushed), then ONE full local pre-merge check to
    `TOTAL PASS` on the branch head, then a backup file:
    `git bundle create D:\Abhay\scratch\gc-icfix-backup\gc-icfix-p<N>-<sha8>.bundle main..fix/gc-icfix`
    and `git bundle verify` on it. A red full check is repaired on the branch and re-run (at most 2 rounds, then the
    failing item is reverted on the branch and parked, so the branch stays green). No `--no-verify`.
    **The single push (u611) happens only after the owner writes "push" in a session:** fetch, merge main into the
    branch, fast checks, the full local check once more only if main brought changes, then `git push`, ONE pull
    request whose body lists every issue with its test file and proof line and carries the `Spec deviation` block
    (Class none unless a row says otherwise; no closing keyword before an issue number unless the whole issue is
    done), wait for the ONE CI run, `python scripts/orchestrator/merge.py <pr> --reviewed-sha <full sha>`, gates
    chained with `&&`. If that CI run is red: repair on the same branch and push again to the SAME pull request;
    never open a second one. No force push. After the merge: compare the main checkout's three pending files with
    main's new content (they must match), restore them to the committed state, `git pull`, restart the app from
    main, remove the branch folder with `wt-rm.ps1`.
13. **Browser.** Claude in Chrome through Sonnet helpers, the owner's visible window, app pages on
    `http://127.0.0.1:5173` only, desktop width. Before any screen task check the PC is unlocked
    (`tasklist //FI "IMAGENAME eq LogonUI.exe"` shows none, then one real screenshot). The page area on this laptop
    is 1536x639: that IS the test size for issue 6. No page-script clicks; a helper that cannot reach a control
    reports it as a finding. Start commands for the app: `docs/process/session-handover-2026-11-08-gc-ictrack.md`
    (feed, API 8765 in bus mode, background worker, vite 5173; Redis 5 on 6380; database `ofo_dev` through the
    tunnel on 5432), run FROM THE BRANCH FOLDER so the screens show the repaired code; the branch folder has no
    `.env`, so read the main checkout's settings the way `docs/process/runbook.md` describes for a worktree and
    never copy secrets into a tracked file. If the main checkout's servers hold the ports, stop only the process ids
    recorded as started by a run of this project, then start from the branch. Practice orders only; "Held at my
    broker" unticked.
14. **Screen proof outside market hours** uses test-data mode (u601). A task that needs live prices is marked
    [LIVE], waits for u609 and does not block its phase's close: its row stays open and is named in the handover.
15. **Stuck work.** At most 2 rounds per item, then a `parked` issue (`python tools/gh_issue.py app ... --stage`)
    with the evidence and `PARKED (#N)` in the row. A second red of one failure class: an independent reviewer
    (fresh context) before a third try, then tell the owner as information. Before a new round on a parked branch,
    merge main into it.
16. **Owner away or after 22:00:** no question tool. A choice the written decisions settle is decided and recorded;
    anything else goes to `docs/process/owner-questions-<date>.md` with a recommendation, and the run continues
    with the next task that does not depend on it.
17. **Done claims.** A row is closed only with the command or screenshot and its result line. "It ran" is a check;
    name the value that moved. A worker's report is a claim: re-run its gate before closing the row.
18. **Run log.** Append-only `docs/process/run-log-GC-ICFIX.md` on the branch: one or two lines at each
    phase start, task close, defect, something-not-working event and what was done, park, and the phase result.
19. **Findings.** Each class of fault proven here gets one file in `knowledge/findings/` in the same phase, written
    as a class with the real case as evidence, then the index regenerated through its wrapper. Classes already
    visible: a saved setting with no reader but its own display; a panel that renders nothing when its read fails;
    a dialog that cannot scroll; a "not found" answer taken as proof without a known-good comparison; a status
    figure with no "as of" time; the test window as the smallest real screen.

## §1 Decisions already made (do not pause on these)

- T, D1-D6 and the five "decided by me" lines in the table at the top of the plan.
- **Issue 1 design:** keep the evaluation-time read of 5ecab208 (no data repair needed for plans already saved);
  the last stage uses the smaller of the plan Target and the playbook's last-stage value, as the Stop does, and the
  plan card states the value in force for the current stage so card and alert always show the same number (ADR-252).
- **Issue 2:** the plan request keeps its own 30 s limit; the global request limit is not changed.
- **Issues 3 and 4:** the engine's after-charges figure is the only source (ADR-008, ADR-263); no screen computes
  its own total. The target and take-profit rules keep their before-charges basis (D1) and say so.
- **Issue 6:** repaired in the shared dialog frame; real-order dialogs get the layout only.
- **Issue 9:** risk alerts (stop) skip the candle confirmation; other rules keep it (REQ-170 AC-1, AC-5).
- **Wording:** every new on-screen sentence goes through the existing wording catalogue and its tests; decision-
  support wording, never advice (ADR-003). The sentences already agreed in this plan: "No plan saved yet: default
  rules apply", "Set plan", "Adjustment limit reached (2 of 2)", "(after charges)", "(before charges)",
  "Time exit (on expiry day)", "Draft", "Running", "Completed".
- **Review depth:** Tier B (fresh Sonnet, diff only) per issue; Tier A (Opus) for issues 3 and 4 only.
- **No migration of existing data** in this run. A task that would need one stops and is parked with the reason.

## §2 Read first / reuse (verified 13 Nov on main 8b0e0a8a unless marked)

- Rule evaluation: `backend/ofo/adjustment/playbook_eval.py` (`_t07` about 539, `_limit` about 438-450, clear /
  already-true / flag about 1060-1074, time exit read about 1267); `backend/ofo/adjustment/adjust_ratios.py`;
  `backend/ofo/adjustment/approaches.py` about 648-654 (expiry-day time exit); `system_playbooks.json` (iron condor
  triggers about 1816-2242, stages about 1784-1799).
- Plan: `backend/ofo_app/routes/adjustment_plan.py` (routes at 439, 487, 502; guard about 74, 281);
  `backend/ofo_app/settings_in_force.py` about 384-409 (Stop into T-06: the pattern for issue 1);
  `guard_readers.json`.
- Rule-check route and watcher: `backend/ofo_app/routes/adjustment_check.py` (about 264, 309, 339);
  `backend/ofo_app/background.py` (suggest-only; alert gate about 55-66); `alert_presets.py`.
- Trade page: `frontend/src/components/strategy/PaperBookPanel.vue`, `PlanEntry.vue` (card shown only when its read
  succeeded, about 6-47), `AdjustPlanSheet.vue` (about 10, 40, 86-94, 127-129), `SaveDraftBar.vue` (about 374, 453),
  `TrackingPanel.vue` (about 54); `frontend/src/services/api.js` (neutral error text 41, 10 s limit 49);
  `frontend/src/lib/adjustPlan.js`; `frontend/src/views/StrategyBuilderPage.vue`.
- Helpers: `frontend/e2e` `findClippedElements`; `usePaperRefresh` and `TRACKING_REFRESH_MS` (on be14b64e).
- Written decisions the repairs rest on (read the BODY, not the title): ADR-008, ADR-202, ADR-207, ADR-214, ADR-216,
  ADR-237, ADR-238, ADR-245, ADR-252, ADR-255, ADR-256, ADR-258, ADR-259, ADR-260, ADR-261, ADR-263, ADR-267,
  ADR-283, ADR-293; REQ-045, REQ-109, REQ-158, REQ-159, REQ-161, REQ-162, REQ-163, REQ-170.
- Findings before designing: `knowledge/findings/` (166 files), especially
  `rule-entry-baseline-taken-at-first-check.json` and `background-trigger-without-the-inputs-it-needs.json`.
- Measured on 13 Nov: plan request 18.3 s and 12.4 s under load (4 s in the morning); rule check 27 s; API process
  about 1.5 GB with 3.4 GB free; about 70 old practice trades in `ofo_dev`.

## §3 Phases and tasks

Tasks, ids and "done when" are the tables in the plan above (copied into this file by task 0). Order inside a phase
is the order of the tables. Setup rows:

| Id | Task | Done when |
|---|---|---|
| u001 | The one branch and folder: `fix/gc-icfix` from main via `wt-new.ps1` (or found already there) | path + sha |
| u002 | On the branch: this contract file; decision rows ADR-294 onward for D1-D6 and the "decided by me" lines; requirement wording corrections; stage rows; the pending ADR-293 / REQ-070 / CLAUDE.md content from `be14b64e`; the plan-Target commit `5ecab208` merged in | files listed; `python tools/ci_local.py` green on the branch |
| u003 | Add tracker rows u001..u611 (nothing removed) | `ArtifactData list` shows the old 106 rows plus the new ones |
| u004 | Backup folder `D:\Abhay\scratch\gc-icfix-backup\` exists; first backup file written and verified | file name + `git bundle verify` line |
| u005 | Bring up the app on this PC from the branch folder; health check | health 200 + commit id served |
| u006 | Core proof (u101-u104) | as stated under Core |

- **Phase 1 = setup + P0** (u001-u006, u101-u176). **Phase 2 = P1** (u201-u335). **Phase 3 = P2** (u401-u484).
  **Phase 4 = P3** (u501-u515). Every phase ends with the full local check green on the branch and a backup file.
  No phase pushes.
- **Phase 5 = tests and close** (u601-u610). u601-u608 may run inside any earlier phase while a full check is
  running, since they need the browser and not the build. u609 needs a trading day and the owner's Kite login from
  09:00. u610 ends the autonomous work: the branch is READY TO PUSH and the run stops.
- **u611 (the one push, pull request, CI run and merge)** is NOT part of any autonomous phase. It runs only in a
  session where the owner has written "push".

## §4 Definition of done

Per phase, ALL of:
- [ ] Every task row of the phase is closed with its evidence line, or carries `PARKED (#N)` with a filed issue.
- [ ] Every repaired issue has: a test that was red before and is green after; an independent checker's verdict that
      names "covers the class: yes"; and, where the table says "Screen", a screenshot from Chrome on a practice
      trade (or the row is marked [LIVE] and listed in the handover).
- [ ] Every checked commit of the phase is on `fix/gc-icfix`; the full local pre-merge check printed `TOTAL PASS`
      on the branch head; the app on this PC runs from that commit with health 200.
- [ ] A verified backup file of the branch for this phase exists in `D:\Abhay\scratch\gc-icfix-backup\`.
- [ ] Nothing was pushed: `git status -sb` in the branch folder shows the branch with no upstream, and
      `gh pr list --head fix/gc-icfix` is empty.
- [ ] The findings of the phase are in `knowledge/findings/` on the branch, and its handover
      `docs/process/session-handover-<date>-gc-icfix-p<N>.md` exists on the branch with DONE / PENDING / BLOCKED /
      PARKED / NEXT. The same handover text is also saved to `D:\Abhay\scratch\gc-icfix-backup\` so the next
      session can read it even before it knows the branch folder.
- [ ] Every builder's agent worktree of the phase is removed with `wt-rm.ps1`; the tracked-file count of the main
      checkout is unchanged; the branch folder `OptionsForOptions2-gc-icfix` is kept.

Whole contract, ALL of:
- [ ] Each of the 26 issues (and the P3 items) is stated in the final report as REPAIRED (proof named), PARKED
      (issue number) or OPEN (reason), with no issue missing from the list.
- [ ] Every rule in the "not reached on live prices" table is stated as FIRED (where shown), NOT POSSIBLE ON TEST
      DATA (gap named), or WAITING FOR MONDAY.
- [ ] No old tracker row was removed or rewritten; old rows changed state only where this run completed all of them.
- [ ] The autonomous work ends with the words "READY TO PUSH" in the final report, the branch head sha, the count of
      commits ahead of main, and the last full local check's `TOTAL PASS` line. Zero pushes, zero pull requests and
      zero CI runs were made by the autonomous phases.

## §5 Final report (each phase, and the last one for the whole)

Plain English for the owner: what was repaired and how it was proven (one line per issue, with the trade number and
the figure that moved); what is parked and why; what waits for a live market; which model did each kind of work;
time and number of full checks used; lessons that should become a rule or a test, proposed, not applied.

## §6 Guardrails (hard stops)

No real order. No deploy. No server work. No new dependency. No data migration. No change to a system playbook's
values. No removal of tracker rows. No kit file edited (file a `harvest` issue instead). No account figure in the
repo. **No push, no pull request and no CI run before the owner writes "push"; then exactly one of each.** No
second integration branch. No `--no-verify`, no force push, no mutating git in the main checkout before u611. If a
task would break one of these, stop that task, park it with the reason, and continue with the next. A parked issue
is filed with the issue tool as usual (filing an issue is not a push).

**Invocation (fresh session, this project folder).**
First run: `/goal C:\Users\itsab\.claude\plans\dreamy-mapping-sunbeam.md`
Every later run (the contract then lives on the branch, not on main):
`/goal D:\Abhay\Ventures\OptionsForOptions2-gc-icfix\docs\process\goal-contract-GC-ICFIX-2026-11-13.md`
The final push, in any session after the report says READY TO PUSH: write `push GC-ICFIX` (task u611).
