# Stage 4b core proof on the real 2026-10-16 order: result

Core: the existing fill ledger (REQ-057, `backend/ofo/orders/model.py` FillLedger / OrderBook.apply_fill) and
reconcile (REQ-060, `backend/ofo/reconciliation/compare.py` compare + `positions.py` position_line_from_kite_row)
accept Kite's REAL orders/trades/positions responses and give the right answer.
Proof: `proof.py` run 2026-10-16 on `D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order/` (snapshots 122104 and
151006) with `PYTHONPATH=<repo>/backend`; stdout in `run-output.txt` (exit 0, `SUMMARY: 4/4 PASS`).
Findings read first: `money-parsed-through-float`, `held-without-platform-fill-invisible-to-ledger`,
`trust-broker-status-word`, `resolution-on-stale-broker-copy` (grep of `knowledge/findings/` for kite, position,
average_price, float, flat, reconcile, F-35).

## Expected checks (PASS only AFTER the scaffolding conversions below)

| # | Result | Printed line |
|---|---|---|
| 1 entry | PASS | `strategy={(NIFTY, CE, 23650.00, 2026-10-19): 65} broker=65@5.1 mismatches=0` (discriminator: broker +130 gives `quantity mismatch ... +65`) |
| 2 exit | PASS | `strategy exited=True broker_net={} flat_row qty=0 mismatches=0` (discriminator: strategy still active vs flat broker gives `missing platform position ... -65`) |
| 3 P&L | PASS | `position_pnl=Decimal('-130.0') fills-sum=Decimal('-130.0') kite pnl=-130 (int)`. Product function: `ofo.engine.legs.position_pnl` (legs.py:103), fed the BUY fill's price as entry and the SELL fill's price as value. Exactly -130 as Decimal; its exponent is `-130.0`, not `-130.00` (no quantize to paise). |
| 4 ledger | PASS | `after entry=65 after replay=65 after exit+replays=0 rows=2 ids=['4484194', '5966618'] states={'OFS1V1L0': ('Executed', 65), 'OFS1V2L0': ('Executed', 65)}`. Re-applying each trade is a no-op. |

## Raw field types in the recording (default `json.load`; no JSON floats anywhere)

- orders: `price` and `average_price` are strings ("5.45", "5.1"); `trigger_price` is int 0; quantities are ints.
- trades: `average_price` is a string; `quantity` is an int; timestamps are naive strings (`order_timestamp` is time-only "12:20:50").
- positions: money is MIXED between snapshots: `average_price` "5.1" (str) at entry and `0` (int) when flat; also
  `sell_price`, `sell_value`, `value`, `day_sell_*` and `sell_m2m` change from int 0 to string. `pnl`, `m2m`,
  `close_price` are ints.
- The strings come from the recorder, not from Kite: live Kite REST sends JSON numbers (finding
  `money-parsed-through-float`, F-33), and the kiteconnect SDK hands over Python floats. **This recording does not
  prove how live floats or JSON numbers are parsed by the product.**

## Product-code refusals hit on real data (the 4b gaps GC-2b must design)

1. `positions.py:53` (`_kite_price`): `ValueError: average_price must be a Decimal or int (floats are refused), got '5.1'` (entry row).
2. `positions.py:53`: `ValueError: last_price must be a Decimal or int (floats are refused), got '3.1'` (flat exit row).
3. Flat row after string conversion: `positions.py:44` -> `engine/legs.py:36` (`require_price(..., allow_zero=False)`):
   `average_price must be > 0, got 0`. Correct refusal (never a 0-price holding), but there is no flat-row path in
   the parser; `grouping.py:295` already skips `quantity == 0` rows before parsing, the reconcile path has no equivalent.
4. `FillEvent` with the trade row's price: `orders/model.py:260` -> `engine/legs.py:31`: `price must be a decimal.Decimal, got str`.
5. SDK-shaped floats (`average_price 5.1`, `last_price 3.1`): `positions.py:53` refuses both. Fail-closed, but means a
   live SDK read is unusable until an adapter converts at the boundary.

