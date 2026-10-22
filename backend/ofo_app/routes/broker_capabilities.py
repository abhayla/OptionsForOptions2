"""Read-only: which broker abilities the platform may offer, for the screens (REQ-117 AC-1, AC-4, W-132).

``GET /api/broker/capabilities`` answers each of the seven named flags as on/off and nothing else (no source text,
no broker name). The flags are declared data (``ofo.broker.kite_capabilities``): no request, query parameter or header
changes the answer, and the route has no write method. A declaration that cannot load answers every flag off. The
screens treat a missing flag or a failed read as off too (``frontend/src/lib/brokerCapabilities.js``).
"""
from __future__ import annotations

from fastapi import APIRouter
from ofo.broker import kite_capabilities
from ofo.broker.capabilities import is_supported, load_or_off

from ofo_app.api_models import ApiModel
from ofo_app.errors import ClosedRoute

router = APIRouter(route_class=ClosedRoute)


class CapabilitiesOut(ApiModel):
    basket_page_orders: bool
    broker_held_triggers: bool
    intraday_product: bool
    order_update_stream: bool
    funds_read: bool
    positions_read: bool
    basket_margin_quote: bool


@router.get("/api/broker/capabilities", response_model=CapabilitiesOut)
async def broker_capabilities() -> CapabilitiesOut:
    flags = load_or_off(kite_capabilities.load_zerodha_capabilities)
    return CapabilitiesOut(**{name: is_supported(flags, name) for name in CapabilitiesOut.model_fields})
