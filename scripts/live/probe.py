"""Read-only live probe / readback (GC-3 P0 item 1b; ADR-097 (2) and (4), ADR-102).

Four subcommands, each over a recorded folder (``--replay <dir>``, no network) or over the owner's stored Kite session:

* ``holdings [--file F] [--save OUT] [--compare BEFORE]``  the eight compared fields per row, the raw key list
* ``contract EXCHANGE:SYMBOL``                              5-level depth, circuit band, available funds
* ``pnl [--tag-prefix X]``                                  gross P&L from the fills beside Kite's position P&L
* ``audit [--since ISO]``                                   the audit log, hash chain verified (run through dev_run.py)

It only READS: every Kite call goes through ``KiteReads`` / ``KiteMargin`` and the runtime door's allow-list. No order,
modify or cancel call exists here. Nothing prints a token or an api key. Exit codes: 0 ok, 2 a read was refused or bad
(a stop, never a skipped check), 3 a compared fact differs.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import fields
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from ofo.audit.log import AuditChainError
from ofo.audit.models import EventType
from ofo.money import zerodha_paise
from ofo.orders.model import realised_pnl
from ofo.timeutil import IST
from ofo_app import live_market
from ofo_app.audit_store import load_log
from ofo_app.broker_config import load_broker_config
from ofo_app.db import get_engine
from ofo_app.kite_margin import KITE_API_URL, KiteMargin, KiteMarginError
from ofo_app.kite_reads import Holding, KiteReadError, KiteReads, holdings_unchanged
from ofo_app.kite_replies import KiteReplyError, fills_from_reply, kite_money

OK, REFUSED, DIFFERS = 0, 2, 3
DEPTH_LEVELS = 5
AUDIT_TYPES = (EventType.ORDER_PREPARED, EventType.BROKER_RESPONSE_RECORDED, EventType.EXECUTION_RECORDED)
_RECORDER_FIELDS = ("quantity", "t1", "collateral")  # the recorder's snapshot keeps three of the eight fields
_INSTRUMENT = re.compile(r"[A-Z0-9_-]+:[A-Z0-9_-]+", re.ASCII)
_DEV_DB = "ofo_dev"
_REPLAY = "replay"  # placeholder credentials for a replay client; nothing is sent


class ProbeStop(Exception):
    """A stop: the message is printed, the exit code is 2."""


def money(value: Decimal) -> str:
    return f"{zerodha_paise(value):.2f}"


# ---- transports: replay and recording ----

class Recorder:
    """Wraps a transport and keeps the last reply text per path (the raw JSON), so the raw key list and depth are
    read from exactly what Kite sent. The headers (which carry the token) are passed through and never stored."""

    def __init__(self, inner: Callable) -> None:
        self._inner = inner
        self.raw: dict[str, str] = {}

    def __call__(self, method, url, headers, body):
        status, text = self._inner(method, url, headers, body)
        self.raw[url.removeprefix(KITE_API_URL).split("?")[0]] = text
        return status, text


class FilesTransport:
    """Serves recorded reply texts by path; any path not recorded is a refused read."""

    def __init__(self, texts: dict[str, str]) -> None:
        self._texts = texts

    def __call__(self, method, url, headers, body):
        path = url.removeprefix(KITE_API_URL).split("?")[0]
        if method != "GET" or path not in self._texts:
            return 404, ""
        return 200, self._texts[path]


def _latest(folder: Path, prefix: str, *, first: bool = False) -> Path:
    found = sorted(folder.glob(f"{prefix}-*.json"))
    if not found:
        raise ProbeStop(f"no {prefix}-*.json in {folder}")
    return found[0] if first else found[-1]


def _envelope(data: object) -> str:
    return json.dumps({"status": "success", "data": data}, default=str)


# ---- clients ----

def _owner_clients(recorder_wrap: bool) -> tuple[KiteReads, KiteMargin | None, Recorder | None]:
    """The owner's stored Kite session, built the way the Execute route builds it (``live_market`` readers). The token
    stays inside those readers; this script never reads or prints it."""
    async def build():
        market = live_market.LiveMarket()
        market._config = load_broker_config()  # the module's own object, as the lifespan sets it
        live_market.set_current(market)
        return await live_market.owner_kite_reads(), await live_market.owner_margin_client()

    reads_pair, margin = asyncio.run(build())
    if reads_pair is None or margin is None:
        raise ProbeStop("no stored Kite session (owner not connected)")
    reads = reads_pair[1]
    recorder = None
    if recorder_wrap:
        recorder = Recorder(reads._call)  # wrap the transport; headers are not read
        reads._call = recorder
    return reads, margin, recorder


def _replay_clients(folder: Path, texts: dict[str, str]) -> tuple[KiteReads, KiteMargin, Recorder]:
    recorder = Recorder(FilesTransport(texts))
    return (KiteReads(api_key=_REPLAY, access_token=_REPLAY, transport=recorder),
            KiteMargin(api_key=_REPLAY, access_token=_REPLAY, transport=recorder), recorder)


# ---- holdings ----

def _load_holdings_file(path: Path) -> tuple[str, object]:
    """('kite', reply text) for a Kite reply or this script's saved snapshot; ('recorder', {key: row}) for the
    recorder's three-field snapshot (a dict keyed EXCHANGE:SYMBOL)."""
    try:
        text = path.read_text(encoding="utf-8")
        doc = json.loads(text, parse_float=Decimal)
    except (OSError, ValueError):
        raise ProbeStop(f"cannot read holdings file {path.name}") from None
    if isinstance(doc, dict) and "status" in doc and "data" in doc:
        return "kite", text
    if isinstance(doc, dict) and set(doc) == {"holdings"}:
        return "kite", _envelope(doc["holdings"])
    if isinstance(doc, dict) and doc and all(isinstance(v, dict) and ":" in k for k, v in doc.items()):
        return "recorder", doc
    raise ProbeStop(f"holdings file {path.name}: kite_read_bad_reply")


