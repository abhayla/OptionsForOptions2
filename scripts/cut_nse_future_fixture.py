"""Cut the NIFTY index-future rows of a real NSE F&O contract file into a small ADR-148 test fixture (read-only source).

Source: ``NSE_FO_contract_16102026.csv.gz`` as downloaded from NSE on 2026-10-19 (the 19102026 file returned 404).
Output: ``tests/fixtures/instruments/nse-fo-16102026-nifty-futures.csv.gz`` with the columns the parser reads
(``ofo.instruments.freeze_file.REQUIRED_COLUMNS``) plus ``BasePric``, the NIFTY ``FUTIDX`` rows only, values unchanged.
Parse it with ``nse_name="NSE_FO_contract_16102026.csv.gz"`` (the file date comes from the NSE name).

Run: python scripts/cut_nse_future_fixture.py <NSE_FO_contract_16102026.csv.gz> <output.csv.gz>
"""
from __future__ import annotations

import csv
import gzip
import io
import sys

sys.path.insert(0, "backend")
from ofo.instruments.freeze_file import REQUIRED_COLUMNS

COLUMNS = [*REQUIRED_COLUMNS, "BasePric"]


def main(source: str, out_path: str) -> int:
    with gzip.open(source, "rt", encoding="utf-8", newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["FinInstrmNm"] == "FUTIDX" and r["TckrSymb"] == "NIFTY"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    with gzip.GzipFile(out_path, "wb", mtime=0) as out:
        out.write(buf.getvalue().encode("utf-8"))
    print(f"{len(rows)} NIFTY future rows")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
