"""W-024 round 10 item 1 (issue 30 round-9 MAJOR 1): redaction sits at the ROOT of logging, not on a logger list.

The structural door is the log-record factory (`logging.setLogRecordFactory`): every record from every logger - named
or not, created before or after start-up, propagating or not - is built by it, so it is redacted before any handler,
filter or formatter sees it. These tests log a real-shaped Kite access token and a held api secret through logger names
the code never registered and assert the captured output carries the marker and never the secret.
"""

from __future__ import annotations

import io
import logging

import pytest

# A Kite Connect access token is 32 letters and digits; this example is made up in that shape (assembled at run time).
KITE_SHAPED = "".join(["x4k9Qm2L", "p7Rt5Vw8", "Yz1Ab3Cd", "6Ef0Gh2J"])
# A secret the process holds. Letters only, so NO shape rule can recognise it: only its VALUE redacts it.
HELD_VALUE = "".join(["kiteexample", "heldletters", "onlyvalue"])
NAMES = ("ofo.execution.safety", "ofo_app.routes.anything", "zz.unrelated")


@pytest.fixture()
def capture():
    from ofo_app.redaction import install_redaction, register_secret

    install_redaction()
    register_secret(HELD_VALUE)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(name)s %(message)s %(detail)s", defaults={"detail": ""}))
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        yield stream
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


def _assert_clean(text: str) -> None:
    from ofo_app.redaction import REDACTED

    assert REDACTED in text
    assert KITE_SHAPED not in text
    assert HELD_VALUE not in text


@pytest.mark.parametrize("name", NAMES)
def test_any_logger_name_is_redacted(capture, name):
    logging.getLogger(name).info("value %s held %s", KITE_SHAPED, HELD_VALUE)
    out = capture.getvalue()
    assert name in out
    _assert_clean(out)


def test_a_child_logger_created_after_start_up_is_redacted(capture):
    child = logging.getLogger("late.%s.child" % id(capture))  # never existed before this line
    child.warning("session %s", KITE_SHAPED)
    _assert_clean(capture.getvalue())


def test_a_non_propagating_logger_with_its_own_handler_is_redacted(capture):
    stream = io.StringIO()
    own = logging.getLogger("zz.isolated.own_handler")
    own.propagate = False
    handler = logging.StreamHandler(stream)
    own.addHandler(handler)
    try:
        own.error("held=%s", HELD_VALUE)
    finally:
        own.removeHandler(handler)
        own.propagate = True
    _assert_clean(stream.getvalue())


def test_extra_fields_and_exception_text_are_redacted(capture):
    log = logging.getLogger("zz.unrelated.extra")
    try:
        raise RuntimeError(f"kite rejected {KITE_SHAPED} with {HELD_VALUE}")
    except RuntimeError:
        log.exception("failed", extra={"detail": KITE_SHAPED})
    _assert_clean(capture.getvalue())


def test_a_handler_added_later_is_still_covered(capture):
    stream = io.StringIO()
    late = logging.StreamHandler(stream)
    logging.getLogger().addHandler(late)
    try:
        logging.getLogger("zz.after").info("%s", KITE_SHAPED)
    finally:
        logging.getLogger().removeHandler(late)
    _assert_clean(stream.getvalue())


def test_a_broken_format_fails_closed_to_the_marker(capture):
    """`%d` with a string argument raises inside formatting: the output is the marker, never the raw argument."""
    logging.getLogger("zz.broken").info("count %d", HELD_VALUE)
    _assert_clean(capture.getvalue())


def test_a_record_built_by_hand_through_makeLogRecord_is_redacted(capture):
    record = logging.makeLogRecord({"name": "zz.hand", "msg": "tok %s", "args": (KITE_SHAPED,),
                                    "levelno": logging.INFO, "levelname": "INFO"})
    logging.getLogger("zz.hand").handle(record)
    _assert_clean(capture.getvalue())


def test_the_record_factory_is_the_redacting_one():
    """Mutation guard: removing the factory hook (or replacing it later) is visible here and in every test above."""
    from ofo_app import redaction

    redaction.install_redaction()
    assert logging.getLogRecordFactory() is redaction.redacting_record_factory


def test_mutation_removing_the_factory_leaks(capture, monkeypatch):
    """Mutation: put the stock factory back -> the value reaches the log (so the tests above are load-bearing)."""
    monkeypatch.setattr(logging, "_logRecordFactory", logging.LogRecord)
    logging.getLogger("zz.mutation").info("%s", KITE_SHAPED)
    assert KITE_SHAPED in capture.getvalue()
