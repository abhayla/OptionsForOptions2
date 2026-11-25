"""B6 (modular doors, Phase 3; D-41 server half): the ONE assembly of a strategy's money figures for the API.

The paper book page (``routes/paper.py``) and the tracking page (``routes/tracking.py``) each used to turn the open
contracts' price answers into a live-price map and call the engine (``ofo.tracking.orderbook``) themselves. They now
ask ``strategy_money_view``: it picks the live prices (``paper.is_live``, the one predicate) and calls the engine;
every figure is the engine's (ADR-008: one engine owns every P&L number). Nothing is added, subtracted or rounded
here, and each route keeps its own reply shape and its own text / rounding of the figures.

The PRICE BASIS is the caller's: the book page passes ``paper.display_price`` answers (ADR-212, the last close after
hours), the tracking page passes ``paper.leg_price`` answers (live only). That difference is data in ``prices``, not
code here. Paper only: no order, no broker call.
"""
from __future__ import annotations

import dataclasses
import functools
from collections.abc import Mapping, Sequence
from decimal import Decimal

from ofo.tracking import paper
from ofo.tracking.orderbook import BookView, LifecycleView, NetPosition, PaperOrder, lifecycles, net_positions


def live_prices(prices: Mapping[int | str, paper.Price]) -> dict[str, Decimal]:
    """The open contracts that have a live price, by contract id text (the engine's key). A stale or missing answer is
    left out whatever number it carries (REQ-109 AC-5)."""
    return {str(cid): p.price for cid, p in prices.items() if paper.is_live(p) and p.price is not None}


@dataclasses.dataclass(frozen=True)
class MoneyView:
    """One strategy's figures from the engine at one set of prices.

    ``priced``: every open contract with a live price. ``live``: the totals' basis, ``priced`` unless the caller said
    the totals stay paused. ``book``: the engine's book at ``live`` (booked always known; unbooked and total ``None``
    while any open contract is unpriced). ``by_contract``: each contract's own figure at ``priced`` (ADR-311: a priced
    leg keeps its figure while the totals are paused).

    ``book`` and ``by_contract`` are computed when first asked and then kept (a view that is only split by
    ``lifecycle`` runs no second engine call). When the totals' basis is the priced set, ``by_contract`` is the book's own
    positions: one engine call serves both."""

    orders: tuple[PaperOrder, ...]
    priced: dict[str, Decimal]
    live: dict[str, Decimal]

    @functools.cached_property
    def book(self) -> BookView:
        return net_positions(self.orders, self.live)

    @functools.cached_property
    def by_contract(self) -> dict[str, NetPosition]:
        engine_book = self.book if self.live is self.priced else net_positions(self.orders, self.priced)
        return {p.instrument_id: p for p in engine_book.positions}

    @property
    def paused(self) -> bool:
        """An open contract is unpriced: the book has no unbooked figure and no total (REQ-109 AC-5)."""
        return self.book.unbooked is None

    def lifecycle(self) -> LifecycleView:
        """The same book split at every flat point (D-10), at ``priced``: the paper page's positions and closed rows."""
        return lifecycles(self.orders, self.priced)


def strategy_money_view(orders: Sequence[PaperOrder], prices: Mapping[int | str, paper.Price], *,
                        totals_priced: bool = True) -> MoneyView:
    """The strategy's figures at ``prices`` (one price answer per open contract). ``totals_priced=False``: the totals
    stay paused whatever the prices (the tracking page for a paused or unconnected book)."""
    priced = live_prices(prices)
    return MoneyView(tuple(orders), priced, priced if totals_priced else {})
