"""GC-TP R-20 / R-15 (ADR-210): the one reviewed sentence for every reason code the paper routes send.

A figure that cannot be shown is a dash; the reply carries the sentence beside it (``*_reason_text``), so the browser
shows text it never writes. Each code maps to exactly one pinned template; a code with no entry here gets the generic
"not available" text (never blank, never the raw code), and tests/test_paper_reason_texts.py fails when a code the
routes can send is missing from ``TEMPLATE_OF``.
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from ofo.errors.explanations import ExplanationText, render_explanation

#: reason code -> explanation template id (ADR-210; no_iv, no_next_open, rates_unavailable reuse reviewed texts)
TEMPLATE_OF: Mapping[str, str] = MappingProxyType({
    "not_priced": "paper_reason_not_priced",
    "model_refused": "paper_reason_model_refused",
    "contract_retired": "paper_reason_contract_retired",
    "contract_delisted": "paper_reason_contract_delisted",
    "token_reassigned": "paper_reason_token_reassigned",
    "contract_missing": "paper_reason_contract_missing",
    "no_iv": "table_reason_no_iv",
    "no_next_open": "table_reason_no_next_open",
    "rates_unavailable": "execute_cost_charges_not_included",
    "prices_not_live": "paper_reason_prices_not_live",
    "multi_expiry": "paper_reason_multi_expiry",
    "whatif_stale": "paper_reason_whatif_stale",  # ADR-210 (7), carried by the what-if reply as ``stale_text``
})
GENERIC = "table_reason_not_available"
#: the Profit left / Loss left words for the two extremes reasons (already in the product; moved here unchanged)
EXTREMES_TEMPLATE_OF: Mapping[str, str] = MappingProxyType({
    "multi_expiry": "paper_reason_multi_expiry",
    "prices_not_live": "paper_extremes_prices_not_live",
    "exited": "paper_reason_exited",
})
EXTREMES_GENERIC = "paper_extremes_unknown"
#: the breakeven dash (ADR-211 (5)): a card on legs with different expiries, and a fully exited strategy
BREAKEVEN_TEMPLATE_OF: Mapping[str, str] = MappingProxyType({
    "multi_expiry": "paper_breakeven_multi_expiry",
    "exited": "paper_reason_exited",
})
#: a code that reaches a Greeks dash from the book: the reason table above, plus the exited word
GREEKS_TEMPLATE_OF: Mapping[str, str] = MappingProxyType({**TEMPLATE_OF, "exited": "paper_reason_exited"})


def reason_text(code: str | None) -> ExplanationText | None:
    """The sentence for a reason code; None for no code; the generic "not available" for a code not mapped."""
    if code is None:
        return None
    return render_explanation(TEMPLATE_OF.get(code, GENERIC))


def extremes_reason_text(code: str | None) -> ExplanationText | None:
    """The sentence for an ``extremes_reason`` code (Profit left / Loss left words)."""
    if code is None:
        return None
    return render_explanation(EXTREMES_TEMPLATE_OF.get(code, EXTREMES_GENERIC))


def breakevens_reason_text(code: str | None) -> ExplanationText | None:
    """The sentence for a ``breakevens_reason`` code; an unmapped code gets the generic "not available" text."""
    if code is None:
        return None
    return render_explanation(BREAKEVEN_TEMPLATE_OF.get(code, GENERIC))


def greeks_reason_text(code: str | None) -> ExplanationText | None:
    """The sentence for a ``greeks_reason`` code (a pause, a contract state, no IV, a refused model, or exited)."""
    if code is None:
        return None
    return render_explanation(GREEKS_TEMPLATE_OF.get(code, GENERIC))
