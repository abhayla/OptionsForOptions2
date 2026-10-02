# Builder brief: W-056 stage 2 - segment-qualified identity + database re-key

Core: the real Zerodha public instrument file loads into PostgreSQL (as `ofo_app`) with every in-scope contract
identified by (exchange segment, exchange token) from the platform's own segment list, and Zerodha's instrument_token
and trading symbol stored only in `broker_instruments`.
Proof (step 1, CI on PostgreSQL as ofo_app): in-scope count = catalogue count = zerodha broker-row count; NIFTY 20050 CE
resolves to (NSE_FO, 40559) with broker row (zerodha, 10383106, NIFTY26O0620050CE); SENSEX 75000 CE to (BSE_FO, 888931);
the 30 real NSE INDICES/cash collisions (e.g. NSE / 1001 = NIFTY 50 and 94SFL28-YL) are outside V1 and never loaded; a
lookup for a broker with no row is refused; a Zerodha lot-size revision writes a dated history row naming the broker.

Why Opus: Tier A data migration plus the app-role privilege allowlist chain (block 9) and the catalogue guard trigger.
Budget: 60 min wall-clock, 80 tool calls. Commit after part A (domain) before part B (database); at budget stop after a
commit and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: A.
Class: instrument identity keyed on one broker's column - any identity built from a broker's own field (token,
symbol, or its `exchange` column used as a segment) instead of the platform-owned exchange segment.
Proof: the real Zerodha file in CI, with the counts and the two named contracts above.

## Spec basis
- REQ-054 AC-3: "Each broker's own token, trading symbol and segment code for a contract are stored in a per-broker table
  keyed to the contract's identity (exchange segment, exchange token), with one broker code vocabulary; a contract with
  no row for a broker cannot be traded at that broker - no symbol is guessed or derived."
- REQ-054 AC-4: "Lot size, tick size and freeze limit are stored per broker with the date the broker's list showed them."
- REQ-054 section Exchange segment vocabulary (added in commit 2f92307 on this branch): V1 values NSE_FO and BSE_FO;
  Zerodha NFO -> NSE_FO, BFO -> BSE_FO; any other row is outside V1 and not loaded.
- spec/findings.md F-10 (the 30 collisions; stage 1 keyed on Zerodha's `exchange`, spec-adherence class 1).
- Q244 and Q257 behaviour from W-053 must keep working (truncated update refused; revisable terms follow the source with
  history; identity changes refused).
- Copy from: none - algochanakya's symbol converter, token manager and per-broker token table are SKIP (F-09, ADR-050).

## Decision taken by the orchestrator (record it in W-056 notes, not in spec/)
Current lot_size, tick_size, freeze_limit and broker_symbol live on the `broker_instruments` row. Their history goes
into the existing append-only `catalogue_term_changes`, extended with a nullable `broker` column (NULL = contract-level
term such as expiry; 'zerodha' = that broker's term). One history table, the W-053 guard reused.

## PART A - domain correction (backend/ofo, standard library)
- `InstrumentId(exchange_segment, exchange_token)`; `exchange_segment` is a closed set {NSE_FO, BSE_FO} (one constant,
  like BROKER_CODES). The Zerodha parser maps `exchange` NFO -> NSE_FO, BFO -> BSE_FO; any other row is skipped as
  outside V1 (counted, not an error); an in-scope row whose identity cannot be parsed stops the load naming the row.
- Keep your duplicate-identity guard; add a test feeding the real collision shape (two NSE rows, token 1001, segments
  INDICES and NSE) and asserting neither is loaded and nothing is raised for them.
- Update the stage-1 tests to the new identity; expected values from the real file and the spec.
- Commit part A (domain suite green).

## PART B - database (backend/ofo_app)
- Migration `0004_broker_instruments` (down_revision `0003_catalogue_store`), through the allowlist chain helper
  (`-- 9. broker instruments` block):
  - `catalogue_contracts`: identity unique on (exchange_segment, exchange_token) with a CHECK on the segment list; drop
    instrument_token and tradingsymbol (moved). Guard trigger identity columns become exchange_segment, exchange_token,
    name, instrument_type, strike; never delete.
  - new `broker_instruments`: contract FK, broker CHECK in ('zerodha'), broker_token TEXT, broker_symbol,
    broker_segment, lot_size, tick_size NUMERIC(10,4), freeze_limit, seen_on/first_seen_at/last_seen_at stamped by the
    database; unique (broker, broker_segment, broker_token) and (contract, broker); app role SELECT + column
    INSERT/UPDATE only as needed, no DELETE.
  - `catalogue_term_changes` + nullable `broker` (same CHECK); history rows for lot/tick/freeze/symbol carry it.
  - migrate 0003 rows into the new shape in the migration, re-runnable, no hand edits.
- `catalogue_store.py`: load/apply_update in the new shape (the 16 failing `test_catalogue_store.py` tests).
- Allowlist block 9 asserts exact privileges, trigger shape and pinned bodies for the new and changed tables.
- Tests (`tests_app/test_broker_instruments.py`, real PostgreSQL, skip with reason locally, CI requires them): the proof
  steps; port `tests_app/test_catalogue_store.py` keeping every W-053 proof line; mutation tests: (1) a column
  instrument_token added to catalogue_contracts is refused by the allowlist; (2) a DELETE on broker_instruments as the
  app role is refused; (3) an exchange_segment outside the list is refused by the CHECK.

## Standing items (run-discipline B4)
- Fail closed: no broker row -> no trade; unknown broker code or segment -> refused; an unparsable in-scope row stops the
  load naming the row.
- Expected values from the real file and the spec, never from running the code.
- Kit CI stays green: tests/ imports no app packages; no wall-clock asserts. Count every SQL call a test asserts on;
  assert the exact columns written.

## Rules
- Continue on branch `build/W-056-broker-identity` in your worktree. Do not edit kit files or spec/. Never write
  `evidence/`. No secrets.
- Run the domain suite and `python -m pytest -c pytest-app.ini -q` before finishing (DB tests skip locally; say so).
- Commit; do not push. Report worktree path, branch, commits.
