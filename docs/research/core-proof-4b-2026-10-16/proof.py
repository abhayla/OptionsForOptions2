"""GC-1 item 8: Stage 4b core proof on the real 2026-10-16 order (THROWAWAY, not product code).

Runs the REAL ofo.* fill ledger (OrderBook.apply_fill) and reconcile (compare + position_line_from_kite_row) on the
recorded Kite orders/trades/positions responses. Every adapter in this file is SCAFFOLDING, labelled below.
Run: PYTHONPATH=<repo>/backend python proof.py
"""
from __future__ import annotations

import datetime
import json
import os
from decimal import Decimal
from pathlib import Path

from ofo.engine import Action, Instrument
from ofo.engine.legs import Leg, position_pnl
from ofo.engine.product import Product
from ofo.orders.model import FillEvent, Order, OrderBook, OrderState
from ofo.reconciliation.compare import compare
from ofo.reconciliation.positions import BrokerPositionLine, position_line_from_kite_row
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.versions import ExecutionResult, Position, ResultStatus, StrategyRecord
from ofo.timeutil import IST

# The recordings folder is not in git: set OFO_KITE_TICKS to the folder holding 2026-10-16/ (finding
# absolute-path-from-one-machine). Run: PYTHONPATH=backend python docs/research/core-proof-4b-2026-10-16/proof.py
ROOT = Path(os.environ["OFO_KITE_TICKS"]) / "2026-10-16"
REAL = ROOT / "real-order"
SNAPS = {"entry": "122104", "exit": "151006"}
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, line: str) -> None:
    results.append((name, ok, line))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {line}")


def load(name: str, *, decimal: bool = True):
    with open(REAL / f"{name}.json", encoding="utf-8") as f:
        return json.load(f, parse_float=Decimal) if decimal else json.load(f)


# ---- 0. raw type census (json.load WITHOUT parse_float, so a JSON float would show as float) ----
print("== 0. raw JSON types per field (default json.load) ==")
census: dict[str, dict[str, set[str]]] = {}
for kind in ("orders", "trades", "positions"):
    fields: dict[str, set[str]] = {}
    for stamp in SNAPS.values():
        data = load(f"{kind}-{stamp}", decimal=False)["data"]
        rows = data["net"] + data["day"] if kind == "positions" else data
        for row in rows:
            for k, v in row.items():
                fields.setdefault(k, set()).add(type(v).__name__)
    census[kind] = fields
    for typ in ("str", "int", "float", "NoneType", "bool", "list", "dict"):
        names = sorted(k for k, t in fields.items() if typ in t)
        if names:
            print(f"  {kind} {typ}: {', '.join(names)}")
    mixed = sorted(k for k, t in fields.items() if len(t) > 1)
    print(f"  {kind} MIXED-type fields across snapshots: {mixed or 'none'}")
floats = [(k, f) for k, fs in census.items() for f, t in fs.items() if "float" in t]
print(f"  JSON floats anywhere: {floats or 'none'}")

# ---- SCAFFOLDING 1: tradingsymbol/instrument_token -> Contract from instruments.json ----
instruments = json.loads((ROOT / "instruments.json").read_text(encoding="utf-8"))  # float-ok: strike is a string


def contract_for(token: int) -> tuple:
    row = instruments[str(token)]
    underlying = row["group"].split(" ")[0]
    strike = None if row["type"] == "FUT" else Decimal(row["strike"])
    return (underlying, Instrument(row["type"]), strike, datetime.date.fromisoformat(row["expiry"]))


TOKEN = 12080386
CONTRACT = contract_for(TOKEN)
SYMBOL = instruments[str(TOKEN)]["symbol"]
print(f"\nscaffolding contract for token {TOKEN}: {CONTRACT} symbol={SYMBOL}")


