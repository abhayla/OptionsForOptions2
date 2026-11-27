# One exit door for paper and real (design, 27 Nov 2026, Lane E, read only)

Branch `docs/paper-real-audit-1127`. Design only: no code, no migration, no broker call. Companion: `docs/design/paper-real-audit-2026-11-27.md` (table rows are cited as "audit row N" by their text; the numbering is in that file).

**Owner's rule this design serves** (ADR-330 (58), 27 Nov, words as given in the lane brief): a paper order differs from a real one only by a tag; every rule, limit, check, refusal, message, screen and code path is the same. Item (58) is not yet in `spec/decisions/ADR-330.md` on this branch; it must be written (R4) before step 1 is built.

**Spec basis:** ADR-002 (every order belongs to a strategy), ADR-008 (one engine, exact decimal), ADR-016 (Zerodha is the authority; margin is a hard gate), ADR-017 (submitted is not executed; no automatic retry; partial is an exception), ADR-018 (Zerodha's state wins; mismatch blocks), ADR-019 (definition vs live state; every trigger records its exact values), ADR-029 (broker behind an adapter), ADR-054 (orders reach Zerodha through Kite's own order page; the server sends nothing), ADR-092 (never split for the freeze limit), ADR-105 (one open plan at a time; real exit legs close the net, `execute_plan.py:223-227`), ADR-117 / D-02 (two-basket rule; paper store puts BUY exits first), ADR-207 (5)(6) (paper stop and expiry records), ADR-212 (no fill outside market hours), ADR-281 (order placement on Kite on hold for the iron condor guidance round; a future automatic two-basket placement needs a SPEC CHANGE of ADR-054 and ADR-100 and an answer to F-102), ADR-322 (3) (a paper exit of a leg with no live price is refused), ADR-328 (4), ADR-330 (10)(24)(28).

## 1. The honest starting point

1. **The door already exists, for paper only.** `backend/ofo_app/paper_exit.py` has `live_exit_prices` (the one live price read) and `exit_strategy(conn, *, user_ref, strategy_id, kind, prices, placed_at, write, only, closes, reason, trigger_id, before_write) -> Outcome` where Outcome is `Exited | NotYet | Flat | Refused`. Its own docstring says "reaches no broker door" (ADR-281) and a test (`test_paper_order_door`) walks it to prove that. The shared step `ofo/tracking/closing.py` `open_legs_to_close(net, only)` is built and used by the paper store; the real path (`execute_plan.py:223-226` `exit_legs`) kept its own two lines because the parked Phase 6 B2 was left out (`docs/design/modular-doors-2026-11-25/PARKED-phase6-B2.md`).
2. **Four callers reach the paper door today**, each with its own gate: the tracking exit route (`routes/tracking.py:543-564`, with `may_act` "exit"), the manual orders route (`routes/paper.py:1370-1429`, with `may_act` "place"), `paper_monitor.py` (stop fired) and `paper_settlement.py` (expiry). The dialog gate is `usePaperExit.js:10-15`; the alert "Exit the position" opens `PaperStrategies` (`AlertsPage.vue:34,81,142`). A time exit has no caller I found (search terms: `time_exit`, `exit_at`, `close_time` in backend; not read in depth).
3. **The real side can only hand over a basket** (audit section 1). `POST /strategies/{id}/execute` with action EXIT builds read-only LIMIT orders (legs by `execute_plan.py:223-227` `exit_legs`; LIMIT orders by `execution/basket.py:276-278`); the user places them on Kite; `POST /strategies/{id}/execution/return` reconciles. Nothing fires it from a stop, an alert, a clock or an expiry.
4. **There is no tag.** Paper is "present in the paper store" / `PaperOrder` type (audit section 2). "Where the tag is read" needs a new field; that is a migration, so it is a late step.

## 2. The one function

Put one module, `ofo_app/exit_door.py` (name for the builder to choose), in front of everything. Interface only:

