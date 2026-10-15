# Builder brief: W-076 freeze limit from NSE's contract file, block at review (Tier A)

Core: parsing the real NSE contract-file sample gives NIFTY26O1923550CE (token 47185) freeze limit 3511 with file date
2026-10-15; a 55-lot NIFTY leg (3,575 units) is blocked at review, a 54-lot leg (3,510 units) passes.
Proof: step 1 is `tests/instruments/test_nse_freeze_file.py` on `tests/fixtures/exchange/NSE_FO_contract_15102026_sample.csv`
(real rows, cut unmodified by the orchestrator - never edit or hand-add rows). Write it FIRST, red.

Tier: A (an execution safety check; a wrong limit lets a basket half-fill). Model: sonnet (builder routing, deliver skill).
Budget: 60 min wall-clock, 70 tool calls. HARD limit: at call 65 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - spec/technical-design/legacy-reuse.md has no freeze-file row (searched: freeze, tick); the legacy map's instrument rows load Zerodha's list, which carries no freeze limit.

Read first: `docs/process/builder-brief.md`, `work/W-076.md`, `spec/decisions/ADR-081.md`, `spec/findings.md` F-36
(the column meanings, measured on the real file), `spec/requirements/REQ-054.md` (AC-4 and its body text),
`tests/fixtures/exchange/README.md`, `CLAUDE.md`.

## Spec basis
- REQ-054 AC-4: "Lot size, tick size and freeze limit are stored per broker with the date the broker's list showed them."
- ADR-081: "A leg whose quantity is above the contract's freeze limit is blocked on the order review with the reason and the limit, never split."
- ADR-081: "While no freeze limit is stored for a contract, the review warns that Zerodha may reject a large order."
- ADR-081: "Zerodha publishes none, so the freeze limit is stored per exchange
  from the exchange's file, with its date"
- F-36 (spec/findings.md): `MaxTradQty` is the freeze limit and the largest allowed order is `MaxTradQty - 1`;
  `FinInstrmId` = exchange token; `XpryDt` seconds from 1980-01-01; `StrkPric` in paise.

## What to build
1. Parser (domain, standard library, `backend/ofo/instruments/`): read an NSE contract file (`.csv` or `.csv.gz`),
   return (exchange token, freeze limit, lot, expiry, strike, type, symbol) for `OPTIDX`/`FUTIDX` rows of V1
   underlyings only. Freeze limit as an int from the `MaxTradQty` text (`3.511000E+03` -> 3511; via Decimal, refuse a
   non-integer value). The header is an allow-list: missing `FinInstrmId`/`MaxTradQty`/`TckrSymb`/`FinInstrmNm`/
   `XpryDt` -> error; never guess a column by position.
2. Cross-check before storing: a row joins to a catalogue contract only on (NSE_FO, exchange token) AND its lot, expiry
   and strike agree with the catalogue; a disagreement is reported and not stored (never overwrite identity data).
3. Store (app layer): Alembic `0013_exchange_freeze_limits` with `down_revision` set to `0011_strategy_planned_entry` on
   your branch (the orchestrator re-chains it onto W-074's `0012_charge_rates` at merge; say so in the migration's
   docstring). Table keyed by (exchange segment, exchange token, file date), the freeze limit and the file name;
   append-only, newest file date in force. A loader function + a CLI entry under `scripts/` that loads a file path.
   The file date comes from the file name (`ddmmyyyy`) - refuse a name that does not parse, and refuse a date in the
   future of the DB clock (ADR-023). Run `python scripts/alembic_migration_guard.py`.
4. Review block (domain): find the order review in `backend/ofo/execution/` (`review.py`; read how it reports a blocked
   leg today and reuse that path). A leg is allowed iff quantity < freeze limit (equivalently <= limit - 1, F-36);
   otherwise the review blocks the leg naming the limit in units and lots, e.g. 3,575 units (55 lots) vs largest
   allowed 3,510 units (54 lots). No stored limit -> the warning of ADR-081, not a block. The words go through the
   error/warning catalogue (`backend/ofo/errors/`) as four-part messages (REQ-065, ADR-086), with pins updated.
5. Do NOT change `slice_quantity` or the Complete/Retry slicing in `sequence.py` / `partial.py` (REQ-058, verified).
   In your report, name every place where an ENTRY basket path would still slice instead of block (the orchestrator
   files it).

## Reviewer checklist (write these first; each must turn red when its guard is mutated)
- Boundary: 3,510 passes, 3,575 blocks; `<` mutated to `<=` must turn a test red (use a synthetic lot of 1 where
  quantity == limit is reachable, labelled synthetic, alongside the real-row tests).
- Join on symbol instead of token -> red (a test with a symbol/ token mismatch row).
- Missing limit -> warning, never a silent pass and never a block.
- A stale file (older file date) never replaces a newer stored limit.
- Header allow-list: a renamed column fails; extra unknown columns are ignored only because the file has ~90 columns
  we do not use - state that rule in a test.
- Every guard has a killing test; list them.

## Rules
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/instruments tests/execution tests/errors`; app:
  `python scripts/orchestrator/db_run.py . python -m pytest -q -rs -p no:cacheprovider -c pytest-app.ini tests_app/test_freeze_store.py`
  (tunnel down -> say so, CI runs it). Then `python <your-worktree>/scripts/orchestrator/atool.py <worktree> W-076 --no-tests`.
- Do not touch `backend/ofo/charges/` or any charges code (W-074 runs in parallel), `views/`,
  `knowledge/findings/INDEX.md`, kit files or `spec/`. Never write `evidence/`. Never mark anything verified.
- Commit and push `build/W-076-freeze`. Do not open a PR.
