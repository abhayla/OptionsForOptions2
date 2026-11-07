# Iron condor adjustments: end-to-end code audit (2026-11-07 14:02 IST)

Code read: `feature/adjustments` at ebefb113. Read from code only; documents were not taken as evidence.
Scope (owner, 2026-11-07): paper and real-Zerodha paths, each gap tagged; the default IC system playbook
(18 applicable approaches, 14 triggers, the day rules that are on, all guards); critical = a missing or broken
step, a possible wrong order, quantity or money number, or no desktop screen for the step.

Future scans: read this file first. A gap listed here is re-checked against code, never re-derived from docs.
Discussion: the owner takes the gaps one at a time; each answer is written in the gap's "Decision" line, and
product decisions also become ADR rows.

Overall: paper works end to end apart from C7 to C14. Live (real Zerodha) can enter and fully exit a condor,
but cannot monitor it, adjust it or settle it at expiry.

Suggested discussion order: paper holes first (C9, C10, C11, C12, C13, C7, C8), then live (C2, C1 + C3 + C14,
C5, C6, C4).

---

## Live (real Zerodha) gaps

### C1: a live adjustment cannot be sent
- **Path:** live
- **What is missing:** `/execute` accepts only ENTRY or EXIT. An ENTRY while legs are held is refused, so there is
  no way to close some legs and open others on a live strategy.
- **Why critical:** step missing. A roll or one-side close of a real condor must be done by hand on Kite, outside the
  platform's checks (margin, sequence, reconciliation).
- **How found:** `backend/ofo_app/routes/execute.py:108` `action: Literal["ENTRY", "EXIT"]`;
  `backend/ofo_app/execute_plan.py:213-220` ("an adjustment, PROPOSED only"); `ofo/strategy/modification.py` has
  0 importers.
- **Why not done:** deliberately left out when live execution was built (W-095 r3, commit 11c2aef0); the
  build order was paper first.
- **Risk while open:** if the user saves the after-legs from the builder as a new strategy, its ENTRY could open a
  second full condor (unverified).
- **Decision:** _open_

#### C1 deep dive (2026-11-07, code read at ebefb113)

An adjustment on a live condor is a chain of 12 parts. The two ends are built: picking the adjustment (1-2) and
recording it once Zerodha returns (9-11). The middle, which turns a confirmed new version into the orders that close
and open legs, is missing (4-6). Parts 7-8 exist only as domain code nothing calls.

| # | Part | State | Evidence |
|---|---|---|---|
| 1 | Pick an approach, see its legs and cost (Compare) | DONE (same for paper and live) | `AdjustCompare.vue:227` calls `POST /adjustment-approaches` (`routes/adjustment.py:483`) |
| 2 | Load the after-legs into the builder for a live strategy | DONE | `StrategyBuilderPage.vue` `prepareApproach`: no paper book, so `setLegs(next)` |
| 3 | Save the after-legs as a PROPOSED version (the active one stays) | DONE in the backend; the screen never says so | `strategy_store.update` calls `_propose` (`strategy_store.py:384-386`, `:594-620`); table from migration 0022 |
| 4 | User confirms the proposed version | Backend DONE, NO SCREEN | `POST /strategies/{id}/versions/{n}/confirm` (`routes/strategies.py:544`); 0 frontend callers |
| 5 | Build the difference basket (new version minus what Zerodha holds: close some legs, open others) | NOT DONE | `routes/execute.py:108` takes ENTRY/EXIT only; `_wanted` builds ENTRY from the ACTIVE definition (`execute.py:354-368`, `strategy_store.load:715`); `_executable` refuses an ENTRY while held (`execute.py:343-351`); `ExecutionAction.ADJUSTMENT` (`ofo/execution/context.py:81,93`) is never used by the app |
| 6 | Execute route accepts an ADJUSTMENT action and links the plan to the proposed version | NOT DONE | `record_plan(..., strategy_version=store.built_from(stored))` always passes the ACTIVE number (`execute.py:410`, `strategy_store.py:532-541`) |
| 7 | Before/After risk, margin and charges of the change, plus the Strategy Guard acknowledgement when the risk profile changes | Domain only, NOT WIRED | `ofo/strategy/modification.py` (`propose_modification`, `prepare_confirmed_modification`) has 0 importers; tests pass (32 passed with partial/review) |
| 8 | Order sequence: protective buys first, a sold leg never sent before its hedge | Domain only, NOT WIRED | `ofo/execution/sequence.py:419` `sequence_plan`; basket built "in plan order" (`basket.py:278`); the paper confirm list puts exits before adds (`paperDrafts.js:118`) |
| 9 | Pre-send checks: margin with current positions, reconciliation, circuit and price band | DONE (reusable as is) | `kite_margin.py:44` `consider_positions=true`; mismatch blocks (`execute.py:395`); `_gate` (`execute.py:404`) |
| 10 | Zerodha return, order book and audit rows | DONE | `routes/execution_return.py:290,350`; `order_audit.record_prepared` (`execute.py:415`) |
| 11 | Make the proposed version active only when Zerodha's position matches it; flag a mismatch or partial | DONE in the backend, but unreachable | `strategy_store.settle_versions` (`:656-712`), called at `routes/execution_return.py:352`; it waits for "a closed ENTRY plan built from" the proposed version, which part 6 can never produce |
| 12 | Partial fill of an adjustment: the four choices (Complete, Retry, Review, Exit partial) | Domain only, NO ROUTE OR SCREEN | `ofo/execution/partial.py` (REQ-058); no route acts on a choice (C5) |

