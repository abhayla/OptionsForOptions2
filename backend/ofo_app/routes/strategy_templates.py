"""``GET /api/strategy-templates``: the reviewed strategy templates for the Learn page (W-117; REQ-011 AC-1, ADR-114).

Read-only and database-free: the one catalogue file (``ofo/strategy/catalogue.yaml``) is read through its loader, and
each name and description reaches the response door as a catalogue text (``ofo.errors.explanations.TemplateText`` only
accepts a text the loaded catalogue holds), so the browser retypes nothing. V1 has one fixed owner and no login, so the
route carries no user value (like ``routes/indices.py``).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from ofo.errors.explanations import render_explanation
from ofo.strategy.loader import load_templates
from ofo.strategy.model import Template

from ofo_app.api_models import ApiModel, CatalogueText, Identifier
from ofo_app.errors import ClosedRoute

PATH = "/api/strategy-templates"

router = APIRouter(route_class=ClosedRoute)


class TemplateLegOut(ApiModel):
    """One leg of a template at its default parameters (W-119): the strike as whole steps from the ATM strike."""

    action: Literal["BUY", "SELL"]
    instrument: Literal["CE", "PE", "FUT"]
    strike_steps: int | None
    expiry_slot: Identifier  # the catalogue slot name (near, next, far)
    quantity_multiplier: int


class TemplateOut(ApiModel):
    id: Identifier
    name: CatalogueText
    description: CatalogueText
    level: Literal["Beginner", "Intermediate", "Advanced"]
    views: list[Literal["bullish", "bearish", "range-bound", "volatile"]]
    objectives: list[Literal["income", "directional", "hedge", "volatility"]]
    legs: list[TemplateLegOut]


class TemplatesOut(ApiModel):
    templates: list[TemplateOut]


def default_legs(t: Template) -> list[TemplateLegOut]:
    """The template's legs at its catalogue defaults (REQ-028: templates are data; the engine prices them)."""
    defaults = {p.name: p.default for p in t.params}
    return [TemplateLegOut(action=leg.action.value, instrument=leg.instrument.value,  # type: ignore[arg-type]
                           strike_steps=None if leg.strike is None else leg.strike.evaluate(defaults),
                           expiry_slot=leg.expiry_slot, quantity_multiplier=leg.quantity_multiplier)  # type: ignore[arg-type]
            for leg in t.legs]


@router.get(PATH, response_model=TemplatesOut)
def strategy_templates() -> TemplatesOut:
    return TemplatesOut(templates=[
        TemplateOut(id=t.id, name=render_explanation("catalogue_template_name", text=t.name),
                    description=render_explanation("catalogue_template_description", text=t.description),
                    level=t.level, views=list(t.views), objectives=list(t.objectives),  # type: ignore[arg-type]
                    legs=default_legs(t))
        for t in load_templates()])
