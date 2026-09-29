"""AC-1 (REQ-053, finding fixture-symbol-not-in-catalogue): every tradingsymbol literal under
``tests/`` must resolve in the real catalogue slice (``tests/fixtures/instruments/instruments_slice.csv``)
with the expiry the symbol itself encodes.

**Practical, deterministic rule** (documented here because the guard's rule must be explainable, not
just enforced):

1. A *full* literal -- a prefix (``NIFTY``/``BANKNIFTY``/``FINNIFTY``/``SENSEX``), a 2-digit year, a
   month/day code (``OCT``, ``NOV``, ... or a weekly day code ``O01``..``O31``), then either digits
   followed by ``CE``/``PE`` (an option) or ``FUT`` directly (a future) -- is found ANYWHERE in the
   file's text (so it also catches a symbol embedded inside a longer message string, e.g. an
   assertion's expected error text). It must appear verbatim as a ``tradingsymbol`` in the catalogue
   CSV. Because the Zerodha symbol format encodes its own expiry (the day/month code IS the expiry),
   catalogue membership of the full literal already proves the symbol is paired with a real, matching
   expiry -- this is exactly what catches the finding's example (``NIFTY26OCT23400CE`` is not a real
   catalogue symbol for expiry 2026-10-06; the real one is ``NIFTY26O0623400CE``).
2. A *dynamic head* -- the same prefix/year/month pattern immediately followed by an f-string ``{``
   (a template whose strike and CE/PE suffix are filled in at runtime, e.g.
   ``f"NIFTY26OCT{strike}{instrument.value}"``) -- is checked differently: the catalogue must contain
   AT LEAST ONE option row (``CE`` or ``PE``) whose tradingsymbol starts with that exact head. This
   catches a template built on a month/day code for which the catalogue holds no options at all (e.g.
   ``NIFTY26OCT`` -- the catalogue's only 2026-10-27 NIFTY row is the future, ``NIFTY26OCTFUT``; it
   holds no NIFTY options at that expiry, so no template built on that head can ever produce a real
   option symbol).

A small, explicit allowlist covers two honest exceptions, each with a one-line reason: (a) a fixture
that is DELIBERATELY not in the catalogue, to prove some guard refuses it (an "attack" fixture); (b) a
locked spec example (scenario-calculations.md §6) whose expiry has no matching row in this catalogue
SLICE at all -- corrected only by inventing a row, which is worse than naming the gap.

Anything not in the catalogue and not allowlisted is a genuine instance of the finding's class and
must be corrected to a real catalogue symbol (same strike/expiry, symbol text only) before this test
is allowed to pass.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
CATALOGUE_CSV = TESTS_DIR / "fixtures" / "instruments" / "instruments_slice.csv"
THIS_FILE = Path(__file__).resolve()

MONTH = r"(?:O[0-9]{2}|OCT|NOV|DEC|JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP)"
FULL_SYMBOL_RE = re.compile(
    rf"\b(?:NIFTY|BANKNIFTY|FINNIFTY|SENSEX)[0-9]{{2}}{MONTH}(?:[0-9]+(?:CE|PE)|FUT)\b"
)
DYNAMIC_HEAD_RE = re.compile(
    rf"(?:NIFTY|BANKNIFTY|FINNIFTY|SENSEX)[0-9]{{2}}{MONTH}(?=\{{)"
)

# (relative file path, exact matched text) -> one-line reason. Every entry is either a deliberate
# "attack" fixture (a symbol a guard elsewhere must refuse) or a locked spec example with no
# matching row in this catalogue SLICE.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("execution/test_strategy_only.py", "BANKNIFTY26OCT50000CE"):
        "attack fixture: a BANKNIFTY order deliberately not in the strategy/catalogue, proving the "
        "sink refuses a contract that is not the strategy's own catalogue symbol.",
    ("execution/test_sink_backup_checks.py", "FINNIFTY26O0623600CE"):
        "attack fixture: FINNIFTY is out of the catalogue's supported-underlying scope; inserted "
        "directly to prove the sink's underlying-equality filter (M7) refuses a same-strike twin.",
    ("execution/test_complete_slices.py", "NIFTY26O0623625CE"):
        "attack fixture (AC-4 negative): a plan contract the catalogue does not hold, proving "
        "sequence_plan refuses an unknown symbol instead of guessing a lot size.",
    ("engine/conftest.py", "NIFTY26OCT"):
        "locked spec example (scenario-calculations.md section 6, the golden Iron Condor) at the "
        "monthly 2026-10-27 expiry; this catalogue slice holds only the monthly FUTURE for that "
        "expiry (NIFTY26OCTFUT), no options -- there is no real row to correct the option legs to, "
        "and the IV values are computed from the spec, never the catalogue.",
    ("engine/test_inputs.py", "NIFTY26OCT22800PE"):
        "same golden Iron Condor fixture as engine/conftest.py: no NIFTY option row exists at the "
        "2026-10-27 expiry in this catalogue slice.",
    ("scenario/scenario_fixtures.py", "NIFTY26OCT"):
        "same golden Iron Condor fixture (scenario-calculations.md section 6) reused for scenario "
        "tests: no NIFTY option row exists at the 2026-10-27 expiry in this catalogue slice.",
    ("scenario/test_modes.py", "NIFTY26OCT22800PE"):
        "same golden Iron Condor fixture: the unavailable-IV message names the same leg used by "
        "engine/conftest.py, for which no catalogue row exists at 2026-10-27.",
    ("audit/test_log.py", "NIFTY24JAN25000CE"):
        "REQ-064: the audit log stores a raw Kite-style broker-response payload EXACTLY as passed, "
        "with no secret filtering and no catalogue lookup; the payload's tradingsymbol is "
        "illustrative content the log must not alter, not a contract this test resolves.",
    ("marketdata/test_quote.py", "NIFTY26O2823500CE"):
        "deferred (out of W-030's named scope, see github.com/abhayla/OptionsForOptions2/issues/51): "
        "NormalizedQuote carries an illustrative instrument_id and performs no catalogue lookup; "
        "corrected in a follow-up.",
    ("marketdata/test_rule_health.py", "NIFTY26O2823500CE"):
        "deferred (out of W-030's named scope, see github.com/abhayla/OptionsForOptions2/issues/51): "
        "same illustrative instrument_id as marketdata/test_quote.py; corrected in a follow-up.",
    ("range/test_pick_lists.py", "NIFTY26NOV"):
        "deferred (out of W-030's named scope, see github.com/abhayla/OptionsForOptions2/issues/51): "
        "pick-list strike range fixture uses a monthly November head for which this catalogue slice "
        "holds no options (only NIFTY26NOVFUT); corrected in a follow-up.",
}


def _load_catalogue_symbols() -> set[str]:
    with CATALOGUE_CSV.open(encoding="utf-8") as fh:
        return {row["tradingsymbol"] for row in csv.DictReader(fh)}


def find_violations(paths: list[Path], catalogue_symbols: set[str],
                     allowlist: dict[tuple[str, str], str] | None = None,
                     base: Path = TESTS_DIR) -> list[tuple[str, int, str, str]]:
    """Return (relative_path, line_number, matched_text, reason) for every literal that is neither a
    real catalogue symbol/head nor allowlisted. Pure function of its inputs -- used directly by the
    mutation test below without touching the real tree."""
    allowlist = allowlist or {}
    violations: list[tuple[str, int, str, str]] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        rel = str(path.resolve().relative_to(base.resolve())).replace("\\", "/") if path.is_absolute() else str(path)
        for m in FULL_SYMBOL_RE.finditer(text):
            sym = m.group(0)
            if (rel, sym) in allowlist:
                continue
            if sym not in catalogue_symbols:
                line = text.count("\n", 0, m.start()) + 1
                violations.append((rel, line, sym, "full symbol not found in the catalogue"))
        for m in DYNAMIC_HEAD_RE.finditer(text):
            head = m.group(0)
            if (rel, head) in allowlist:
                continue
            if not any(s.startswith(head) and s.endswith(("CE", "PE")) for s in catalogue_symbols):
                line = text.count("\n", 0, m.start()) + 1
                violations.append((rel, line, head, "no catalogue option starts with this head"))
    return violations


def _real_test_files() -> list[Path]:
    return sorted(p for p in TESTS_DIR.rglob("*.py") if p.resolve() != THIS_FILE)


def test_every_tradingsymbol_literal_in_tests_resolves_in_the_catalogue() -> None:
    """AC-1: core proof. Scans every ``tests/**/*.py`` file (this guard excluded) for tradingsymbol
    literals and fails, listing file:line, if any is neither a real catalogue symbol/head for its
    paired expiry nor an explicitly-reasoned allowlist entry."""
    catalogue_symbols = _load_catalogue_symbols()
    violations = find_violations(_real_test_files(), catalogue_symbols, ALLOWLIST)
    assert violations == [], "tradingsymbol literal(s) not in the catalogue (see ALLOWLIST to accept):\n" + "\n".join(
        f"  {path}:{line}: {sym!r} ({reason})" for path, line, sym, reason in violations
    )


def test_guard_goes_red_on_the_findings_example_mutation() -> None:
    """Core/Proof mutation: reintroducing NIFTY26OCT23400CE paired with expiry 2026-10-06 (the exact
    finding example) must be caught. Run against a synthetic snippet (never the real tree) so this
    test itself never needs the real files to be broken."""
    catalogue_symbols = _load_catalogue_symbols()
    mutated_source = (
        "import datetime\n"
        "EXPIRY = datetime.date(2026, 10, 6)\n"
        'CONTRACT = "NIFTY26OCT23400CE"\n'
    )
    scratch = TESTS_DIR / "_scratch_mutation_probe.py"
    scratch.write_text(mutated_source, encoding="utf-8")
    try:
        violations = find_violations([scratch], catalogue_symbols, ALLOWLIST)
    finally:
        scratch.unlink()
    assert violations, "the guard must go red on NIFTY26OCT23400CE (not a real catalogue symbol)"
    assert any(sym == "NIFTY26OCT23400CE" for _, _, sym, _ in violations)


def test_allowlist_entries_are_not_stale() -> None:
    """Every ALLOWLIST entry names a file that still contains the literal it excuses, so a future
    correction that removes the literal is forced to also remove the now-dead allowlist entry."""
    for (rel_path, literal), _reason in ALLOWLIST.items():
        full_path = TESTS_DIR / rel_path
        assert full_path.is_file(), f"allowlisted file missing: {rel_path}"
        assert literal in full_path.read_text(encoding="utf-8"), (
            f"allowlist entry {rel_path!r}/{literal!r} no longer matches the file's contents"
        )