**Also blocks C1 end to end (other gaps):** C2 (a live strategy is not monitored, so no trigger leads to the
suggestion), C3/C14 (sequence), C4 (freeze split), C5 (part 12).

**Unverified:** whether Kite's basket screen places orders in list order. The sequence only helps if it does, or if
the basket is split into a buy step and a sell step.

**Doc mismatch fixed:** `work/W-144.md` says `todo`, but its versions code is built (commit 049806e5, migration
0022, `strategy_store.py:445-712`). A note was added there. The status field is left for the verifier.

**Correction to the first pass:** the auditor named `TwoBasketStepper.vue`; that file does not exist.

### C2: a live condor is not monitored
- **Path:** live
- **What is missing:** the background worker and `read_tracked` read only `public.paper_orders`. Real fills are
  never written there, so a live strategy gets no triggers, stop lines, day rules or adjustment count.
- **Why critical:** step missing. Example: NIFTY runs through the short strike and no alert is raised.
- **How found:** `backend/ofo_app/background.py:1609` ("tracked (open paper legs)");
  `backend/ofo_app/adjustment_readers.py:116` (`paper_book.load_owned`); `backend/ofo_app/paper_book.py:24`
  (`FROM public.paper_orders`); only `paper_store.place` writes that table.
- **Why not done:** paper-first build order, never extended to the live order book.
- **Decision:** _open_

### C3: the live basket order is not sequenced
- **Path:** live
- **What is missing:** the playbook says "buy legs first; buy back shorts before selling hedges". The basket is built
  in plan order (ENTRY) or sorted by contract (EXIT).
- **Why critical:** wrong order possible. A short can go before its hedge, giving a margin spike or a rejection
  that leaves the position half-hedged.
- **How found:** `backend/ofo/execution/basket.py:278-296` ("in plan order"); `backend/ofo_app/execute_plan.py:223-226`
  (`sorted(held.items())`); `ofo/execution/sequence.py` is imported only by `partial.py` and `review.py`, which no
  route uses.
- **Why not done:** unknown. The sequencer was written and never connected.
- **Decision:** _open_

### C4: no split above the freeze limit
- **Path:** live
- **What is missing:** an order above the exchange freeze quantity blocks the whole basket; `slice_quantity` is not
  called from the app.
- **Why critical:** step missing for large size. Example: a 30-lot NIFTY exit cannot be sent.
- **How found:** `backend/ofo/execution/freeze.py:9` ("never splits a leg"), `:73-77`; grep `slice_quantity` in
  `backend/ofo_app` gives 0 hits.
- **Why not done:** a design choice to block rather than split.
- **Decision:** _open_

### C5: partial fill or one rejected leg has no next step
- **Path:** live
- **What is missing:** the server works out the choices for a partial plan, but no route acts on Complete or Retry,
  and no screen shows the choices.
- **Why critical:** step missing and no screen. A rejected hedge leaves a naked short; the only way out is
  "exit all".
- **How found:** `backend/ofo_app/execution_return.py:49`, `backend/ofo_app/routes/execution_return.py:298`;
  grep `choice|partial` in `frontend/src/components/execution/ReturnCheck.vue` gives 0 hits;
  `TwoBasketStepper.vue` is used by no page.
