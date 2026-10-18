"""GC-3 P0 item 1b: the read-only probe (scripts/live/probe.py) over recorded replies. Non-DB; the audit part runs once
against ofo_dev through dev_run.py (reported in the PR), and its refusal of any other database is tested here.

Recorded inputs: the 2026-10-16 trades / positions / orders / quote replies in ``tests/fixtures/kite_replies`` and the
real funds reply ``kite_probe/margins-151006.json``. The owner's holdings are not committed: the recorder-snapshot
fixture has the real file's SHAPE (symbol-keyed, quantity / t1 / collateral) with placeholder symbols, and the full
Kite reply shape is the documented fixture."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import sys
from http import HTTPStatus
from pathlib import Path

import pytest
from ofo.timeutil import IST
from ofo_app.kite_reads import KiteReads
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
REPLIES = ROOT / "tests" / "fixtures" / "kite_replies"
PROBE_FIXTURES = Path(__file__).parent / "fixtures" / "kite_probe"
SECRET, API_KEY = "tok-SECRET-123", "key-SECRET-456"
CONTRACT = "NIFTY26O1923650CE"
INSTRUMENT = "NFO:" + CONTRACT
OK, REFUSED, DIFFERS = 0, 2, 3
LEVELS = 10  # five a side

spec = importlib.util.spec_from_file_location("probe", ROOT / "scripts" / "live" / "probe.py")
probe = importlib.util.module_from_spec(spec)
sys.modules["probe"] = probe
spec.loader.exec_module(probe)


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """A replay folder named the way the recorder names its files."""
    for src, dst in [(REPLIES / "trades-151006.json", "trades-151006.json"),
                     (REPLIES / "positions-151006.json", "positions-151006.json"),
                     (REPLIES / "orders-151006.json", "orders-151006.json"),
                     (REPLIES / "quote-150720.json", "quote-150720.json"),
                     (PROBE_FIXTURES / "margins-151006.json", "margins-151006.json"),
                     (PROBE_FIXTURES / "holdings-recorder-snapshot.json", "holdings-before-1.json"),
                     (REPLIES / "holdings-documented.json", "holdings-before-2.json")]:
        shutil.copy(src, tmp_path / dst)
    return tmp_path


def run(capsys, folder: Path | None, *argv: str) -> tuple[int, str]:
    args = (["--replay", str(folder)] if folder else []) + list(argv)
    code = probe.main(args)
    return code, capsys.readouterr().out


def edit(path: Path, change) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    change(doc)
    path.write_text(json.dumps(doc), encoding="utf-8")


# ---- (a) holdings ----

def test_core_pnl_from_the_two_real_fills_equals_kites_minus_130(folder, capsys) -> None:
    """Core: (3.10 - 5.10) x 65 = -130.00 from the fills (ADR-102) beside Kite's position pnl -130, equal, exit 0."""
    code, out = run(capsys, folder, "pnl")
    assert code == OK
    assert "fill BUY 65 NIFTY26O1923650CE @ 5.10" in out
    assert "fill SELL 65 NIFTY26O1923650CE @ 3.10" in out
    assert "gross_pnl_from_fills -130.00" in out
    assert "kite_position_pnl -130.00" in out
    assert out.rstrip().endswith("pnl_equal")


def test_recorder_snapshot_prints_rows_and_raw_keys_and_names_what_it_lacks(folder, capsys) -> None:
    """Attack 1: the recorder's snapshot is not a Kite reply; printed as it is, unrecorded fields named."""
    code, out = run(capsys, folder, "holdings", "--file", "holdings-before-1.json")
    assert code == OK
    assert "holding BSE:AAAHOLD quantity=100 t1=0 collateral=0" in out
    assert "raw_first_row_keys collateral, quantity, t1" in out
    assert "not_recorded isin, used_quantity, authorised_quantity" in out


def test_recorder_snapshots_unchanged_exit_0_and_one_quantity_changed_exit_3(folder, capsys) -> None:
    """Attack 1: unchanged -> holdings_unchanged exit 0; one quantity changed -> exit 3 naming symbol and field."""
    shutil.copy(folder / "holdings-before-1.json", folder / "holdings-after-1.json")
    code, out = run(capsys, folder, "holdings", "--file", "holdings-after-1.json",
                    "--compare", "holdings-before-1.json")
    assert (code, out.splitlines()[-1]) == (OK, "holdings_unchanged")
    edit(folder / "holdings-after-1.json", lambda d: d["NSE:BBBHOLD"].update(quantity="8"))
    code, out = run(capsys, folder, "holdings", "--file", "holdings-after-1.json",
                    "--compare", "holdings-before-1.json")
    assert code == DIFFERS
    assert "holding_changed NSE:BBBHOLD quantity before=7 after=8" in out
    assert "holdings_unchanged" not in out


