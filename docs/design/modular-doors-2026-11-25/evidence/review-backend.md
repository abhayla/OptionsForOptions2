# Backend "doors" review: one capability, one function

Repo `D:\Abhay\Ventures\OptionsForOptions2`, branch `fix/ic-live-test-1123` (5d9b53ca). Read-only. All paths are under `backend/` unless shown. I read the 23 Nov `DUPLICATES.md` first (helper-level copies: R1 expiry cut-offs, R3 rupee text, R5 settle maths, R8 Kite token wiring; those are not repeated here). Defect ids D-01, D-05, D-41, D-60, S-20 are taken from the task brief; I did not open the defect list itself, so where I link a defect to a cause that is my reading of the code, not a reproduced fact. I ran nothing (no tests, no processes).

## Summary table

| # | Capability | Places | One shared function? | Risk if left | Proposed door | Size | First? |
|---|---|---|---|---|---|---|---|
| 1 | Exit / close legs (paper) | 5 order writers: `routes/paper.py:1296 place_paper_orders`, `routes/tracking.py:513 exit_tracking`, `paper_monitor.py:205 _fire`, `paper_settlement.py:164 _settle_strategy`, plus the browser builds the exit basket (`frontend/src/lib/paperList.js:201 exitRowsFor`) | Only the WRITE is shared (`paper_store.place`, `paper_store.py:119`). "Which legs, which side, how many, at what price" is rebuilt 4 times | Money (wrong exit set or price) | `exit_strategy(strategy_id, reason, price_mode, legs=None)` | L | after #3 |
| 2 | Real-order exit | `routes/execute.py:362` -> `execute_plan.py:223 exit_legs` (plan EXIT), `ofo/execution/partial.py:788 close_partial_strategy` | Two builders of "close the net, opposite side" (real) plus a third in paper. Real path always LIMIT, paper has no limit orders | Money | Share only the "close list" (`open_legs_to_close`), keep the real gate separate | M | after #1 |
| 3 | Read a live price (leg or index) | 9 readers, 7 different "hold the feed" mechanisms, 5 that hold nothing | `live_push.hold_and_read` (`live_push.py:95`) is the claimed ONE but is bypassed 4 times | Money + wrong figure (D-01, D-41, S-20) | `read_market(ctx, feed, underlying, leg_keys, need_index, purpose)` | M | YES, first |
| 4 | "May this act now?" gates | `paper_limit.refuse_when_closed` (`paper_limit.py:119`), `paper_monitor.on_quote` (`:177` calendar), `market_state` (`outcome.py:224`), `paper.is_live`, 3 other copies | Partly: `market_state` is the one answer but 4 callers use the raw calendar or `snapshot.market_closed` | Wrong figure / wrongly enabled button (D-05) | `may_act(ctx, action, at) -> Allowed or Refused(reason)` | S-M | after #3 |
| 5 | Trigger save + crossed + fire | `paper.py:1637 _already_crossed`, `stops.crossed` (`ofo/tracking/stops.py`), `paper_monitor.py:172 on_quote` | `stops.crossed` shared; the PRICE fed into it is read 3 different ways | Money (D-01: a stop saved unchecked) | `check_trigger_levels(...)` on top of door #3 | S | with #3 |
| 6 | P&L / charges assembly | `routes/paper.py:651 _figures`, `routes/tracking.py:312 _figures`, `outcome.py:389 read_booked`, `adjustment_history.py:333 closed_figures_many`, `routes/adjustment.py:428 price_after` | Engine maths shared (`net_positions`), API assembly done twice for the same strategy (paper vs tracking) | Wrong figure | `strategy_money_view(strategy_id, prices)` | L | after #3 |
| 7 | Alerts / notifications | `paper_trigger_store.add_alert` (called only from `paper_monitor._fire`), `playbook_store.open_suggestion` via `background.DbGateStore.apply`, `notifier.notify` (worker watch only) | Three separate systems, no shared "raise an alert" | Maintenance + wrong text (S-20) | `raise_alert(kind, strategy_id, facts)` | M | late |
| 8 | Order recording | `paper_store.place` | YES, one writer (good) | Low | none; pass it a proper order list from door #1 | - | - |

Order of work I recommend: door 3 (price) -> door 5 (trigger check, tiny) -> door 4 (gates) -> door 1 (exit) -> door 6 (figures) -> door 2 -> door 7.

