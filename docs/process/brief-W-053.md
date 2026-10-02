# Builder brief: W-053 persist the instrument catalogue in PostgreSQL

Core: a real Zerodha public instrument file loads into PostgreSQL and reads back to the same contracts the W-006 parser
produced, with Decimal strikes and tick sizes unchanged.
Proof (step 1): download the real public list (`ofo.instruments.downloader.download_instruments_csv`, no login), parse
it, save through the new store, reload; NIFTY (NFO) and SENSEX (BFO) option and future counts in the file equal the
table; 5 named contracts match field by field (strike, expiry, lot size, tick size, tradingsymbol). Record the counts and
the 5 contracts in your report. Then remove one unexpired contract from a copy and show the update is refused with no
row changed.

Why Opus: Tier A; it changes the app-role privilege allowlist (a guard meant to be hard to bypass).
Budget: 60 min wall-clock, 80 tool calls. At budget, stop and report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`).
Tier: A (work/W-053.md tier raised from B in this PR: the allowlist is a security guard).

## Spec basis
- REQ-053 AC-2: "The contract catalogue (what exists) is stored separately from current eligibility (what Zerodha
  permits); contracts are never permanently deleted because they are unavailable today."
- Owner decision Q244: "refuse any update that removes a not-yet-expired contract" (already implemented in `backend/ofo/instruments/catalogue.py` `Catalogue.update`; do not re-implement it).
- ADR-047 copy first; ADR-048 test role; money/price columns NUMERIC, never float (project rule decimal-money-boundaries).

## Copy from (legacy-reuse.md M2; algochanakya@bf9faf7)
- `backend/app/models/instruments.py` -> `backend/ofo_app/models.py` table `public.catalogue_contracts` (ADAPT): Numeric
  strike `NUMERIC(12,2)` and tick size `NUMERIC(10,4)` with Decimal/server defaults (legacy has a float `0.05` default),
  unique (exchange, instrument_token), no `source_broker`, plus `currently_listed BOOLEAN` and `first_seen_at` /
  `last_seen_at` stamped by the database.
- `backend/tests/backend/instruments/test_instrument_master.py`: adapt its cases (BFO/SENSEX rows, lot sizes) to our
  store tests.
- `backend/app/services/instrument_master.py`: REFERENCE only.

## Design (required)
- `backend/ofo_app/catalogue_store.py`: `load_catalogue(session) -> ofo.instruments.catalogue.Catalogue` and
  `apply_update(session, contracts, *, as_of, force=False)` = load, call the domain `Catalogue.update`, write the result in
  ONE transaction; a refused update writes nothing. Eligibility stays out of this table (REQ-053 AC-2).
- Grants: `ofo_app` SELECT, column-level INSERT and UPDATE only on `currently_listed`, `last_seen_at`; no DELETE (never
  deleted). Migration `0002_*` after W-051's baseline, owner-run, same precondition checks.

## Migration and allowlist (W-051 and W-052 merged before you start)
- Migration revision id 0003_catalogue_store with down_revision 0002_audit_store, owner-run; extend the app-role allowlist
  through the chain helper W-052 added (build on 0002's extended allowlist SQL, add a `-- 8. catalogue store` block),
  asserting the exact privileges on `catalogue_contracts` and its sequence; head test checks markers 1-8.
- Also close two owner-level gaps the W-052 round-2 review found in the allowlist: (a) check each guarded trigger's
  `tgtype` is the intended timing/level/event (BEFORE ROW INSERT for the ledger and audit link triggers, AFTER ROW INSERT
  for the anchor trigger), with a mutation test re-creating one as BEFORE UPDATE; (b) pin each guarded trigger function's
  body (`md5(prosrc)` recorded at migration time) with a mutation test replacing a body.

## Tests (tests_app/test_catalogue_store.py; real PostgreSQL; the real-file proof is marked `network` and runs in CI)
- Round trip on a small fixture built from REAL rows copied from the downloaded file (state the download date in the
  fixture header), and the full real-file proof in CI.
- A refused update leaves every row unchanged; DELETE as `ofo_app` is refused.

## Standing items (run-discipline B4)
- Fail closed: a row whose strike or tick cannot be parsed as Decimal stops the load, naming the row.
- Kit CI stays green; nothing under `tests/` imports app packages.

## Rules
- Branch from origin/main after W-051 merged. Do not edit kit files. Never write `evidence/`. No secrets.
- Run the domain suite and `python -m pytest -c pytest-app.ini -q` before finishing. Commit; do not push.
