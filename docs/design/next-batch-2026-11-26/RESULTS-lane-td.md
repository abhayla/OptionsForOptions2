# Lane TD: browser walk of builder, stops and dialogs (11 items)

STATUS: 21:55 IST 27 Nov, in progress. Proven so far: I-41 (partly), I-79. Not yet run: I-20, I-21, I-66, I-71, I-72, I-78, I-86, I-88, I-93.
Branch test/r2-walk-builder-1128 (from integration/weekend-1127 + integration/conflicts-1127 16c536f0). Paper only, no broker.

## Set-up as run (decided, not asked)
- PostgreSQL 16 (`pg_ctlcluster 16 main start`), database exactly `ofo_dev`, roles as in app-tests.yml, migrated to `0059_last_close (head)`.
- Python deps from requirements-app.txt; frontend `npm ci && npm run build`; `vite preview` on 4173 (/api -> 127.0.0.1:8000), second preview on 4174 with `OFO_API_TARGET=http://127.0.0.1:9` (closed port).
- Catalogue: ofo_dev had no contracts, so `seed_scenario.py ADJ-02` refused ("0 live catalogue contracts for NIFTY 22500 PE 2026-11-09"). Loaded the scenario's own instrument rows through the guarded loader `catalogue_load.run` with as_of = scenario day (script `tests_browser/r2_1128_d/load_cat.py`), then `python scripts/seed_scenario.py ADJ-02` -> "ADJ-02 strategy id 1".
- Clock: the catalogue routes judge currency on the real database clock (2026-11-27), so with APP_ENV=development the 9 Nov contracts read as expired and the builder showed "This strategy's paper position could not be read, so it is not shown. Try again." (all API answers were 200; the catalogue answered 0 contracts). Fix of the set-up, not of the product: API started with `APP_ENV=test TEST_CATALOGUE_DATE=2026-11-06 OFO_SCENARIO=ADJ-02` (the test pin the code provides; scenario mode allows `test`). Dummy broker settings (KITE_*, BROKER_TOKEN_KEY) because the app refuses to start without them; nothing connects.
- Browser: Playwright + preinstalled Chromium, 1366x768, JPEG screenshots in `screens-td/`.

## Per item
