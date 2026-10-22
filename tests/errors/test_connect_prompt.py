"""REQ-015 AC-2: the contextual Zerodha connection prompt is the requirement's sentence, word for word."""
from __future__ import annotations

from ofo.errors import CATALOGUE

#: Typed from REQ-015 AC-2 on purpose (not imported from the code): the test must die if the code's text drifts.
AC2_SENTENCE = ("Connect your Zerodha account to continue. We'll use your Zerodha account to verify availability, "
                "check margin and prepare/execute your strategy.")


def test_the_not_connected_gate_asks_with_the_ac2_sentence_exactly():
    assert CATALOGUE["gate_broker_not_connected"].what_happened == AC2_SENTENCE


def test_no_template_still_asks_for_the_connection_in_the_old_words():
    old = "Your Zerodha account is not connected. Connect it to continue."
    assert [tid for tid, t in CATALOGUE.items() if old in t.what_happened] == []