---

## 1. Exit a strategy / exit legs (paper)

### Where each exit is built and recorded

| Exit way | Who decides the legs | Who decides the price | Order kind | Where recorded |
|---|---|---|---|---|
| Manual Exit / Exit all button (the one the frontend uses) | The BROWSER: `exitRowsFor` builds side and lots from the list (`frontend/src/lib/paperList.js:201-212`), posts to `/paper/strategies/{id}/orders` (`PaperStrategies.vue:330`) | Server: `_server_exit_prices` (`routes/paper.py:1218-1243`), live price of each leg, `paper.leg_price` | `exit` | `place_paper_orders` -> `paper_limit.place_checked` -> `paper_store.place` (`paper.py:1323-1326`) |
| Second manual exit route `POST /strategies/{id}/tracking/exit` | Server, from the ENTRY legs (`bk.legs[i].quantity`, `tracking.py:550`) | Server: `paper.exit_prices_now` (`tracking.py:546`) | `exit` | `paper_limit.place_checked` (`tracking.py:554`) |
| Conditional index exit + leg stop (armed trigger) | Server: net open quantity of each contract, opposite side (`paper_monitor.py:231-233`) | Server: tick price for a leg stop, one provider read for an index exit (`_exit_prices`, `:244-260`) | `stop` | `paper_store.place` directly (`paper_monitor.py:231`), NOT through `place_checked` |
| Expiry settlement | Server: net open of each due contract (`paper_settlement.py:171-177`) | Intrinsic value from the index close (`settle_price`, `:125`) | `settle` | `paper_store.place` directly (`:184`) |
| Adjustment "close" / "reduce" | The browser again: the adjustment screen posts a basket to the same `/paper/strategies/{id}/orders` route; `ofo/adjustment/approaches.py:412 close()` only builds the preview | Server for `exit` kind; for `add`/`open` kind the browser's typed price (`paper.py:1325` `exit_prices.get(i, o.price)`) | `exit`/`add`/`open` | same as the manual route |
| Plan target / stop-loss / time exit | NOT an exit. `adjustment_check.exit_inputs_of` (`adjustment_check.py:281`) and `approaches.py` A-27/A-35 only feed an offered approach or an alert. Nothing in `ofo_app` places an order from a plan condition (grep of every `paper_store.place` / `NewOrder(` caller: only the 5 sites above) | - | - | - |

### Do they share one function?
No. They share the writer (`paper_store.place`, `paper_store.py:119`, which checks "must reduce, never exceed open", `_check_reducing` `:85`), and the manual routes share `paper_limit.place_checked` (`paper_limit.py:125`), which adds the market-hours refusal and the adjustment limit. The monitor and settlement skip `place_checked`, which is right for settlement (it must run after the close) but means a stop-out never counts as an adjustment (see `paper_limit.py` docstring: "every batch after the entry is one adjustment"; whether that is wanted is a spec question, unverified).

"From the net open book, make the opposite orders" is written three times in the server:
- `paper_monitor.py:231-233` (`"SELL" if open_net[c] > 0 else "BUY"`, `abs(open_net[c])`)
- `paper_settlement.py:171-177` (`side = "BUY" if net < 0 else "SELL"`, `abs(net)`)
- `routes/tracking.py:471 _opposite` + `:550` (works from ENTRY legs, `bk.legs[i].side/.quantity`, not the net book)
and once more in the browser (`paperList.js:201`: `p.units > 0 ? 'SELL' : 'BUY'`).
The real path has a fourth, `execute_plan.py:223 exit_legs` (`Action.SELL if net > 0 else Action.BUY`).

