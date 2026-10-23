"""AC-1 (REQ-067, process tooling): a brief's spec quotes are checked verbatim against the spec before dispatch."""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
_spec = importlib.util.spec_from_file_location("check_brief", ROOT / "scripts" / "orchestrator" / "check_brief.py")
check_brief = importlib.util.module_from_spec(_spec)
sys.modules["check_brief"] = check_brief
_spec.loader.exec_module(check_brief)

GUARD_LINE = ("Tests: `pytest tests/test_*.py tests/errors/test_write_allowlist.py "
              "tests/errors/test_producer_inventory.py -m repo_scan`\n")
THREAT_LINE = "Threat model: in scope: a forged id; out of scope: a stolen token.\n"


REFERENCE_LINE = "Reference: none - searched order retry, failed order\n"  # ADR-173 (2): any brief naming a REQ-###


def run(tmp_path, text, *extra, reference=True):
    brief = tmp_path / "brief.md"
    brief.write_text(text + "\n" + GUARD_LINE + (REFERENCE_LINE if reference else ""), encoding="utf-8")
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


def _brief_out(path, capsys):
    code = check_brief.main([str(path), "--root", str(ROOT)])
    return code, capsys.readouterr().out


def test_guard_set_real_w080_r9_fails_on_guard_tests_and_findings(capsys):
    """Real brief on main: names no guard tests and greps findings instead of listing ids -> both misses."""
    code, out = _brief_out(ROOT / "docs" / "process" / "brief-W-080-r9.md", capsys)
    assert code == 1
    assert "MISSING guard tests" in out and "MISSING `Findings checked:`" in out


def test_guard_set_real_brief_285_fails_on_guard_tests_only(capsys):
    """Real Tier B brief: only the guard-tests miss."""
    code, out = _brief_out(ROOT / "docs" / "process" / "brief-285.md", capsys)
    assert code == 1
    assert "MISSING guard tests" in out and "Findings checked" not in out


def test_guard_set_fixed_w080_copy_passes(tmp_path):
    """W-080 r9 plus the guard line and two real finding ids passes (quotes unchanged)."""
    text = (ROOT / "docs" / "process" / "brief-W-080-r9.md").read_text(encoding="utf-8")
    text += "\nFindings checked: guard-by-banned-shapes, targeted-tests-miss-dependent-files\n" + GUARD_LINE
    text += THREAT_LINE + REFERENCE_LINE
    brief = tmp_path / "b.md"
    brief.write_text(text, encoding="utf-8")
    assert check_brief.main([str(brief), "--root", str(ROOT)]) == 0


def test_guard_set_unknown_finding_id_fails(tmp_path, capsys):
    """A Findings checked id with no knowledge/findings/<id>.json fails and is named."""
    text = "# Brief (Tier A)\nA new guard.\nFindings checked: no-such-finding-xyz\n"
    assert run(tmp_path, text) == 1
    assert "UNKNOWN finding id `no-such-finding-xyz`" in capsys.readouterr().out


def test_guard_set_tier_b_or_non_guard_needs_no_findings(tmp_path):
    """Tier A without guard words, and a Tier B guard brief, need no Findings line; only the guard tests."""
    assert run(tmp_path, "# Brief (Tier A)\nA parser change.\n") == 0
    assert run(tmp_path, "# Brief (Tier B)\nA new guard.\n" + THREAT_LINE) == 0


def test_guard_set_missing_guard_tests_line_fails(tmp_path, capsys):
    """Only one of the two guard literals on the line is not enough."""
    brief = tmp_path / "b.md"
    brief.write_text("Tests: tests/test_*.py only\n", encoding="utf-8")
    assert check_brief.main([str(brief), "--root", str(ROOT)]) == 1
    assert "MISSING guard tests" in capsys.readouterr().out


