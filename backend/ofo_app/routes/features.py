"""W-121 (REQ-073 AC-6, ADR-165): which switchable features the server has on, for the screens.

Today one: ``order_path``. The screens show an Execute action only on the answer ``on``; any other answer, a missing
field or a failed read is treated as off (the frontend fails closed). The server still refuses the order routes itself
(``ofo_app.order_path_switch``): this read only keeps the screens from offering what the server will refuse.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter

from ofo_app.api_models import ApiModel
from ofo_app.errors import ClosedRoute
from ofo_app.order_path_switch import order_path_on

router = APIRouter(route_class=ClosedRoute)


class FeaturesOut(ApiModel):
    order_path: Literal["on", "off"]


@router.get("/features", response_model=FeaturesOut)
async def features() -> FeaturesOut:
    return FeaturesOut(order_path="on" if order_path_on() else "off")
