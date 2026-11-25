# DUPLICATES: verified list

Date: 2026-11-23. Repo state: main at commit d387d4cd. Read-only pass; no code run.

How to read: "confirmed (read both)" means I opened every body named in that entry this pass. "unconfirmed (names only)" means I did not; where a reviewer read the bodies I say "reviewer read, not re-opened by me". Ranks: RISK (behaviour differs, or guards money, safety or who-can-see-what), COST (same job, identical or near-identical, only slows changes), HARMLESS (intended or not a duplicate).

## Reviewer claims I found wrong or too weak
1. Domain review D2 says every Decimal parser requires a finite value. `backend/ofo/instruments/parser.py:52-59` does not: it strips, rejects blank, calls `Decimal(raw)` and returns. `Decimal("NaN")` and `Decimal("Infinity")` parse. Whether a later check catches them was not found (only `catalogue.py:66` and `freeze_file.py:91` check finite, on other fields).
2. Frontend review D2 says four of five browser time copies use `en-IN`, `Asia/Kolkata`, "medium style". Only `lib/brokerAccount.js:21` uses medium; `pages/BrokerSettingsPage.vue:65`, `pages/SettingsPage.vue:54`, `components/adjustments/PreferencesTab.vue:48` use short. It also missed that `components/adjustments/SystemPlaybookAdmin.vue:58` calls `toLocaleString()` with no zone (browser time), the same fault it flagged only for `pages/OptionChainPage.vue:151`.
3. App review item 7 says the SQL rule and the cache rule are "same rule". They differ on a refused stored value (R4). Too weak, not false.
4. App review item 6 treats the strategy-ownership SQL as one repeated statement. `ofo_app/playbook_store.py:293` is not the same: it has no `deleted_at IS NULL` (R2).
5. App review item 4 says `execute_plan._money` has "no rounding, returns None". True, but it also has no finite check, so a `Decimal("NaN")` passes (R6).
6. Domain review D1 is right that the 15:30 / 15:39 gap may be deliberate. It is deliberate for settlement (R1). It could not see the third cut-off in the app layer (`paper_settlement.py`), which the cross-area pass found.

---

## RANK 1: RISK

### R1. "Is this contract expired?" has three different cut-offs. confirmed (read both)
- Where: `backend/ofo/reconciliation/settlement.py:58-63` `is_expired`; `backend/ofo/outcome/snapshot.py:143-145` `_expired`; `backend/ofo_app/paper_settlement.py:117-121` `last_due_day` (with `:220-231` `next_run`); date-only variants `backend/ofo/adjustment/approaches.py:649-652` `is_expiry_day` and `backend/ofo/execution/safety.py:545-550`.
- Same job: yes (all answer "is this expiry over yet").
- How they differ:
  - settlement: expiry date before IST today, or today and time >= `EXPIRY_DAY_SETTLE_FROM` = 15:39 (`ofo/timeutil.py:32`). Used by `reconciliation/compare.py:571` and `ofo_app/real_settlement.py:29`.
  - snapshot: expiry before `clock.date()`, or `combine(expiry, EXPIRY_CLOSE) <= clock`, EXPIRY_CLOSE = 15:30 (`timeutil.py:30`). It uses the raw clock date, not an IST conversion.
  - paper: today settles from a database setting `facts.paper_settle_from`, default 1545 (`ofo/settings/registry.json:665-674`), read in `paper_settlement.py:117`.
  - approaches and safety: date equality only, no time of day.
- Docstring or ADR for the different cut-off: yes for 15:39. `settlement.py:30-33` ("SENSEX options traded until 15:39 ... settling at 15:30 would close a leg that can still trade"), `ADR-083.md:21,26` (F-33, "15:39 candles leave the exact close time open"), `compare.py:566-569`, `real_settlement.py:8`. For 15:30 in snapshot, only its own docstring (`snapshot.py:144`: "after the close no contract is valued with time left"). No ADR line explains why valuation stops at 15:30 while settlement waits to 15:39, and nothing explains the 15:45 paper default beyond the registry note "NSE/BSE publish the index closing value after the 15:30 close" (`registry.json:674`). Searched the spec for "15:39" only.
- Harm: SENSEX expiry day, 15:35: the payoff screen values the leg as expired (no time value) while the contract still trades and reconciliation counts it live. At 15:41: reconciliation calls the real leg expired but the paper leg stays open until 15:45.
- Natural single home: `ofo/timeutil.py` for the three times, with one named rule per purpose in `ofo/reconciliation/settlement.py`.