### Real differences (behaviour, not style)
1. **Who knows the quantity.** The main manual route trusts the browser's side and lots. The server only refuses if it would not reduce (`paper_store._check_reducing`) and ignores the browser's price for kind `exit` (`paper.py:1307-1308`). `exit_tracking` and the monitor use the server's own book. A browser bug in `exitRowsFor` (for example sending only some legs) silently becomes "a partial exit".
2. **Price rule.** All paper exits are a fill at the live price now (`leg_price`, live only; after hours refused, `paper_limit.refuse_when_closed`). There is NO limit-price exit in paper at all: `ORDER_KINDS = open/add/exit/settle/stop` (`ofo/engine/orderbook.py:44`), and `paper_store.place` records a fill, never a pending order. The owner's "if exit is triggered with a limit condition, put limit orders for all legs" has no paper equivalent today. The real path is the reverse: it is ALWAYS a LIMIT (`ofo/execution/basket.py:168` default `order_type = "LIMIT"`; `basket_post.py:48` refuses anything not a read-only LIMIT), priced at the worst depth level needed to fill (`execute_plan.py:8-12`, `executable_limit`), which behaves like a marketable limit.
3. **Leg order (ADR-117 / F-102 / D-02).** Paper: BUY-backs first (`paper_store.buys_first`, `paper_store.py:98-106`, applied inside `place`); the browser also sorts (`paperList.js:210-211`); the monitor relies on `place` to reorder (comment `paper_monitor.py:233` "D-02: the stored (buys first) order"); settlement relies on `place`. Real EXIT: `exit_legs` sorts by contract key "for a stable basket order" (`execute_plan.py:223-226`), which is not buys-first; whether `checked_basket` reorders was not read (unverified). Real partial close uses "buy-backs of shorts, then sells of longs" (`partial.py` docstring, `:794-797`). So the "shorts bought back first" rule is implemented in three places with three mechanisms.
4. **Already-flat handling.** Monitor and settlement re-read the book under the strategy row lock and skip a flat leg (`paper_monitor.py:216-221`; `paper_settlement.py:174-176`). `exit_tracking` and the browser route rely on `EXIT_EXCEEDS_OPEN` raised by the store and turn it into a "leg already exited" refusal (`tracking.py:475-494 _write`; `paper.py:1334-1336`).
5. **Reason text.** Only the monitor and settlement write a reason on the order (`paper_monitor.py:232`, `paper_settlement.py:179-180`); manual exits write none (`NewOrder(...)` at `paper.py:1325` has no reason argument; `_closing_reasons`, `paper.py:596`, reads reasons back).
6. **Second manual route may be dead.** I found no frontend caller of `/strategies/{id}/tracking/exit` (grep of `frontend/src` for `tracking/exit` returned nothing; only `ofo_app/scenario_mode.py:93` lists it). Backend tests may still use it (not checked). If dead, it is a duplicate door to delete, not merge.

### Symptoms already seen
- D-05 (builder Exit enabled while server down): the enable/disable logic is in the browser (`PaperStrategies.vue:257 canExit` checks only `p.open && p.lots !== null`), the server only refuses at click time (`tracking_not_connected`, `paper.py:1226-1227`). There is no server-side "may I exit now?" answer the screen can ask beforehand (see capability 4).
- S-20 (see capability 3 and 7).

### Proposed door
`exit_strategy(strategy_id, reason, price_mode, only_contracts=None)`:
- Inputs: strategy id; reason code (manual, conditional index, leg stop, plan target, plan stop, time, adjustment close); price mode (`now` = live price of each leg; later `limit` with a per-leg limit price, only after the paper book can hold pending orders); optional contract subset (partial exit / reduce, with quantities).
- It reads the open net book itself (under the strategy row lock), builds the opposite-side order for each open contract, orders them buys first, gets prices through door 3, refuses the whole exit if any leg has no live price, then calls `paper_store.place`. Output: the stored orders, or a named refusal; nothing written on refusal.
- Callers: the manual route, the monitor, plan-condition firing (new), the adjustment "close" basket (reduce keeps the subset input).
- The real exit stays a separate door (capability 2) because it must go through the broker gate, but it should take its "which legs to close" list from the same function (`open_legs_to_close(net_book)`), so the two cannot disagree.
- NOT proposed now: limit orders in paper. That needs a pending-order concept (a new kind, a fill rule, cancel) = a spec change. Flag it to the owner as the one genuinely new feature inside this refactor.

Risk if left: money (a wrong set of legs exits, or the leg order differs between exit ways). Size L. Depends on door 3 (price) and door 4 (gate).

---

## 2. Real-order exit (Kite basket)