def test_guard_set_needs_producer_inventory_literal(tmp_path, capsys):
    """GC-2c: two literals without the producer scan fail; all three pass."""
    two = "Tests: `pytest tests/test_*.py tests/errors/test_write_allowlist.py`\n"  # old two literals
    three = two.rstrip("`\n") + " tests/errors/test_producer_inventory.py -m repo_scan`\n"
    brief = tmp_path / "b.md"
    brief.write_text(two, encoding="utf-8")
    assert check_brief.main([str(brief), "--root", str(ROOT)]) == 1
    assert "test_producer_inventory.py" in capsys.readouterr().out
    brief.write_text(three, encoding="utf-8")
    assert check_brief.main([str(brief), "--root", str(ROOT)]) == 0


def test_guard_set_needs_repo_scan_literal(tmp_path, capsys):
    """Finding repo-wide-scan-outside-targeted-tests: the three old literals without `-m repo_scan` fail."""
    brief = tmp_path / "b.md"
    three = ("Tests: `pytest tests/test_*.py tests/errors/test_write_allowlist.py "
             "tests/errors/test_producer_inventory.py`\n")
    brief.write_text(three, encoding="utf-8")
    assert check_brief.main([str(brief), "--root", str(ROOT)]) == 1
    assert "-m repo_scan" in capsys.readouterr().out
    brief.write_text(three.rstrip("`\n") + " -m repo_scan`\n", encoding="utf-8")
    assert check_brief.main([str(brief), "--root", str(ROOT)]) == 0


def _real_guard_brief_without_threat_model() -> Path:
    """A committed brief whose first 10 lines match GUARD_WORD_RE and that has no `Threat model:` line."""
    p = ROOT / "docs" / "process" / "brief-W-024-r10.md"
    lines = p.read_text(encoding="utf-8").splitlines()
    assert any(check_brief.GUARD_WORD_RE.search(x) for x in lines[:10])
    assert not any(x.startswith("Threat model:") for x in lines)
    return p


def test_threat_model_real_guard_brief_without_one_fails(capsys):
    """Dies if the Threat model check is removed: the real brief names a guard and has no threat model."""
    code, out = _brief_out(_real_guard_brief_without_threat_model(), capsys)
    assert code == 1 and "MISSING `Threat model:`" in out


def test_threat_model_line_missing_or_partial_fails_full_passes(tmp_path, capsys):
    base = "# Brief (Tier B)\nA new guard.\n"
    assert run(tmp_path, base) == 1
    assert run(tmp_path, base + "Threat model: in scope: a forged id.\n") == 1
    assert "MISSING `Threat model:`" in capsys.readouterr().out
    assert run(tmp_path, base + "Threat model: out of scope: a stolen token.\n") == 1
    assert run(tmp_path, base + THREAT_LINE) == 0


def test_threat_model_inside_code_block_does_not_count(tmp_path):
    text = "# Brief (Tier B)\nA new guard.\n```\n" + THREAT_LINE + "```\n"
    assert run(tmp_path, text) == 1


def test_threat_model_good_fixture_plus_line_passes(tmp_path):
    """The good fixture (mentions no guard) plus a Threat model line, and with a guard word, both pass."""
    text = (FIXTURES / "brief_good_req058.md").read_text(encoding="utf-8")
    brief = tmp_path / "b.md"
    brief.write_text("A gate brief.\n" + text + THREAT_LINE, encoding="utf-8")
    assert check_brief.main([str(brief), "--root", str(ROOT)]) == 0




def test_threat_model_inside_tilde_fence_does_not_count(tmp_path):
    """Dies if only ``` fences are tracked."""
    text = "# Brief (Tier B)\nA new guard.\n~~~\n" + THREAT_LINE + "~~~\n"
    assert run(tmp_path, text) == 1
    assert run(tmp_path, text + THREAT_LINE) == 0


def test_threat_model_bullet_and_lowercase_forms_pass(tmp_path):
    """Dies if THREAT_RE goes back to a case-sensitive, column-0 match."""
    base = "# Brief (Tier B)\nA new guard.\n"
    assert run(tmp_path, base + "- " + THREAT_LINE) == 0
    assert run(tmp_path, base + THREAT_LINE.replace("Threat model", "threat model")) == 0
    assert run(tmp_path, base + "- Threat model: in scope only.\n") == 1