def test_full_reply_prints_the_eight_fields_and_the_raw_key_list(folder, capsys) -> None:
    """The documented full reply: the eight compared fields per row and the sorted keys of the raw first row."""
    code, out = run(capsys, folder, "holdings", "--file", "holdings-before-2.json")
    assert code == OK
    assert ("holding BSE:GOLDBEES isin=INF204KB17I5 quantity=2 t1_quantity=0 used_quantity=0 authorised_quantity=0 "
            "collateral_quantity=0") in out
    raw = json.loads((folder / "holdings-before-2.json").read_text(encoding="utf-8"))["data"][0]
    assert "raw_first_row_keys " + ", ".join(sorted(raw)) in out


def test_save_then_compare_detects_a_changed_field_and_a_removed_row(folder, capsys, tmp_path) -> None:
    """--save writes the 8-field snapshot; --compare reuses holdings_unchanged: change/missing exit 3."""
    saved = tmp_path / "saved.json"
    assert run(capsys, folder, "holdings", "--file", "holdings-before-2.json", "--save", str(saved))[0] == OK
    code, out = run(capsys, folder, "holdings", "--file", "holdings-before-2.json", "--compare", str(saved))
    assert (code, out.splitlines()[-1]) == (OK, "holdings_unchanged")
    edit(saved, lambda d: d["holdings"][0].update(used_quantity=1))
    code, out = run(capsys, folder, "holdings", "--file", "holdings-before-2.json", "--compare", str(saved))
    assert code == DIFFERS and "holding_changed BSE:GOLDBEES used_quantity before=1 after=0" in out
    edit(saved, lambda d: d["holdings"].clear())
    code, out = run(capsys, folder, "holdings", "--file", "holdings-before-2.json", "--compare", str(saved))
    assert code == DIFFERS and "holding_added BSE:GOLDBEES" in out


def test_shapes_that_differ_are_a_stop_not_a_comparison(folder, capsys) -> None:
    """A recorder snapshot against a full reply cannot be compared: exit 2, never 'unchanged'."""
    code, out = run(capsys, folder, "holdings", "--file", "holdings-before-2.json",
                    "--compare", "holdings-before-1.json")
    assert code == REFUSED and "holdings_shapes_differ" in out and "holdings_unchanged" not in out


@pytest.mark.parametrize("field", ["tradingsymbol", "exchange", "isin", "quantity", "t1_quantity", "used_quantity",
                                   "authorised_quantity", "collateral_quantity"])
def test_a_row_lacking_one_of_the_eight_fields_is_bad_reply_exit_2(folder, capsys, field) -> None:
    """Attack 2: never an empty list, never a skipped check."""
    edit(folder / "holdings-before-2.json", lambda d: d["data"][0].pop(field))
    code, out = run(capsys, folder, "holdings", "--file", "holdings-before-2.json")
    assert code == REFUSED and "kite_read_bad_reply" in out
    assert "holdings_rows" not in out


def test_an_unreadable_or_unknown_holdings_file_is_a_stop(folder, capsys) -> None:
    """A file that is neither a Kite reply nor a snapshot is exit 2."""
    (folder / "holdings-before-3.json").write_text('{"x": 1}', encoding="utf-8")
    assert run(capsys, folder, "holdings", "--file", "holdings-before-3.json")[0] == REFUSED
    assert run(capsys, folder, "holdings", "--file", "missing.json")[0] == REFUSED


# ---- (c) pnl ----

def test_an_edited_fill_price_makes_the_pnl_differ_exit_3(folder, capsys) -> None:
    """Attack 3: fill price edited -> gross differs from Kite's pnl -> exit 3 and the difference is printed."""
    edit(folder / "trades-151006.json", lambda d: d["data"][1].update(average_price="3.2"))
    code, out = run(capsys, folder, "pnl")
    assert code == DIFFERS
    assert "gross_pnl_from_fills -123.50" in out and "pnl_differs fills=-123.50 kite=-130.00" in out


