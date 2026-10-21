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

from ofo_app.api_models import ApiModel, CatalogueText, Identifier
from ofo_app.errors import ClosedRoute

PATH = "/api/strategy-templates"

router = APIRouter(route_class=ClosedRoute)


class TemplateOut(ApiModel):
    id: Identifier
    name: CatalogueText
    description: CatalogueText
    level: Literal["Beginner", "Intermediate", "Advanced"]
    views: list[Literal["bullish", "bearish", "range-bound", "volatile"]]
    objectives: list[Literal["income", "directional", "hedge", "volatility"]]


class TemplatesOut(ApiModel):
    templates: list[TemplateOut]


@router.get(PATH, response_model=TemplatesOut)
def strategy_templates() -> TemplatesOut:
    return TemplatesOut(templates=[
        TemplateOut(id=t.id, name=render_explanation("catalogue_template_name", text=t.name),
                    description=render_explanation("catalogue_template_description", text=t.description),
                    level=t.level, views=list(t.views), objectives=list(t.objectives))  # type: ignore[arg-type]
        for t in load_templates()])
