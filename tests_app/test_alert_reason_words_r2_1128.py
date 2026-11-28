"""I-58 (test plan 28 Nov 2026): some alert rows showed only the trade's name as their reason. Every alert row, in
Active and in History, says WHY in words: its text is never the trade's name (or empty) and names its rule kind; a
record the inbox cannot word falls back to the rule in words with its figures when it has them.
Real case: the ADJ-02 iron condor ("Scenario ADJ-02" (#id, 9 Nov)) with one alert of each actionable kind.
Spec basis: ADR-330 (3) (Active and History say what the record says), (19)(b) (name in the quoted slot).
"""
from __future__ import annotations

from decimal import Decimal as D

import pytest
import test_adjustment_check as check_test
from ofo_app import actionable_alerts as aa
from test_adjustment_check import _seeded
from test_adjustment_opportunities import _call, _clean
from test_alert_routes import FIRED

app_db_url = check_test.app_db_url
OK = 200
#: (rule id, kind, trigger id, words the row must carry)
CASES = [
    ("T-06", "plan_loss_stop", "T-06", "loss stop"),
    ("T-07", "plan_profit_target", "T-07", "profit target"),
    ("plan.rupee_loss", "plan_rupee_loss", "plan.rupee_loss", "plan loss stop"),  # W-28: ONE loss stop (ADR-330 (5)(a))
    ("plan.rupee_profit", "plan_rupee_profit", "plan.rupee_profit", "rupee"),
    ("plan.time_exit", "plan_time_exit", "plan.time_exit", "time exit"),
    ("T-05", "adjustment_rule", "T-05", "djustment"),
]


@pytest.mark.parametrize("case", CASES)
@pytest.mark.parametrize("with_figures", [True, False])
async def test_an_alert_row_says_why_in_words_never_only_the_trade_name(app_db_url, monkeypatch, case,
                                                                         with_figures):
    rule, kind, trigger, words = case
    sid = await _clean(app_db_url, await _seeded(app_db_url, monkeypatch, "ADJ-02"))
    reading = (D("12.5000"), D("10.0000")) if with_figures else (None, None)
    async with app_db_url.begin() as conn:
        alert = await aa.raise_actionable(conn, "owner", sid, rule, kind, at=FIRED, value=reading[0],
                                          threshold=reading[1], trigger_id=trigger, stage=None)
    status, active = await _call("GET", "/api/alerts/active")
    row = next(a for a in active["alerts"] if a["id"] == alert.id)
    assert status == OK
    text, name = row["text"], row["strategy_name"]
    assert text and text.strip() != name.strip() and f'"{name}"' != text, (kind, text, name)
    assert words.lower() in text.lower(), (kind, text)
    if with_figures:
        assert "12.5" in text and "10" in text, text
    assert (await _call("POST", f"/api/alerts/{alert.id}/answer", {"answer": "continue"}))[0] == OK
    done = next(i for i in (await _call("GET", "/api/alerts/answered"))[1]["items"] if i["id"] == alert.id)
    assert done["text"] == text  # History says the same words as Active did