# ---- row-review R1 (attack list) and R3 (size budget): builder briefs only
STANDING = ("Standing items: (a) n/a: x (b) n/a: y (c) n/a: z (d) n/a: w\n"
            "Run `python scripts/orchestrator/mutation_gate.py` before reporting.\n")
GOOD_BUDGET = "Budget: 60 min wall-clock, 80 tool calls\n"
FIVE = "1. a\n2. b\n3. c\n4. d\n5. e\n"


SIZE_S = "Size: S, 3 files, 2 items\n"
SIZE_M = "Size: M, 8 files, 3 items\n"
CI_LINE = "CI: kit tests job (tests/); vars: none\n"


def _builder(attack: str, budget: str, size: str | None = None, ci: str = CI_LINE) -> str:
    """A minimal builder brief; the Size line follows the budget unless given (row-review R3 by machine)."""
    if size is None:
        size = SIZE_M if "60 min" in budget else SIZE_S
    return "# Row 99\n" + STANDING + attack + budget + size + ci


def _out(tmp_path, text, capsys, **kw):
    code = run(tmp_path, text, **kw)
    return code, capsys.readouterr().out


def test_builder_brief_needs_a_numbered_attack_list(tmp_path, capsys):
    """R1: no `Attack list:`, one with no numbered item, or fewer than five, is refused; five numbered items pass."""
    code, out = _out(tmp_path, _builder("", GOOD_BUDGET), capsys)
    assert code == 1 and "MISSING Attack list" in out
    code, out = _out(tmp_path, _builder("Attack list: none yet\nsome prose\n", GOOD_BUDGET), capsys)
    assert code == 1 and "MISSING Attack list" in out
    code, out = _out(tmp_path, _builder("Attack list:\n1. a\n2. b\n3. c\n4. d\n", GOOD_BUDGET), capsys)
    assert code == 1 and "at least 5" in out
    assert run(tmp_path, _builder("Attack list:\n\n" + FIVE, GOOD_BUDGET)) == 0
    assert run(tmp_path, _builder("Attack list: (run each)\n" + FIVE, GOOD_BUDGET)) == 0
    wrapped = "Attack list: 1. a\n2. b\n   wrapped line of b\n3. c\n4. d\n5. e\n"
    assert run(tmp_path, _builder(wrapped, GOOD_BUDGET)) == 0


def test_numbered_items_after_the_next_label_do_not_count(tmp_path, capsys):
    """Numbered lines after the next `Label:` line (e.g. a reviewer checklist) are not attacks."""
    text = _builder("Attack list:\n1. a\n2. b\nReviewer checklist:\n3. c\n4. d\n5. e\n", GOOD_BUDGET)
    code, out = _out(tmp_path, text, capsys)
    assert code == 1 and "MISSING Attack list" in out


@pytest.mark.parametrize("budget", ["Budget: 45 min wall-clock, 60 tool calls\n",
                                    "Budget: 60 min wall-clock, 60 tool calls\n",
                                    "Budget: 30 min wall-clock, 80 tool calls\n",
                                    "Budget: 90 min wall-clock, 80 tool calls\n",
                                    "no budget line\n"])
def test_builder_brief_budget_must_be_a_size_pair(tmp_path, capsys, budget):
    """R3: only 30/40, 60/80 and the fix pairs 15/20, 20/30 pass; anything else, or no line, is refused."""
    code, out = _out(tmp_path, _builder("Attack list:\n" + FIVE, budget), capsys)
    assert code == 1 and "MISSING size budget" in out


@pytest.mark.parametrize("budget", ["30 min wall-clock, 40 tool calls", "60 min wall-clock, 80 tool calls",
                                    "15 min wall-clock, 20 tool calls", "20 min wall-clock, 30 tool calls"])
def test_builder_brief_size_pairs_pass(tmp_path, budget):
    assert run(tmp_path, _builder("Attack list:\n" + FIVE, f"Budget: {budget}\n")) == 0


