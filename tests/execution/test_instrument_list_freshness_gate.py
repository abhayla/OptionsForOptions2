"""INSTR-FRESH: a stale instrument list reaches the existing data-health gate and refuses an ENTRY basket with the
existing "gate_data_unhealthy" sentence (no new wording); a closing basket is carried as the existing stale-data
warning (the route then refuses it for want of a confirmation step: reported to the owner)."""
from __future__ import annotations

from execution_inputs import all_true_context, check, closing_orders, condor_legs
from ofo.engine import Strategy
from ofo.execution import CheckCode, DataHealth, DataInput, ExecutionAction, FlagCode


def _health(state: DataHealth) -> dict:
    return {d: (state if d is DataInput.INSTRUMENT_LIST else DataHealth.HEALTHY) for d in DataInput}


def test_a_stale_instrument_list_blocks_an_entry_with_the_existing_sentence(condor, catalogue, eligibility):
    result = check(condor, all_true_context(data_health=_health(DataHealth.STALE)), catalogue, eligibility)
    assert result.failed_codes == {CheckCode.DATA_UNHEALTHY}
    assert [f.reason for f in result.failures] == [
        "Market data needed for execution (instrument list) is out of date. Execution is paused until it is current."]


def test_a_missing_list_stamp_blocks_an_entry(condor, catalogue, eligibility):
    result = check(condor, all_true_context(data_health=_health(DataHealth.UNAVAILABLE)), catalogue, eligibility)
    assert result.failed_codes == {CheckCode.DATA_UNHEALTHY}


def test_a_list_loaded_today_passes_the_gate(condor, catalogue, eligibility):
    result = check(condor, all_true_context(data_health=_health(DataHealth.HEALTHY)), catalogue, eligibility)
    assert result.failures == ()


def test_a_closing_basket_on_a_stale_list_is_a_warning_not_a_block(catalogue, eligibility):
    legs = condor_legs()
    ctx = all_true_context(data_health=_health(DataHealth.STALE), action=ExecutionAction.EXIT, active_legs=legs)
    result = check(Strategy(closing_orders(legs)), ctx, catalogue, eligibility)
    assert result.failures == () and result.requires_confirmation
    assert FlagCode.DATA_STALE_ON_EXIT in {f.code for f in result.flags}
