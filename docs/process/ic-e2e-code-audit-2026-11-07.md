# Iron condor adjustments: end-to-end code audit (2026-11-07 14:02 IST)

Code read: `feature/adjustments` at ebefb113. Read from code only; documents were not taken as evidence.
Scope (owner, 2026-11-07): paper and real-Zerodha paths, each gap tagged; the default IC system playbook
(18 applicable approaches, 14 triggers, the day rules that are on, all guards); critical = a missing or broken
step, a possible wrong order, quantity or money number, or no desktop screen for the step.

Future scans: read this file first. A gap listed here is re-checked against code, never re-derived from docs.

## Critical, not done

| id | gap | path | evidence (file:line) |
|---|---|---|---|
| C1 | A live adjustment cannot be executed. `/execute` takes only ENTRY or EXIT, and an ENTRY while legs are held is refused ("an adjustment, PROPOSED only"). `ofo/strategy/modification.py` is imported by nothing | live | `backend/ofo_app/routes/execute.py:108`, `backend/ofo_app/execute_plan.py:213-220` |
| C2 | A live strategy is not monitored. The background worker and `read_tracked` read only `public.paper_orders`, and real fills never write there. So a live strategy gets no triggers, no stop lines, no day rules and no adjustment count | live | `backend/ofo_app/background.py:1609`, `backend/ofo_app/adjustment_readers.py:116`, `backend/ofo_app/paper_book.py:24` |
| C3 | Live basket order is not sequenced (buy first). The basket is built in plan or contract order. `ofo/execution/sequence.py` reaches the app only through `partial.py` and `review.py`, which no route uses | live | `backend/ofo/execution/basket.py:278-296`, `backend/ofo_app/execute_plan.py:223-226` |
| C4 | No freeze-limit split: an order above the freeze limit blocks the whole basket. `slice_quantity` is not called from `ofo_app` | live | `backend/ofo/execution/freeze.py:9,73-77` |
| C5 | Partial fill or one leg rejected: the server lists the choices, but no route acts on Complete or Retry. `ReturnCheck.vue` has 0 `choice`/`partial` hits, and `TwoBasketStepper.vue` is used by no page | live | `backend/ofo_app/execution_return.py:49`, `backend/ofo_app/routes/execution_return.py:298` |
| C6 | Live expiry settlement is not wired: `settle_expired_legs`/`settle_legs` have 0 callers in `ofo_app`. Only paper settlement starts | live | `backend/ofo/reconciliation/settlement.py:77`, `backend/ofo_app/main.py:96` |
| C7 | T-11 (IV change since entry) never fires on live prices: `entry_atm_iv` is set only on scenario paths | both (live market) | `backend/ofo/adjustment/playbook_eval.py:536`, `backend/ofo_app/background.py:1202` |
| C8 | T-14 (gamma, loss on a 1% move) is evaluated in scenario mode only | both (live market) | `backend/ofo_app/adjustment_check.py:382` (commit ee7dbaab) |
| C9 | The max-2 adjustment limit only filters what is offered. Paper order placement has no limit check, so a builder edit takes a 3rd adjustment | paper (live has no adjustment) | `backend/ofo/adjustment/offered.py:33-40`, `backend/ofo_app/routes/paper.py:726-760` |
| C10 | Paper fill and exit price comes from the browser; the server checks only the tick size. A server-priced exit route exists (`POST /strategies/{id}/tracking/exit`), but no frontend code calls it | paper | `backend/ofo_app/routes/paper.py:703-706,742`, `backend/ofo_app/routes/tracking.py:425` |
| C11 | A-29 (reduce) can propose a 0-lot trade: the guard refuses only under 2 lots, and `lots // reduce_divisor` is 0 when the divisor is larger than the lots | both | `backend/ofo/adjustment/approaches.py:714-726` |
| C12 | A-04 (roll to next expiry) shows no after-adjustment payoff: two expiries raise `MultiExpiryError` | both | `backend/ofo_app/routes/adjustment.py:415-416` |
| C13 | No screen shows a finished strategy: `COMPLETED_STATUSES = []`, and a closed status is never stored | both | `frontend/src/pages/MyStrategiesPage.vue:24` |
| C14 | The paper confirm list puts every exit before every add, so a roll sells the new short before buying the new wing. Harmless on paper; it must not be reused for live | paper, blocks live | `frontend/src/lib/paperDrafts.js:118` |

## Verified done (code exists and runs from a loop or a route)

- **Paper monitoring on live prices:** T-01, T-02, T-03, T-06, T-07, T-09, T-10b, T-13, T-18, T-19 and T-21 (`backend/ofo/adjustment/playbook_eval.py:474-736`). The worker is at `backend/ofo_app/background.py:1151-1268`.
- **Day rules and situations:** expiry 14:30 close rule (`playbook_eval.py:932`), weekend/holiday 15:00 carry check (`:1144`), S-02 (`:1211`), S-12 (`:1232`).
- **IC approaches:** 15 approaches build legs and 3 are non-trade by design. All are reachable from Compare (`frontend/src/components/strategy/AdjustCompare.vue:227` calls `POST /adjustment-approaches`). 181 domain tests pass.
- **Paper path:** mixed close/open basket in one transaction, and an exit never exceeds the open quantity (`backend/ofo_app/paper_store.py:59-63`).
- **Paper exits and settlement:** index and leg stop exits (`backend/ofo_app/paper_monitor.py:226-235`), paper expiry settlement (`backend/ofo_app/paper_settlement.py`, started at `main.py:96`).
- **Live safety checks:** margin check fails closed (`backend/ofo_app/checked_basket.py:59-64`), a reconciliation mismatch blocks execution (`backend/ofo_app/routes/execute.py:395`), and there is no auto retry.

## Not critical, or by design

- **T-16 / % of margin stop:** off by default in the IC playbook version 0040 (ADR-247). The background process also has no margin source (#627, `backend/ofo_app/background.py:1745`).
- **Exit rules (profit target, stops, time exit, expiry rule):** they raise a suggestion, and the user presses to act (ADR-003). Only paper stop triggers write exits automatically.
- **Charges:** shown beside the P&L, never subtracted (`backend/ofo_app/routes/paper.py:172`, REQ-109 AC-10).
- **Debit limit:** "Rs 500 or 10% of max profit" is read as whichever is larger (`backend/ofo/adjustment/liquidity.py:170-171`). This is open for an owner decision.
- **Low OI:** a strike under 10,000 OI is flagged, not hidden (`backend/ofo/adjustment/liquidity.py:5`).

## Documents corrected by this audit

- `docs/research/sensibull-study-2026-10-21/gap-list.md` P4/P5: paper per-leg stop and conditional exit are built.
- `work/W-109.md:34`: Adjustments and Live Strategies pages are built.
- Historical handovers that say paper settlement is not built (`docs/process/session-handover-2026-10-28-gcbp.md:38`) and that Exit all was removed (`docs/process/goal-contract-GC-UI-2026-10-28.md:215`) are dated records. They are left as written, and this file supersedes them.
