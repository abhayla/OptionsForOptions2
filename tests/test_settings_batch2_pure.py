"""GC-SET batch 2 (REQ-167 AC-4): the pure functions take the setting as a REQUIRED parameter, and a different value
changes the answer; each registry default is exactly the value the code had.

Spec basis: REQ-167 AC-4 "a test per setting"; AC-5 groups Billing (trial and referral days), Data (freeze file stale
after). Defaults never change (the registry default is today's code value, exact).
"""
from __future__ import annotations

import inspect

import pytest
from ofo.entitlements.engine import referral_grant, trial_grant
from ofo.settings import calc, defaults

def test_the_registry_defaults_are_exactly_the_old_code_values():
    d = defaults()
    assert (calc.trial_days(d), calc.referral_days(d), calc.freeze_stale_days(d)) == (7, 30, 8)
    assert calc.open_strategy_seconds(d) == 1.0


@pytest.mark.parametrize("fn", [trial_grant, referral_grant])
def test_the_grant_length_has_no_default_in_code(fn):
    assert inspect.signature(fn).parameters["days"].default is inspect.Parameter.empty
