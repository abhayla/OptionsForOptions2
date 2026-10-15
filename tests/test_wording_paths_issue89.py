"""Issue #89 (ADR-003 Q230/Q235): the three user-text paths named there reach the ONE shared checker,
``ofo.wording.check_platform_text``, and a forbidden promise phrase is refused on each:

1. ``ofo.execution.safety`` Flag texts (CheckFailure texts come from ``render()``, covered via path 2's builder);
2. ``ofo.marketdata.disconnect`` (the message is a catalogue ``UserFacingError``; its builder runs the checker);
3. ``ofo.rules.templates`` labels (``render_explanation`` -> ``check_explanation_wording`` -> the checker).

Each path gets the phrases below, taken from the ADR-003 forbidden list and the Q230/Q235 word-form families.
"""
from __future__ import annotations

import datetime

import pytest

from ofo import wording
from ofo.errors import model, render
from ofo.errors.explanations import check_explanation_wording, render_explanation
from ofo.execution.safety import Flag, FlagCode
from ofo.marketdata.disconnect import DisconnectStatus, disconnect_error, disconnect_message

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
WHEN = datetime.datetime(2026, 10, 15, 10, 42, 17, tzinfo=IST)

FORBIDDEN = [
    "This is the best trade",          # ADR-003 phrase / Q226 bare word
    "Recommended trade",               # ADR-003 phrase
    "Guaranteed profit",               # ADR-003 phrase
    "Risk-free exit",                  # ADR-003 phrase
    "Certain profit on this leg",      # ADR-003 phrase
    "You should take this trade",      # ADR-003 phrase
    "Your losses are minimised",       # Q235 word form
    "You cannot lose here",            # Q235 promise
    "No loss on this strategy",        # Q235 promise
    "A safer way to exit",             # Q230 word form
]


def test_forbidden_phrases_are_refused_by_the_shared_checker_itself() -> None:
    for phrase in FORBIDDEN:
        with pytest.raises(ValueError, match="banned wording"):
            wording.check_platform_text(phrase, "probe")


# --- path 1: execution/safety.py Flag --------------------------------------------------------------------------------

@pytest.mark.parametrize("phrase", FORBIDDEN)
def test_safety_flag_refuses_forbidden_phrase(phrase: str) -> None:
    with pytest.raises(ValueError, match="banned wording"):
        Flag(FlagCode.UNLIMITED_LOSS, phrase)


def test_safety_flag_keeps_allowed_text() -> None:
    Flag(FlagCode.UNLIMITED_LOSS, "This strategy has no upper limit on loss.")
    Flag(FlagCode.CHARGES_UNAVAILABLE, "Charges could not be estimated; the safety check still ran.")


# --- path 2: marketdata/disconnect.py --------------------------------------------------------------------------------

def test_disconnect_text_passes_the_shared_checker_and_keeps_owner_sentence() -> None:
    assert disconnect_message(WHEN) == (
        "Live market data disconnected. Last updated: 10:42:17 AM. Live strategy monitoring is paused."
    )
    err = disconnect_error(WHEN)
    for part in (err.what_happened, err.impact, err.what_is_blocked, err.next_action):
        wording.check_platform_text(part, "disconnect part")


@pytest.mark.parametrize("phrase", FORBIDDEN)
def test_disconnect_message_builder_refuses_forbidden_phrase(phrase: str) -> None:
    fields = dict(model._fields_of(disconnect_error(WHEN)))
    fields["what_happened"] = phrase
    with pytest.raises(ValueError, match="banned wording"):
        model._checked(fields)


def test_disconnect_status_refuses_a_plain_string_message() -> None:
    with pytest.raises(TypeError):
        DisconnectStatus(error="Live monitoring is risk-free", last_updated=WHEN)  # type: ignore[arg-type]


# --- path 3: rules/templates.py labels -------------------------------------------------------------------------------

@pytest.mark.parametrize("phrase", FORBIDDEN)
def test_rule_label_wording_check_refuses_forbidden_phrase(phrase: str) -> None:
    with pytest.raises(ValueError):
        check_explanation_wording(phrase, "rule label probe")


def test_every_rule_label_template_passes_check_platform_text() -> None:
    from decimal import Decimal as D

    from ofo.rules import templates as t
    from ofo.rules.inputs import InputName
    from ofo.rules.model import RuleAction

    act = RuleAction.ALERT_ONLY
    rules = [
        t.entry_immediate("a", action=act),
        t.entry_level_reached("a", D("24000"), t.Direction.AT_OR_ABOVE, action=act),
        t.entry_range("a", D("23000"), D("24000"), action=act),
        t.entry_premium_target("a", D("3750"), receive=True, action=act),
        t.entry_premium_target("a", D("3750"), receive=False, action=act),
        t.entry_volatility("a", InputName.IV, D("20"), D("30"), action=act),
        t.entry_volatility("a", InputName.IV, D("20"), None, action=act),
        t.entry_volatility("a", InputName.IV_PERCENTILE, None, D("30"), action=act),
        t.entry_time_window("a", datetime.time(9, 30), datetime.time(11, 0), action=act),
        t.exit_profit_target("a", D("3000"), action=act),
        t.exit_max_loss("a", D("5000"), action=act),
        t.exit_time("a", days_to_expiry=2, action=act),
        t.exit_time("a", days_to_expiry=1, at_or_after=datetime.time(14, 0), action=act),
        t.exit_underlying_level("a", D("23000"), t.Direction.AT_OR_BELOW, action=act),
    ]
    for rule in rules:
        wording.check_platform_text(str(rule.description), f"rule label {rule.rule_id}")


def test_render_explanation_still_refuses_an_unknown_template() -> None:
    with pytest.raises(ValueError):
        render_explanation("rule_label_best_trade")


def test_render_of_unknown_error_template_is_refused() -> None:
    with pytest.raises(Exception):
        render("no_such_template")
