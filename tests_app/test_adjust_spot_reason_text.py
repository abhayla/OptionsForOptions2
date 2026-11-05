"""GC-SET step 6 (REQ-156 AC-1): every per-source spot reason the user sees is words, never a code.

Class: every reason code ``resolve_spot`` can emit, for each of the three sources, and an unknown code."""
from __future__ import annotations

import pytest

from ofo.marketdata.spot_source import (
    REASON_ABSENT, REASON_FUTURE, REASON_NO_PRICE, REASON_NO_TIME, REASON_NOT_FINITE, REASON_STALE,
    SOURCE_FEED, SOURCE_LAST_CLOSE, SOURCE_REST, SpotAnswer, SourceState,
)
from ofo_app.api_models import AdjustSpotOut
from ofo_app.routes import adjustment as route

SOURCES = (SOURCE_FEED, SOURCE_REST, SOURCE_LAST_CLOSE)
CODES = (REASON_ABSENT, REASON_NO_PRICE, REASON_NO_TIME, REASON_FUTURE, REASON_STALE, REASON_NOT_FINITE,
         SourceState.NOT_FOUND.value, SourceState.FAILED.value, SourceState.EMPTY.value)


def _block(code: str) -> dict:
    return route._spot_block(SpotAnswer(None, None, None, tuple((s, code) for s in SOURCES)))


@pytest.mark.parametrize("code", CODES)
def test_every_emitted_code_has_a_sentence(code: str) -> None:
    block = _block(code)
    assert len(block["reasons"]) == 3
    for item in block["reasons"]:
        text = str(item["reason_text"])
        assert text != code and text != item["reason"]
        assert " " in text and "_" not in text
    AdjustSpotOut.model_validate(block)  # the reply shape carries reason_text


def test_unknown_code_reads_reason_not_given_never_the_code() -> None:
    block = _block("weird_new_code")
    for item in block["reasons"]:
        assert str(item["reason_text"]) == "reason not given"
    assert "weird_new_code" not in str(block["text"])