```
exit_position(request: ExitRequest) -> ExitOutcome

ExitRequest:
  user_ref, strategy_id
  cause: DIALOG | ALERT_ACTION | STOP_FIRED | TIME_EXIT | EXPIRY      # why; recorded, never branches behaviour
  legs: all open | named contract keys                                # whole open quantity of each (per-lot choice: see Q11, a SPEC CHANGE for real)
  asked_at: the one clock reading
  trigger_id / trigger_values: for STOP_FIRED, the exact values (ADR-019)

ExitOutcome (one sentence + one record, same for both tags):
  Refused(code, sentence, blocked_what, next_step)                   # ADR-029 error shape
  NotYet(reason)                                                     # no live price for a leg; nothing stored
  Flat                                                               # nothing open
  Done(orders, state)    state in: HANDED_OFF | PARTLY_FILLED | FILLED | UNKNOWN
```

Every caller below becomes "build an ExitRequest, call `exit_position`, show the outcome":

| Caller (today) | Becomes |
|---|---|
| Exit dialog / Exit all / per-leg Exit (`usePaperExit`, `exitAllPaper`, `exitPaper`) | one `useExit` composable posting cause DIALOG |
| Alert answer "Exit the position" (`AlertsPage.vue`) | opens the same dialog, cause ALERT_ACTION |
| Stop fired (`paper_monitor.py`) | cause STOP_FIRED with trigger values |
| Time exit | cause TIME_EXIT (needs a clock trigger; none found today) |
| Expiry (`paper_settlement.py`, `real_settlement.py`) | cause EXPIRY, gate profile above (step 8 of the build order: the exchange settles real, so the adapter records, it does not send) |

### Fixed order inside the door (the same for both tags; each step is one function, none reads the tag)

The Opus review (section 9) changed this list. Two rules came out of it: **prices are read before the lock, never under it** (`paper_exit.py:14-17` records deadlock A3), and **reconciliation comes before "Flat"**, as the real route does today (`execute.py:394`).

0. Read prices through the one price door (section 5), outside any lock (`live_exit_prices`, as `tracking.py:559` does today).
1. Row lock on the strategy (as `exit_strategy` step 1 today).
2. **Reconciliation block (ADR-018):** an unresolved mismatch between our book and Zerodha's blocks the exit, before any other refusal, so the user sees the true reason (`execute.py:394`, `gate_reconciliation_mismatch`). Paper's "Zerodha's view" is its own book, so the check passes by construction through the same function (no skip).
3. **One exit in progress (ADR-105):** refuse when a plan is open (`execution_plan_store.py:270-271`, `PLAN_OPEN`) or a tagged order is still open at Zerodha (`execute.py:331-332`). A `HANDED_OFF` basket moves no net (`held_units` counts fills only, `execute_plan.py:200-205`), so the row lock alone does not stop a second basket from a stop, the dialog and an alert. The door records the plan before it returns the basket. Same function for paper (a paper exit is never in progress, so it passes).
4. Strategy state: nothing open -> `Flat`; closed -> `Refused` (same codes, one sentence each). Flat is judged from the reconciled book (step 2 passed), not from ours alone.
5. **Market rule (ADR-119 calendar):** ONE function. Paper uses `may_act` (`paper.py:1394`, `tracking.py:549`); real uses `market_open` passed into the gate (`execute.py:66,678`, `safety.py:358`). Two implementations of one rule is a defect (`paper_monitor.py:47` says "the ONE market-open rule"); the door calls one.
6. Closes = `open_legs_to_close(net, only)`, opposite side, whole open quantity of each chosen leg; order per Q8.
7. **Price rule per cause (section 5).** All-or-nothing for "Exit all", a stop, a time exit: if any leg has no live price the whole request is `NotYet` and nothing is stored or prepared, because a partial exit can drop a protective leg and leave a short naked (REQ-056 AC-4; today `tracking.py:538-540` and `paper_exit.py:132-134`). Per-leg exits only for legs the user names (ADR-322 (3)).
8. **Freeze limit (ADR-092) and margin (ADR-016):** real already does both on an exit (`execute.py:455-467`); paper does neither (audit). The door applies both to both (Q4 asks how paper gets the margin read without a broker session).
9. `adapter.execute(closes, prices)` (below).
10. One write: orders, the timeline entry, the trigger record for STOP_FIRED with its exact values (ADR-019), the alert. The trigger is claimed under the lock, before the write (`paper_exit.py:135` `before_write`; a stop fires once). The door never commits; each caller keeps its transaction.

