"""GC-TPD R-37: the pure decision of scripts/checks/paper_orders_order_check.py (red on bad, green on good)."""
import datetime
import importlib.util
import pathlib

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts/checks/paper_orders_order_check.py"
spec = importlib.util.spec_from_file_location("paper_orders_order_check", SCRIPT)
chk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chk)

T = datetime.datetime(2026, 10, 1, 9, 15, tzinfo=datetime.UTC)
H = datetime.timedelta(hours=1)


def test_exit_before_open_is_a_violation():
    bad = chk.violations([(7, 1, "exit", T), (7, 1, "open", T + H)])
    assert bad == [(7, 1, "exit", T, T + H)]
    assert chk.report(bad)[0] == "violations: 1"


def test_good_order_book_has_no_violation():
    rows = [(7, 1, "open", T), (7, 1, "add", T + H), (7, 1, "exit", T + 2 * H), (8, 1, "settle", T + H)]
    assert chk.violations(rows) == []
    assert chk.report([]) == ["violations: 0"]


def test_equal_time_is_not_a_violation():
    assert chk.violations([(7, 1, "open", T), (7, 1, "exit", T)]) == []


def test_other_contract_or_strategy_does_not_mix():
    assert chk.violations([(7, 1, "exit", T), (7, 2, "open", T + H), (8, 1, "open", T + H)]) == []
