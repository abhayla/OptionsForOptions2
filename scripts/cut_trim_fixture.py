"""Cut the two reduced real Kite instrument lists the ADR-148 structural trim tests use (NIFTY + SENSEX only, gzipped).

Sources (read-only, saved from Zerodha's live instrument list on the owner's account):
- 2026-10-15 ``instruments.json`` (a token -> row map the 2026-10-15 run saved: symbol, type, strike, expiry, lot);
- 2026-10-21 ``kite-instruments-0840.csv`` (the full Kite CSV downloaded at 08:40 IST).

Outputs, in Kite CSV columns, under ``tests/fixtures/instruments/``:
- ``kite-2026-10-15-nifty-sensex.csv.gz``: the 2026-10-15 rows. The JSON holds no exchange token, segment or tick
  size, so: exchange token = instrument token >> 8 (Kite's documented token layout; checked below against every token
  the 2026-10-21 list still carries), segment/exchange from the underlying (NIFTY -> NFO, SENSEX -> BFO), tick size
  from the 2026-10-21 list's row for the same underlying + expiry + type. The index rows are the 2026-10-21 ones.
- ``kite-2026-10-21-nifty-sensex.csv.gz``: every 2026-10-21 row whose name is NIFTY or SENSEX on NFO/BFO, plus the two
  index rows, unchanged.

Run: python scripts/cut_trim_fixture.py <2026-10-15 instruments.json> <2026-10-21 kite csv> <output dir>
"""
from __future__ import annotations

import csv
import gzip
import io
import json
import sys
from pathlib import Path

COLUMNS = ["instrument_token", "exchange_token", "tradingsymbol", "name", "last_price", "expiry", "strike",
           "tick_size", "lot_size", "instrument_type", "segment", "exchange"]
EXCHANGE = {"NIFTY": "NFO", "SENSEX": "BFO"}
INDEX_SYMBOLS = {("NSE", "NIFTY 50"), ("BSE", "SENSEX")}


def _write(path: Path, rows: list[dict]) -> None:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    with gzip.GzipFile(path, "wb", mtime=0) as out:  # mtime=0: the same input always gives the same bytes
        out.write(buf.getvalue().encode("utf-8"))


def main(old_json: str, new_csv: str, out_dir: str) -> int:
    with open(new_csv, encoding="utf-8", newline="") as fh:
        new = list(csv.DictReader(fh))
    index_rows = [r for r in new if r["segment"] == "INDICES" and (r["exchange"], r["tradingsymbol"]) in INDEX_SYMBOLS]
    kept_new = [r for r in new if r["name"] in EXCHANGE and r["exchange"] == EXCHANGE[r["name"]]]
    by_token = {r["instrument_token"]: r for r in kept_new}
    ticks = {(r["name"], r["expiry"], r["instrument_type"]): r["tick_size"] for r in kept_new}

    with open(old_json, encoding="utf-8") as fh:
        old = json.load(fh)  # float-ok: strikes and lots are kept as the JSON's own strings/ints, never computed
    old_rows = list(index_rows)
    for token, row in sorted(old.items(), key=lambda kv: int(kv[0])):
        if row.get("type") not in ("CE", "PE", "FUT"):
            continue
        name = row["group"].split(" ")[0]
        if name not in EXCHANGE:
            continue
        exchange_token = str(int(token) >> 8)
        carried = by_token.get(token)
        if carried is not None and carried["exchange_token"] != exchange_token:
            raise SystemExit(f"token {token}: derived exchange token {exchange_token} != list's "
                             f"{carried['exchange_token']}")
        tick = ticks.get((name, row["expiry"], row["type"]))
        if tick is None:  # an expiry gone by 2026-10-21: the same underlying + type's tick on the nearest expiry
            tick = next(t for (n, _e, ty), t in sorted(ticks.items()) if n == name and ty == row["type"])
        old_rows.append({"instrument_token": token, "exchange_token": exchange_token, "tradingsymbol": row["symbol"],
                         "name": name, "last_price": "0", "expiry": row["expiry"], "strike": row["strike"],
                         "tick_size": tick, "lot_size": str(row["lot"]), "instrument_type": row["type"],
                         "segment": f"{EXCHANGE[name]}-{'FUT' if row['type'] == 'FUT' else 'OPT'}",
                         "exchange": EXCHANGE[name]})
    out = Path(out_dir)
    _write(out / "kite-2026-10-15-nifty-sensex.csv.gz", old_rows)
    _write(out / "kite-2026-10-21-nifty-sensex.csv.gz", index_rows + kept_new)
    print(f"2026-10-15: {len(old_rows)} rows; 2026-10-21: {len(index_rows) + len(kept_new)} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