**Cause chooses a gate profile, the same for both tags.** The gates are a table keyed by cause, not branches in code: DIALOG / ALERT_ACTION / STOP_FIRED / TIME_EXIT run steps 0-10. **EXPIRY is a settlement, not an exit order:** it runs at 15:30 after the close at intrinsic value (`paper_settlement.py:17,128-129,158-160`), so the market rule (5) and the live-price rule (7) do not apply to it; it uses the official settle price and the same writer (10). Real expiry is settled by the exchange, so its adapter reconciles and records and sends nothing.

### The tag and the adapters

The tag is read **once**, in one function `adapter_for(strategy) -> ExitAdapter`, at step 9. No other line of backend or frontend may branch on it (a repo-scan test, listed in the parity suite, keeps that true). Display words ("Paper", "Real (Zerodha order)", ADR-330 (10)) come from the tag by one lookup, not by `if`.

```
ExitAdapter.execute(closes, prices, request) -> Done
```

| | Paper adapter (exists as `exit_strategy`'s write) | Real adapter (new) |
|---|---|---|
| Does | records each exit at its price at once | builds the Kite basket (`build_basket`, our tag per order, `make_tag`, `basket.py:123`) and returns it to be placed on Kite's page (ADR-054) |
| State returned | `FILLED` | `HANDED_OFF` (**submitted is not executed**, ADR-017); the record is "prepared, not placed" until reconcile |
| How it becomes filled | n/a | `execution/return` reads Zerodha's orders/trades/positions (ADR-018: Zerodha's state wins) and moves the record to `FILLED`, `PARTLY_FILLED` or `UNKNOWN`; the exit then shows its done sentence from the same code as paper |
| Retry | none | none: a refused or failed leg is shown; the user chooses Complete / Retry / Close (`partial.py:728,755,788`), each a new confirmed act (ADR-017). A basket nobody places: see Q12 |
| Substitution | none | none: a contract Zerodha will not accept is refused, never swapped (ADR-016) |
| Broker call | none (a test walks it) | none to place; reads only (`kite_endpoints.py:23-29`) |

Both adapters satisfy one `ExitAdapter` contract test, run against both, so a paper adapter cannot drift from the real one.

## 3. How ADR-016 to ADR-019 hold

| Rule | Where it holds in the door |
|---|---|
| ADR-016 Zerodha is the authority; margin hard gate; no silent substitution | steps 7-8; real adapter refuses a contract Zerodha rejects; paper's check is the same function over the same instrument master |
| ADR-017 submitted is not executed | `HANDED_OFF` is a state of its own; screens and P&L read FILLED only; the paper adapter never shows HANDED_OFF because it has no hand-off |
| ADR-017 no automatic retry | no code path calls the adapter twice for one ExitRequest; a stop that found no live price is `NotYet` and is re-evaluated on the next tick: nothing was submitted, so that is not a retry of an order; once a real basket is HANDED_OFF the trigger is spent (`before_write` claim, as `paper_monitor` does today) and never hands off again, and step 3 refuses a second basket while the first is open (what happens if nobody places the first: Q12) |
| ADR-017 partial is an exception | `PARTLY_FILLED` opens the existing Complete / Retry / Close choice; paper cannot produce it (owner question Q6) |
| ADR-018 mismatch blocks | step 3, same function for both tags |
| ADR-019 exact trigger values, immutable timeline | step 10; STOP_FIRED stores the crossing tick and level in the record |
| ADR-054 server sends nothing | the real adapter returns a basket; a test asserts no allowed call writes to /orders or /gtt |

## 4. What each cause does on the real path today vs after the door

| Cause | Paper today | Real today | After step 5 (real adapter) | Needs owner |
|---|---|---|---|---|
| Dialog / Exit all | records at once | `/execute` EXIT -> basket page | one dialog, basket for real | step 5 |
| Alert "Exit the position" | opens the paper dialog | opens the paper dialog (wrong door for a real position, audit row on AlertsPage) | opens the same dialog, adapter by tag | step 4 fixes the door, 5 the adapter |
| Stop fired | worker records the exit | nothing watches | a real stop can only **alert and prepare** the basket; it cannot place it (ADR-054) | Q1 |
| Time exit | none found | none | same as stop | Q1 |
| Expiry | settles at intrinsic and writes | logs only | the exchange settles; the adapter reconciles and records, sends nothing | step 7 |

