"""Totals over paper books and a book's Decay sum (GC-TP step 4a; ADR-008: the one engine owns every money number).

Spec basis: REQ-109 AC-4 / AC-5 (the one engine derives the figures; a figure that needs a price that is not live is
absent, never a partial sum); REQ-145 AC-2 / F-63 (Decay to the next market open, after Theta); screens 050-053 (the
totals strip: Total P&L, Booked, Unbooked, Total Decay).

- ``signed_decay``: per-unit decay x signed net quantity summed over a book's open contracts, UNROUNDED (the P&L
  table's Decay column rule: per-unit x quantity x sign, BUY +1, SELL -1).
- ``book_totals``: exact sums of booked (always known), unbooked (None as soon as one book's is None) and total
  (booked + unbooked, None with it); Decay summed unrounded over the books and rounded ONCE to the paisa, half-even
  (the table's TOTAL row rule), None as soon as one book's decay is None. No books: every figure is 0.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal

from ofo.money import PAISE


@dataclass(frozen=True)
class BookTotals:
    booked: Decimal
    unbooked: Decimal | None
    total: Decimal | None
    decay: Decimal | None  # rounded to the paisa


def signed_decay(units: Iterable[tuple[Decimal, int]]) -> Decimal:
    """Sum of (per-unit decay x signed net quantity) over a book's open contracts, unrounded."""
    return sum((unit * net_quantity for unit, net_quantity in units), Decimal(0))


def book_totals(books: Sequence[tuple[Decimal, Decimal | None]], decays: Sequence[Decimal | None]) -> BookTotals:
    """``books``: each book's (booked, unbooked); ``decays``: each book's unrounded decay (None when absent)."""
    booked = sum((b for b, _ in books), Decimal(0))
    unbooked = None
    if all(u is not None for _, u in books):
        unbooked = sum((u for _, u in books if u is not None), Decimal(0))
    decay = None
    if all(d is not None for d in decays):
        decay = sum((d for d in decays if d is not None), Decimal(0)).quantize(PAISE, rounding=ROUND_HALF_EVEN)
    return BookTotals(booked, unbooked, None if unbooked is None else booked + unbooked, decay)