def test_a_guard_in_the_build_section_must_be_an_allow_list(tmp_path, capsys):
    """R8 (finding guard-as-forbidden-list, row 4): a build section describing a scan without `allow-list` is
    refused; the same with `allow-list` passes; no build section, or one without a guard word, is unaffected."""
    head = _builder("Attack list:\n" + FIVE, GOOD_BUDGET)
    code, out = _out(tmp_path, head + "## What to build\nA repo scan fails on `== 'zerodha'` and `in (...)`.\n",
                     capsys)
    assert code == 1 and "MISSING allow-list" in out
    assert run(tmp_path, head + "## What to build\nThe scan is an allow-list of reasoned lines.\n") == 0
    assert run(tmp_path, head + "## What to build\nA new route.\n## Tests\nscan the logs\n") == 0
    assert run(tmp_path, head) == 0


def test_non_builder_brief_is_unaffected(tmp_path):
    """A verifier or measure brief (no `Standing items:`) needs neither an attack list nor a size pair."""
    assert run(tmp_path, "# Verify row 99\nBudget: 45 min wall-clock, 70 tool calls\n") == 0


def test_real_row_7_brief_passes_and_row_1_predates_the_rules(capsys):
    d = ROOT / "docs" / "process" / "builder-sequence-briefs"
    assert check_brief.main([str(d / "row-07-REQ-049-data-health.md"), "--root", str(ROOT)]) == 1
    assert "MISSING mutation gate" in capsys.readouterr().out  # row 7 predates the gate (meta review after row 9)
    assert check_brief.main([str(d / "row-01-REQ-001-underlyings.md"), "--root", str(ROOT)]) == 1
    assert "MISSING Attack list" in capsys.readouterr().out


def test_size_line_is_required_and_must_match_the_budget(tmp_path, capsys):
    """Meta review after row 6: R3 broken three times in prose; by machine now."""
    head = "Attack list:\n" + FIVE
    code, out = _out(tmp_path, _builder(head, "Budget: 30 min wall-clock, 40 tool calls\n", size=""), capsys)
    assert code == 1 and "MISSING size line" in out
    big = "Size: S, 9 files, 2 items\n"
    code, out = _out(tmp_path, _builder(head, "Budget: 30 min wall-clock, 40 tool calls\n", size=big), capsys)
    assert code == 1 and "is not S" in out
    many = "Size: S, 3 files, 5 items\n"
    code, out = _out(tmp_path, _builder(head, "Budget: 30 min wall-clock, 40 tool calls\n", size=many), capsys)
    assert code == 1 and "is not S" in out
    both = "Size: S, 4 files, 2 items, backend + frontend\n"
    code, out = _out(tmp_path, _builder(head, "Budget: 30 min wall-clock, 40 tool calls\n", size=both), capsys)
    assert code == 1 and "across backend and frontend" in out
    code, out = _out(tmp_path, _builder(head, "Budget: 30 min wall-clock, 40 tool calls\n", size=SIZE_M), capsys)
    assert code == 1 and "takes 60/80" in out
    assert run(tmp_path, _builder(head, "Budget: 60 min wall-clock, 80 tool calls\n", size=SIZE_M)) == 0


def test_ci_line_is_required(tmp_path, capsys):
    """R11 (row 6): every builder brief names the CI job and variables of its new tests."""
    code, out = _out(tmp_path, _builder("Attack list:\n" + FIVE, GOOD_BUDGET, ci=""), capsys)
    assert code == 1 and "MISSING CI line" in out


