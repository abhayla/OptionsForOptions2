# Builder brief: W-056 re-key the instrument catalogue on the exchange identity

Core: the real Zerodha public instrument file loads into the re-keyed catalogue with every contract identified by
(exchange, exchange_token) and Zerodha's instrument_token and trading symbol stored only as Zerodha's broker data, and
the W-053 proofs (counts, field match, Q244 refusal, Q257 history) still hold.
Proof (step 1, CI on PostgreSQL as ofo_app): in-scope count = catalogue count = zerodha broker-row count; NIFTY 20050 CE
resolves to (NFO, 40559) with broker row (zerodha, 10383106, NIFTY26O0620050CE); SENSEX 75000 CE to (BFO, 888931); a
lookup for a broker with no row is refused; a lot-size revision writes a dated per-broker row; no table outside the
per-broker table stores instrument_token.

Why Opus: Tier A; re-keys the catalogue, eligibility and the send_guard choke point, plus a data migration.
Budget: 60 min wall-clock, 80 tool calls. Do STAGE 1 (domain) fully and commit before STAGE 2 (database); if the
budget runs out, stop after a commit and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: A.

## Spec basis
- REQ-054 AC-3: "Each broker's own token, trading symbol and segment code for a contract are stored in a per-broker table
  keyed to the contract's identity (exchange segment, exchange token), with one broker code vocabulary; a contract with
  no row for a broker cannot be traded at that broker - no symbol is guessed or derived."
- REQ-054 AC-4: "Lot size, tick size and freeze limit are stored per broker with the date the broker's list showed them."
- REQ-053 decision of 2026-10-02 (SPEC CHANGE to the Q257 identity list) and ADR-050; spec/findings.md F-01..F-05.
- Q244 and Q257 behaviour from W-053 must keep working (truncated update refused; revisable terms follow the source with
  history; identity changes refused).
- Copy from: none - algochanakya's symbol converter, token manager and per-broker token table are SKIP (F-09, ADR-050).

## STAGE 1 - domain (backend/ofo, standard library, kit CI runs tests/)
- `backend/ofo/instruments/`: add `InstrumentId(exchange, exchange_token)` (frozen). `Contract` keeps identity +
  descriptive fields (exchange, exchange_token, name/underlying, expiry, strike, instrument_type, segment) and revisable
  terms; Zerodha's `instrument_token` and `tradingsymbol` become a `BrokerRef(broker='zerodha', broker_token,
  broker_symbol, broker_segment, lot_size, tick_size, freeze_limit=None, seen_on)` attached to the catalogue entry.
  One broker code vocabulary: a closed set with only `zerodha` in V1.
- The Zerodha parser maps each row into (Contract, BrokerRef('zerodha', ...)).
- `Catalogue` and `EligibilityRegistry` key on `InstrumentId`; Q244 and identity-change logic unchanged in meaning.
- `execution/safety.py`, `execution/send_guard.py`, `execution/partial.py`, `execution/sequence.py`: take Zerodha's token
  and symbol from the entry's zerodha BrokerRef; no BrokerRef for the broker -> refuse (fail closed, AC-3).
- Update the domain tests that use `contract.instrument_token` (about 53 references in 13 files) to the new shape;
  expected values unchanged where behaviour is unchanged. Add tests for: lookup by InstrumentId; missing BrokerRef
  refused at send_guard; identity is (exchange, exchange_token) not instrument_token.
- Commit stage 1 (domain suite green) before stage 2.

## STAGE 2 - database (backend/ofo_app)
- Migration `0004_broker_instruments` (down_revision `0003_catalogue_store`), owner-run, through the allowlist chain
  helper (`-- 9. broker instruments` block):
  - `catalogue_contracts`: identity unique on (exchange, exchange_token); drop instrument_token and tradingsymbol from it
    (moved). Keep the W-053 guard trigger semantics (identity columns now exchange, exchange_token, name,
    instrument_type, strike, segment; never delete).
  - new `broker_instruments` (contract FK, broker CHECK in ('zerodha'), broker_token TEXT, broker_symbol, broker_segment,
    lot_size, tick_size NUMERIC(10,4), freeze_limit, seen_on/first_seen_at/last_seen_at stamped by the database),
    unique (broker, broker_segment, broker_token) and (contract, broker); app role SELECT + column INSERT/UPDATE only
    as needed, no DELETE; dated lot/tick history either here or by extending `catalogue_term_changes` (state which).
  - migrate existing rows (0003 data) into the new shape in the migration, re-runnable, no hand edits.
- `catalogue_store.py`: load/apply_update in the new shape; revisable terms follow the source with history (Q257).
- Allowlist block 9 asserts the exact privileges, trigger shape and pinned bodies for the new table.
- Tests (`tests_app/test_broker_instruments.py`, real PostgreSQL, skip with reason locally, CI requires them): the proof
  steps; update `tests_app/test_catalogue_store.py` to the new shape keeping every W-053 proof line; a mutation test
  storing instrument_token in catalogue_contracts is refused by the allowlist/guard.

## Standing items (run-discipline B4)
- Fail closed: no BrokerRef -> no trade; an unknown broker code -> refused; a row whose identity cannot be parsed stops
  the load naming the row.
- Expected values from the real file and the spec, never from running the code.
- Kit CI stays green: tests/ imports no app packages; no wall-clock asserts.

## Rules
- Branch from origin/main (ADR-050 merged at 4bc9d0d). Do not edit kit files or spec/. Never write `evidence/`. No secrets.
- Run the domain suite and `python -m pytest -c pytest-app.ini -q` before finishing (DB tests skip locally; say so).
- Commit; do not push. Report worktree path, branch, commits.