def _read_kite_holdings(text: str) -> tuple[tuple[Holding, ...], list[str]]:
    reads, _, recorder = _replay_clients(Path("."), {"/portfolio/holdings": text})
    rows = reads.fetch_holdings()
    raw = json.loads(recorder.raw["/portfolio/holdings"]).get("data")
    keys = sorted(raw[0]) if isinstance(raw, list) and raw else []
    return rows, keys


def _holding_line(h: Holding) -> str:
    return f"holding {h.exchange}:{h.tradingsymbol} isin={h.isin} " + " ".join(
        f"{f.name}={getattr(h, f.name)}" for f in fields(h) if f.type == "int")


def _holdings_changes(before: Sequence[Holding], after: Sequence[Holding]) -> list[str]:
    out = []
    for c in holdings_unchanged(before, after):
        name = f"{c.key[0]}:{c.key[1]}"
        if c.before is None or c.after is None:
            out.append(f"holding_{'added' if c.before is None else 'missing'} {name}")
            continue
        out.extend(f"holding_changed {name} {f.name} before={getattr(c.before, f.name)} "
                   f"after={getattr(c.after, f.name)}"
                   for f in fields(c.before) if getattr(c.before, f.name) != getattr(c.after, f.name))
    return out


def _recorder_changes(before: dict, after: dict) -> list[str]:
    out = []
    for key in sorted(before.keys() | after.keys()):
        if key not in before or key not in after:
            out.append(f"holding_{'added' if key not in before else 'missing'} {key}")
            continue
        out.extend(f"holding_changed {key} {f} before={before[key].get(f)} after={after[key].get(f)}"
                   for f in _RECORDER_FIELDS if before[key].get(f) != after[key].get(f))
    return out


def cmd_holdings(args) -> int:
    if args.replay:
        folder = Path(args.replay)
        path = folder / args.file if args.file else _latest(folder, "holdings-before", first=True)
        shape, content = _load_holdings_file(path)
        if shape == "recorder":
            return _holdings_recorder(args, folder, content, path)
        rows, keys = _read_kite_holdings(content)
    else:
        reads, _, recorder = _owner_clients(True)
        rows = reads.fetch_holdings()
        raw = json.loads(recorder.raw["/portfolio/holdings"]).get("data")
        keys = sorted(raw[0]) if isinstance(raw, list) and raw else []
    print(f"holdings_rows {len(rows)}")
    for h in rows:
        print(_holding_line(h))
    print("raw_first_row_keys " + (", ".join(keys) if keys else "(no rows)"))
    if args.save:
        Path(args.save).write_text(json.dumps({"holdings": [{f.name: getattr(h, f.name) for f in fields(h)}
                                                            for h in rows]}, indent=1), encoding="utf-8")
        print(f"saved {args.save}")
    if args.compare:
        shape, before = _load_holdings_file(_resolve(args, args.compare))
        if shape != "kite":
            raise ProbeStop("holdings_shapes_differ: the before file is a recorder snapshot, the read is a full reply")
        changes = _holdings_changes(_read_kite_holdings(before)[0], rows)
        return _report_changes(changes)
    return OK


