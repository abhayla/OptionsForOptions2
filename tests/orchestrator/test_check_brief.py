"""AC-1 (REQ-067, process tooling): a brief's spec quotes are checked verbatim against the spec before dispatch."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
_spec = importlib.util.spec_from_file_location("check_brief", ROOT / "scripts" / "orchestrator" / "check_brief.py")
check_brief = importlib.util.module_from_spec(_spec)
sys.modules["check_brief"] = check_brief
_spec.loader.exec_module(check_brief)


def run(tmp_path, text, *extra):
    brief = tmp_path / "brief.md"
    brief.write_text(text, encoding="utf-8")
    return check_brief.main([str(brief), "--root", str(ROOT), *extra])


def test_ac1_misquote_of_req060_ac2_fails_and_names_it(capsys):
    """AC-1: the reconstructed W-037 brief misquotes REQ-060 AC-2 -> exit 1, output names the citation and line."""
    code = check_brief.main([str(FIXTURES / "brief_bad_w037.md"), "--root", str(ROOT)])
    out = capsys.readouterr().out
    assert code == 1
    assert 'FAIL    line 3: REQ-060 AC-2: "every run compares all non-exited strategies"' in out
    assert "nearest spec line:" in out


def test_ac1_exact_quote_of_req058_ac6_passes_across_a_line_wrap(capsys):
    """AC-1: an exact quote (wrapped over two lines in the brief, over two in the YAML) passes."""
    code = check_brief.main([str(FIXTURES / "brief_good_req058.md"), "--root", str(ROOT)])
    assert code == 0
    assert "1 OK, 0 FAIL, 0 UNCITED" in capsys.readouterr().out


def test_ac1_quote_from_the_wrong_ac_fails(tmp_path):
    """AC-1: real REQ-058 AC-6 text attributed to REQ-058 AC-1 must fail (AC scope, not whole file)."""
    assert run(tmp_path, 'REQ-058 AC-1 "V1 never resubmits a failed order automatically"') == 1


def test_ac1_curly_quotes_and_ellipsis(tmp_path):
    """AC-1: curly quotes are accepted and an ellipsis checks each fragment; a wrong fragment fails."""
    ok = 'REQ-058 AC-6 “V1 never resubmits … the user chooses the next action”'
    bad = 'REQ-058 AC-6 "V1 never resubmits ... the user always retries"'
    assert run(tmp_path, ok) == 0
    assert run(tmp_path, bad) == 1


def test_ac1_second_quote_shares_the_citation(tmp_path):
    """AC-1: 'REQ-058 AC-6 "a" and "b"' checks both quotes against AC-6, and a bad second one fails."""
    good = 'REQ-058 AC-6 "V1 never resubmits" and "the user chooses the next action"'
    assert run(tmp_path, good) == 0
    assert run(tmp_path, 'REQ-058 AC-6 "V1 never resubmits" and "the app retries twice"') == 1


def test_ac1_adr_and_question_citations(tmp_path):
    """AC-1: ADR-010 quote checked against the ADR file; Q237 against its open-questions section."""
    assert run(tmp_path, 'ADR-010 "Adjustment opportunity"') == 0
    assert run(tmp_path, 'ADR-010 "Near adjustment"') == 1
    assert run(tmp_path, 'Q237 "CI for the API/web layers"') == 0
    assert run(tmp_path, 'Q237 "nightly cron on the VPS"') == 1


def test_ac1_uncited_quote_reported_but_fails_only_when_strict(tmp_path, capsys):
    """AC-1: a quote with no citation is UNCITED; exit 0 normally, exit 1 with --strict."""
    text = 'The builder must "never guess a strike" everywhere.'
    assert run(tmp_path, text) == 0
    assert "UNCITED" in capsys.readouterr().out
    assert run(tmp_path, text, "--strict") == 1


def test_ac1_missing_spec_file_or_ac_fails(tmp_path, capsys):
    """AC-1: a citation of a nonexistent requirement or AC is a FAIL, not a silent pass."""
    assert run(tmp_path, 'REQ-999 AC-1 "anything"') == 1
    assert "not found" in capsys.readouterr().out
    assert run(tmp_path, 'REQ-058 AC-99 "anything"') == 1


def test_ac1_missing_brief_file_is_usage_error(tmp_path):
    """AC-1: a brief path that does not exist exits 2, never 0."""
    assert check_brief.main([str(tmp_path / "nope.md"), "--root", str(ROOT)]) == 2


def test_w040_ac_cite_beats_trailing_q_id(tmp_path, capsys):
    """AC-1: 'REQ-058 AC-6 (Q193): "..."' checks against AC-6; the Q-id after it does not override the AC cite."""
    text = 'REQ-058 AC-6 (Q193): "V1 never resubmits a failed order automatically; the failure is shown with its reason"'
    assert run(tmp_path, text) == 0
    assert "REQ-058 AC-6" in capsys.readouterr().out
    bad = 'REQ-058 AC-6 (Q193): "V1 always resubmits a failed order automatically"'
    assert run(tmp_path, bad) == 1


def test_w040_q_quote_found_in_adr_owner_decision_section(tmp_path, capsys):
    """AC-1: a Q230 quote whose text lives in spec/decisions/ADR-003.md (not open-questions) checks OK."""
    text = 'Q230: "the ban covers every word form of the five words"'
    assert run(tmp_path, text) == 0
    assert "1 OK" in capsys.readouterr().out
    assert run(tmp_path, 'Q230: "the ban covers only the exact word best"') == 1


def test_w040_short_quote_is_too_short_not_ok(tmp_path, capsys):
    """AC-1: a quote under 12 chars is TOO-SHORT: exit 0 normally, exit 1 with --strict, never reported OK."""
    text = 'REQ-058 AC-6 "V1 never"'
    assert run(tmp_path, text) == 0
    out = capsys.readouterr().out
    assert "TOO-SHORT" in out and "1 OK" not in out
    assert run(tmp_path, text, "--strict") == 1


def test_w040_ellipsis_fragments_must_be_in_order(tmp_path):
    """AC-1: '"the user chooses the next action ... V1 never resubmits"' has both fragments but reversed -> FAIL."""
    assert run(tmp_path, 'REQ-058 AC-6 "the user chooses the next action ... V1 never resubmits"') == 1
    assert run(tmp_path, 'REQ-058 AC-6 "V1 never resubmits ... the user chooses the next action"') == 0
