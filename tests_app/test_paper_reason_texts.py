"""GC-TP R-20 / R-15 (ADR-210): every reason code the paper routes send has exactly one reviewed server text.

Core proof: the code sets are read from the routes' own Literal types (ChargesReason, ContractReason, DecayReason,
PauseReason, ExtremesReason); each must map to a non-empty ExplanationText, the seven ADR-210 sentences must be
byte-equal to spec/decisions/ADR-210.md, and an unknown future code gets the generic "not available" text.
"""
from __future__ import annotations

import pathlib
import re
import typing
from decimal import Decimal

import yaml
from ofo.engine.extremes import ExtremesReason
from ofo.errors.explanations import EXPLANATIONS, TABLE_REASON_TEXT, ExplanationText
from ofo.tracking import paper, paper_decay
from ofo.tracking.paper_decay import Decay
from ofo_app import paper_reasons
from ofo_app.routes import paper as paper_routes

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPECTED_SEVEN = 7
ADR = ROOT / "spec" / "decisions" / "ADR-210.md"


def _codes(tp: object) -> set[str]:
    args = typing.get_args(tp)
    if typing.get_origin(tp) is typing.Literal:
        return set(args)
    out: set[str] = set()
    for a in args:
        out |= _codes(a)
    return out


def _sent_codes() -> set[str]:
    return (_codes(paper_routes.ChargesReason) | _codes(paper.ContractReason) | _codes(paper_decay.DecayReason)
            | _codes(paper.PauseReason) | _codes(ExtremesReason))


def _adr_sentences() -> dict[str, str]:
    decision = yaml.safe_load(ADR.read_text(encoding="utf-8").split("---")[1])["decision"]
    found = dict(re.findall(r"\(\d\) (\w+): \"(.*?)\"", decision))
    stale = re.search(r"\(7\) a stale what-if figure: \"(.*?)\"", decision)
    assert stale
    found["whatif_stale"] = stale.group(1)
    return found


def test_the_code_sets_are_what_the_task_listed() -> None:
    assert _sent_codes() == {"rates_unavailable", "not_priced", "contract_retired", "contract_delisted",
                             "token_reassigned", "contract_missing", "no_iv", "no_next_open", "model_refused",
                             "prices_not_live", "multi_expiry"}


def test_every_code_has_a_non_empty_text() -> None:
    for code in sorted(_sent_codes()):
        got = paper_reasons.reason_text(code)
        assert isinstance(got, ExplanationText) and got.strip(), code
        assert code not in got, code  # the raw code is never the text


def test_the_seven_texts_are_byte_equal_to_the_adr() -> None:
    sentences = _adr_sentences()
    assert len(sentences) == EXPECTED_SEVEN
    for code, expected in sentences.items():
        assert paper_reasons.reason_text(code) == expected, code


def test_the_three_reused_texts_are_the_reviewed_ones() -> None:
    assert paper_reasons.reason_text("no_iv") == TABLE_REASON_TEXT["no_iv"]
    assert paper_reasons.reason_text("no_next_open") == TABLE_REASON_TEXT["no_next_open"]
    assert paper_reasons.reason_text("rates_unavailable") == EXPLANATIONS["execute_cost_charges_not_included"].text


def test_an_unknown_future_code_is_the_generic_text_never_blank_or_raw() -> None:
    got = paper_reasons.reason_text("some_future_code")
    assert got == TABLE_REASON_TEXT["not_available"]
    assert "some_future_code" not in got
    assert paper_reasons.reason_text(None) is None


def test_every_extremes_code_has_its_words_and_an_unknown_one_the_generic() -> None:
    for code in sorted(_codes(ExtremesReason)):
        got = paper_reasons.extremes_reason_text(code)
        assert got and got.startswith("Profit left and Loss left are not worked out"), code
        assert code not in got
    assert paper_reasons.extremes_reason_text("future_code") == "Profit left and Loss left are not worked out."
    assert paper_reasons.extremes_reason_text(None) is None


def test_the_old_contract_price_stale_sentence_is_not_the_what_if_text() -> None:
    assert not paper_reasons.reason_text("whatif_stale").startswith("Stale: the latest price")


def test_the_routes_put_the_text_beside_every_reason() -> None:
    """The reply carries the text next to each code: charges, totals, decay and a contract state."""




    d = Decimal
    strategies = [{"booked": d("1"), "unbooked": None, "pause_reason": "contract_retired", "charges": None,
                   "charges_reason": "not_priced"}]
    out = paper_routes._totals(strategies, [Decay(None, "model_refused")])
    assert out["totals_reason_text"] == paper_reasons.reason_text("contract_retired")
    assert out["decay_reason_text"] == paper_reasons.reason_text("model_refused")
    assert out["charges_reason_text"] == paper_reasons.reason_text("not_priced")
    ok = paper_routes._totals([{"booked": d("1"), "unbooked": d("2"), "pause_reason": None, "charges": d("3"),
                                "charges_reason": None}], [Decay(d("1"), None)])
    assert ok["totals_reason_text"] is None and ok["decay_reason_text"] is None and ok["charges_reason_text"] is None
    price = paper.Price("k", "token_reassigned", None, None)
    assert paper_routes._state_text(price) == paper_reasons.reason_text("token_reassigned")
    assert paper_routes._state_text(paper.Price("k", "live", d("1"), None)) is None
    assert paper_routes._state_text(None) is None