# ---- SCAFFOLDING 2: IST attached to Kite's naive timestamps ----
def ist(text: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(text).replace(tzinfo=IST)


NOW = ist("2026-10-16 15:30:00")


def clock() -> datetime.datetime:
    return NOW


# ---- 1. REAL parser on REAL rows (no conversion) ----
print("\n== 1. position_line_from_kite_row on the real net rows, unconverted (parse_float=Decimal load) ==")
refusals: list[str] = []
for label, stamp in SNAPS.items():
    for row in load(f"positions-{stamp}")["data"]["net"]:
        try:
            line = position_line_from_kite_row(row)
            print(f"  {label}: ACCEPTED {line}")
        except ValueError as exc:
            msg = f"{label} row {row['tradingsymbol']} qty={row['quantity']}: {type(exc).__name__}: {exc}"
            refusals.append(msg)
            print(f"  REFUSED {msg}")


# ---- SCAFFOLDING 3: minimal boundary conversion (NOT in product code) ----
PRICE_FIELDS = ("average_price", "last_price")


def convert(row: dict) -> dict:
    out = dict(row)
    for k in PRICE_FIELDS:
        if isinstance(out.get(k), str):
            out[k] = Decimal(str(out[k]))
    return out


def broker_net(stamp: str) -> tuple[dict, list]:
    net: dict = {}
    notes = []
    for row in load(f"positions-{stamp}")["data"]["net"]:
        if row["quantity"] == 0:
            notes.append(f"flat row {row['tradingsymbol']} (quantity 0, average_price {row['average_price']!r}) "
                         "-> no line, no units (never a 0-price holding)")
            continue
        line = position_line_from_kite_row(convert(row))
        net[contract_for(row["instrument_token"])] = net.get(contract_for(row["instrument_token"]), 0) + line.net_quantity
        notes.append(f"line {line.contract} net={line.net_quantity} avg={line.average_price} ltp={line.ltp} "
                     f"product={line.product}")
    return net, notes


print("\n== 2. converted rows -> broker net map ==")
NET = {}
for label, stamp in SNAPS.items():
    NET[label], notes = broker_net(stamp)
    for n in notes:
        print(f"  {label}: {n}")
    print(f"  {label}: broker_net = {NET[label]}")

# ---- SCAFFOLDING 4: a test-only strategy record (copied from tests/reconciliation/recon_fixtures.executed) ----
definition = StrategyDefinition("NIFTY", (DefinitionLeg(Action.BUY, CONTRACT[1], CONTRACT[2], CONTRACT[3], 65),))
record = StrategyRecord(definition, at=ist("2026-10-16 12:20:00"), clock=clock)
v1 = record.propose_execution(at=ist("2026-10-16 12:20:10"))
record.confirm(v1.number, at=ist("2026-10-16 12:20:20"))
record.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, Position.of({CONTRACT: 65}),
                                    ist("2026-10-16 12:20:50"), "OFS1V1L0"))

print("\n== 3. Expected 1: after entry (122104) ==")
entry_row = convert(load("positions-122104")["data"]["net"][0])
line = position_line_from_kite_row(entry_row)
rep = compare(NET["entry"], {"S1": record}, at=ist("2026-10-16 12:21:04"), clock=clock)
ok = (record.active_version.intended_position.as_dict() == {CONTRACT: 65} and line.net_quantity == 65
      and line.average_price == Decimal("5.1") and len(rep.mismatches) == 0)
check("1 entry", ok, f"strategy={record.active_version.intended_position.as_dict()} broker={line.net_quantity}@"
      f"{line.average_price} mismatches={len(rep.mismatches)}")
disc = compare({CONTRACT: 130}, {"S1": record}, at=ist("2026-10-16 12:21:04"), clock=clock)
print(f"  discriminator: broker +130 instead of +65 -> {[m.describe() for m in disc.mismatches]}")

print("\n== 4. Expected 2: after exit (151006) ==")
before_exit = compare(NET["exit"], {"S1": record}, at=ist("2026-10-16 15:10:06"), clock=clock)
print(f"  discriminator: strategy still active (+65) vs broker flat -> {[m.describe() for m in before_exit.mismatches]}")
record.observe_broker_position(Position.of({}), at=ist("2026-10-16 15:10:06"), reference="obs-151006")
record.mark_exited(at=ist("2026-10-16 15:10:07"), actor="proof", resolution="exit order OFS1V2L0 filled")
rep2 = compare(NET["exit"], {"S1": record}, at=ist("2026-10-16 15:10:08"), clock=clock)
flat_row = load("positions-151006")["data"]["net"][0]
ok = record.exited and NET["exit"] == {} and flat_row["quantity"] == 0 and len(rep2.mismatches) == 0
check("2 exit", ok, f"strategy exited={record.exited} broker_net={NET['exit']} flat_row qty={flat_row['quantity']} "
      f"mismatches={len(rep2.mismatches)}")

# ---- 5. Fill ledger (SCAFFOLDING: orders registered by the script; version v1 for both, see RESULT.md) ----
print("\n== 5. Expected 4: fill ledger on the two real trades ==")


def order_from_row(row: dict) -> Order:
    return Order("S1", "L0", row["tradingsymbol"], Action(row["transaction_type"]), row["quantity"],
                 Decimal(row["price"]), broker_order_id=row["order_id"], version_id="v1", client_tag=row["tag"],
                 product=Product(row["product"]))


def fill_from_trade(row: dict) -> FillEvent:
    return FillEvent(row["trade_id"], row["order_id"], row["tradingsymbol"], Action(row["transaction_type"]),
                     row["quantity"], Decimal(row["average_price"]), ist(row["fill_timestamp"]))


def new_book() -> OrderBook:
    book = OrderBook(clock=clock)
    book.bind_strategy("S1", record)
    for row in load("orders-151006")["data"]:
        book.add(order_from_row(row))
        book.mirror_broker_state(row["tag"], OrderState.PENDING)
    return book


