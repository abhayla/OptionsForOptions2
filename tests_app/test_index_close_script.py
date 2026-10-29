"""GC-TP 5a: scripts/checks/index_close.py refuses anything but ofo_dev, prints one line per answer state, and
uses the SENSEX index's KITE token (not the exchange token) from the catalogue."""
import datetime
import importlib.util
import pathlib
from decimal import Decimal

import pytest
from ofo.instruments.models import BSE_INDEX, INDEX_ROWS, ZERODHA
from ofo.instruments.parser import parse_instruments_csv

REPO = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("index_close", REPO / "scripts" / "checks" / "index_close.py")
index_close = importlib.util.module_from_spec(spec)
spec.loader.exec_module(index_close)
DAY = datetime.date(2026, 10, 29)
HOST = "postgresql://example-host:5432/"


@pytest.mark.parametrize("url", [HOST + "ofo_test", HOST + "ofo_prod", HOST + "ofo_dev_old",
                                 "postgresql://ofo_dev@example-host/ofo_test", ""])
def test_refuses_unless_database_url_names_ofo_dev(url, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", url)
    with pytest.raises(SystemExit) as exit_:
        index_close.main(["SENSEX", "2026-10-29"])
    assert str(exit_.value).startswith("REFUSED") and "example-host" not in str(exit_.value)


def test_refuses_when_database_url_is_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as exit_:
        index_close.main(["SENSEX", "2026-10-29"])
    assert str(exit_.value).startswith("REFUSED")


def test_ofo_dev_passes_the_guard():
    index_close.refuse_unless_dev(HOST + "ofo_dev")  # no exit


@pytest.mark.parametrize("argv", [[], ["SENSEX"], ["BANKNIFTY", "2026-10-29"], ["SENSEX", "29-10-2026"]])
def test_bad_arguments_exit_with_usage(argv):
    with pytest.raises(SystemExit):
        index_close.parse_args(argv)


def test_the_output_lines():
    assert index_close.result_line("SENSEX", DAY, Decimal("83211.07")) == "SENSEX 2026-10-29 close 83211.07"
    assert index_close.result_line("SENSEX", DAY, None) == "SENSEX 2026-10-29 no candle"
    assert (index_close.failed_line("SENSEX", DAY, RuntimeError("token tok-SECRET"))
            == "SENSEX 2026-10-29 read failed: RuntimeError")


def test_script_index_keys_are_the_catalogue_index_rows():
    assert set(index_close.INDEXES.values()) == set(INDEX_ROWS)


def test_the_catalogue_row_for_sensex_carries_kites_instrument_token_not_the_exchange_token():
    csv = REPO / "tests" / "fixtures" / "kite_ws" / "instruments-2026-10-08-subscribed.csv"
    listed = list(parse_instruments_csv(csv))
    seg, exchange_token = index_close.INDEXES["SENSEX"]
    row = [lc for lc in listed if (lc.contract.exchange_segment, lc.contract.exchange_token) == (seg, exchange_token)]
    assert seg == BSE_INDEX and len(row) == 1
    kite_token = row[0].ref(ZERODHA).broker_token
    assert kite_token == "265" and exchange_token == 1  # noqa: S105 - the URL needs 265
