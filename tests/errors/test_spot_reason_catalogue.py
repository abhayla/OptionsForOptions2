"""Class guard (spot review round 2, M1): every spot reason code the spot source can carry has a catalogue line, so the
screen never says "reason not given" for a code the code itself produces (REQ-065: user wording via the catalogue)."""
from __future__ import annotations

from ofo.errors.explanations import EXPLANATIONS
from ofo.marketdata import spot_source


def test_every_reason_code_has_a_catalogue_line() -> None:
    codes = {name: value for name, value in vars(spot_source).items() if name.startswith("REASON_")}
    assert codes, "no REASON_* constants found"
    missing = [f"{name}={value}" for name, value in codes.items()
               if f"adjust_spot_why_{value}" not in EXPLANATIONS]
    assert not missing, f"reason codes without a catalogue line: {missing}"
