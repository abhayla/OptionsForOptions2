# GC-ICSAFE run log

Contract: `goal-contract-GC-ICSAFE-2026-11-10.md`. Status rows c01..c57 on the project status page. Times are IST,
read from the clock.

## 2026-11-10 (Tue, NSE holiday; started 20:39, not the planned trading-day morning)

- c01 20:40: rows c01..c57, o01..o08, n01..n09 exist. No row's done line held on main 5a8f5683. Rows already true:
  none. Today is a holiday (`market_calendar.json`), so c07..c11 and c40 move to the next trading day (Wed 11 Nov).
- c02 20:41: work folder `OptionsForOptions2-gc-icsafe`, branch `build/gc-icsafe`, contract committed d9735310.
- c03 20:41: PR #690 merged (main fec23bbe).
- c04 20:42: 853dffe2 and 724fbe7e merged by sha (the toast commit in both is one patch, equal patch-id).
- c05 20:42: three loose main-checkout files byte-identical on the branch (2f4c112d), then restored on main; the
  stray `.claude/g2.log` (a "no tests ran" message) read and removed.
- c12 20:47 CORE PROOF, run early because today's login (10 Nov 09:39) is valid until 06:00 on 11 Nov and a margin read
  needs no open market: a process with no live-market object (`live_market.current_session()` is None, as in the
  worker) read the owner's stored session through `feed_main.store_readers` and made one funds read with
  `KiteMargin.fetch_available_funds`. Output: "worker session OK ... margin read OK at 20:47:22, age 0.1 s". No figure
  printed or stored. Limit of this proof: it used the margin reader's Kite client, not the whole
  `screen_margin_reader` chain with a strategy basket; c40 proves the whole chain on a live day.

## Reuse map (c06). Every build brief quotes its line.

Corrections to the contract's section 2, found by reading the code on 0fac11d3:

- **#682 (screens that hang).** `settings_store.database_now`, `catalogue_picker.database_now` and
  `paper_book.load_owned` do NOT open a connection; each takes the caller's. The second connection is opened by readers
  that route code calls: `adjustment_readers.read_tracked` (:123), `read_roll_inputs` (:80), a third at :222, and
  `get_sessionmaker()()` sites in `routes/outcome.py` (:84, :159, :253, :385), `routes/leg_edit.py` (:183, :251, :275)
  and `routes/leg_picker.py` (:486). Fix line: those readers take the request's own session (`db.get_db`,
  `ofo_app/db.py:50`) instead of opening one.
- **#686 (calendar).** The state `MarketStatus.NO_CALENDAR` already exists (`ofo/market_calendar.py:32-37`, `:95-96`).
  No new state is written. The gap: no API field and no screen tells it from "closed" (`market_closed` is the only
  field; `components/states/MarketClosedBanner.vue`). Also `next_open` / `last_close` return None in the last days of
  2026 when the look-ahead crosses into 2027.
- **Notifier (c25).** The API's outbound guard allows only loopback, the database and Kite (`ofo_app/main.py:156-158`),
  and the Notifier listens on the server's own loopback. A call from this PC needs the proxy address in the owner's
  private notes; the guard needs the Notifier door added.

| Fix | Existing code it must use | Where the change goes |
|---|---|---|
| #685 item 3, alert left open (c13, c14) | `playbook_store.lapse` (:768), `lapse_all` (:789), `background._lapse_open_of` (:629), `_lapse_exited` (:1660) | RCA first: records 212/213 were OPENED after the adjustment was booked. Opening is `DbGateStore.apply` (`background.py:656`, `open_suggestion` at :693); the tracked position is read in `owner_lister` (:1721-1731). The suggestion row stores no legs. A new lapse reason must be added to `LAPSE_REASONS` (`playbook_store.py:55-61`) |
| #685 item 4, limit mismatch (c15) | T-03 per-stage list in `ofo/adjustment/system_playbooks.json:356` (monthly 0.25, 0.30, 0.35); record threshold stamped at `background.py:677-695` from the evaluation's stage | The panel's "Early-stage limit" source was NOT found by search; c15 starts by finding it |
| #685 item 5, labels (c16) | `adjustment_check.condition_line` (:742), `RUPEE_TRIGGERS` (:726, holds only T-02), template `adjust_condition_line`; T-09 `cmp: le` in `system_playbooks.json:475` | Same functions; text through the templates |
| #627 worker login (c22-c24) | `feed_main.store_readers` (:380, gives `read_session` -> `StoredSession` with token, fingerprint, expiry), `broker_config.load_broker_config`, `outcome_margin.OutcomeMargin(session, open_client, clock)`, `kite_margin.KiteMargin`, `MarginCache` / `screen_margin_reader` / `_margin_loop` (`background.py:471-522`, :1631) | `background.py:1870-1887`: the worker's margin source reads the stored session (each refresh, so a late login is picked up) instead of `live_market.margin_source()` whose two readers answer None with no live-market object. No margin code, no token store |
| Heartbeat (c26, c27) | No store holds a worker alive time (searched: heartbeat, last_cycle, worker_status). API periodic tasks start in `main.py:96-99` (`paper_monitor.start()` is the pattern). Market hours: `live_market.market_open_at` (:369) | Store choice is the builder's first step: Redis key on the existing bus client (`feed_bus.new_client`) before any table |
| Notifier client (c25) | No client exists. HTTP: `httpx` (`ofo_app/kite_http.py`) and `urllib_transport`. Settings: `ofo_app/config.py` | One small module; the door added to the outbound guard |
| #686 calendar (c28, c29) | `ofo/market_calendar.py`: `market_status` (:110), `_day_status` (:93), `NO_CALENDAR`; 12 reader modules. Screen: `routes/catalogue.py:76` calls `market_status`; app-wide banner pattern `components/layout/ScenarioBanner.vue` in `AppLayout.vue` | The module once; one API field; one banner beside ScenarioBanner |
| #680 contract list (c31-c33) | `ofo/instruments/catalogue.py` `update` (:188-235 and the refusal after), `MAX_EXPIRY_LOSS_FRACTION` (:58), `check_max_delist_percent` (:64); chain `catalogue_refresh.start` -> `catalogue_load.load_once` -> `run` -> `catalogue_store.apply_update` | The one guard in `update`. The refused list of 2026-11-09 is NOT on disk (the download is held in memory only); the fixture is today's download |
| #682 one connection (c35-c39) | `db.get_db` (`ofo_app/db.py:50`), pool size `config.DB_POOL_SIZE` | See the correction above |
