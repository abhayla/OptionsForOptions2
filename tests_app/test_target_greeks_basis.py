"""GC-ICFIX u507 (user-test notes ISSUES.md 41, 43): the "Greeks at target" block printed the raw 4-decimal position
figures ("theta 264.6944") with no basis, beside a Greeks card that says "Per position, 65 units". The server now sends
the figures as text at the card's own places (delta, theta, vega 2; gamma 4, rounded once from the unrounded total)
and the basis sentence itself ("Per position, N units"; "Per position" when the legs differ). No database."""
from __future__ import annotations

import pathlib
import re
import sys
from decimal import Decimal

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ofo.errors.explanations import render_explanation
from test_outcome_route import _body, provider_for_catalogue
from test_outcome_target_booked import _post

D = Decimal


@pytest.fixture(scope="module")
def provider():
    return provider_for_catalogue()
TWO_PLACES = re.compile(r"^-?\d+\.\d{2}$")
FOUR_PLACES = re.compile(r"^-?\d+\.\d{4}$")


async def _greeks(provider, lots: int | None = None) -> tuple[dict, dict]:
    extra = {}
    if lots is not None:
        extra["legs"] = [{**leg, "lots": lots} for leg in _body(provider)["legs"]]
    out = await _post(provider, None, **extra)
    return out, out["target"]["greeks"]


async def test_the_total_comes_as_two_decimal_text_gamma_at_the_cards_four(provider):
    _, g = await _greeks(provider)
    shown = g["total_display"]
    for name in ("delta", "theta", "vega"):
        assert TWO_PLACES.match(shown[name]), (name, shown[name])
        assert abs(D(shown[name]) - D(g["total"][name])) <= D("0.005")
    assert FOUR_PLACES.match(shown["gamma"]), shown["gamma"]


async def test_the_basis_names_the_units_one_lot(provider):
    out, g = await _greeks(provider)
    units = {leg["quantity"] for leg in out["legs"]}
    assert len(units) == 1
    assert g["basis_text"] == render_explanation("target_greeks_basis_units", count=units.pop())
    assert g["basis_text"].startswith("Per position, ") and g["basis_text"].endswith(" units")


async def test_the_basis_scales_with_lots(provider):
    one, g1 = await _greeks(provider)
    two, g2 = await _greeks(provider, lots=2)
    q1, q2 = one["legs"][0]["quantity"], two["legs"][0]["quantity"]
    assert q2 == 2 * q1
    assert g2["basis_text"] == render_explanation("target_greeks_basis_units", count=q2) != g1["basis_text"]


async def test_no_time_left_has_the_sentence_and_no_figures(provider):
    out = await _post(provider, None, target_at="2026-10-13T15:30:00+05:30")  # the condor's own expiry close
    g = out["target"]["greeks"]
    assert g["total"] is None and g["total_display"] is None and g["unavailable_text"]
