# Goal contract GC-TRACK1: the owner builds or types in an iron condor, and the app tracks it to the exit (2026-11-12)

**Status:** APPROVED scope (owner 2026-11-11 ~23:4x IST "Approve 1-11 as listed", narrowed by the owner 2026-11-12
~00:1x IST to ONE user, the owner's own Kite account: ADR-291). Never run before this version.
**Executor:** `/goal` in a fresh session of this project, started on a trading day before 09:00 IST (first choice
Thu 12 Nov 2026). Market-hours tasks are marked [LIVE]; the rest run any time.
**Standing direction step:** 4 as restated by ADR-290 and narrowed by ADR-291 (see the 2026-11-11/12 change-log lines
of `docs/process/standing-direction.md`). Clean-up D-07 (fix-list triage only) and D-11 beside it.
**This file, ADR-290, ADR-291** sit on local branch `docs/owner-goal-2026-11-11` (commit c40db762 holds ADR-290; the
rest is uncommitted in the main checkout). Task k02 lands that branch first.
**Written against:** main `70bd2b61`, 2026-11-12 00:2x IST.

**Mission, in plain words:** the owner, on his own Kite Connect app and account, either builds an iron condor in the
app or types in one he already holds at a broker. From then on the app watches it in the background with no screen
open, against the owner's own adjustment settings, raises the adjustment and other suggestions as the market meets
their conditions, and keeps doing so until he exits; then it stops. The app places no order (ADR-290, ADR-281). Other
users, sign-up, per-user Kite apps and hosting are out (ADR-291).

**Core:** an iron condor TYPED IN BY HAND as "held at my broker" (four legs, own prices, an entry time earlier
today) is picked up by the background watcher with no screen open and checked against the owner's settings on live
prices, without a single "already true" alert at the moment it is saved.
**Proof (task k04, [LIVE], before any code of stages B to E):** a throwaway spike on `ofo_dev`: create such a
strategy through the existing save path plus typed paper orders (REQ-109 AC-1) with a back-dated entry note; close
every app page; watch 10 minutes. Read back from the worker log: the strategy id, check count > 0, price source
`live`, the stop value read from the owner's settings, and the trigger states. Pass = checked on live prices, count
> 0, no trigger reported "already true" on the first check. If the watcher does not pick it up, or the first check
raises "already true" alerts that are not true -> record the measured cause (that cause IS stage B's first task) and
continue; HALT only if the watcher cannot read a typed-in strategy at all.

## §0 Run rules

1. **Idempotent start.** First: read this file, ADR-290, ADR-291, `docs/process/standing-direction.md`, the newest
   `docs/process/session-handover-*.md`, `git log --oneline -40` on main and status rows `k01..k32`. A row whose done
   line already holds on main is marked done with that evidence and skipped.
2. **No orders (ADR-290 (1), ADR-281).** No real order, no Kite order page, no click inside any Kite order panel.
   Margin and funds figures and the owner's Kite client id never go into any file, commit, issue or status row
   (public repo; ADR-291 consequences).
3. **Iron condor freeze holds** (standing direction rule 2): no new approach, trigger, wording round or guide
   content. Stage D fixes named defects only.
4. **Name the step.** Every brief and commit subject starts `GC-TRACK1 k<nn>`.
5. **Status page:** https://claude.ai/artifact/LcMTSr5xx8LvAYVniotkxK, db collection `tasks`, rows `kind: "task"`,
   ids `k01..k32`, ordered 301..332; task k01 creates them. One update at a task's START and one at its FINISH (state,
   time from the clock in the same step, minutes, evidence line), `if_version` pinned, never mid-task.
6. **Workers.** Builders `model: sonnet`. Every brief carries `Budget:`, `Core:` / `Proof:`, `Class:`,
   `Spec basis:`, `Report: evidence-table`, the `.claude/kit/builder-brief.md` standing items, a `Reuse:` line from a
   grep done before the brief, and every answer state (stated, absent, not found, failed, empty, ambiguous) with what
   each does. Merge the builder's reported sha after a diff read, never a branch by name.
7. **Tests.** Targeted per file. DB tests one file at a time:
   `python scripts/orchestrator/db_run_fresh.py . python -m pytest -c pytest-app.ini tests_app/<file>.py`.
   Long output to a log outside the repo; read the tail. Non-DB app tests per merge batch with DB URLs unset.
8. **Browser.** Claude in Chrome, the owner's visible window, app pages only, desktop width; check the PC is unlocked
   (one real screenshot) before any screen task. Servers: the start commands of
   `docs/process/session-handover-2026-11-08-gc-ictrack.md`, under Desktop Commander `start_process`. Stop only PIDs
   this run started; never select a process by its command line.
9. **Stuck work.** At most 2 rounds per item, then a `parked` issue with evidence and `PARKED (#N)` in the row. A
   second red of one failure class: an independent reviewer (fresh context) before a third try. Owner away or after
   22:00: write to `docs/process/owner-questions-2026-11-12.md` with a recommendation; the question tool is blocked
   at night.
10. **Done claims.** Every done row names the command or screenshot and its result line. "It ran" is a check; name
    the value that moved. A worker's report is a claim: re-run its gate before marking the row.
11. **No VPS work.** Nothing in this run touches the VPS (hosting is out, ADR-291).

## §1 Decisions already made (do not pause on these)

- **One user** (ADR-291): `current_user_ref()` stays the owner (`routes/broker.py:78,203`); the owner's Kite app key
  stays in settings (`broker_config.py:120`). No sign-in, user table or per-user key store is built. Every new store
  and query still takes `user_ref`; nothing assumes one strategy per user.
- **A held condor typed in by hand** reuses the builder plus typed paper orders (REQ-109 AC-1). New: a source label
  `held_elsewhere` (screen: "Held at my broker") beside paper; an entry date and time the owner states (may be earlier,
  never in the future, inside the contract's life); broker name as optional free text, shown, never used.
- **Rule starting point for a typed-in condor** (ADR-283 needs the market at the fill): the market at the moment the
  owner SAVES it, and the screen says so ("rules start from <time>"). Not back-filled from history. Technical call;
  reason: no stored market for a past moment, and a guessed one raises or hides alerts wrongly (finding
  rule-entry-baseline, six occurrences).
- **Changes made at the broker** are recorded by the owner with the existing paper order and exit forms at his own
  typed price (REQ-109). The held condor's screen shows one line: "Changes you make at your broker are not seen by the
  app. Record them here." No broker read in this run (Zerodha read-in is later, ADR-290 (3)).
- **Tracking lifetime** (ADR-290 (5)): the watcher checks every open strategy of the owner, paper and held alike;
  with no open strategy it does no work; a strategy leaves tracking when its last leg is closed or settled (ADR-259).
- **Settlement at expiry** for a held condor: the existing paper settlement (`paper_settlement.py`) covers
  `held_elsewhere` too, at intrinsic value from the closing index, then Completed (ADR-259). The real-leg half of #684
  stays parked.
- **Hide order placing:** Execute / "Send to Kite" and the basket form are not rendered (feature flag off through
  `features.py`, the existing flag pattern); the code stays (ADR-165 (1)).
- **Fix-list triage** (stage D): the items of `docs/process/fix-plan-2026-11-07/ic-test-issues-snapshot.md` not fixed
  by batch 1 are read once; each is marked DEFECT (a wrong number, a wrong or missing suggestion, a wrong alert) or
  DEPTH (frozen). Only DEFECTs that change what the owner sees on a tracked condor are fixed here, at most 6 tasks; the
  rest go into one `deferred` issue.
- **Review tier:** Tier B (fresh Sonnet, diff only) per merge batch; no Tier A (no auth, money path or migration of
  existing data beyond adding a column with a default).

## §2 Read first / reuse (verified 2026-11-11 on main 70bd2b61)

- Watcher: `backend/ofo_app/background.py:1809-1852` (open strategies of the owner, `OWNER_REF`, the `Watched` rows);
  `:547-559` the stored-session reader; T-16 margin read via `outcome_margin.py` / `kite_margin.py` (proven 11 Nov,
  GC-ICSAFE c40).
- Typed paper orders: `routes/paper.py:96-106` (`PaperOrderIn.price`), `:751` POST orders; tracking:
  `routes/tracking.py` (exit at `:81`); strategies: `routes/strategies.py:83,141` (`entry_source` typed/captured).
- Rule starting point: ADR-283; finding `knowledge/findings/rule-entry-baseline-taken-at-first-check.json`;
  `entry_facts_store.py`.
- Settlement: `paper_settlement.py`, `real_settlement.py` (#684 body). Flags: `features.py`, `routes/features.py`.
  Order screens: `frontend/src/components/execution/BasketForm.vue`, `ExecuteCost.vue`,
  `strategy/StrategyActions.vue`.
- Open defects in scope: #692 item 19 (alarm "not checked" 1-4 min after a leg change), #627 restart service, #661,
  #664 (both parked; read before the triage).
- Finding `background-trigger-without-the-inputs-it-needs.json` before stage C.

## §3 Tasks (each <= 15 min; status row id = k + number)

### Stage A. Set up and prove the core
| # | Task | Done when |
|---|---|---|
| 01 | Create status rows k01..k32 | rows listed by `ArtifactData list` |
| 02 | Land `docs/owner-goal-2026-11-11` (ADR-290, ADR-291, direction lines, questions file, this file) as one docs PR, merge on green | merge sha on main |
| 03 | Worktree `OptionsForOptions2-gc-track1` from main via `wt-new.ps1`, branch `build/gc-track1` | path + sha |
| 04 | [LIVE] CORE PROOF (above) on `ofo_dev` | worker log lines read back |
| 05 | Record the proof result and its measured cause, if any, in the run log | run-log line |

### Stage B. Held condor typed in by hand
| # | Task | Done when |
|---|---|---|
| 06 | `held_elsewhere` source + stated entry time + broker text (migration, column defaults) | migration test green |
| 07 | "I hold this at my broker" on the builder save path; four legs with typed prices and the entry time | route test |
| 08 | Rule starting point = save time (fix the k04 cause if it showed one) | test: no "already true" at save |
| 09 | Record a broker change (adjust, exit) at a typed price on a held condor | test |
| 10 | Screens: "Held at my broker" label, entry time, the "changes at your broker" line, "rules start from" | screenshot |

### Stage C. Tracking until exit
| # | Task | Done when |
|---|---|---|
| 11 | Watcher includes held condors with paper ones; nothing assumes one strategy | test: 2 open strategies, both watched |
| 12 | The owner's settings in force for a held condor (ADR-264), same as paper | test |
| 13 | No open strategy: no checks; a closed or settled strategy leaves tracking | test |
| 14 | Suggestions and alerts from a held condor reach Alerts > Active and the bell | test |
| 15 | Held condor settles at expiry through paper settlement -> Completed | test on a fixed past expiry |
| 16 | #692 item 19: alarm "not checked" for 1-4 min after a leg change | test red then green, or PARKED |
| 17 | #627 restart: the watcher restarts after it dies (local supervisor) and the heartbeat shows it | test |
| 18 | [LIVE] 30 minutes, no screen open: one held condor typed in today + one paper condor, both checked | worker log: check counts per strategy > 0 |
| 19 | [LIVE] One adjustment suggestion seen on the held condor through Compare, recorded at a typed price | screenshot + figures moved |

### Stage D. Suggestions you can trust
| # | Task | Done when |
|---|---|---|
| 20 | Hide order placing (feature flag) | screenshot: no Execute anywhere |
| 21 | Triage the fix list: DEFECT / DEPTH per item | table in the run log |
| 22-27 | Fix the top DEFECTs (at most 6, one task each, failing test first) | each: test red then green |
| 28 | One `deferred` issue with the remaining DEFECTs and the DEPTH list | issue number |

### Stage E. Review and close
| # | Task | Done when |
|---|---|---|
| 29 | Tier B review per merge batch (fresh Sonnet, diff only) | verdicts |
| 30 | Prepush (`python scripts/orchestrator/prepush.py`, under Desktop Commander) for HEAD | marker for HEAD |
| 31 | Merge request, merge on green (`merge.py <pr> --reviewed-sha <sha>`) | merge sha |
| 32 | Remove the worktree (`wt-rm.ps1`, package counts before and after), handover, final report | handover file |

## §4 Verification gates

- Per merge batch: `python tools/ci_local.py` and the touched test files; DB files one at a time.
- Every screen task: a screenshot read back, desktop width, PC unlocked.
- Before k31: the `prepush.py` marker for HEAD.

## §5 Failure budget and hard stops

- Core proof: HALT only if the watcher cannot read a typed-in strategy at all (above).
- Hard stops: any order path, any VPS work, any account figure or the owner's Kite client id in a file, any push of
  `.env`, deleting data in `ofo_dev` other than rows this run created.
- 2 rounds per item, then park. A parked row in stage B or C leaves the goal unmet: say so in the report.

## §6 Done (results)

1. An iron condor typed in by hand as "held at my broker" (four legs, own prices, an earlier entry time) is saved,
   labelled, and its rules start from its save time; a broker change recorded by hand moves its figures.
2. With no app page open, the watcher checks every open strategy of the owner, held and paper, on live prices against
   the owner's settings (worker log counts per strategy > 0), raises suggestions into Alerts, stops when none is open,
   and a held condor settles at expiry into Completed.
3. No order button is shown anywhere. The fix list is triaged; each fixed DEFECT has a red-then-green test; the rest
   are in one deferred issue.
4. The code is on main; nothing this run started is running; the main checkout is clean.
Any row that ends PARKED is named with its issue in the report, and the goal is reported PARTIAL.

## §7 Final report

Plain words: what the owner can do now that he could not before; what is still missing (expected: multi-user,
sign-up, per-user Kite apps, hosting, Zerodha read-in); every PARKED row with its issue; an evidence table per Done
item; cost (minutes, review rounds, CI runs); the lessons with their mechanism.

## §8 Authorization trail

| When | Decision | By |
|---|---|---|
| 2026-11-11 | No real order; build or type in an iron condor; tracked to exit (ADR-290) | owner, chat |
| 2026-11-11 | Hand entry now, Zerodha read-in later | owner, question tool |
| 2026-11-11 | A Kite connection = the person's own Kite Connect app | owner, question tool; restated 11-12 |
| 2026-11-11 | Scope 1-11 in the stated order | owner, question tool |
| 2026-11-12 | One user only, the owner's own Kite account; multi-user, sign-up, hosting out (ADR-291) | owner, chat |
| 2026-11-12 | Rule start = save time; hide Execute by flag; Tier B review; at most 6 defect fixes | session, technical calls |
