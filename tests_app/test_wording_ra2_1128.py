"""Lane RA2 item 9 (decision-support wording, ADR-003; every new sentence is "pending owner read"):
(1) an index exit that HAS fired words its line in the past tense (the preview keeps "After these orders");
(2) the 3 fired leg-stop ids and the 2 new fired-exit ids are in ``STOP_LINE_TEMPLATES``; a stored line reads back;
(3) the Return door says what really happened when the strategy changed while the user was at Kite.
Real case (ADR-330 (6), 25 Nov): the exit of the condor's short 26000 CE left max loss at -2,860 before and -12,005.51
after, with the sold 25400 PE less protected."""
from __future__ import annotations

import datetime
from decimal import Decimal
from types import SimpleNamespace

from ofo.errors import render
from ofo.errors.explanations import render_explanation, restore_explanation
from ofo.tracking.paper_alert import STOP_LINE_TEMPLATES
from ofo_app.routes import paper as paper_routes

MINUS = "\u2212"  # the server's minus sign on money text


def _leg():
    strike = render_explanation("strike_part", strike="25400")
    return render_explanation("contract_display", underlying="NIFTY", day=1, month="Dec", strike=strike,
                              instrument="PE")


def _risk():
    return SimpleNamespace(max_loss_before=Decimal("-2860"), max_loss_after=Decimal("-12005.51"), exposed=("a",))


def test_a_fired_index_exit_reads_in_the_past_tense_and_the_preview_is_unchanged():
    names = {"a": _leg()}
    preview = str(paper_routes._exit_warning(_risk(), names).warning_text)
    fired = str(paper_routes._exit_warning(_risk(), names, fired=True).warning_text)
    assert preview == (f"After these orders, maximum loss: {MINUS}2,860.00 before, {MINUS}12,005.51 after. "
                       "Sold option with less protection: NIFTY 1 Dec 25400 PE.")
    assert fired == (f"After the exit, maximum loss was {MINUS}2,860.00 before and {MINUS}12,005.51 after. "
                     "A sold option was left with less protection: NIFTY 1 Dec 25400 PE.")


def test_every_fired_line_wording_is_in_the_stop_line_templates_and_a_stored_line_reads_back():
    for template_id in ("paper_leg_stop_fired", "paper_leg_stop_fired_unlimited", "paper_leg_stop_fired_unknown",
                        "paper_exit_fired_loss", "paper_exit_fired_less_protected"):
        assert template_id in STOP_LINE_TEMPLATES, template_id
    line = render_explanation("paper_exit_fired_loss", before=render_explanation("paper_charges", amount=Decimal("1")),
                              after=render_explanation("paper_charges", amount=Decimal("2")))
    back = restore_explanation("paper_exit_fired_loss", str(line))
    assert str(back) == str(line)


def test_the_closed_market_orders_line_carries_the_same_prefix_as_the_exit_line():
    day = datetime.date(2026, 11, 30)
    assert str(render_explanation("exit_market_closed_entries", day=day)) == (
        "The market is closed. Orders can be placed from 09:15 on Monday 30 Nov.")
    assert str(render_explanation("exit_market_closed_entries_no_day")) == (
        "The market is closed. Orders can be placed when it opens.")


def test_the_return_door_changed_sentence_says_what_happened_and_what_to_do():
    parts = render("execution_return_changed")
    assert parts.what_happened == (
        "Something changed on this strategy while you were away at Kite, so nothing was recorded.")
    assert parts.next_action == "Press Return again."
