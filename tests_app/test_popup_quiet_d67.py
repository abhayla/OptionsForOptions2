"""D-67 (ADR-326 (5)): the server is the one source of "pop up now". Every open record of GET /adjustment-opportunities
carries ``popup_due``; the record itself (and so the bell's count) is unchanged. Real case 23 Nov 2026: condor C10
(strategy 166, gamma 2.95 % vs 2 %) and C11 (167, tested delta 0.3809 vs 0.35), raised 1 to 3 minutes after opening.
"""
from __future__ import annotations

import datetime as dt
import inspect
from decimal import Decimal

from ofo_app import playbook_store
from ofo_app.routes import adjustment_opportunities as route
from ofo_app.routes.adjustment_opportunities import OpportunityOut, PopupFacts, inbox_body

ENTRY = dt.datetime(2026, 11, 23, 9, 20, 0, tzinfo=dt.UTC)


def _row(who: tuple[int, int, str, str], figures: tuple[str, str], shown: dt.datetime) -> playbook_store.InboxRow:
    """who = (strategy id, record id, rule id, trigger id); figures = (value, threshold)."""
    sid, sug_id, rid, trig = who
    s = playbook_store.Suggestion(sug_id, sid, rid, trig, "Entry", Decimal(figures[0]), Decimal(figures[1]), shown,
                                  "open", None, [{"cmp": "ge", "label": "Gamma", "group": f"g{sug_id}"}])
    return playbook_store.InboxRow(s, f"C{sid - 156}", True)


def _records(body: dict) -> dict[int, dict]:
    return {r["id"]: r for g in body["groups"] for r in g["records"]}


def test_field_exists_on_the_reply_model():
    assert "popup_due" in OpportunityOut.model_fields


def test_two_condors_true_at_entry_wait_then_pop_up_and_the_records_stay():
    rows = [_row((166, 1, "R-gamma", "T-02"), ("2.95", "2.00"), ENTRY + dt.timedelta(minutes=1)),
            _row((167, 2, "R-delta", "T-04"), ("0.3809", "0.35"), ENTRY + dt.timedelta(minutes=3))]
    def facts(now: dt.datetime) -> PopupFacts:
        return PopupFacts(entry={166: ENTRY, 167: ENTRY},
                          seen_clear={(166, "R-gamma"): False, (167, "R-delta"): False}, now=now)

    early = inbox_body(rows, popup=facts(ENTRY + dt.timedelta(minutes=3)))
    assert [r["popup_due"] for r in _records(early).values()] == [False, False]
    assert early["totals"]["conditions"] == len(rows)
    assert [c["count"] for c in early["counts"] if c["outcome"] == "open"] == [len(rows)]
    assert all(r["outcome"] == "open" and r["can_act"] for r in _records(early).values())
    late = inbox_body(rows, popup=facts(ENTRY + dt.timedelta(minutes=5)))
    assert [r["popup_due"] for r in _records(late).values()] == [True, True]


def test_rule_false_at_entry_then_true_pops_up_at_once_and_a_second_strategy_is_not_held():
    rows = [_row((166, 1, "R-gamma", "T-02"), ("2.95", "2.00"), ENTRY + dt.timedelta(minutes=2)),
            _row((167, 2, "R-delta", "T-04"), ("0.3809", "0.35"), ENTRY + dt.timedelta(minutes=2))]
    facts = PopupFacts(entry={166: ENTRY, 167: ENTRY},
                       seen_clear={(166, "R-gamma"): True, (167, "R-delta"): False},
                       now=ENTRY + dt.timedelta(minutes=2))
    got = _records(inbox_body(rows, popup=facts))
    assert got[1]["popup_due"] is True  # became true after a check that found it false
    assert got[2]["popup_due"] is False  # the other strategy's own state decides, not the first one's


def test_entry_time_unknown_pops_up_at_once_and_no_facts_means_due():
    rows = [_row((166, 1, "R-gamma", "T-02"), ("2.95", "2.00"), ENTRY + dt.timedelta(minutes=1))]
    none_known = PopupFacts(entry={}, seen_clear={(166, "R-gamma"): False},
                            now=ENTRY + dt.timedelta(minutes=1))
    assert _records(inbox_body(rows, popup=none_known))[1]["popup_due"] is True
    assert _records(inbox_body(rows))[1]["popup_due"] is True


def test_a_settled_record_is_never_quiet():
    row = _row((166, 1, "R-gamma", "T-02"), ("2.95", "2.00"), ENTRY + dt.timedelta(minutes=1))
    done = playbook_store.InboxRow(
        playbook_store.Suggestion(1, 166, "R-gamma", "T-02", "Entry", Decimal("2.95"), Decimal("2.00"),
                                  row.suggestion.shown_at, "dismissed", None, row.suggestion.timeline), "C10", True)
    facts = PopupFacts(entry={166: ENTRY}, seen_clear={(166, "R-gamma"): False}, now=ENTRY)
    assert _records(inbox_body([done], popup=facts))[1]["popup_due"] is True


def test_a_rule_first_found_true_two_minutes_after_entry_waits_until_five():
    rows = [_row((166, 1, "R-gamma", "T-02"), ("2.95", "2.00"), ENTRY + dt.timedelta(minutes=2))]
    late = PopupFacts(entry={166: ENTRY}, seen_clear={(166, "R-gamma"): False},
                      now=ENTRY + dt.timedelta(minutes=2))
    assert _records(inbox_body(rows, popup=late))[1]["popup_due"] is False
    five = PopupFacts(entry=late.entry, seen_clear=late.seen_clear, now=ENTRY + dt.timedelta(minutes=5))
    assert _records(inbox_body(rows, popup=five))[1]["popup_due"] is True


def test_a_scenario_dated_strategy_uses_the_clock_it_is_given():
    scn = dt.datetime(2026, 11, 3, 9, 20, tzinfo=dt.UTC)
    rows = [_row((166, 1, "R-gamma", "T-02"), ("2.95", "2.00"), scn + dt.timedelta(minutes=1))]
    kw = {"entry": {166: scn}, "seen_clear": {(166, "R-gamma"): False}}
    two = PopupFacts(now=scn + dt.timedelta(minutes=2), **kw)
    five = PopupFacts(now=scn + dt.timedelta(minutes=5), **kw)
    assert _records(inbox_body(rows, popup=two))[1]["popup_due"] is False
    assert _records(inbox_body(rows, popup=five))[1]["popup_due"] is True


def test_the_route_reads_the_app_clock_not_the_real_one():
    src = inspect.getsource(route.adjustment_opportunities)
    assert "get_answer_clock" in inspect.getsource(route) and "datetime.now" not in src