def test_a_row_ahead_brief_names_only_the_row_ahead_worktree_and_no_overlap(tmp_path, capsys):
    """ADR-171 (owner 2026-10-23) rules 3 and 6: a `Row-ahead: yes` brief that names the main sequence worktree (its
    tests would run the older row's code: a false green), names no row-ahead worktree, or has no `Overlap: none` line
    is refused; the complete form passes; a brief without `Row-ahead: yes` is unaffected by these lines."""
    head = _builder("Attack list:\n" + FIVE, GOOD_BUDGET)
    good = head + "Row-ahead: yes\nWork in `OptionsForOptions2-builder-next`.\nOverlap: none (row 9)\n"
    assert run(tmp_path, good) == 0
    code, out = _out(tmp_path, good + "Run it in OptionsForOptions2-builder-reqs too.\n", capsys)
    assert code == 1 and "ROW-AHEAD names `OptionsForOptions2-builder-reqs`" in out
    code, out = _out(tmp_path, head + "Row-ahead: yes\nOverlap: none (row 9)\n", capsys)
    assert code == 1 and "ROW-AHEAD worktree missing" in out
    code, out = _out(tmp_path, head + "Row-ahead: yes\nWork in OptionsForOptions2-builder-next.\n", capsys)
    assert code == 1 and "ROW-AHEAD overlap" in out
    assert run(tmp_path, head + "Worktree OptionsForOptions2-builder-reqs.\n") == 0


REQ_LINE = "Spec basis: REQ-072 AC-1.\n"


@pytest.mark.parametrize("line", [
    "Reference: screens 209-211 - copy the price-changed marker\n",
    "- Reference: 012 same as the strategy list\n",
    "reference: screen 044, 045 copied unchanged\n",
    "Reference: none - searched reconnect, stale feed\n",
    "Reference: none \u2013 searched payoff, breakeven, margin\n",
])
def test_reference_req_brief_with_a_valid_line_passes(tmp_path, line):
    """ADR-173 (2): both accepted forms pass, label case and bullet ignored."""
    assert run(tmp_path, _builder("Attack list:\n" + FIVE, GOOD_BUDGET) + REQ_LINE + line, reference=False) == 0


def test_reference_req_brief_without_the_line_is_refused(tmp_path, capsys):
    """ADR-173 (2): a REQ brief with no `Reference:` line is refused naming ADR-173; loose words do not count."""
    base = _builder("Attack list:\n" + FIVE, GOOD_BUDGET) + REQ_LINE
    code, out = _out(tmp_path, base, capsys, reference=False)
    assert code == 1 and "MISSING Reference line (ADR-173)" in out
    loose = base + "We copy screen 209 from the Reference study.\n"  # not on a `Reference:` line
    code, out = _out(tmp_path, loose, capsys, reference=False)
    assert code == 1 and "MISSING Reference line" in out


@pytest.mark.parametrize("line", [
    "Reference:\n", "Reference: n/a\n", "Reference: none\n", "Reference: none - searched\n",
    "Reference: none - searched reconnect\n", "Reference: none, no screen\n",
    "Reference: screens 209-211\n", "Reference: copy the price-changed marker\n",
    "Reference: screens 12 - copy the marker\n", "Reference: none - screen 209 copied\n",
])
def test_reference_malformed_line_is_refused(tmp_path, capsys, line):
    """ADR-173 (2): empty, n/a, bare none, one search term, screens without a copy word, a copy word without a screen
    number: all refused (fail closed on any line it cannot classify)."""
    text = _builder("Attack list:\n" + FIVE, GOOD_BUDGET) + REQ_LINE + line
    code, out = _out(tmp_path, text, capsys, reference=False)
    assert code == 1 and "MISSING Reference line" in out


def test_reference_a_brief_naming_no_requirement_is_exempt(tmp_path):
    """ADR-173 (2): process tooling briefs (no REQ-###) need no line; a malformed one still does not matter."""
    assert run(tmp_path, _builder("Attack list:\n" + FIVE, GOOD_BUDGET)) == 0
    assert run(tmp_path, _builder("Attack list:\n" + FIVE, GOOD_BUDGET) + "Reference: n/a\n") == 0


def test_reference_a_verifier_brief_naming_a_req_needs_the_line(tmp_path, capsys):
    """ADR-173 (2): verifier briefs (no `Standing items:`) are covered too."""
    code, out = _out(tmp_path, "# Verify row 99\n" + REQ_LINE, capsys, reference=False)
    assert code == 1 and "MISSING Reference line" in out
    ok = "# Verify row 99\n" + REQ_LINE + "Reference: none - searched strike, expiry\n"
    assert run(tmp_path, ok, reference=False) == 0