- **Why not done:** work stopped mid-way (commit beea6cdb, "W-096 WIP").
- **Decision:** _open_

### C6: live expiry settlement is not wired
- **Path:** live
- **What is missing:** `settle_expired_legs` / `settle_legs` exist, but nothing in the app calls them. Only paper
  settlement is started.
- **Why critical:** wrong money. A live leg that expires stays "open" in the platform, so P&L after expiry is wrong.
- **How found:** grep `settle_expired_legs|settle_legs` in `backend/ofo_app` gives 0 hits;
  `backend/ofo/reconciliation/settlement.py:11-12` ("Not here: the scheduler"); `backend/ofo_app/main.py:96`.
- **Why not done:** the scheduler step was never added.
- **Decision:** _open_

## Paper and live gaps

### C7: trigger T-11 (IV change since entry) never fires on live prices
- **Path:** both (live market)
- **What is missing:** `entry_atm_iv` is set only on scenario-test paths; live it is always "Entry ATM IV not
  available".
- **Why critical:** a switched-on trigger never fires. An IV spike after entry is missed.
- **How found:** `backend/ofo/adjustment/playbook_eval.py:536`; grep `entry_atm_iv` shows assignments only at
  `backend/ofo_app/background.py:1202`, `adjustment_check.py:570,620`, `routes/playbooks.py:528`, all scenario paths.
- **Why not done:** no live store of the IV at entry exists (`entry_facts_store` has no such field).
- **Decision:** _open_

### C8: trigger T-14 (loss on a 1% move) runs in scenario mode only
- **Path:** both (live market)
- **What is missing:** the gamma figures are computed only when scenario mode is on.
- **Why critical:** a switched-on trigger never fires on live prices.
- **How found:** `backend/ofo_app/adjustment_check.py:382` (`scenario_mode.current() is None: return state`).
- **Why not done:** deliberate, commit ee7dbaab ("T-14 evaluated in scenario mode only ... live unchanged").
- **Decision:** _open_

### C9: the max-2 adjustment limit is not enforced
- **Path:** paper (live has no adjustment yet, see C1)
- **What is missing:** the limit only filters which approaches are offered. Saving paper orders has no limit check.
- **Why critical:** limit not enforced. A 3rd adjustment goes through by editing in the builder.
- **How found:** `backend/ofo/adjustment/offered.py:33-40`; `backend/ofo_app/routes/paper.py:726-760`; no limit check
  in `backend/ofo_app/paper_store.py`.
- **Why not done:** unknown.
- **Decision:** _open_

### C10: the paper fill and exit price comes from the browser
- **Path:** paper
- **What is missing:** the server checks only the tick size and range. A server-priced exit route exists
  (`POST /strategies/{id}/tracking/exit`), but no frontend code calls it.
- **Why critical:** wrong money. A stale price books a wrong paper P&L.
- **How found:** `backend/ofo_app/routes/paper.py:703-706,742`; `frontend/src/lib/tracking.js:54-59`;
  `frontend/src/lib/paperDrafts.js:128-131`; `backend/ofo_app/routes/tracking.py:425`; grep `tracking/exit` in
  `frontend/src` gives 0 hits.
- **Why not done:** unknown.
- **Decision:** _open_

### C11: adjustment A-29 (reduce size) can propose a 0-lot trade
- **Path:** both
- **What is missing:** the guard refuses only under 2 lots, and `lots // reduce_divisor` is 0 when the divisor is
  larger than the lots.
- **Why critical:** wrong quantity. Example: 2 lots with divisor 3 shows a "reduce" that trades 0 lots.
- **How found:** `backend/ofo/adjustment/approaches.py:714-726`.
- **Why not done:** missed edge case.
- **Decision:** _open_

### C12: adjustment A-04 (roll to next expiry) shows no after-adjustment payoff
- **Path:** both
- **What is missing:** two expiries raise `MultiExpiryError`, so no After payoff or P&L is shown.
- **Why critical:** no screen for the step's risk. The user picks the roll without seeing its risk.
- **How found:** `backend/ofo_app/routes/adjustment.py:415-416`.
- **Why not done:** the payoff engine prices one expiry only.
- **Decision:** _open_

### C13: no screen shows a finished strategy
- **Path:** both
- **What is missing:** a closed status is never stored, and the Completed page filter is empty, so it always shows
  nothing.