def test_tag_prefix_selects_the_fills_of_those_orders(folder, capsys) -> None:
    """--tag-prefix keeps the fills whose order carries the tag; both real orders are OFS1V1L0 / OFS1V2L0."""
    code, out = run(capsys, folder, "pnl", "--tag-prefix", "OFS1")
    assert code == OK and "gross_pnl_from_fills -130.00" in out
    code, out = run(capsys, folder, "pnl", "--tag-prefix", "NOPE")
    assert code == REFUSED and "at least one fill" in out


SAVED = {"orders": "orders-151006.json", "trades": "trades-151006.json", "positions": "positions-151006.json"}


def _without_saved_lines(out: str) -> str:
    return "\n".join(line for line in out.splitlines() if not line.startswith("saved "))


def test_save_dir_keeps_the_exact_replies_and_replay_gives_identical_output(folder, capsys, tmp_path) -> None:
    """Core: pnl --save-dir writes the 3 raw replies byte for byte; --replay of that folder prints the same lines."""
    target = tmp_path / "after-exit"
    code, first = run(capsys, folder, "pnl", "--tag-prefix", "OFS1", "--save-dir", str(target))
    assert code == OK and sorted(os.listdir(target)) == [
        "orders-saved.json", "positions-saved.json", "trades-saved.json"]
    for name, original in SAVED.items():
        assert (target / f"{name}-saved.json").read_bytes() == (folder / original).read_bytes()
    code, second = run(capsys, target, "pnl", "--tag-prefix", "OFS1")
    assert code == OK and second == _without_saved_lines(first) + "\n"
    assert "gross_pnl_from_fills -130.00" in second


def test_save_dir_refuses_a_folder_that_is_not_empty_and_writes_nothing(folder, capsys, tmp_path) -> None:
    """A non-empty DIR (or a file) is refused before any read; its content is untouched (never overwritten)."""
    target = tmp_path / "taken"
    target.mkdir()
    (target / "orders-saved.json").write_text("keep", encoding="utf-8")
    code, out = run(capsys, folder, "pnl", "--save-dir", str(target))
    assert code == REFUSED and "not empty" in out and "gross_pnl" not in out
    assert os.listdir(target) == ["orders-saved.json"]
    assert (target / "orders-saved.json").read_text(encoding="utf-8") == "keep"
    plain_file = tmp_path / "a-file"
    plain_file.write_text("x", encoding="utf-8")
    assert run(capsys, folder, "pnl", "--save-dir", str(plain_file))[0] == REFUSED


def test_save_dir_accepts_an_existing_empty_folder_and_saves_orders_without_a_tag_prefix(
        folder, capsys, tmp_path) -> None:
    """--save-dir without --tag-prefix still saves orders (3 of 3), and an existing empty DIR is fine."""
    target = tmp_path / "empty"
    target.mkdir()
    code, out = run(capsys, folder, "pnl", "--save-dir", str(target))
    assert code == OK and "gross_pnl_from_fills -130.00" in out
    assert (target / "orders-saved.json").read_bytes() == (folder / SAVED["orders"]).read_bytes()
    assert len(os.listdir(target)) == len(SAVED)


def test_a_fill_that_leaves_the_contract_open_is_a_stop(folder, capsys) -> None:
    """realised_pnl refuses open fills: only the BUY -> exit 2, no gross figure printed."""
    edit(folder / "trades-151006.json", lambda d: d["data"].pop(1))
    code, out = run(capsys, folder, "pnl")
    assert code == REFUSED and "still open" in out and "gross_pnl" not in out


# ---- (b) contract ----

def test_contract_prints_five_levels_each_side_band_and_funds(folder, capsys) -> None:
    """The real 15:07:20 quote: buy L1 3.30 x 55250 (32 orders), 5 levels a side, band 0.05-81.55, funds 873.00."""
    code, out = run(capsys, folder, "contract", INSTRUMENT)
    assert code == OK
    assert "depth_buy L1 price=3.30 quantity=55250 orders=32" in out
    assert len(re.findall(r"^depth_(buy|sell) L[1-5] ", out, re.MULTILINE)) == LEVELS
    assert "depth_sell L5 price=3.55 quantity=35945 orders=15" in out
    assert "circuit_band lower=0.05 upper=81.55" in out
    assert "available_funds 873.00" in out


def test_contract_without_a_band_says_unknown_and_a_bad_name_is_refused(folder, capsys) -> None:
    """A quote with no circuit limits prints 'unknown' (never a guess); a malformed instrument is exit 2."""
    def drop(doc):
        doc["data"][INSTRUMENT].pop("lower_circuit_limit")
    edit(folder / "quote-150720.json", drop)
    code, out = run(capsys, folder, "contract", INSTRUMENT)
    assert code == OK and "circuit_band unknown" in out
    assert run(capsys, folder, "contract", "nifty;rm")[0] == REFUSED