trades = load("trades-151006")["data"]
print(f"  raw trade-row price types: {[type(t['average_price']).__name__ for t in trades]}")
try:
    FillEvent(trades[0]["trade_id"], trades[0]["order_id"], trades[0]["tradingsymbol"], Action.BUY, 65,
              trades[0]["average_price"], ist(trades[0]["fill_timestamp"]))
    print("  FillEvent with raw string price: ACCEPTED")
except ValueError as exc:
    refusals.append(f"FillEvent price as raw string: {exc}")
    print(f"  REFUSED FillEvent with raw string price: {exc}")

book = new_book()
fills = [fill_from_trade(t) for t in trades]
book.apply_fill(fills[0])
after_entry = book.position("S1", SYMBOL)
book.apply_fill(fills[0])  # replay
after_replay = book.position("S1", SYMBOL)
book.apply_fill(fills[1])
book.apply_fill(fills[1])
book.apply_fill(fills[0])
after_exit = book.position("S1", SYMBOL)
ids = sorted(f.trade_id for f in book.raw_fills())
states = {v.order.client_tag: (v.state.value, v.filled_quantity) for v in book.views_for("S1")}
ok = (after_entry == 65 and after_replay == 65 and after_exit == 0 and ids == ["4484194", "5966618"]
      and len(book.raw_fills()) == 2)
check("4 ledger", ok, f"after entry={after_entry} after replay={after_replay} after exit+replays={after_exit} "
      f"rows={len(book.raw_fills())} ids={ids} states={states}")

print("\n== 6. Expected 3: gross P&L ==")
buy = next(f for f in book.raw_fills() if f.side is Action.BUY)
sell = next(f for f in book.raw_fills() if f.side is Action.SELL)
leg = Leg(Action.BUY, CONTRACT[1], CONTRACT[2], CONTRACT[3], buy.quantity, buy.price)
pnl = position_pnl(leg, sell.price)
by_fills = sum((f.price * f.quantity if f.side is Action.SELL else -f.price * f.quantity) for f in book.raw_fills())
kite_pnl = load("positions-151006")["data"]["net"][0]["pnl"]
ok = (pnl == Decimal("-130.00") and isinstance(pnl, Decimal) and by_fills == pnl
      and Decimal(kite_pnl) == pnl)
check("3 pnl", ok, f"position_pnl={pnl!r} fills-sum={by_fills!r} kite pnl={kite_pnl!r} ({type(kite_pnl).__name__})")

print("\n== 7. Attack cases ==")
book2 = new_book()
try:
    book2.apply_fill(fills[1])
    print(f"  A1 exit before entry: ACCEPTED, position={book2.position('S1', SYMBOL)}; "
          f"then entry -> ", end="")
    book2.apply_fill(fills[0])
    print(f"position={book2.position('S1', SYMBOL)}")
except ValueError as exc:
    print(f"  A1 exit before entry: REFUSED {exc}")

float_row = dict(load("positions-151006", decimal=False)["data"]["net"][0])
float_row.update(quantity=65, average_price=5.1, last_price=3.1)  # what the kiteconnect SDK would hand over
try:
    print(f"  A2 SDK floats (avg 5.1, ltp 3.1): ACCEPTED {position_line_from_kite_row(float_row)}")
except ValueError as exc:
    refusals.append(f"A2 float row: {exc}")
    print(f"  A2 SDK floats: REFUSED {exc}")
float_ltp_only = convert(load("positions-122104")["data"]["net"][0])
float_ltp_only["last_price"] = 3.1
try:
    print(f"  A2b float last_price only: ACCEPTED {position_line_from_kite_row(float_ltp_only)}")
except ValueError as exc:
    print(f"  A2b float last_price only: REFUSED {exc}")

flat = convert(load("positions-151006")["data"]["net"][0])
try:
    print(f"  A3 flat row through parser (avg int 0): ACCEPTED {position_line_from_kite_row(flat)}")
except ValueError as exc:
    print(f"  A3 flat row through parser: REFUSED {exc}  (not silently a 0-price holding)")
try:
    BrokerPositionLine(SYMBOL, 0, Decimal(0))
    print("  A3b BrokerPositionLine(qty 0, avg 0): ACCEPTED")
except ValueError as exc:
    print(f"  A3b BrokerPositionLine(qty 0, avg 0): REFUSED {exc}")
a3c = compare({CONTRACT: 0}, {"S1": record}, at=ist("2026-10-16 15:10:09"), clock=clock)
print(f"  A3c compare with explicit 0-unit line: mismatches={len(a3c.mismatches)}")

print("\n== refusals hit (product code, real data) ==")
for r in refusals:
    print(f"  - {r}")
print(f"\nSUMMARY: {sum(ok for _, ok, _ in results)}/{len(results)} PASS")
