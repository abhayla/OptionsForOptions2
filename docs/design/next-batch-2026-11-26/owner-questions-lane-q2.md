# Owner questions, Lane Q2 (screens, Wave 2), 26 Nov 2026

Asked through the coordinator only. Each question names what was built meanwhile; every built choice is reversible.

## LQ2-1 "Real P&L" on the one Positions list has no figure to show

Business call: what the "Real P&L" total shows while the server sends no real P&L.

Spec basis: ADR-330 (10) "The top shows two totals, 'Real P&L' and 'Paper P&L', never added together"; ADR-016 (real
rows from Zerodha first); ADR-008 (one engine owns every P&L number; the browser does no arithmetic). Class-1 fact:
`GET /positions` returns units only, no price and no P&L (`backend/ofo_app/routes/positions.py:10` docstring "no
price, P&L", `:53-73` reply shapes); strategy-level real P&L is "W-111 part 2", not built.

Real case: the owner's 25 Nov screen test showed no Zerodha positions open (real orders are hidden, ADR-281), so
today the Real total would have nothing to add even with a server figure.

Options:
- (a) Show "Real P&L" with a dash and the line "Real P&L is not shown yet: the server does not price Zerodha
  positions." The page prints a server figure the day one is served (`pnl_text`), with no browser sum. **Recommended**:
  it keeps ADR-330 (10)'s two totals visible, invents no number (ADR-008), and needs no server work in this lane.
- (b) Hide the Real total until W-111 part 2 is built. Not chosen meanwhile: the owner asked for two totals, and a
  hidden one looks like a missing feature.
- (c) Build real pricing now (W-111 part 2). Not chosen: server and market-data work outside this lane, Tier A.

Built meanwhile: (a).