### R2. Strategy ownership SQL repeated, one copy differs; two `lock_strategy`. confirmed (read both)
- Where (identical text `SELECT 1 FROM public.strategies WHERE id = :s AND user_ref = :u AND deleted_at IS NULL`): `execution_plan_store.py:152`, `strategy_alert_style_store.py:32`, `strategy_level_watch_store.py:26`, `strategy_pause_store.py:26`, `tracked_book.py:33`. Different: `playbook_store.py:293` has `WHERE id = :strategy_id AND user_ref = :user_ref` and no `deleted_at` test. Join form with the deleted test: `paper_book.py:22-29`. The stores' own wrappers: `order_book_store.py:113`, `playbook_store.py:674`, `strategy_pause_store.py:55`, `strategy_level_watch_store.py:55`, `strategy_alert_style_store.py:76`. Also `scenario_guard.py:34` (different purpose, not opened beyond the line).
- Same job: yes (is this strategy mine).
- Differ: the main read path hides a deleted strategy "exactly like a missing one" (`strategy_store.py:136-141`, REQ-070 AC-6). `playbook_store._owned` (called at `playbook_store.py:681,703,732,911,922,971`) lets a soft-deleted strategy pass for rule state, suggestions and held-crossing reads and writes.
- `lock_strategy` (c): `strategy_store.py:364-367` takes the row lock via `_locked`; `execution_plan_store.py:247-254` calls it and converts the error to `PlanStoreError`. Wrapper, not a copy (see H5). `order_book_store._locked` (`:106-110`) wraps the plan one again.
- Harm: a user deletes a strategy; its playbook suggestions and held entries can still be written for it, so a deleted strategy keeps showing in the adjustment inbox or background checks (not traced to a screen).
- Natural single home: `ofo_app/strategy_store.py` (it already owns the deleted-hidden reads).

### R3. Rupee text is written in at least six places, with two grouping styles. confirmed (read both)
- Where: `ofo/engine/display.py:31` `_group_indian`, `:77` `format_rupees`; `ofo/errors/slots.py:70-75` `_format_rupees`; `ofo/errors/gate_slots.py:152` `Rupees.format`, `:168` `DisplayRupees.format`, `:189` `WorstCase.format`; browser `frontend/src/lib/displayFormat.js:186` `groupMoney`, `:198` `groupedIndian`, `:202` `rupeesText`; `frontend/src/lib/tracking.js:115` `groupIndian`, `:122` `signedRupees`.
- Same job: yes (turn a rupee Decimal or text into user text).
- Differ:
  - `display.format_rupees`: Indian grouping, always 2 decimals, half-even, minus is U+2212 (`₹17,19,000.00`).
  - `errors/slots._format_rupees`: Python `{:,}` western grouping, whole rupees printed with no decimals (`₹1,719,000`).
  - `gate_slots.Rupees` and `WorstCase`: `f"₹{value:,}"`, western grouping, decimals as given.
  - `gate_slots.DisplayRupees` correctly calls `format_rupees` and swaps the minus to ASCII (`:164-168`).
  - Browser: `rupeesText` and `signedRupees` use `BigInt` text grouping; `groupMoney` uses a regex; `signedRupees` adds `+` and no rupee sign.
- Why split: `gate_slots.py:164` says the lazy import exists because `ofo.engine.display` imports `ofo.errors` (a loop), so the reviewer's guess is right.
- Harm: one refusal message can show margin needed as `₹296,332.80` (via `Rupees`) and a balance as `₹2,96,332.80` (via `DisplayRupees`) side by side.
- Natural single home: `ofo/engine/display.py` for the server, `frontend/src/lib/displayFormat.js` for the browser.