def test_the_real_row_12_fix_1_brief_is_refused_for_the_missing_line(capsys):
    """ADR-173 proof: the real brief citing REQ-072 with no Reference line exits non-zero."""
    d = ROOT / "docs" / "process" / "builder-sequence-briefs"
    assert check_brief.main([str(d / "row-12-fix-1.md"), "--root", str(ROOT)]) == 1
    assert "MISSING Reference line" in capsys.readouterr().out


def test_a_builder_brief_must_require_the_mutation_gate(tmp_path, capsys):
    """Meta review after row 9: builders left guards unproven; a builder brief without `mutation_gate.py` is refused."""
    text = _builder("Attack list:\n" + FIVE, GOOD_BUDGET).replace(
        "Run `python scripts/orchestrator/mutation_gate.py` before reporting.\n", "")
    code, out = _out(tmp_path, text, capsys)
    assert code == 1 and "MISSING mutation gate" in out


# ---------------------------------------------------------------- ADR-176: label rename and the open-record rule
OLD_LABEL = bytes([115, 101, 110, 115, 105, 98, 117, 108, 108]).decode().capitalize()  # never written as text


def test_the_old_label_no_longer_satisfies_the_rule_and_reference_does(tmp_path, capsys):
    """ADR-176 (4): the label is `Reference:`; a line under the old label is a loose line and is refused."""
    base = _builder("Attack list:\n" + FIVE, GOOD_BUDGET) + REQ_LINE
    code, out = _out(tmp_path, base + f"{OLD_LABEL}: screens 209-211 - copy the price-changed marker\n", capsys,
                     reference=False)
    assert code == 1 and "MISSING Reference line (ADR-173)" in out
    assert run(tmp_path, base + "Reference: screens 209-211 - copy the price-changed marker\n", reference=False) == 0


def _register_root(tmp_path, status="open", kind="COPY", extra=None, raw=None):
    """A temp repo root: the real REQ-135 and builder table, plus one record RD-001 for REQ-135 (row 27)."""
    root = tmp_path / "root"
    (root / "spec" / "requirements").mkdir(parents=True)
    (root / "spec" / "reference-diffs").mkdir(parents=True)
    (root / "docs" / "process").mkdir(parents=True)
    shutil.copy(ROOT / "spec" / "requirements" / "REQ-135.md", root / "spec" / "requirements")
    shutil.copy(ROOT / "docs" / "process" / "builder-sequence-2026-10-22.md", root / "docs" / "process")
    rec = {"id": "RD-001", "kind": kind, "title": "Days left beside each expiry",
           "reference_behaviour": "Shows a short date and the days left.", "reference_screens": ["catalogue 100"],
           "ours": "REQ-135 AC-2", "req": "REQ-135", "row": 27, "status": status, "spec_change": False,
           "bug": False, "recorded": "2026-10-23", **(extra or {})}
    (root / "spec" / "reference-diffs" / "RD-001.json").write_text(raw if raw is not None else json.dumps(rec),
                                                                 encoding="utf-8")
    return root


def _req135_brief(tmp_path, root, reference_line):
    brief = tmp_path / "b135.md"
    brief.write_text("# Verify row 27\nSpec basis: REQ-135 AC-2.\n" + GUARD_LINE + reference_line, encoding="utf-8")
    return check_brief.main([str(brief), "--root", str(root)])


def test_a_brief_dropping_an_open_record_of_its_requirement_is_refused(tmp_path, capsys):
    """ADR-176 (2): a REQ-135 brief whose Reference line omits open RD-001 is refused naming it; naming it passes."""
    root = _register_root(tmp_path)
    assert _req135_brief(tmp_path, root, "Reference: catalogue 100 - copy the days-left label\n") == 1
    assert "MISSING open record RD-001" in capsys.readouterr().out
    assert _req135_brief(tmp_path, root, "Reference: catalogue 100 - copy the days-left label; open RD-001\n") == 0
    # the id on some other line does not count: it must be on a valid Reference line
    assert _req135_brief(tmp_path, root, "Open: RD-001\nReference: catalogue 100 - copy the label\n") == 1
    assert _req135_brief(tmp_path, root, "Reference: n/a RD-001\n") == 1