- Entry: `routes/execute.py` `_execute` (`:385-411`): reads held units from stored plans (`ep.held_units`, ADR-096), refuses EXIT at net 0 (`_executable`, `:350-359`), `_wanted` builds the legs (`:361-363` -> `execute_plan.exit_legs`), `_banded` reads circuit bands, `ep.price_legs` prices each leg on real depth, `_gate` runs the safety gate, `_basket` -> `checked_basket` builds a sealed read-only LIMIT basket (`:454-470`), `plans.record_plan` stores it, `order_audit.record_prepared`. The user then posts the basket to Kite in the browser (`basket_post.py`); the platform never sends the order itself (module docstring of `paper_monitor.py:7` says the monitor "never reaches Zerodha").
- Partial / failed entry: a different exit builder, `ofo/execution/partial.py:788 close_partial_strategy`, which slices by freeze quantity via `sequence.exit_orders` (`ofo/execution/sequence.py:398`).
- Real settlement at expiry: `ofo_app/real_settlement.py` (records, does not send orders; cut-off differs from paper, DUPLICATES R1).
- Differences from paper: held units come from stored PLANS plus adopted holdings, not from the paper order book (`execute.py:388-389`); price is a depth-based LIMIT, not a live tick; leg order is sorted-by-contract (see capability 1 item 3); results come back only after the user posts and reconciliation reads the Kite book (`execution_return.py`).
- Proposed: keep it apart (it is Tier-A money code with its own gate and audit). Share only `open_legs_to_close(held_units)` (inputs: signed net per contract; output: legs in the one agreed order, buy-backs first). Risk: money if the orders differ (a long sold before its short is bought back leaves a naked short). Size M. After door 1. Whether `checked_basket` already fixes the order was not read: unverified, check before touching.

---

## 3. Reading the live price (leg or index)

### The readers (what each holds, what it does not)

| # | Reader | file:line | Reads | Asks the feed to hold? | Notes |
|---|---|---|---|---|---|
| a | Paper book / list | `routes/paper.py:535 _snapshot` -> `:514 _hold_until_ready` | legs + index + forward strikes | YES, one hold of `ids + index + forward strikes` until priced and IV solvable, 3 s (`:511 FORWARD_WAIT_S`) | uses `hold_and_read` |
| b | Tracking page / list / exit / basket facts | `routes/tracking.py:215 _snapshot` -> `planned_entry.py:119 hold_until_priced` | legs only | YES but only the UNPRICED legs, NOT the index | own hold loop, does not use `hold_and_read` |
| c | Paper exit price (`_server_exit_prices`) | `paper.py:1218`, calls `tracking._snapshot` (`:1236`) | legs | as (b): legs only, no index | a different reader from the one that drew the book on the same screen |
| d | Trigger save "already crossed" | `paper.py:1637 _already_crossed`, raw `read_snapshot` at `:1647` | legs or index | NO hold at all | D-01 |
| e | Monitor leg prices (index exit) | `paper_monitor.py:65 provider_prices` raw `read_snapshot` | open legs | NO hold in the read, but `reload` subscribes the open contracts of a conditional exit (`:139-141`) | OK for index exits |
| f | Monitor index value for the alert text | `paper_monitor.py:262 _index_now` | index | NO hold; and `reload` subscribes the index only for a conditional exit (`:139-141 if t.kind == "conditional_exit"`), not for a leg stop | S-20 |
| g | Basket facts / first fill index | `adjustment_readers.py:794 _index_spot_held` and `:365 held_read` | index, chain window | YES via `hold_and_read` | correct |
| h | Builder / outcome (`StrategyPush` + REST) | `routes/outcome.py:1263` raw `read_snapshot`; push in `live_push.py` | legs + spot | NO hold in the read; relies on the browser's own socket subscription (`outcome.py:1264-1268` comment ADR-077) | differs from paper book price basis (see below) |
| i | Ready-made presets spot | `routes/ready_made.py:124 _hold_and_read` with `INDEX_LEASE` (`:66`) | index | YES, a third kind of hold (a "lease") | |
| j | Background alert worker | `background.py:261 read_prices` + `:1152 _strategy_tokens`/`:1199 _hold` | legs + index | YES, its own subscription | owns its own provider |
| k | Chain / index push, leg picker, leg edit | `chain_push.py:305`, `index_push.py:84`, `leg_picker.py:377`, `leg_edit.py:459` | index | per-screen, not traced | not opened beyond the line |

So there are at least five ways to hold (`live_push.hold_and_read`, `planned_entry.hold_until_priced`, `ready_made` lease, monitor `_resubscribe`, background `_hold`) and `hold_and_read`'s own docstring says it is "THE one hold-and-read of a request read" (`live_push.py:95-103`), which is not true of (b), (i), (e), (j).