## 5. A stale price on the real path, against ADR-330 (28)

Today's rules, all for paper, none for real:
- ADR-330 (28): **entry** while prices are disconnected is allowed, with a confirm line "Prices are not live; the entry is the last captured price, as of 14:46"; the user can type his own entry price (REQ-109 AC-1).
- ADR-322 (3): an **exit** of a leg with no live price is refused, per leg, "Prices are not live; try again when they update".
- ADR-212: no fill outside market hours.

One price door returns, per leg, one of `live(price, as_of)`, `last_captured(price, as_of)`, `none`. The door applies the same words to both tags:
- Exit, `last_captured` or `none`: for "Exit all", a stop or a time exit the whole request is `NotYet` with the ADR-322 (3) sentence and nothing is stored or prepared; for legs the user names, only the named leg that lacks a price is refused. (ADR-322 (3) allows the per-leg exit; the door does not turn it into dropping a protective leg.)
- Entry, `last_captured`: allowed with the ADR-330 (28) line the user confirms.

What changes for real: a real exit basket carries LIMIT prices from depth (`execute_plan.py`, `leg_quote`); a stale depth price would sit on a real order that can fill at a bad level, which paper can never show. Following the rule literally, the real exit is refused exactly like paper; the real entry follows (28) and the typed limit price is the user's own. Whether a real order should be allowed on a "last captured" price at all is a business choice (Q2). The door must not decide it.

## 6. Build order (each step leaves the app working)

Steps marked **PAPER-SIDE** do not touch the real order route and are safe to build without the owner watching (Tier B build, one verifier). Steps marked **WAIT** touch `routes/execute.py`, `execute_plan.py`, `execution/*` or turn the real door on, and wait for the owner (Tier A, Opus review, per the lane rules).

| # | Step | Side | Keeps the app working because |
|---|---|---|---|
| 0 | Write the rule as a decision row: ADR-330 (58) text, the tag rule, and the one-tag-per-strategy rule if Q9 is answered | docs | no code |
| 1 | `ExitRequest`/`ExitOutcome` types and `exit_position` wrapping today's `exit_strategy`; the tracking exit route, `paper_monitor` and `paper_settlement` call it; **behaviour identical**, existing paper tests are the oracle | PAPER-SIDE | a pure wrapper with golden tests |
| 2 | Move the gates (closed, market rule, price rule, exceeds-open, busy) from the routes into the door's fixed order, **prices still read before the lock and the exit still all-or-nothing**; refusals keep their codes. EXPIRY keeps its own profile | PAPER-SIDE | the same refusals in the same order; a test per refusal code; a race test (stop and dialog at once) and a stale-leg test on an iron condor |
| 3 | The `ExitAdapter` contract and its contract test; the paper adapter is `exit_strategy`'s write; real adapter is a stub that raises "not wired" and is **unreachable** (the tag is paper everywhere) | PAPER-SIDE | no caller can reach the stub |
| 4 | Frontend: one `useExit` composable replaces `usePaperExit`, `exitAllPaper`/`exitPaper` and the alert's own opening; the dialog is generalised (title from the tag, kind 'real' still not rendered). Display only, but `AlertsPage.vue:81,142` is a surface real users share: a real position's alert must stop opening the paper dialog | PAPER-SIDE (display) | same endpoints, same screens, paper only |
| 5a | Parity tests written (audit section C) and run in "expected red" mode for the real side; no product change | PAPER-SIDE | tests only |
| 5 | Real adapter: `build_basket` + `HANDED_OFF` + reconcile into `FILLED`; `/execute` EXIT calls the door; the door's steps 0-8 apply to real exits (the one market rule, the open-plan guard, freeze, margin, reconciliation, all-or-nothing price rule); real keeps every refusal it has today | **WAIT** | behind `order_path` off by default; the old real exit page stays until the owner turns the new one on |
| 6 | Tag field (migration) and `adapter_for`; paper strategies and real strategies both go through the door by tag; remove the paper-store-membership test as a stand-in | **WAIT** (migration, both tags) | backfill: a strategy with paper orders gets `paper`, one with real fills gets `real`, **every other strategy stays untagged and is refused an order until its first order fixes the tag** (never default to real); the one-tag rule decided in Q9 |
| 7 | Stops/triggers by tag: `paper_trigger_store` becomes a trigger store for both; the monitor fires STOP_FIRED through the door; on a real strategy it alerts and prepares the basket (Q1), never places | **WAIT** | triggers for real strategies are created off by default |
| 8 | Real expiry: the adapter records the exchange's settlement after reconcile; `real_settlement.py` stops being "logs only" | **WAIT** | no order is sent in any case |
| 9 | P&L: one engine for both (ADR-008); retire the second path (audit rows on `real_pnl.py`/`orderbook.py`); `PositionsTotals.vue` stops printing "not shown yet" | **WAIT** (money number) | dependency of "same screens"; larger than the exit and may be its own lane |

