"""Issue 297 items 1-2 (REQ-067 AC-4, ADR-086): the answer-level notice (`output_label`) carries only the model label.
A leg's own notice ("no live quote", "stale since ...") lives on that leg's `label`, and the page prints it once under
the leg's contract name. The 2026-10-16 live pushes had `estimated from spot; <trading symbol>: no live quote` in
`output_label` AND the same notice on the leg, so the page showed the raw trading symbol and the notice twice.
Real 2026-10-08 replay; the state is made by changing ONE input (a leg's quote) of the real snapshot."""
import dataclasses

from marketdata._kite_fixture import all_instrument_ids, new_provider, replay
from ofo.outcome import OutcomeState, build_outcome, read_snapshot
from outcome.test_same_engine import RATE, VALUATION, definition

from ofo.outcome.snapshot import LegMarket


def _no_quote_outcome():
    provider, clock, items = new_provider()
    provider.subscribe(all_instrument_ids(items))
    replay(provider, clock)
    d = definition(provider)
    snap = read_snapshot(provider, "NIFTY", [p.instrument_id for p in d.legs], VALUATION, RATE)
    first = d.legs[0].instrument_id
    snap = dataclasses.replace(snap, legs={**snap.legs, first: LegMarket(first, snap.legs[first].contract, None)})
    return build_outcome(d, snap)


def test_a_no_quote_leg_notice_is_on_the_leg_only_never_in_the_answer_label_with_a_raw_symbol():
    out = _no_quote_outcome()
    assert out.state is OutcomeState.COMPUTED
    noticed = [leg for leg in out.legs if leg.label]
    assert [leg.label for leg in noticed] == ["no live quote"]
    label = str(out.output_label or "")
    assert "no live quote" not in label  # printed once: on the leg
    for leg in out.legs:
        assert leg.symbol not in label and leg.instrument_id not in label
