"""GC-SET batch 2 (REQ-167 AC-4, AC-5 Billing): the trial and referral lengths are the settings in force."""
from __future__ import annotations

import datetime
from datetime import timedelta
from decimal import Decimal

from ofo.entitlements.engine import referral_grant, trial_grant
from ofo.settings import calc, defaults

from .helpers import note

NOW = datetime.datetime(2026, 10, 1, 9, 0, tzinfo=datetime.UTC)


def test_the_trial_length_is_the_setting_in_force():
    for days in (7, 14):
        values = defaults()
        values["billing.trial_days"] = Decimal(days)
        assert trial_grant("t", NOW, "reg", note(), days=calc.trial_days(values)).duration == timedelta(days=days)


def test_the_referral_length_is_the_setting_in_force():
    for days in (30, 45):
        values = defaults()
        values["billing.referral_days"] = Decimal(days)
        assert referral_grant("r", NOW, "row", note(), days=calc.referral_days(values)).duration == timedelta(days=days)