- **Why critical:** no screen. After the exit the user cannot see the final result.
- **How found:** `frontend/src/pages/MyStrategiesPage.vue:6,24` (`COMPLETED_STATUSES = []`); paper "EXITED" is worked
  out on the fly (`backend/ofo_app/routes/paper.py:428`).
- **Why not done:** the strategy store only ever had the "draft" status.
- **Decision:** _open_

### C14: the paper confirm list puts every exit before every add
- **Path:** paper, blocks live (C1)
- **What is missing:** the confirm list orders exits before adds, so a roll sells the new short before buying the
  new wing.
- **Why critical:** wrong order, if reused for live. Harmless on paper.
- **How found:** `frontend/src/lib/paperDrafts.js:118` (`return [...exits, ...adds]`); seen on paper strategy 89
  ("S Add 24950 CE ... B Add 25050 CE").
- **Why not done:** unknown.
- **Decision:** _open_

---

## Verified done (code exists and runs from a loop or a route)

- **Paper monitoring on live prices:** T-01, T-02, T-03, T-06, T-07, T-09, T-10b, T-13, T-18, T-19 and T-21
  (`backend/ofo/adjustment/playbook_eval.py:474-736`). The worker is at `backend/ofo_app/background.py:1151-1268`.
  Alerts reach the user as inbox rows, `GET /api/adjustment-opportunities` and the header toast.
- **Day rules and situations:** expiry 14:30 close rule (`playbook_eval.py:932`), weekend/holiday 15:00 carry check
  (`:1144`), S-02 (`:1211`), S-12 (`:1232`). The IC playbook file has `time_exit 14:30` and the 0.3% expiry rule
  switched on.
- **IC approaches:** 15 approaches build legs and 3 are non-trade by design (A-23, A-37, A-38). All are reachable
  from Compare (`frontend/src/components/strategy/AdjustCompare.vue:227` calls `POST /adjustment-approaches`).
  181 domain tests pass.
- **Paper path:** mixed close/open basket in one transaction, and an exit never exceeds the open quantity
  (`backend/ofo_app/paper_store.py:59-63`).
- **Paper exits and settlement:** index and leg stop exits (`backend/ofo_app/paper_monitor.py:226-235`), paper
  expiry settlement (`backend/ofo_app/paper_settlement.py`, started at `main.py:96`).
- **Live safety checks:** margin check fails closed (`backend/ofo_app/checked_basket.py:59-64`), a reconciliation
  mismatch blocks execution (`backend/ofo_app/routes/execute.py:395`), and there is no auto retry.

## Not critical, or by design

- **T-16 / % of margin stop:** off by default in the IC playbook version 0040 (ADR-247). The background process also
  has no margin source (#627, `backend/ofo_app/background.py:1745`).
- **Exit rules (profit target, stops, time exit, expiry rule):** they raise a suggestion, and the user presses to act
  (ADR-003). Only paper stop triggers write exits automatically.
- **Charges:** shown beside the P&L, never subtracted (`backend/ofo_app/routes/paper.py:172`, REQ-109 AC-10).
- **Debit limit:** "Rs 500 or 10% of max profit" is read as whichever is larger
  (`backend/ofo/adjustment/liquidity.py:170-171`). Example: Rs 10,000 max profit allows a Rs 1,000 debit. Open for an
  owner decision.
- **Low OI:** a strike under 10,000 OI is flagged, not hidden (`backend/ofo/adjustment/liquidity.py:5`).
- **S-01 (wait until 09:30 at a gap open):** limits only T-13; other triggers can flag at 09:15
  (`playbook_eval.py:540-543`). Borderline; owner to judge.

## Not checked

- No tests that need the database were run.
- How the production build serves `/api`.
- Whether the IC playbook body stored in the database matches the file.

## Documents corrected by this audit

- `docs/research/sensibull-study-2026-10-21/gap-list.md` P4/P5: paper per-leg stop and conditional exit are built.
- `work/W-109.md:34`: Adjustments and Live Strategies pages are built.
- Historical handovers that say paper settlement is not built (`docs/process/session-handover-2026-10-28-gcbp.md:38`)
  and that Exit all was removed (`docs/process/goal-contract-GC-UI-2026-10-28.md:215`) are dated records. They are
  left as written, and this file supersedes them.
