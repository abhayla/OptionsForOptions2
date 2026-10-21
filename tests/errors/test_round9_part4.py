"""W-024 round 9 part 4 (REQ-065 AC-2, ADR-003 Q226): Strategy Guard refusals, the partial-execution flow's slicing
refusals and broker-mismatch texts, the choice labels and the sequence notes all come from the catalogue.

Expected texts are written from the meaning of the messages they replace, not copied from running the code.
"""
from __future__ import annotations

import datetime
from decimal import Decimal

import pytest
from ofo.engine import Action, Instrument, Leg
from ofo.execution.planned import ExecutionPlan, PlannedLeg
from ofo.execution.sequence import SliceRefused, _batched

PARTS = ("what_happened", "impact", "what_is_blocked", "next_action")


def test_guard_refused_refuses_a_plain_string() -> None:
    from ofo.strategy.guard import GuardRefused

    with pytest.raises(TypeError):
        GuardRefused("Strategy Guard has not checked this exact action. Nothing was sent.")  # type: ignore[arg-type]


def test_guard_refusals_carry_four_parts_and_keep_reason_and_text() -> None:
    from ofo.engine import UNLIMITED
    from ofo.errors import render
    from ofo.strategy.guard import GuardRefused

    err = GuardRefused(render("guard_not_checked"))
    assert err.reason == "Strategy Guard has not checked this exact action for this strategy and version."
    assert str(err) == err.reason
    assert all(line for line in err.text.split("\n")) and len(err.text.split("\n")) == 4
    rows = (("max loss", Decimal("-26000"), UNLIMITED), ("margin", None, Decimal("40000.00")))
    ack = GuardRefused(render("guard_acknowledgement_required", rows=rows))
    assert ack.reason == ("This action changes your strategy's risk profile: max loss: -26,000 -> unlimited; "
                          "margin: unknown -> 40,000.00.")
    assert ack.text.count("\n") == 3


def test_risk_profile_sentence_is_the_requirements_exact_sentence() -> None:
    from ofo.strategy.guard import RISK_PROFILE_CHANGED

    assert RISK_PROFILE_CHANGED == "This action changes your strategy's risk profile"  # REQ-036 AC-5


def test_risk_rows_slot_refuses_unknown_metrics_and_free_text() -> None:
    from ofo.errors import render

    with pytest.raises(ValueError):
        render("guard_acknowledgement_required", rows=(("a free sentence", Decimal("1"), Decimal("2")),))
    with pytest.raises(TypeError):
        render("guard_acknowledgement_required", rows=(("margin", "free text", Decimal("2")),))


def test_spec_fixed_choice_labels_are_the_exact_words() -> None:
    from ofo.errors.explanations import CHOICE_LABEL_TEXT
    from ofo.execution.partial import PartialChoice

    assert CHOICE_LABEL_TEXT["RETRY_FAILED_LEG"] == "Retry Failed Leg"
    assert CHOICE_LABEL_TEXT["CLOSE_PARTIAL_STRATEGY"] == "Close Partial Strategy"
    assert [c.value for c in PartialChoice] == ["Complete Strategy", "Retry Failed Leg", "Review Manually",
                                                 "Close Partial Strategy"]


def test_lot_refusal_is_typed_and_keeps_the_old_wording_pieces() -> None:
    """ADR-092 removed freeze slicing; the typed refusal that remains is the whole-lots one (``_batched``)."""
    leg = Leg(Action.BUY, Instrument.CE, Decimal("24000"), datetime.date(2026, 9, 30), 65, Decimal("50.00"))
    plan = ExecutionPlan("S-1", (PlannedLeg("L1", "NIFTY2693024000CE", leg),))

    class Constraints:
        def max_orders_per_batch(self) -> int:
            return 10

    with pytest.raises(SliceRefused) as info:
        _batched(plan, [["L1"]], Constraints(), {"L1": 100}, {"L1": 65})
    err = info.value
    assert err.message.what_happened == (
        "Nothing prepared: 100 units of NIFTY2693024000CE is not a whole number of lots of 65.")
    assert isinstance(err, ValueError) and "whole number of lots of 65" in str(err)
    assert err.text.count("\n") == 3
    with pytest.raises(TypeError):
        SliceRefused(detail="x", message="a plain string")  # type: ignore[arg-type]


def test_sequence_labels_and_margin_notes_come_from_the_explanation_catalogue() -> None:
    from ofo.execution.sequence import MARGIN_NOT_USED, StepKind

    assert [k.value for k in StepKind] == ["Establish protection", "Establish short positions",
                                           "Legs with no protection relation"]
    assert MARGIN_NOT_USED == "margin impact unknown — not used"


@pytest.mark.parametrize("template_id,slots", [
    ("guard_risk_profile_changed", {}), ("guard_not_checked", {}),
    ("partial_ready_risk_changed", {"count": 2}),
    ("partial_slice_not_whole_lots", {"units": 100, "contract": "NIFTY2693024000PE", "lot": 65}),
    ("partial_slice_no_lot_size", {"count": 0, "contract": "NIFTY2693024000PE"}),
    ("partial_read_stale", {}),
    ("partial_mismatch_unknown_order", {"order": "BRK-1"}),
    ("partial_mismatch_other_strategy", {"order": "BRK-1"}),
    ("partial_mismatch_order_unmatched", {"order": "BRK-1"}),
    ("partial_mismatch_order_missing", {"order": "k-2", "seconds": 60}),
    ("partial_mismatch_outside_plan", {"contract": "NIFTY2693024000PE"}),
    ("partial_mismatch_quantity", {"contract": "NIFTY2693024000PE", "units": 130, "limit": -65}),
    ("partial_mismatch_fills_differ", {"ledger": (("NIFTY2693024000PE", -65),), "broker": ()}),
    ("partial_mismatch_unresolved", {}),
    ("partial_mismatch_product_ambiguous", {"contract": "NIFTY2693024000PE"}),
    ("send_entry_product_not_nrml", {}),
    ("partial_mismatch_other_product_only", {"contract": "NIFTY2693024000PE"}),
])
def test_every_part4_template_renders_all_four_parts(template_id: str, slots: dict) -> None:
    from ofo.errors import render

    message = render(template_id, **slots)
    for name in PARTS:
        assert getattr(message, name).strip(), (template_id, name)


def test_mutation_a_free_order_id_is_refused() -> None:
    """A slot is a closed pattern: an order id carrying a sentence cannot reach the text."""
    from ofo.errors import render

    with pytest.raises(ValueError):
        render("partial_mismatch_unknown_order", order="please wire money now")