def _holdings_recorder(args, folder: Path, snapshot: dict, path: Path) -> int:
    """The recorder's snapshot is NOT a Kite reply: three of the eight fields, keyed by symbol. It is printed as it is
    and compared on those three fields only; the five fields it did not record are named, never invented."""
    print(f"shape recorder_snapshot (not a Kite reply) file={path.name}")
    print(f"holdings_rows {len(snapshot)}")
    for key in sorted(snapshot):
        print(f"holding {key} " + " ".join(f"{f}={snapshot[key].get(f)}" for f in _RECORDER_FIELDS))
    first = snapshot[sorted(snapshot)[0]]
    print("raw_first_row_keys " + ", ".join(sorted(first)))
    print("not_recorded isin, used_quantity, authorised_quantity (and the symbol/exchange fields are the key)")
    if args.save:
        raise ProbeStop("--save needs a full Kite reply; this file is a recorder snapshot")
    if args.compare:
        shape, before = _load_holdings_file(_resolve(args, args.compare))
        if shape != "recorder":
            raise ProbeStop("holdings_shapes_differ: one file is a recorder snapshot, the other a full reply")
        return _report_changes(_recorder_changes(before, snapshot))
    return OK


def _resolve(args, name: str) -> Path:
    path = Path(name)
    if not path.exists() and args.replay:
        path = Path(args.replay) / name
    return path


def _report_changes(changes: list[str]) -> int:
    if not changes:
        print("holdings_unchanged")
        return OK
    for line in changes:
        print(line)
    return DIFFERS


# ---- contract ----

def _depth_lines(raw_quote: str, instrument: str) -> list[str]:
    data = json.loads(raw_quote, parse_float=Decimal).get("data")
    quote = data.get(instrument) if isinstance(data, dict) else None
    depth = quote.get("depth") if isinstance(quote, dict) else None
    if not isinstance(depth, dict):
        raise ProbeStop("kite_read_bad_reply: the quote has no depth")
    lines = []
    for side in ("buy", "sell"):
        levels = depth.get(side)
        if not isinstance(levels, list):
            raise ProbeStop(f"kite_read_bad_reply: depth {side} missing")
        for n, lv in enumerate(levels[:DEPTH_LEVELS], start=1):
            lines.append(f"depth_{side} L{n} price={money(kite_money(lv.get('price'), 'price'))} "
                         f"quantity={lv.get('quantity')} orders={lv.get('orders')}")
    return lines


def _contract_texts(folder: Path, instrument: str) -> dict[str, str]:
    quote_files = sorted(folder.glob("quote-*.json"))
    fetch = folder / "fetch.json"
    if quote_files:
        quote_text = quote_files[-1].read_text(encoding="utf-8")
    elif fetch.exists() and isinstance(json.loads(fetch.read_text(encoding="utf-8")).get("quote"), dict):
        quote = json.loads(fetch.read_text(encoding="utf-8"))["quote"]
        quote_text = _envelope({instrument: quote})
    else:
        raise ProbeStop(f"no quote-*.json or fetch.json quote in {folder}")
    return {"/quote": quote_text, "/user/margins": _latest(folder, "margins").read_text(encoding="utf-8")}


def cmd_contract(args) -> int:
    instrument = args.instrument
    if not _INSTRUMENT.fullmatch(instrument):
        raise ProbeStop("contract must look like NFO:NIFTY26O1923650CE")
    if args.replay:
        reads, margin, recorder = _replay_clients(Path(args.replay), _contract_texts(Path(args.replay), instrument))
    else:
        reads, margin, recorder = _owner_clients(True)
    bands = reads.fetch_circuit_bands([instrument])
    for line in _depth_lines(recorder.raw["/quote"], instrument):
        print(line)
    if instrument in bands:
        print(f"circuit_band lower={money(bands[instrument][0])} upper={money(bands[instrument][1])}")
    else:
        print("circuit_band unknown (absent or not a valid band)")
    print(f"available_funds {money(margin.fetch_available_funds())}")
    return OK


# ---- pnl ----

def _kite_position_pnl(positions: dict, contracts: set[str]) -> tuple[Decimal, Decimal]:
    pnl = unrealised = Decimal(0)
    for row in positions["net"]:
        if row.get("tradingsymbol") in contracts:
            pnl += kite_money(row.get("pnl"), "pnl")
            unrealised += kite_money(row.get("unrealised"), "unrealised")
    return pnl, unrealised