Steps 1-5a (and 0) can run unattended. The first thing that changes what a real user can do is step 5; the first thing that can lose real money by being wrong is step 7 (a stop that prepares a basket nobody places is silent protection: the alert must say so in words).

## 7. Questions that are the owner's (business choices; I decide none)

Each: the decisions it sits beside, the real case, and my recommendation (not a decision).

- **Q1 A stop or time exit fires on a real position: what happens?** Beside ADR-054, ADR-100, ADR-165, ADR-207 (5), ADR-281 (2), ADR-017. The server cannot place an order today and ADR-281 (2) says automatic placement needs a SPEC CHANGE and an answer to F-102 (Kite's basket does not guarantee run order). Options: (a) alert plus a prepared exit basket the user places on Kite, with the sentence "No order has been sent"; (b) wait until Zerodha confirms in writing that offsite orders are non-algo and the placement route is built (ADR-054). Recommendation: (a) now, labelled plainly; it is the only version that keeps ADR-054 and gives a real stop any meaning. Real case: 26 Nov paper trade 172 closed through a stop at 174.73; on a real trade the same cross today produces nothing.
- **Q2 Stale price on a real order: refuse or allow with a line?** Beside ADR-330 (28), ADR-322 (3), ADR-212. Options: (a) mirror paper exactly: exit refused per leg, entry allowed with the confirm line and the user's own typed limit price; (b) refuse stale on real for both. Recommendation: (a), because the rule is "same", and the typed limit price is the user's own number; note that (a) lets a real BUY limit be placed on a price 4 minutes old (the 26 Nov 14:46 case).
- **Q3 (withdrawn after review).** Real already refuses outside market hours (`safety.py:358`, `execute.py:678`); my first draft said it did not. What remains is a technical call, not the owner's: one market rule function for both (door step 5).
- **Q4 Which paper checks does the rule add to paper, and which does real get that paper lacks?** Beside ADR-016, ADR-092, ADR-330 (58). Paper has no margin check, freeze check, circuit check, lot alignment (audit row on `execution/*`). Real already does freeze and margin on exits (`execute.py:455-467`). Options: (a) paper gets freeze/circuit/lot checks (no broker needed) and a margin check only when a Zerodha session is connected, otherwise a "margin not checked" line; (b) paper gets all four and needs a connected broker; (c) leave paper without, state it for paper by name in a new decision. Recommendation: (a). Real gets `take_profit_at_loss` (ADR-326) and the adjustment-count limit, which paper has and real lacks (audit rows; zero-hit grep, see section 8).
- **Q5 Which sentence wins when `paper_*` and `gate_*` words differ for the same case?** Beside ADR-029, ADR-330 (58). Recommendation: one sentence per case, written once by the owner for the case, with no tag word except in the title.
- **Q6 Does paper simulate a partial fill or a rejected leg?** Beside ADR-017. Today paper never produces them, so the Complete / Retry / Close path is untestable on paper. Recommendation: no simulation now; the parity test uses a stub broker for the real side. Revisit if the owner wants paper to teach those choices.
- **Q7 When may the real exit door be turned on, and who is watching?** Beside ADR-281 (hold), `kite_flags.json` `order_path`. Recommendation: after step 5a is green and the owner watches the first real exit on a one-lot test during market hours.
- **Q8 Exit order of legs.** Beside ADR-117 / D-02, ADR-017 (Q26), F-102. Paper puts BUY exits first (store, D-02); real sorts by contract key (`execute_plan.py:226`) and sequences with "never all buys first" hard-coded (`sequence.py:5-6,30-32`). Options: (a) buys first on both; (b) the sequencer's order on both. Recommendation: (a) for exits (buying back shorts first removes the open risk first), with the buy confirmed filled before the next is handed off while F-102 stays open.
- **Q9 Can one strategy hold paper and real orders, and what is an untagged strategy?** Beside ADR-276, `adjust_history.py:163` (a mixed step already raises). Recommendation: one tag per strategy, fixed at the first order; an untagged saved idea has no tag and can place no order until the first order sets it; a new real trade from a paper idea is a new strategy.
- **Q11 Per-lot exit on real (SPEC CHANGE).** Beside ADR-105 (exit closes the net), ADR-092, ADR-002 (Strategy Guard). Paper's confirm list lets the user choose lots per leg; real closes exactly the net (`execute_plan.py:224-227`). The rule says same: either real gains a per-lot exit (a spec change) or paper loses it. Recommendation: real gains it, refused when the remainder would leave a short without its protective leg.
- **Q12 A real exit basket nobody places.** Beside ADR-017, ADR-054, ADR-105. The trigger is spent when the basket is handed off and the open plan refuses every later exit until reconciled. Options: (a) the plan lapses and the trigger re-arms after a stated time or when the user discards the basket; (b) both stay until the user acts, with an alert that says so. Recommendation: (a) with a visible "Discard this basket" action; an unplaced stop basket must never be silent.
- **Q10 Real P&L on screen (step 9) before or after the exit door?** Beside ADR-008, ADR-330 (10)(24). Recommendation: after; the exit door does not depend on it, but "same screens" does.

## 8. What I did not verify

- No time-exit caller was found; I did not read `playbooks`/`background` for a clock exit. Say so before building cause TIME_EXIT.
- `routes/execute.py` and `execution_return.py` were read only at their heads; the claim that they lack take-profit, duplicate-leg and `paper_limit` checks rests on a zero-hit grep (D1: zero hits prove only the pattern failed).
- That the alert "Exit the position" opens the paper dialog for a real position is read from `AlertsPage.vue:34,81,142`, not run.
- Which source the header bell badge reads (`AppHeader.vue:57` vs `:325`) is unread.

## 9. Opus review of this design (27 Nov), and what changed

One independent Tier A review (Opus; why: the design is for the path that exits a real money position). Verdict was REVISE. Findings and what this file now says:

| # | Finding | Result |
|---|---|---|
| 1 | "That leg is NotYet, the others proceed" would drop a protective leg (short 24000 CE stale, long wings closed, short left naked) | fixed: all-or-nothing for Exit all / stop / time exit; per-leg only for legs the user names (step 7, section 5) |
| 2 | The design dropped the real guard against a second basket (`PLAN_OPEN`, open tagged order) | fixed: step 3, plan recorded before the basket is returned |
| 3 | "Flat" before reconciliation, the reverse of `execute.py:394` | fixed: reconciliation is step 2 |
| 4 | Prices read under the lock (deadlock A3, `paper_exit.py:14-17`); trigger claim missing | fixed: step 0 reads before the lock; claim in step 10 |
| 5 | "Same steps for every cause" breaks expiry (15:30, after the close) | fixed: gate profile by cause, one table for both tags |
| 6 | Wrong claim: real has a market gate (`safety.py:358`) | fixed here; the audit row 7 was corrected too; Q3 withdrawn |
| 7 | Lots per leg conflicts with real's whole-net exit | `lots` removed from the request; Q11 (spec change) |
| 8 | `acknowledged_not_live` undefined and risky | deleted |
| 9 | Trigger spent after hand-off; open plan blocks later exits if basket is never placed | Q12 |
| 10 | Backfill tagging every unknown strategy `real` | fixed: untagged until first order (step 6, Q9) |
| 11 | Wrong citations (`execute_plan.py:225`, buys-first claim, ADR-105 / ADR-117 meaning) | fixed in this file |
| 12 | Build step 4 changes how a real position's alert opens | labelled "display" and kept in the safe list with the caution |

The review did not read `execution_return.py` reconcile, `real_settlement.py`, F-102, the full text of ADR-054/281/330 or the frontend beyond `usePaperExit.js` and `AlertsPage.vue`. Those remain unreviewed.