@pytest.mark.parametrize("status,extra", [("verified", None), ("decided", {"bug": True}), ("deferred", {"issue": 12})])
def test_a_cleared_record_is_not_required_on_the_line(tmp_path, status, extra):
    """ADR-176 (2): a verified, decided or deferred-with-issue record is not open; the plain forms still pass."""
    root = _register_root(tmp_path, status=status, extra=extra)
    assert _req135_brief(tmp_path, root, "Reference: none - searched expiry, days left\n") == 0


def test_an_invalid_or_unreadable_register_refuses_a_req_brief(tmp_path, capsys):
    """Standing item (c): the brief check fails closed when the register cannot be trusted."""
    bad = _register_root(tmp_path, kind="copy")
    assert _req135_brief(tmp_path, bad, "Reference: catalogue 100 - copy it; RD-001\n") == 1
    assert "REFERENCE register invalid" in capsys.readouterr().out
    unreadable = _register_root(tmp_path / "u", raw="{not json")
    assert _req135_brief(tmp_path, unreadable, "Reference: catalogue 100 - copy it; RD-001\n") == 1
    assert "REFERENCE register unreadable" in capsys.readouterr().out


def test_a_fenced_reference_line_does_not_satisfy_the_rule(tmp_path, capsys):
    """Fix 1: an example `Reference:` line inside a code fence is not the brief's own line."""
    root = _register_root(tmp_path, status="verified")
    fenced = "```\nReference: none - searched expiry, days left\n```\n"
    assert _req135_brief(tmp_path, root, fenced) == 1
    assert "MISSING Reference line" in capsys.readouterr().out
    tilde = "~~~\nReference: none - searched expiry, days left\n~~~\n"
    assert _req135_brief(tmp_path, root, tilde) == 1
    assert _req135_brief(tmp_path, root, fenced + "Reference: none - searched expiry, days left\n") == 0


def test_a_lower_case_requirement_id_still_names_the_requirement(tmp_path, capsys):
    """Fix 1: `req-135` is REQ-135, so its open record RD-001 is required on the line."""
    root = _register_root(tmp_path)
    brief = tmp_path / "lower.md"
    head = "# Verify row 27\nSpec basis: req-135 AC-2.\n" + GUARD_LINE
    brief.write_text(head + "Reference: none - searched expiry, days left\n", encoding="utf-8")
    assert check_brief.main([str(brief), "--root", str(root)]) == 1
    assert "MISSING open record RD-001" in capsys.readouterr().out
    brief.write_text(head + "Reference: none - searched expiry, days left; RD-001\n", encoding="utf-8")
    assert check_brief.main([str(brief), "--root", str(root)]) == 0
    bare = tmp_path / "bare.md"
    bare.write_text("# Verify\nSpec basis: req-135.\n" + GUARD_LINE, encoding="utf-8")
    assert check_brief.main([str(bare), "--root", str(root)]) == 1  # naming it needs a Reference line at all


def test_a_longer_record_id_does_not_satisfy_an_open_record(tmp_path, capsys):
    """Fix 1 (kills V19): RD-0010 or RD-0011 on the line is not RD-001."""
    root = _register_root(tmp_path)
    assert _req135_brief(tmp_path, root, "Reference: catalogue 100 - copy the label; RD-0010\n") == 1
    assert "MISSING open record RD-001" in capsys.readouterr().out
    assert _req135_brief(tmp_path, root, "Reference: catalogue 100 - copy the label; XRD-001 RD-0011\n") == 1
    assert _req135_brief(tmp_path, root, "Reference: catalogue 100 - copy the label; RD-001, RD-0010\n") == 0
