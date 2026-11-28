STATUS 00:25 | all held tasks done: stage 1 pushed (f9b2a0f), stages 2 and 3 pushed (09efab8df), wave 1 merged, migration renumbered 0065_position_tags, position_kind on every paper-list row, 590 block proof; final check running on this head | next push: this one, then closed | blocker: none

# Lane R1: real positions get the same screens, backend (round 3)

Spec basis: ADR-330 (73) (the decision this lane implements; (64) withdrawn), (58); ADR-281; ADR-016 to ADR-019; ADR-292 (4), (5); ADR-003; ADR-008; ADR-002.
Base: origin/integration/weekend-r3-1129 (a1d70422, wave 0; alembic head was 0062_order_request_keys_expiry). Branch: feat/real-same-screens-be-1128. Status ceiling: Fixed, not tested (on the owner's PC).

## The field contract (frozen 28 Nov 19:25 IST; Lane R2 codes against it; two clarifications 21:55)
Every body that carries a strategy's order, trigger or alert (the order door's answer, the trigger list and its answers, the
active alerts, the strategy list rows) carries, with these exact names:

| Field | Type | Meaning |
|---|---|---|
| `position_kind` | `"paper"` \| `"real"` \| `"unknown"` \| `"none"` | the STORED tag (`strategy_position_tags`); `none` = no order yet; `unknown` = no tag and an order, or unreadable (fail closed) |
| `position_kind_text` | string \| null | the one sentence of the row (catalogue `position_kind_real` / `position_kind_unknown`); null for paper and none |
| `stored_not_sent` | `true` \| `null` | `true` ONLY when the answer is about a REAL position (the action was stored in the app; nothing was sent to Zerodha). Paper bodies carry `null` (clarification: null, not absent) |
| `record` | object \| `null` | `{"action": "open"\|"add"\|"exit"\|"stop"\|"stop_fired", "stored_at": ISO-8601 with offset, "price": Decimal text, "text": the record's one catalogue line}` (clarification: `text` added, e.g. "Exit stored 10:05 at 39.15. Not sent to Zerodha. Place it in Kite."). Null for paper and when none is stored |