### R4. "Setting value in force" has a SQL copy and a memory copy that treat a bad row differently. confirmed (read both)
- Where: `ofo_app/settings_store.py:82-103` `rows_in_force`; `ofo_app/settings_cache.py:113-129` `resolve`. Documented as deliberate (app review: `settings_cache.py` docstring, #636 r4).
- Same job: yes (newest row not after `at`, else default).
- Differ: if the row in force is refused by the registry, `rows_in_force` raises `SettingsError` (`:99-101`, fail closed); `resolve` falls back to the registry default and only calls `refused(...)` (`:124-127`). The SQL text `_IN_FORCE` was not opened.
- Harm: an admin stores a max-lots value the registry refuses; the API read raises, while the background worker keeps checking strategies with the default limit.
- Natural single home: one rule in `ofo/settings/` (the domain already owns `layers.py`), with the two readers only fetching rows.

### R5. Intrinsic value at expiry is computed in the app layer as well as the engine. confirmed (read both)
- Where: `ofo/engine/legs.py:105-111` `_long_value_at`; `ofo_app/paper_settlement.py:124-130` `settle_price`.
- Same job: yes. Bodies are the same maths: CE `max(market-strike, 0)`, PE `max(strike-market, 0)`, future = level.
- Differ: none in maths; the engine copy works on a `Leg`, the app copy on `(instrument, strike, close)`.
- Harm: project rule says one engine owns every P&L number (ADR-008). A change to expiry maths (for example a settlement rule for futures) would change the screens and not paper settlement, so a paper strategy settles at a different value from the one the payoff screen showed.
- Natural single home: `ofo/engine/legs.py` (expose a public function that takes instrument, strike and level).

### R6. Kite money figures are read by three parsers with different rules. confirmed (read both)
- Where: `ofo_app/kite_replies.py:69-92` `kite_money`; `ofo_app/kite_margin.py:145-154` `_money`; `ofo_app/execute_plan.py:102-105` `_money`. (`kite_period_reads.py:75` `vix_values` has its own local check, not opened.)
- Same job: yes (Kite number to exact Decimal).
- Differ:
  - `kite_money`: accepts int, Decimal, a float (via `Decimal(str(value))`) and a decimal string; refuses bool; rounds half-up to paisa unless `exact=True`.
  - `kite_margin._money`: exact types Decimal or int only; refuses NaN and infinity; rounds half-up; raises `KiteMarginError`.
  - `execute_plan._money`: any Decimal or int (subclasses allowed), no finite check, no rounding, returns None on anything else.
- Harm: a margin figure is rounded to the paisa on one path and a depth price is not; a `NaN` quote price passes `execute_plan._money` and reaches the pre-execution gate.
- Natural single home: `ofo_app/kite_replies.py` `kite_money`.

### R7. Strict Decimal parsing exists six times in the domain, with different strictness. confirmed (read both)
- Where: `ofo/strategy/stored_form.py:361-370` `_decimal_from`; `ofo/settings/__init__.py:72-81` `_dec`; `ofo/adjustment/playbook_eval.py:1285-1293` `_decimal_text`; `ofo/instruments/parser.py:52-59` `_parse_decimal`; `ofo/adjustment/detection.py:53-56` `_decimal`; `ofo/engine/executable_price.py:26-33` `_decimal`.
- Same job: yes (check an input is a safe Decimal), except `detection` and `executable_price` which take an existing Decimal.
- Differ: `stored_form`: string only, refuses float, finite, and `str(number) == value` (exact text). `settings._dec`: string only, finite, no exact-text test. `playbook_eval`: string, finite, `>= 0`, returns None on failure. `parser`: strips, rejects blank, no finite test (NaN parses). `detection`: Decimal only, finite. `executable_price`: Decimal or int (not bool), finite for Decimal only, comment says Zerodha prints whole prices as ints.
- Error types differ (`StoredFormError`, `RegistryError`, `ValueError`, None).
- Harm: a tick size or strike `NaN` in the instrument CSV passes the parser (`parser.py:142-143`), where the strategy stored form would have refused it.
- Natural single home: `ofo/strategy/stored_form.py` `decimal_from_text` for text; or one helper beside `ofo/money.py`.

### R8. Six places read the owner's stored Kite token and each wires it by hand. confirmed (read both)
- Where: `history_finalize.py:49-72`, `kite_history.py:162-192`, `paper_settlement.py:285-318`, `live_market.py:153-160`, `feed_main.py:380-398`, `background.py:539-599`.
- Same job: yes. All six end in `broker_token_store.access_token_for` (`:91`) or `access_session_for` (`:100`), which is the only decrypting code, so the secret handling is not copied; the wiring is.
- Differ:
  - `history_finalize`: no catch for `BrokerStoreError` or `BrokerConfigError`; makes its own engine and disposes it.
  - `live_market`: no catch at all; uses the shared `get_engine()`.
  - `kite_history`: catches both, logs the code only, returns None.
  - `paper_settlement`: catches both, returns a reader that answers None.
  - `feed_main`: uses `access_session_for` (token plus expiry from one row), connection per read.
  - `background`: config error means "no login"; the reload swallows any `Exception` by class name.
- `call_with_token` (`broker_token_store.py:168`), which ends the session when Kite says TokenException, has no caller under `backend/` (Grep). `tests_app` not searched.
- Harm: if the broker settings are missing, the nightly history finalize and the live market start crash with a raw error while the settlement job says "no session" and carries on.
- Natural single home: `ofo_app/broker_token_store.py`.

### R9. Kite HTTP is called through two urllib paths, one httpx path, with copied headers and error parsing. confirmed (read both) for the urllib pair, headers, and error_type; the httpx client was not compared
- Where: `ofo_app/kite_margin.py:126-142` `urllib_transport` and `:244-255` `kite_headers`, `error_type`; `ofo_app/kite_history.py:38-50` `urllib_transport` and `:60` inline headers; `ofo_app/kite_client.py:55-60` `_error_type`, `:76-77` version header; `ofo_app/kite_http.py:213,283` `KiteClient`/`KiteAsyncClient` (not opened).
- Same job: yes (send one Kite request through the allow-list door, turn failures into codes).
- Differ: margin returns error bodies on HTTPError and turns door refusal into `KiteMarginError("kite_margin_refused")`; history returns `""` as the body on HTTPError, so it can only see the status, and raises `CandleFetchError` on body or transport faults. History's 403 does not tell "token dead" from other 403s; margin does (`kite_margin.py:197`: 403 or `TokenException`). `error_type` takes text in one and a response object in the other, same dict lookup.
- Rule broken: project rule "reuse the shared Kite helpers instead of writing a fourth copy" (`.claude/rules/project/fastapi-sqlalchemy.md`).
- Harm: a Kite token that dies during the after-close history run is reported as a plain fetch error; the same death during a margin read is reported as a token problem.
- Natural single home: `ofo_app/kite_http.py` for the call and headers; one `error_type` beside it.

### R10. Browser time is formatted by hand in six places; two use the browser's own time zone. confirmed (read both)
- Where: `frontend/src/lib/displayFormat.js:128` `istTime` (the home; `:101` builds an IST formatter); by hand with `en-IN` and `Asia/Kolkata`: `lib/brokerAccount.js:21`, `pages/BrokerSettingsPage.vue:65`, `pages/SettingsPage.vue:54`, `components/adjustments/PreferencesTab.vue:48`; browser zone: `components/adjustments/SystemPlaybookAdmin.vue:58` (`toLocaleString()`), `pages/OptionChainPage.vue:151` (`toLocaleTimeString()`); also `composables/useChainLive.js:145` `daysLeft` uses `toLocaleDateString('en-CA')` on the browser date.
- Same job: yes (show a server instant to the user).
- Differ: zone (IST vs browser), style (short vs medium), suffix " IST" added by hand in four.
- Harm: a user opening the option chain from another time zone sees "as of" in local time while the exchange runs on IST; `daysLeft` is a day off around midnight there.
- Natural single home: `frontend/src/lib/displayFormat.js`.

### R11. "Database now / database today" in four places. unconfirmed (names only)
- Where: `ofo_app/catalogue_picker.py:40` `database_now`, `:117` `database_today`; `ofo_app/settings_store.py:78-79` `database_now` (one line, opened: `session.execute(_NOW)`); `ofo_app/execute_replay.py:231` `database_clock_today`.
- Reviewer read the bodies and says the first two run the same query; `database_today` honours the test pin. I did not open `catalogue_picker.py:40` or `:117`.
- Harm if they differ: an expiry list judged on a different "today" than a settings read.
- Natural single home: `ofo_app/catalogue_picker.py` or `ofo_app/sql_time.py` (not decided).

### R12. "To IST" conversions are repeated, and only one checks for naive input. unconfirmed (names only)
- Where: `ofo/adjustment/alert_gate.py:176` `_ist` (reviewer: checks aware first); `ofo/marketdata/kite_provider.py:43`; inline `.astimezone(IST)` in `ofo/adjustment/monitor_pause.py:42`, `ofo/broker/session.py:83`, `ofo/reconciliation/settlement.py:61`, `ofo/execution/safety.py:545` (opened: no naive check; Python's `astimezone` reads a naive datetime as the server's local time); and more than 40 places in `ofo_app` (Grep stopped at its 40-line limit).
- Natural single home: `ofo/timeutil.py`.

---

## RANK 2: COST (same job, no behaviour difference found; reviewer read bodies, not re-opened by me unless noted). All unconfirmed (names only) by my standard.

| # | What | Where | Note |
|---|---|---|---|
| C1 | `_is_int` (int but not bool), one-line identical body | `ofo/strategy/definition.py:88`, `model.py:54`, `modification.py:71`, `stored_form.py:145` | home: `ofo/strategy/stored_form.py` or a small shared module |
| C2 | month names table and "DD Mon YYYY" text | `ofo/strategy/definition.py:97`, `ofo/errors/slots.py:37`, `ofo/errors/gate_slots.py:34-35` | home: `ofo/strategy/definition.py` |
| C3 | `_rounded(g: Greeks)` | `ofo/outcome/target.py:222`, `ofo/tracking/paper_greeks.py:47` | home: `ofo/table/model.py` `round_greek` |
| C4 | float to 2dp Decimal | `ofo/marketdata/forward.py:76` `_q2`, `ofo/engine/black_scholes.py:126` `_to_decimal` | home: `ofo/engine/black_scholes.py` |
| C5 | Saturday constant 5 | `ofo/timeutil.py:37`, `ofo/market_calendar.py:24`, `ofo/adjustment/playbook_eval.py:1466`, used `ofo_app/catalogue_picker.py:58` | breaks the "import it" rule in `python-domain.md`; home: `ofo/timeutil.py` |
| C6 | dash-with-reason cell | `ofo/adjustment/compare.py:182`, `compare_cost_rows.py:44`, `ofo/table/model.py:181` | home: `ofo/adjustment/compare_cost_rows.py` |
| C7 | refuse a test-only switch outside test | `ofo_app/pinned_clock.py:38`, `replay_mode.py:42`, `execute_replay_switch.py:21`, `scenario_mode.py:224` | home: `ofo_app/config.py` |
| C8 | start/stop/sleep loop for background tasks | `paper_settlement.py:254`, `real_settlement.py:120`, `catalogue_refresh.py:110`, `worker_watch.py:126`, `paper_monitor.py:267` | no shared scheduler found |
| C9 | charges-paid wrappers | `routes/paper.py:731`, `routes/adjustment_history.py:142`, `adjustment_check.py:861` (all under `ofo_app/`) | reviewer read all three: wrappers, not arithmetic |
| C10 | two `OrderRow` protocols | `ofo_app/execution_return.py:62`, `reconcile_attribution.py:121` | names only |
| C11 | same endpoint read by several screens | GET `/strategies` x5 (listed in CODE-MAP B); `/catalogue/{u}/expiries` x4 (`pages/CreateStrategyPage.vue:109`, `OptionChainPage.vue:65`, `components/strategy/LegPicker.vue:109`, `ReadyMadePanel.vue:45`); `/broker/status` x3; `/settings` x3 | I confirmed the call lines by Grep, not the reply parsing; home: `frontend/src/services/api.js` plus one helper per endpoint in `lib/` |
| C12 | test fakes: Kite client x4-5 (`tests_app/test_kite_login.py:69`, `test_kite_ws_resubscribe.py:31`, `test_periodic_positions_read.py:55`, `test_rate_limit_door.py:38`, `test_kite_margin_client.py:37`); `FakeBroker` x2; `FakeProvider` x4; `FakeChannel` x3; `FakeRedis` x2; `FakeMargin` x3; chain builders x6; `FakeConn` x2 | see scripts review section 3 | home: one fakes module per area under `tests_app/` |
| C13 | golden iron condor defined three times | `tests/engine/conftest.py`, `tests/scenario/scenario_fixtures.py`, `tests/table/conftest.py` (latter "kept in sync by hand") | test drift risk, no product effect |
| C14 | reply inventory twin | `scripts/reply_inventory.py`, `tests_app/reply_inventory.py` | not diffed |
| C15 | dead second toast | `frontend/src/components/common/Toast.vue` (no importer) vs `components/layout/ToastHost.vue` + `composables/useToast.js` | delete, do not merge |
| C16 | five thin wrappers to reach an agent's worktree | `scripts/orchestrator/agit.py`, `aregen.py`, `agentwt.py`, `atool.py`, `ev_agent.py` | exist because a shell guard blocks the kit folder name |
| C17 | record read-only Kite replies | `docs/research/kite-proof-2026-10-07/kite_rest_capture.py`, `order_shape_capture.py`, `docs/research/live-proofs-2026-10-16/afternoon/rec_rest.py`, `scripts/live/probe.py` | probe.py is the kept one |
| C18 | two "settings" screens | `frontend/src/pages/SettingsPage.vue`, `components/adjustments/PreferencesTab.vue` + `lib/settingsGroups.js` | overlap unverified; different audiences (admin vs user) |

## RANK 3: HARMLESS or intended

| # | What | Why harmless |
|---|---|---|
| H1 | `ofo/engine/orderbook.py` and `ofo/tracking/orderbook.py` | 19-line re-export, not a copy (domain review; not opened by me) |
| H2 | `db_run.py`, `db_run_fresh.py`, `dev_run.py` | Three on purpose: shared test DB, throwaway DB, dev DB (docstrings read by reviewer) |
| H3 | `tools/ci_local.py`, `scripts/orchestrator/prepush.py`, `atool.py`, `merge_preflight.py` | Layered: prepush imports ci_local and adds three checks |
| H4 | `tools/merge_when_green.py`, `scripts/orchestrator/merge.py`, `land.py` | Layered wrappers; `merge.py:25` calls the kit gate |
| H5 | `ofo_app/execution_plan_store.py:247` `lock_strategy` over `strategy_store.py:364` | I opened both: the first calls the second and renames the error. Intended wrapper. Belongs to the R2 fix, not a second lock |
| H6 | `ErrorMessage.vue` vs `LoadFailed.vue` | Different purposes (four-part error vs retry panel), by headers |
| H7 | `docs/research/kite-proof-2026-10-07/kite_core_proof.py` vs `ofo/broker/kite_auth.py`, `ofo_app/kite_client.py` | Ancestor of product code, cited in comments (`kite_auth.py:10`, `kite_client.py:5`); keep as history |
| H8 | `tests/adjust_scenarios_gen.py` -> `tests/fixtures/adjust_scenarios` -> `scripts/build_system_playbooks.py` -> `backend/ofo/adjustment/system_playbooks.json` | Generated chain with `--check`; needs regeneration, not merging |
| H9 | `LegList.vue` vs `StrategyTable.vue`/`StrategyLegRow.vue`; `PayoffChart`, `AdjustPayoffChart`, `StrategyPriceChart` | Different jobs on the same data (frontend review; chart setups not diffed, so partly unverified) |
| H10 | Old live-proof scripts under `docs/research/live-proofs-2026-10-16/` that touch what `kite_margin.py` now does | Throwaway proofs, not imported anywhere |
| H11 | Greek rounding `ofo/table/model.py:317` vs `ofo/engine/black_scholes.py:41` | Domain review marked low and not verified |

---

## Counts
- Total groups: 41 (RISK 12, COST 18, HARMLESS 11).
- Confirmed (read both): 10, all RISK (R1 to R10), plus H5 which I also opened. Counting H5: 11 confirmed.
- Unconfirmed (names only): 30. By rank: RISK 2 (R11, R12), COST 18 (reviewer read the bodies for most; I did not re-open them), HARMLESS 10.
- Per rank: RISK 10 confirmed / 2 unconfirmed; COST 0 confirmed / 18 unconfirmed; HARMLESS 1 confirmed / 10 unconfirmed.
- Budget note: about 52 of 70 tool calls used. Not opened though listed: `kite_http.py` httpx client, `catalogue_picker.py:40,117`, `kite_period_reads.py:75`, SQL `_IN_FORCE`, `scenario_guard.py`.