def cmd_pnl(args) -> int:
    if args.replay:
        folder = Path(args.replay)
        texts = {"/trades": _latest(folder, "trades").read_text(encoding="utf-8"),
                 "/portfolio/positions": _latest(folder, "positions").read_text(encoding="utf-8")}
        if args.tag_prefix:
            texts["/orders"] = _latest(folder, "orders").read_text(encoding="utf-8")
        reads, _, _ = _replay_clients(folder, texts)
    else:
        reads, _, _ = _owner_clients(False)
    trades, positions = reads.fetch_trades(), reads.fetch_positions()
    if args.tag_prefix:
        ids = {o.get("order_id") for o in reads.fetch_orders() if str(o.get("tag") or "").startswith(args.tag_prefix)}
        trades = [t for t in trades if t.get("order_id") in ids]
    try:
        fills = fills_from_reply(trades)
        gross = realised_pnl(fills)
        contracts = {f.contract for f in fills}
        kite_pnl, kite_unrealised = _kite_position_pnl(positions, contracts)
    except (KiteReplyError, ValueError) as exc:
        raise ProbeStop(f"pnl: {exc}") from None
    print(f"fills {len(fills)} contracts {', '.join(sorted(contracts))}")
    for f in fills:
        print(f"fill {f.side.name} {f.quantity} {f.contract} @ {money(f.price)}")
    print(f"gross_pnl_from_fills {money(gross)}")
    print(f"kite_position_pnl {money(kite_pnl)}")
    print(f"kite_position_unrealised {money(kite_unrealised)}")
    if gross != kite_pnl:
        print(f"pnl_differs fills={money(gross)} kite={money(kite_pnl)}")
        return DIFFERS
    print("pnl_equal")
    return OK


# ---- audit ----

def _since(text: str | None) -> datetime.datetime | None:
    if text is None:
        return None
    try:
        when = datetime.datetime.fromisoformat(text)
    except ValueError:
        raise ProbeStop("--since must be an ISO date or time") from None
    return when if when.tzinfo else when.replace(tzinfo=IST)


async def _load_audit():
    engine = get_engine()
    if engine.url.database != _DEV_DB:
        raise ProbeStop(f"audit reads only {_DEV_DB}; DATABASE_URL names another database")
    try:
        async with engine.connect() as conn:
            return await load_log(conn)
    finally:
        await engine.dispose()


def cmd_audit(args) -> int:
    since = _since(args.since)
    try:
        log, anchor = asyncio.run(_load_audit())
    except AuditChainError as exc:
        print(f"hash chain FAILED: {exc}")
        return DIFFERS
    events = log.events
    print(f"hash chain verified rows={len(events)} anchor_count={anchor.count}")
    shown = 0
    for seq, e in enumerate(events, start=1):
        if e.event_type in AUDIT_TYPES and (since is None or e.timestamp >= since):
            print(f"audit_row seq={seq} type={e.event_type.value} at={e.timestamp.isoformat()} "
                  f"correlation={e.correlation_id}")
            shown += 1
    print(f"audit_rows_listed {shown}")
    return OK


# ---- cli ----

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="probe.py", description=__doc__.splitlines()[0])
    p.add_argument("--replay", metavar="DIR", help="read recorded replies from DIR instead of calling Kite")
    sub = p.add_subparsers(dest="command", required=True)
    h = sub.add_parser("holdings")
    h.add_argument("--file", help="replay: the holdings file in DIR (default: the first holdings-before-*.json)")
    h.add_argument("--save", metavar="FILE")
    h.add_argument("--compare", metavar="BEFORE")
    h.set_defaults(run=cmd_holdings)
    c = sub.add_parser("contract")
    c.add_argument("instrument", metavar="EXCHANGE:SYMBOL")
    c.set_defaults(run=cmd_contract)
    n = sub.add_parser("pnl")
    n.add_argument("--tag-prefix")
    n.set_defaults(run=cmd_pnl)
    a = sub.add_parser("audit")
    a.add_argument("--since", metavar="ISO")
    a.set_defaults(run=cmd_audit)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.run(args)
    except KiteReadError as exc:
        print(f"read refused: {exc.code}")
    except KiteMarginError as exc:
        print(f"read refused: {exc.code}")
    except ProbeStop as exc:
        print(f"stop: {exc}")
    return REFUSED


if __name__ == "__main__":
    sys.exit(main())