Where: the order door's answer (`POST /paper/strategies/{id}/orders`, top level), `GET/POST .../triggers` and
`GET /real/strategies/{id}/triggers` (top level, and per row `stored_not_sent` and `record` of that stop), `GET /api/alerts/active`
(per alert: the position's newest record; a reached stop reads `stop_fired`), `GET /strategies` (per row).
Rules for the frontend: show `record.text` as the one line under the row; never show a P&L "as if filled" from `record.price`; a real
row's quantity and P&L stay the Zerodha figure; a real position's armed stop now reads `state: "armed"` (`not_applicable_text` stays in
the shape, null for real; it is set only when the kind is `unknown`). The order door answers a real exit with HTTP 201 and the book of the
paper orders that exist (none for a sent basket: every figure of the app's own is absent, `state: "PAUSED"`, `status_word: "Running"`).

## How the page knows a real exit was STORED (answer to Lane R2, 28 Nov 23:05)
- The reply to an order post for a real position is ALWAYS definite: HTTP 201 with `stored_not_sent: true` and `record` (action, stored_at, price, text) = stored; or a refusal with its catalogue sentence and nothing stored (409/422 for a rule, 503 for the unknown-kind block or an unreadable check). The page never infers "the exit happened" from legs: for a real position no leg changes (the broker is the authority); the signal is `record` (and `stored_not_sent`) in the reply.
- Unknown outcome (the reply was lost, a timeout, a 5xx): the page resolves it in either of two ways, both safe. (1) Send the SAME request again with the SAME `client_request_id`: the server answers the first result (the same `record`) and stores nothing a second time (one record per user, key and action). (2) Re-read the row: `GET /paper/strategies` (each row), `GET /strategies` (each row) and `GET /api/alerts/active` carry the position's newest `record`; `GET .../triggers` carries the stop records; no `record` newer than the press = nothing was stored. The existing unknown-outcome block (code 590, Lane B2) applies to a real position's record the same way.
- `GET /paper/strategies`: every row now carries `position_kind` ("paper" | "real" | "unknown"; never missing; a failed kind read reads "unknown" for every row, never a 5xx), `position_kind_text`, `stored_not_sent` and `record`.

## For the owner lane
1. `routes/tracking.py` `POST /strategies/{id}/tracking/exit` still refuses a real position (409, "This is a real position, so no paper order is placed for it."): its answer (`TrackingOut`) is built from a paper book a real position does not have. The Exit on a row goes through `POST /paper/strategies/{id}/orders` (frontend `addToPaper`), which stores the record. If the tracking route is still linked for a real row, Lane R2 should call the orders route.
2. Rows for `docs/process/friction-log.md` (outside this lane's files), for the coordinator to add: (a) the cloud test database is shared by the gate and by a developer's own runs: two test files in one pytest run, or a run beside a gate, pollute it ("Catalogue update refused: would drop 750 of 750 ... contracts") and cost two 20-minute reruns; the fix is `bash scripts/orchestrator/cloud_services.sh --reset` and ONE file per run (or per-file database copies for the developer loop); (b) a lane's message to the coordinator is refused until the owner approves the session's device trust, which the lane cannot ask for: the first push is then the only report; (c) `tests_app/reply_inventory.py` needs a reviewer note per new string owner, written by hand.
3. Two tests fail on the build head itself, independent of this lane: `tests_app/test_exit_door.py::test_monitor_and_tracking_exit_at_once_one_wins_no_deadlock[before_claim]` and `[before_place]` (their fixture runs `ALTER TABLE public.paper_alerts DISABLE TRIGGER USER`; the table no longer exists). Not touched.
4. Lane B2's `execution_plan_store` could write the tag at Execute (`strategy_store.claim_tag(conn, strategy_id)` in the plan's transaction) instead of waiting for the first read. Optional.
5. A held position's add and open (ADR-292 (4)) still go to `paper_orders` (Q3 interim); `paper_store.place` still refuses an exit on a held position (the order door sends the exit to a record before it gets there).

## Decided for the owner
1. The tag is stored in a NEW insert-only table `strategy_position_tags` (strategy_id PK, tag paper|real), not a column on `strategies`: the strategies guard trigger is pinned in the app-role allow-list (a column would mean rewriting that pinned chain). Same meaning as the brief's `strategies.position_tag`: written once, never updated (guard OF065 refuses UPDATE and DELETE, even for the owner role). Migration `0065_position_tags` (after the build's 0064_order_attempts; first written as 0063, renumbered after wave 1; up, down by one, up checked).
2. No trigger writes the tag: the allow-list refuses an unexpected trigger on paper_orders, execution_plans and strategy_held_entries (found by running the migration). The code writes it once, first write wins: `paper_store.place` (under the strategy lock, at the first paper order -> paper) and `strategy_store.claim_tag` for a basket sent by Execute (stored on the first read of its kind -> real). Between an Execute and the first read the tag is absent; an order with no tag reads `unknown` only if the claim itself fails, otherwise the read stores `real` first.
3. A held entry (ADR-292) stays real whatever is stored: its basket is stored first (tag paper, same transaction), the held row after it. `kind_of` reads: held -> real; else the stored tag. The stored row is untouched (guard test pins it).
4. n7 (`test_exit_door_real_fd3`): the kind is read ONCE, BEFORE the commit (the door's check); that read decides and the answer after the commit reuses it. Pinned as `calls == 1` (was `>= 2`, the old FD5 expectation).
5. Backfill: held -> real; else a paper order -> paper; else an execution plan -> real; no order -> no row.
6. One record per action per request: a basket of "exit A + add A'" stores two records (unique on user, request key, action), so a repeated press stores one of each. Several legs of one action are one record with a list of legs; `record.price` is the first leg's.
7. Checks a real action runs (the same door as paper): market closed (60) refuses before anything is stored; the size of every order and leg total over an EMPTY book (the broker's quantity is not in this app, so a leg total is checked on the stored basket alone: looser than paper); the request key (the same `"paper"` door key, it is the same route; `request_key.py` is not edited); the unknown-kind block (503, nothing stored). Not run for a real position: the adjustment limit and the paper-order reducing check (both read a paper book), stop cancelling and suggestion linking.
8. A real position's open legs, for a stop and for the worker's fire, are its own recorded paper legs when it has any (a held position), else the stored plan's legs "as last read" (Q4 interim). A stop on a leg the plan does not have is refused (`paper_trigger_leg_not_open`); an index exit records every leg.
9. A reached stop: `claim_fire` (once per trigger) -> one `stop_fired` record -> one alert (informational History row, the same alert module) -> no paper order, no broker call. A leg without a live price stays armed (the paper rule). Other armed stops of the strategy stay armed after one fires (Q2 interim).
10. A held position's exit is a record; a basket that MIXES an exit with add/open on a held position is refused 409 (`user_input_request_not_available`, no new sentence: one basket, one place).
11. Stages 2 and 3 are pushed together (one push): they share the route, the worker and the catalogue, and the core proof needs both.

## Question for the owner
Q1 (interim built: NO). Does a stored exit close the app's view? Interim: the row stays open and shows the record line until Zerodha shows zero quantity; status stays "Running". Recommendation: the same; the broker is the authority.
Q2 (interim built as the note says: a fired stop is claimed once and stops; a stored manual exit cancels the armed stops it covers: every leg exited cancels every armed stop of the strategy, a partial exit cancels the leg stops of the exited contracts; a fired stop does not cancel the strategy's other stops). After a stored exit or a fired stop, should the watcher keep alerting? Recommendation: one reminder alert 15 minutes later if Zerodha still shows the quantity ("Exit stored at 10:05; Zerodha still shows this position open").
Q3 (interim: leave as is). A held condor's add and open stay paper orders that change the shown book; only its exit goes to records. Recommendation: move held add and open to records too, so a held position's book never changes by anything the user stores.
Q4 (interim: the plan's legs "as last read", or a held position's recorded paper legs). Where does the worker read a real position's open legs? Recommendation: the Zerodha snapshot read already used by `routes/positions.py`; confirm it is reachable from the worker's separate process, then replace `PaperMonitor._closing_legs`.

## New wording for the owner to read (all pending owner read; pinned in tests/errors/template_pins.json)
- `position_kind_real` (replaces "Real position: exit and protect it in Kite. ..."): "Real position. Zerodha shows its quantity and P&L. Exits and stops you store here are not sent. Place them in Kite."
- `monitoring_why_exit_not_applicable` (replaces "Not being watched: this is a real position, ..."; the worker no longer emits it): "Watching this real position. An alert only; nothing is sent."
- Gates `real_position_exit_refused` / `_open_refused` / `_add_refused` (the paper store's structural refusal; the tracking exit route): "This is a real position, so no paper order is placed for it." / "Your exit, add or stop for a real position is stored from its row; nothing is sent to Zerodha." / "Placing a paper order on a real position." / "Use the row's Exit or Stops, then place it in Kite."
- `real_exit_dialog`: "This stores your exit in the app as a record and a reminder. It does not place an order and does not change your Zerodha position. Place it in Kite."
- `real_exit_stored`: "Exit stored. Not sent to Zerodha. Place it in Kite. This position stays open here until Zerodha shows it closed."
- `real_stop_stored`: "Stop stored for this real position. When it is reached you get an alert. Nothing is sent to Zerodha. Place the exit in Kite."
- `real_add_stored`: "Add stored. Not sent to Zerodha. Place it in Kite."
- `real_record_exit` / `_add` / `_open`: "Exit|Add|Open stored {HH:MM} at {price}. Not sent to Zerodha. Place it in Kite."
- `real_record_stop`: "Stop stored {HH:MM} at {price}. When it is reached you get an alert. Nothing is sent to Zerodha. Place the exit in Kite."
- `real_record_stop_fired`: "Stop reached {HH:MM} at {price}. Stored as an exit record. Not sent to Zerodha. Place it in Kite."
- Alert body of a reached real stop (`real_alert_body_one` / `_one_named` / `real_alert_body`): "{what}; exit stored at {price}. Not sent to Zerodha. Place it in Kite." (and the one-leg-named and several-legs shapes).

## New test files
- tests_app/test_position_tag_r1_1128.py (24): the tag never flips for every order kind and every record action; claim rules; migration round trip and downgrade refusal; insert-only guards; no broker column.
- tests_app/test_real_records_r1_1128.py (12): exit, add, open and stop on a real position stored as records, no paper order; a repeated press with one request key stores one; market closed refuses; unreadable kind 503; held exit is a record and held add stays paper; paper unchanged; no reader names the record table (the structural guard "no reader counts a record").
- tests_app/test_real_stop_fired_r1_1128.py (4): CORE PROOF (design note section 6, a to g): a reached real stop gives one alert with the sentence, one `stop_fired` record, zero paper orders, tag real, kind unchanged, paper book empty and list row `has_paper_order` false, the egress seam saw no call; claimed once; below its level nothing; an unreadable kind leaves it armed.
- Rewritten (the old rule pinned a refusal): test_exit_door_real_fd3 (r6, n1 order post, n7 one read, the sentence), test_fields_r2_fd2 (877 exit, stop, real read, keep, unknown 503, list shape), test_held_entry (held exit is a record), test_held_stop_ra_1128 (f1 fires as a record, t1 patches `_kind_in_fire`), test_na_closed_fe4_1128 (a real position reads what paper reads), test_r6_r7_fe3_1128 (r6), test_review_fe3_1128 (f4, f5), test_real_position_stops_fe2_1128, test_plan_watch (r6: a held position reads live lines), test_alert_routes (field set), test_position_kind_adr330_64 (kind_of takes the tag), tests_app/reply_inventory.py (regenerated; three reviewer notes written), tests/errors/template_pins.json (17 re-pinned or new, all "pending owner read").

## Found, not assigned (28 Nov, owner's order of 23:35: recorded, not fixed, not handed on)
Evidence is the Opus review (read-only, no database) and the gate runs; each item names its file.
1. `backend/ofo_app/paper_limit.py` `record_checked` (F2): an exit, add or open of a real position is not checked against the plan (contract not in the plan, a side that does not close, a quantity above the plan's). Run: exit on contract 999999, SELL, 7500 units, stored. Nothing is sent; the record could mislead a later screen.
2. `backend/ofo_app/real_action_store.py` `StoredRecord.price` and `routes/paper.py` `_record_stop` (F3): `record.price` is the first leg's price (a 4-leg exit reads as one price); an index-exit stop stores the index level as every leg's price.
3. `backend/ofo_app/routes/paper.py` `_answer` call in `place_paper_orders` (F4): a first basket carrying a `held` block commits a real position but the answer says `position_kind: "paper"`.
4. `backend/ofo_app/paper_monitor.py` `_fire_real` / `_closing_legs` (F7): the legs are read without the strategy row lock (a held add committed between the read and the claim is missing from the `stop_fired` record).
5. `backend/ofo_app/routes/paper.py` `_no_paper_book` (F8): a sent basket answers `booked: 0` and `state: "PAUSED"` while its stops are watched.
6. `backend/ofo_app/routes/paper.py` (F9): an unknown kind answers 503 "busy" (reads as try again) though a missing tag is structural.
7. `routes/strategies.py`, `routes/alerts.py` (F10): after a stop is cancelled its `stop` record stays the newest; "Keep" re-arms a real stop without a new `stop` record.
8. `backend/ofo_app/strategy_store.py` `claim_tag` (F11, not a regression): if Execute inserts its plan without the strategy row lock, a first paper order at the same moment can claim `paper` for a sent basket (closed by writing the tag in Execute's own transaction: "For the owner lane" 4).
9. `tests_app/test_exit_door.py::test_monitor_and_tracking_exit_at_once_one_wins_no_deadlock[before_claim]` and `[before_place]` fail on the build head (their fixture runs `ALTER TABLE public.paper_alerts DISABLE TRIGGER USER`; the table no longer exists). Coordinator: Lane T.

## Not done
- Contract fields on `GET /paper/strategies/{id}` (the book) and `GET /strategies/{id}/tracking` for a real position: those answer as before; only the order door, the stops answers, the active alerts and the strategy list carry the fields.
- `routes/tracking.py` for a real position (see "For the owner lane" 1).
- The Opus review ran once for stages 2 and 3 together (see Reviews); a second round was not needed (no open money finding).
- The browser walk (Lane R2's screens).

## Reviews
Opus review of stages 2 and 3 (reviewer subagent, read-only, no database): PASS on the money invariants: no path from a real action or a reached stop to `paper_store.place`, a `paper_orders` insert, a broker or the network; no reader counts a record as a fill; the tag cannot flip; a repeated press stores one record; Decimal round trips exact. Findings and what was done:
- F1 (MAJOR, could cost money through the user's own Kite order): a stop stayed armed after the exit that covered it and raised a later "place it in Kite" alert. FIXED before the push: a stored exit cancels the stops it covers (`routes/paper._cancel_covered_stops`; tests `test_a_partial_exit_cancels_only_the_leg_stop...`, `test_an_exit_of_every_leg_cancels_every_armed_stop...`, `test_an_add_cancels_no_stop`). Found on the way: the order door's orphan-stop sweep (`_armed_leg_stops`) ran before the records branch and would have cancelled every stop of a real position on ANY next order; the records branch now runs first.
- F5 (defence in depth) FIXED: `real_action_store.record` refuses a leg with a quantity that is not a whole positive number or a side other than BUY/SELL.
- F6 FIXED: the plan read in `PaperMonitor._real_legs` runs in a savepoint (a database error no longer aborts the shared reload).
- FOUND, NOT ASSIGNED (cannot cost money today, nothing is sent; none started; see "Found, not assigned" below): F2 `record_checked` does not check the exit/add legs against the plan (contract not in the plan, side that does not close, quantity above the plan's; looser than paper, and the plan is "as last read"); F3 `record.price` is the first leg's price (a 4-leg exit shows one price; an index-exit stop stores the index level as every leg's price); F4 a first basket with a `held` block answers `position_kind: "paper"` though the position becomes real; F7 `_fire_real` reads the legs without the strategy row lock (a held add committed between the read and the claim is missing from the `stop_fired` record); F8 `_no_paper_book` answers `booked: 0` and `state: "PAUSED"` for a sent basket whose stops are watched; F9 an unknown kind answers 503 "busy" (reads as try again); F10 after a stop is cancelled its `stop` record stays the newest line ("When it is reached you get an alert."), and "Keep" re-arms a real stop without a new `stop` record; F11 (not a regression) if Execute inserts its plan without the strategy row lock, a first paper order running at the same moment can claim `paper` for a sent basket: item "For the owner lane" 4 (write the tag at Execute) closes it.
- Q4 stale legs (the plan, not Zerodha): a leg the user closed in Kite is still listed in an index-exit alert. The owner's question Q4 above.

| task / model / minutes |
|---|
| lane build, tests, reruns / Sonnet / about 160 |

SAFE TO CLOSE (head: the head of feat/real-same-screens-be-1128 that carries this line; check TOTAL PASS on it before the coordinator takes it). Done: the stored tag, the record store and its door (open, add, exit, stop), the worker's real branch, the catalogue sentences, the contract fields (order door, triggers, active alerts, strategy list, paper list), the migration 0065, the core proof and the guards. Not done: the items under "Found, not assigned" and "Not done" above, the answers to Q1 to Q4 (the owner's), the browser walk (Lane R2's).
