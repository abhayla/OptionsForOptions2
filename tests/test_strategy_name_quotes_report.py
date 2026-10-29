"""GC-TPD R-9: the pure decision of scripts/checks/strategy_name_quotes_report.py."""
import importlib.util
import pathlib

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts/checks/strategy_name_quotes_report.py"
spec = importlib.util.spec_from_file_location("strategy_name_quotes_report", SCRIPT)
rep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rep)


def test_a_pair_wrapping_the_whole_name_is_reported():
    out = rep.report([(1, '"Short Iron Condor"'), (2, "Short Strangle")])
    assert out == ["quoted names: 1", "strategy 1 name '\"Short Iron Condor\"'"]


def test_a_quote_inside_a_name_is_not_reported():
    assert rep.report([(3, 'O"Neil'), (4, 'say "hi" now'), (5, '"'), (6, None), (7, "")]) == ["quoted names: 0"]
