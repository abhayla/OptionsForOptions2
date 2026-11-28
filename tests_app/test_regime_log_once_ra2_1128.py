"""Lane RA2 (Lane TG finding, W-09): "regime input adx not read: ValueError" was logged on EVERY cycle of
a PATH scenario. Cause: the PATH scenarios carry no day candles (only ADJ-60 has ``market.daily``), so ADX(14) has 0 of
its 28 daily bars and ``regime.adx`` raises ``needs 28 daily bars, got 0``. The input stays None = "not checked" (never
a pass, ADR-279 (4)), which is right; the log was wrong: the class name only, again and again. Now the plain reason
(our own message, no token or body) is logged ONCE per input and reason; a different reason is logged again."""
from __future__ import annotations

import logging

from ofo_app import regime_inputs

NEEDS = "needs 28 daily bars, got 0"


def _raises(message: str):
    def read():
        raise ValueError(message)
    return read


def test_the_same_unreadable_input_is_logged_once_with_its_plain_reason(caplog):
    regime_inputs._TOLD.clear()
    with caplog.at_level(logging.WARNING, logger="ofo_app.regime_inputs"):
        answers = [regime_inputs._attempt("adx", _raises(NEEDS)) for _ in range(5)]
    assert answers == [None] * 5, "not read stays None: not checked, never a pass"
    told = [r.getMessage() for r in caplog.records]
    assert told == [f"regime input adx not read: ValueError: {NEEDS}"], told


def test_a_different_reason_or_another_input_is_logged_again(caplog):
    regime_inputs._TOLD.clear()
    with caplog.at_level(logging.WARNING, logger="ofo_app.regime_inputs"):
        regime_inputs._attempt("adx", _raises(NEEDS))
        regime_inputs._attempt("adx", _raises("a day candle has no range"))
        regime_inputs._attempt("vix", _raises(NEEDS))
    assert len(caplog.records) == 3  # noqa: PLR2004 - three distinct (input, reason) pairs


def test_a_kite_error_keeps_its_class_only_log_never_its_text(caplog):
    from ofo_app.kite_reads import KiteReadError  # noqa: PLC0415

    regime_inputs._TOLD.clear()

    def read():
        raise KiteReadError("token abc123 refused")
    with caplog.at_level(logging.WARNING, logger="ofo_app.regime_inputs"):
        assert regime_inputs._attempt("vix", read) is None
    assert [r.getMessage() for r in caplog.records] == ["regime input vix not read: KiteReadError"]


def test_a_value_error_that_is_not_this_modules_own_message_logs_its_class_only(caplog):
    """Opus review F6: a ValueError from parsing a Kite row can carry a slice of the response."""
    regime_inputs._TOLD.clear()
    with caplog.at_level(logging.WARNING, logger="ofo_app.regime_inputs"):
        regime_inputs._attempt("adx", _raises("time data 'access_token=XYZ;AAAA' does not match format"))
    assert [r.getMessage() for r in caplog.records] == ["regime input adx not read: ValueError"]