Price BASIS differs too:
- `paper.leg_price` = live only (used for fills/stops/triggers).
- `paper.display_price` = live, or after hours the held last close (`ofo/tracking/paper.py:120-133`); its docstring says never for a fill.
- Outcome (builder) reads `snapshot.legs[...].quote` through `read_snapshot` with its own health rules (`outcome.py:1263-1275`).
- Adjustment check uses `mark_of`: LTP inside a sound book, else bid-ask mid (`adjustment_check.py:327-330`, ADR-266).
- Worker uses `_leg_quote` from the option chain (`background.py:261-288`).
That is five answers to "what is this leg's price", each defensible alone.

### Symptoms linked
- **D-01 (stop saved unchecked).** `_already_crossed` reads with no hold (`paper.py:1647`) and treats a failed or unpriced read as "saved, arms at the next live tick" (docstring `:1640-1642`; `except Exception ... return None`, `:1661-1663`). In an API process that holds nothing for NIFTY, the index has no quote, so `price_of(snapshot.spot)` is "missing" and `stops.crossed` is False (`ofo/tracking/stops.py`: not live -> not crossed). That matches the "no price" cause in the brief; matching the `kite_provider` `_wanted` set (`ofo/marketdata/kite_provider.py:73,115`, "a token nobody holds never reaches the book") is consistent with it. I did not reproduce it.
- **D-41 (two readers, two leg LTPs on one builder screen).** The builder shows the outcome reader (h) while the paper book next to it uses reader (a); different hold, different price basis (`display_price` vs raw quote). Cause is my reading of the code, not reproduced.
- **S-20 ('index value not available' in leg-stop alerts).** `_fire` asks for the index value for the alert (`paper_monitor.py:230` -> `_index_now :262-271`), but the monitor only keeps the index subscribed for conditional-exit triggers (`:139-141`); a leg-stop-only strategy has no index subscription in the monitor, so the index is unheld unless something else holds it, and `_index_now` swallows the failure and returns None (`:268-271`). Same class as D-01. Not reproduced.

### Proposed door
`read_market(ctx, feed, underlying, leg_keys, need_index, purpose)` returning one snapshot object that carries: each leg's price answer (state live/stale/missing, price, time), the index price answer, `market_closed`, and for purposes that need it the forward/IV inputs.
- It ALWAYS holds `leg_keys + index (if need_index) + forward strikes (if purpose needs IV)` through ONE implementation (the existing `hold_and_read`), releases in `finally`, and waits a bounded time.
- `purpose` picks the basis: `fill` (live only, `leg_price`), `display` (`display_price`), `check` (mark). One function, three named bases, so a screen cannot mix them by accident.
- Callers: paper book/list, tracking, exit price, trigger save check, monitor (index value for alerts), basket facts. Builder REST/push can keep the socket-held path but should call the same price-basis functions.
- Plan for the monitor: subscribe the index for every armed trigger of a strategy (not only conditional exits), so the alert text always has the index (fixes S-20 at the source).
Risk if left: money (D-01 lets a stop be saved already crossed; `_server_exit_prices` can refuse an exit for want of a hold that the book next to it did take) and wrong figure (D-41). Size M. FIRST.

---

## 4. "May this act now?" gates

Places:
- Market hours for fills: `paper_limit.refuse_when_closed` (`paper_limit.py:119-123`, via `market_state`), called by `place_paper_orders` (`paper.py:1316`), `exit_tracking` (`tracking.py:532`), `place_checked` (`paper_limit.py:131`). The monitor uses the raw calendar (`paper_monitor.py:177 market_calendar.is_market_open`). Settlement uses the calendar for the schedule (`paper_settlement.py:223`). The trigger save uses `snapshot.market_closed` (`paper.py:1649`). The book uses `snapshot.market_closed` (`paper.py:498`). Others: `adjustment_readers.py:433,623,756`, `chain_push.py:457,508,722`, `index_push.py:110,114`, `indices.py:86`, `leg_picker.py:428,522,676`, `planned_entry.py:96,103`, `outcome.py:1291`.
- `market_state` is documented as "the ONE market-state read" (`outcome.py:224-230`); `market_closed_for(provider, at)` is the provider's answer. The monitor's `is_market_open(now, holidays)` and `snapshot.market_closed` are two further answers; whether all three agree on a holiday, on 15:30 to 15:45, or on SENSEX trading to 15:39 (DUPLICATES R1) was not tested: unverified.
- "Live or stale" per price: `paper.is_live` (`ofo/tracking/paper.py:84`) for fills; `DataHealth` checks for display; `strategy_monitoring_status`/`feed_state` for the worker (`background.py:255-262`).
- "Exit allowed": there is no single server answer. The pieces are: market open, contract live (`tracked_contracts` state, `paper.py:1225-1229`), price live (`:1240`), something open to exit (`paper_store` under lock), and the browser's `canExit` (D-05). The builder Exit button therefore cannot ask the server.