def test_contract_with_no_depth_is_bad_reply(folder, capsys) -> None:
    """A quote without depth is a stop (exit 2)."""
    edit(folder / "quote-150720.json", lambda d: d["data"][INSTRUMENT].pop("depth"))
    code, out = run(capsys, folder, "contract", INSTRUMENT)
    assert code == REFUSED and "depth" in out


# ---- safety: no secret, no write call ----

def test_live_path_never_prints_the_token_or_api_key(monkeypatch, capsys) -> None:
    """Attack 4: a live-shaped client with a fake token and key, through success and failure paths."""
    seen = []

    def transport(method, url, headers, body):
        seen.append((method, url))
        if url.endswith("/portfolio/holdings"):
            return 200, (REPLIES / "holdings-documented.json").read_text(encoding="utf-8")
        return 403, '{"error_type": "TokenException"}'

    def fake(_wrap):
        rec = probe.Recorder(transport)
        return KiteReads(api_key=API_KEY, access_token=SECRET, transport=rec), None, rec

    monkeypatch.setattr(probe, "_owner_clients", fake)
    assert probe.main(["holdings"]) == OK
    assert probe.main(["pnl"]) == REFUSED  # /trades refused: a stop, with a code
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err and API_KEY not in captured.out + captured.err
    assert "read refused: kite_read_token" in captured.out
    assert seen == [("GET", "https://api.kite.trade/portfolio/holdings"), ("GET", "https://api.kite.trade/trades")]


def test_no_live_session_is_a_stop(monkeypatch, capsys) -> None:
    """Live with no stored session: exit 2 'no stored Kite session', nothing sent."""
    async def none():
        return None

    live_market = probe.live_market
    monkeypatch.setattr(live_market, "owner_kite_reads", none)
    monkeypatch.setattr(live_market, "owner_margin_client", none)
    monkeypatch.setattr(probe, "load_broker_config", object)
    assert probe.main(["holdings"]) == REFUSED
    assert "no stored Kite session" in capsys.readouterr().out


def test_the_script_has_no_order_path() -> None:
    """Attack 5: no order endpoint, no place/modify/cancel verb, no POST, no direct network import."""
    source = (ROOT / "scripts" / "live" / "probe.py").read_text(encoding="utf-8")
    for banned in ("/orders/regular", "place_order", "modify_order", "cancel_order", "POST", "urllib", "httpx",
                   "requests", "/gtt"):
        assert banned not in source
    assert set(re.findall(r'"(/[a-z/]+)"', source)) <= {"/portfolio/holdings", "/trades", "/portfolio/positions",
                                                         "/orders", "/quote", "/user/margins"}


def test_the_replay_transport_refuses_any_unrecorded_path_and_any_non_get() -> None:
    """The replay serves recorded paths by GET only; anything else is a 404 (a refused read), never a made-up reply."""
    t = probe.FilesTransport({"/trades": "{}"})
    assert t("GET", "https://api.kite.trade/trades", {}, None) == (200, "{}")
    assert t("POST", "https://api.kite.trade/trades", {}, None)[0] == HTTPStatus.NOT_FOUND
    assert t("GET", "https://api.kite.trade/orders/regular", {}, None)[0] == HTTPStatus.NOT_FOUND


# ---- (d) audit guards ----

def test_audit_refuses_any_database_but_ofo_dev(monkeypatch, capsys) -> None:
    """Never ofo_test: the audit read stops before connecting when DATABASE_URL names another database."""
    class Engine:
        url = make_url("postgresql+asyncpg://127.0.0.1:5432/ofo_test")

        async def dispose(self) -> None:
            raise AssertionError("must not connect")

    monkeypatch.setattr(probe, "get_engine", Engine)
    assert probe.main(["audit"]) == REFUSED
    assert "audit reads only ofo_dev" in capsys.readouterr().out


def test_since_reads_iso_as_ist_and_refuses_junk(capsys) -> None:
    """--since: a naive ISO time is IST; junk is a stop."""
    assert probe._since("2026-10-16T12:00:00").utcoffset() == IST.utcoffset(None)
    assert probe._since(None) is None
    assert probe.main(["audit", "--since", "yesterday"]) == REFUSED
