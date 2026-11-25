"""D-31 (ADR-309 (1), ADR-320): a rule with an open record is shown on the trade page (panel and drawer) with the figures
of that record, the same ones the opportunity list shows; the check's value of the moment is the separate "Now" value.
Real case 23 Nov, condor C6: the list said 0.7293 % (the record), the panel 0.6882 % (this poll), the drawer 0.6851 %
(an earlier poll), within a minute, none labelled."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

from ofo.adjustment import playbook_eval as pe
from ofo_app import playbook_store
from ofo_app.routes import adjustment_check as route
from ofo_app.routes.adjustment_opportunities import condition_text

RULE = "T-01"
SHOWN = dt.datetime(2026, 11, 23, 9, 1, 20, tzinfo=dt.UTC)


def _record(value: str) -> playbook_store.Suggestion:
    return playbook_store.Suggestion(
        41, 160, RULE, "T-01", "Last day", Decimal(value), Decimal("0.7500"), SHOWN, "open", None,
        [{"cmp": "le", "label": "Spot distance from the short strike", "unit": "%", "group": "g"}])


def _poll(value: str) -> SimpleNamespace:
    flag = pe.Flag(RULE, "T-01", "Last day", Decimal(value), Decimal("0.7500"), "le")
    return SimpleNamespace(results=(flag,), values=(SimpleNamespace(rule_id=RULE, cmp="le"),), clear=())


def test_a_live_flag_with_an_open_record_shows_the_records_figures():
    record = _record("0.7293")
    for poll in ("0.6882", "0.6851"):  # two polls within a minute: the shown condition does not move
        [shown] = route.shown_results(_poll(poll), [record])
        assert shown.value == Decimal("0.7293")
        out = route.result_out(shown, "w", {RULE: 41}, body=None)
        assert out["condition"] == condition_text(record)  # the list's own sentence
        assert out["value"] == route._num(Decimal("0.7293"))


def test_a_flag_without_an_open_record_stays_the_polls_own():
    [shown] = route.shown_results(_poll("0.6882"), [])
    assert shown.value == Decimal("0.6882")
