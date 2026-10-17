# Brief: GC-3 P0 item 1b - the read-only live probe / readback script (Tier B)

Core: one script reads holdings (with the raw reply's key list), depth + circuit band + funds for one named contract,
trades + positions -> gross P&L from the fills beside Kite's position P&L, and the audit log (hash chain verified) -
dry-run on the recorded 2026-10-16 replies first.
Proof: `python scripts/live/probe.py --replay D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order holdings` prints
the 8-field rows and the raw key list of `holdings-before-121602.json`; `... pnl` prints gross P&L -130.00 from the two
fills (BUY 65 @ 5.10, SELL 65 @ 3.10) beside Kite's -130 from `positions-151006.json`.

Common brief: docs/process/builder-brief.md
Contract: docs/process/goal-contract-GC-3-2026-10-19.md, P0 item 1b (read it). Tier B: a read-only tool, no order path,
no product module changed. No work item (tooling); branch `build/gc3-p0-probe`.

Spec basis:
- ADR-097 (4): "/portfolio/holdings is read before and after and must be unchanged".
- ADR-097 (2): "no app code or assistant action sends an order or operates Kite''s site" - this script only READS.
- ADR-102: "Realised and position P&L computed from broker fills (sells minus buys, price x quantity) is exact Decimal"
  and "quantized half-up to the paisa only for output (-130.00, not -130.0), by the one helper in ofo/money.py".
- ADR-102 consequence: "(3.10 - 5.10) x 65 = -130.00 from the two fills".

Copy from: none - a new read-only operator tool over existing app readers; reuse them, never re-implement.

## What to build: `scripts/live/probe.py` (+ `tests_app/test_live_probe.py`, non-DB except part d)
Subcommands; each takes `--replay <dir>` (read recorded JSON files, no network) or runs live (a real `KiteReads` built
from the owner's stored session exactly as `ofo_app.routes.execute` / `live_market.owner_kite_reads()` does it - reuse
that, never read the token yourself, never print it or the api key).
- (a) `holdings`: `KiteReads.fetch_holdings()` rows (the eight fields) AND the sorted key list of the RAW reply's first
  row (live: capture the raw JSON through a recording transport wrapper passed as `transport=`; replay: the file). A
  `KiteReadError` is printed with its code and exits 2 (a refused read is a stop, never a skipped check). `--save
  <file>` writes the 8-field snapshot as JSON; `holdings --compare <before.json>` prints `holdings_unchanged` (reuse
  the existing comparison in `ofo_app/kite_reads.py`, the `HoldingChange` function) and exits 3 on any change.
- (b) `contract <EXCHANGE:SYMBOL>`: 5-level depth, circuit band (`fetch_circuit_bands`), funds (`GET /user/margins`
  through the existing margin reader the Execute route uses). Replay: the quote/margins files in `--replay`.
- (c) `pnl [--tag-prefix X]`: trades + positions; gross P&L from the fills using the existing
  `ofo.orders.model.realised_pnl` (built on W-091's trades -> FillEvent adapter; reuse both, never re-implement), printed beside Kite's position `pnl` /
  `unrealised` for the same contract; exits 3 when they differ.
- (d) `audit [--since <ISO>]`: `audit_store.load_log(conn)` on ofo_dev (run through `scripts/orchestrator/dev_run.py`,
  refuses any DB but ofo_dev), prints "hash chain verified" or the failure, and lists the `order_prepared` /
  `broker_response_recorded` / `execution_recorded` rows after `--since`.
- Output: plain text, one line per fact, money as 2-decimal strings. Uses `print` (it is a CLI; the "no print" rule is
  for library code). No order, modify or cancel call anywhere; it must pass the runtime Kite door's allow-list.

## Attack cases the reviewer will run (put the tests in first)
1. Replay `holdings` on `holdings-before-121602.json` vs `holdings-after-151006.json`: unchanged -> exit 0; a copy
   with one quantity changed -> exit 3 naming the symbol and field.
2. A holdings file whose row lacks one of the eight fields -> `kite_read_bad_reply`, exit 2, never an empty list.
3. Replay `pnl` on trades-151006 + positions-151006 -> "-130.00" and Kite "-130", equal, exit 0; a fill price edited
   -> exit 3.
4. The script never prints the access token or api key (assert on captured stdout/stderr with a fake token).
5. Grep the script: no `/orders/regular`, no `place_order`, no POST except `/margins/basket` if reused.
6. `audit` against ofo_dev through dev_run.py lists rows and "hash chain verified" (one real run, paste the output).

Reviewer checklist: replay outputs match the hand values above; read-only (attack 5); fail-closed exits 2/3; no
secret printed; reuse (no copied comparison or P&L code).

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Plus: `python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_live_probe.py` (non-DB parts).
No new duplicated literal; reuse the existing helper; ruff/mypy baselines must not rise; targeted tests only; no
regenerated files in the PR.
Budget: 30 min wall-clock, 60 tool calls
Report: evidence-table