Missing glue (not refusals: the code does not exist in `backend/`; `ofo_app` not checked in this proof):
- No Kite trades-row -> `FillEvent` parser (`trade_id` appears only in `orders/model.py`).
- No Kite positions response -> `compare()` broker map: `BrokerPositionLine.contract` is the tradingsymbol string,
  while `compare` keys on `(underlying, Instrument, strike, expiry)` (issue #115).
- No realised P&L from the fill ledger; `position_pnl` works per leg, so the script paired the fills itself.
- The ledger and the `StrategyRecord` are separate: the script drove `apply_result`, `observe_broker_position` and
  `mark_exited` by hand. Nothing derives the record's exit from the ledger reaching 0.

## Attack cases

- A1 exit trade before entry trade: **accepted**, ledger position -65 (a short the strategy never held), then 0 after
  the entry. The end state is right; the in-between state would read as a side flip to anything checking it then.
- A2 SDK floats: refused (see 5). A2b float `last_price` only: refused with `last_price must be a Decimal or int (floats are refused), got 3.1`.
- A3 flat row: the parser refuses `average_price 0` (no 0-price holding); with the row dropped, `compare` gives 0
  mismatches; `compare({contract: 0})` also gives 0 (zero lines dropped by `units_map`).

## Scaffolding (none of this is product code)

1. tradingsymbol/instrument_token -> Contract from `instruments.json` (underlying = first word of `group`).
2. IST (`ofo.timeutil.IST`) attached to Kite's naive timestamps.
3. Boundary conversion: `Decimal(str(v))` for string `average_price`/`last_price`; a `quantity == 0` row is skipped
   (no line, no units). **This conversion is NOT in product code.**
4. A test-only `StrategyRecord` (built like `tests/reconciliation/recon_fixtures.executed`), bound into an
   `OrderBook`; both real orders registered as Orders of version `v1` (the tag OFS1V2L0 suggests v2; the record has
   only v1), moved to Pending with `mirror_broker_state`; order prices `Decimal(row["price"])`; trade prices
   `Decimal(row["average_price"])`.

## Proposed finding (class)

`broker-reply-shape-unproven-at-domain-boundary`: the domain parsers (`position_line_from_kite_row`, `FillEvent`)
accept only Decimal/int money, and nothing in `backend/ofo` converts a Kite reply (JSON number, SDK float, or a
recorded string) into that shape, nor maps a tradingsymbol to the reconcile contract key, nor handles a flat
(quantity 0, average 0) row. Real values: entry `average_price "5.1"`, flat `average_price 0` / `last_price "3.1"`,
trade `average_price "5.1"`/`"3.1"`. Measured: 4 of 4 checks pass only with 4 scaffolding adapters; without them the
first real row is refused. Does not prove: live JSON-number or SDK-float parsing, multi-leg or partial fills,
out-of-order postbacks, MIS rows, or charges (F-35 stays an owner item).

## Verdict

The 4b core logic holds on the real order: with exact Decimal inputs the ledger records both real trades once,
replays are no-ops, the position returns to 0, reconcile gives 0 mismatches at entry and at exit (and the
discriminators show it does flag +130 and a still-active strategy), and gross P&L is exactly -130, matching Kite's
`pnl: -130`. It does NOT hold end to end: every real row is refused at the boundary, and the chain runs only through
four throwaway adapters. GC-2b must design (a) one Kite adapter that turns orders/trades/positions replies (JSON
numbers via `parse_float=Decimal`, SDK floats via `Decimal(str(v))`, or strings) into domain types, (b) a flat-row
rule in the reconcile path matching `grouping.py:295`, (c) token -> contract-key mapping from the catalogue,
(d) trade rows -> `FillEvent` with IST, (e) record state (exit) driven from the ledger/broker read, and
(f) a decision on out-of-order fills (A1) and on quantizing realised P&L to paise.