Proposed door: `may_act(ctx, action, strategy_id, at)` with action in {open, add, exit, set_trigger, save_stop}; returns Allowed, or the named refusal (`gate_market_closed`, `tracking_not_connected`, `tracking_exit_contract_not_live`, ...). The routes call it before any write; a read-only twin endpoint (`GET .../can-act?action=exit`) lets the builder enable or grey out Exit from the same answer (fixes D-05's class). Reuses `refuse_when_closed` and `market_state`, so it is mostly wiring. Risk: wrong figure/wrongly enabled button; a stop-out firing outside hours is already guarded by the monitor's own check. Size S-M. After door 3 (it needs the connected/live answer from the same read).

---

## 5. Trigger save, crossed check and firing

- Save: `add_paper_triggers` (`paper.py:1668-1693`): lock strategy (D-05 comment: "two saves at one instant cannot both pass the read below"), `_new_triggers` (`:1617`) builds from the body, `_already_crossed` (`:1637`), dedupe, `paper_trigger_store.add`, commit, `paper_monitor.notify()`.
- Crossed rule: `stops.crossed(trigger, price)` (`ofo/tracking/stops.py`, 57 lines): live price at or beyond the level. This one rule is shared by the save check (`paper.py:1657`) and the monitor (`paper_monitor.py:179`). Good.
- Price fed into it: save check = raw unheld snapshot, index via `paper.price_of(snapshot.spot, underlying)` (`paper.py:1652`; the same thing exists as `paper.index_price`, `ofo/tracking/paper.py:143`, so there are two spellings); leg stop via `paper.leg_price` (`:1654`); monitor = the arriving tick `paper.price_of(quote, ...)` (`paper_monitor.py:178-182`). A trigger can be accepted as "not crossed" on a read that has no price, then fire on the next tick.
- Firing: `PaperMonitor._fire` (`:205-243`) described in capability 1.
- Other trigger-like things: level watches (`strategy_level_watch_store.py`), pause (`strategy_pause_store.py`), held-entry switches (`held_switches.py`); not opened.

Proposed: no new door; the save check becomes a thin call on door 3 (`read_market(..., purpose=fill, need_index=True)`) plus `stops.crossed`, and the one "index price" spelling `paper.index_price`. And when the read cannot give a live price at save time, decide ONE rule (today: save and arm; that is documented at `paper.py:1640-1642` as REQ-109 AC-8, so it is a spec choice, not a bug, but the user is not told). Risk: money (D-01). Size S. Do with door 3.

---

## 6. P&L / charges assembly

Same maths everywhere (the one engine `net_positions` / `lifecycles` / `book_after_charges`), but the API reply is assembled in parallel places:
- `routes/paper.py:651 _figures` + `:852 _charges` + `:916 after_charges` + `:939 _after` + `:1118 _totals`, `:1162 today_totals`, `:1182 _after_total`, `:1203 _charges_total`: the paper book/list/home. Price basis: `display_price` (closed-market close allowed).
- `routes/tracking.py:296 _book_figures` + `:312 _figures` + `:280 _after`: tracking page and list. Price basis: `leg_price` via `paper.tracking_view` (live only; paused when any leg unpriced, `:301`). Calls the same `after_charges` function imported from paper (`tracking.py:291`).
- `outcome.py:389 read_booked`: booked P&L only, for the builder's what-if target (`net_positions(...).booked`).
- `adjustment_history.py:317, 328, 333`: closed figures for the Completed list, `strategies.py:447-450` re-uses it.
- `routes/adjustment.py:428 price_after`, `:410 _closed_booked`, `adjustment_check.py:861-891`: the adjustment compare's own before/after figures (`ofo/engine/adjust_money.py`).
- Positions page `routes/positions.py:167` and home: not traced.
`routes/paper.py:531-545` and `tracking.py:215-224` also read prices differently (capability 3), so the card and the tracking page of one strategy can show different "unbooked" for the same instant. I did not compare outputs on real data: unverified, but the two paths use different price functions (`display_price` vs `leg_price`) and different pause rules (`paper.py:662-673` vs `tracking.py:301`).

Proposed door: `strategy_money_view(orders, prices, rates, basis)` returning one record: booked, unbooked, total, charges paid, charges to close, after charges, per-position rows, state (LIVE/PAUSED/EXITED/NOT_CONNECTED), pause reason. `paper.py` `_figures` and `tracking.py` `_figures` both become views of it; `read_booked` becomes `.booked`. Callers: paper book/list/home, tracking, builder target, closed list. Risk: wrong figure (two screens disagree). Size L (many tests pin today's text). After door 3.

---

## 7. Alerts / notifications

Three unrelated systems:
1. Paper trigger alerts: `paper_trigger_store.add_alert` (`:149`) written only by `PaperMonitor._fire` (`paper_monitor.py:236-239`), read by `GET /paper/alerts` (`paper.py:1746-1765`). Text built from `ofo/tracking/paper_alert.py` (`stop_reason_at`, `alert_body`).
2. Adjustment opportunities / playbook suggestions: background worker `DbGateStore.apply` -> `playbook_store.open_suggestion` / `record_held` (`background.py:783-829`), words from `record_fields` (`:735`).
3. Operator notifications: `notifier.notify` (`notifier.py:77`), used by `worker_watch.py:153` (the only caller I found).
No shared "raise alert" function; each has its own dedupe (trigger claim row, one-open-record-per-rule, Notifier `dedupe_key`). Mistake class: the alert text is built where the alert is raised, from whatever the raiser happens to hold (S-20: no index).
Proposed: `raise_alert(kind, strategy_id, facts)` that takes the facts and calls door 3 itself for anything missing (index, leg prices), then writes the right store. Risk: maintenance + wrong text. Size M. Late (nothing breaks money).

---

## 8. Order recording

One writer: `paper_store.place` (`paper_store.py:119`); its own docstring and the monitor's say it is "the only writer of paper_orders" (`paper_settlement.py:18`, `paper_monitor.py:8`), and `tests_app/test_paper_order_door.py` is said to walk the import graph (cited in the monitor docstring, file not opened). Callers found by grep: `routes/paper.py:1323` (via `place_checked`), `routes/tracking.py:554` (via `place_checked`), `paper_monitor.py:231`, `paper_settlement.py:184`; `paper_book.py:69`, `tracked_book.py:98-103` and `paper_trigger_store.py:139` build `NewOrder` rows for reading/reconciliation, not writing (not opened beyond the lines). Real orders are recorded as plans (`execution_plan_store.py`, `order_book_store.py`), a different shape. This is the one capability that already has a good door. The gap is only that two of the four callers bypass `place_checked` (monitor, settlement): correct for settlement, a spec question for stops (does a stop-out count as an adjustment?).

---

## Other doors I noticed (not in your list)

- **Duplicate-leg / held-contract check.** `paper.py:1279 _refuse_duplicate_legs` (ADR-319) runs only when ordering. The builder's strike step (`routes/leg_edit.py`, MOVES `:118`) has no held-contract check (grep of `leg_edit.py` for "duplicate"/"held" found only docstring uses of "held" about quotes). That is D-60's class: a rule enforced at one door, not at the other that reaches the same state. Proposed `check_legs_allowed(legs, underlying, held_contracts)` called by both. Size S, risk wrong figure/wrong order.
- **Hold-the-feed** is repeated in 5 mechanisms (capability 3).
- **"Expired?" cut-offs** are in DUPLICATES R1 (3 times); the exit door above needs one answer for "settle from" and "market open until".

## Not checked

`checked_basket` leg order; frontend builder Exit enable logic (D-05) beyond `canExit`; positions/home route assembly; backend tests of `tracking/exit`; whether the 15:30/15:39/15:45 gates in capability 4 agree; the defect list itself.
