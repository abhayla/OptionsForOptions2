# Builder brief: W-097 Live 5-level depth for the Execute price - keep what the full frame already carries (Tier A: the price an order is sent at)

Core: the recorder's real 2026-10-16 session (`D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/frames-120730.bin.gz`, 708 MB,
read through `ofo.marketdata.kite_frames.iter_recording`) yields, for NIFTY26O1923650CE (Kite token 12080386), the
latest full-mode frame at or before 15:07:20 IST with 5 bid and 5 ask levels; compare it with Zerodha's REST quote of
the same second (`real-order/fetch.json` key `quote.depth`: bids 3.3/55250, 3.25/67535, ...; asks 3.35/56810,
3.4/53755, ...) and report level by level what matches. Then `executable_limit` on the frame's depth gives BUY 65 ->
3.35 and SELL 65 -> 3.30 if the levels match (if they differ, the frame wins for the test and the report says how).
Proof: step 1 is a throwaway script under `docs/research/depth-proof-2026-10-17/` (`proof.py` + `run-output.txt`) that
does exactly that on the real file and prints the two depths side by side; then cut ONE frame (the one used) into
`tests/fixtures/kite_ws/full-frame-12080386-150720.bin` with a README line naming its source offset, for the test.

Tier: A (the depth sets the LIMIT price an order is sent at, ADR-080). Model: sonnet.
Budget: 50 min wall-clock, 56 tool calls. HARD limit: at call 52 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words.
Copy from: none - spec/technical-design/legacy-reuse.md has no depth row we may reuse (searched: depth, quote); the
parser is this project's own (`kite_frames.py`, W-059).
Findings checked: money-parsed-through-float, fallback-time-claims-missing-data, staleness-by-last-change-age,
liveness-from-shared-subscribers, guard-as-forbidden-list, fixture-symbol-not-in-catalogue
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py

Read first: `docs/process/builder-brief.md` (every line applies), `CLAUDE.md`, `backend/ofo/marketdata/kite_frames.py`,
`backend/ofo/marketdata/feed_health.py` (`QuoteBook`), `backend/ofo/marketdata/kite_provider.py`,
`backend/ofo_app/live_push.py`, `backend/ofo_app/live_market.py`, `backend/ofo/engine/executable_price.py`
(`Depth`, `depth_from_quote`, `executable_limit`), `tests/marketdata/` (how recordings are replayed in tests).

## Spec basis
- ADR-080 (3), Execute at current market conditions: "sets each leg's LIMIT to the worst price level in Kite's 5-level
  depth needed to fill the whole quantity (BUY: ask side, SELL: bid side), rounded per (2)"
- F-29 (spec/findings.md): depth price 0 means absent - never a Rs 0 level.

## Work card (commit FIRST as `work/W-097.md`, frontmatter shape of `work/W-091.md`)
id W-097; title "Live 5-level depth kept from Kite full frames and readable for the Execute price (ADR-080 (3))";
requirement_ids [REQ-073]; tier A; status in_progress; depends_on []; affected [backend/ofo/marketdata/,
backend/ofo_app/, tests/, tests_app/]; tests_required ['AC-1: tests/marketdata/test_depth_from_frames.py'];
core/proof = the lines at the top; review_status 'not reviewed'; next_action 'Tier A review'.

## What to build
1. `kite_frames.py`: a full (184-byte) packet's ten depth entries (5 bid, 5 ask: quantity, price, orders) parsed into
   exact Decimal levels; a price-0 entry is absent (dropped, never a Rs 0 level); existing `bid`/`ask` fields unchanged.
   A quote (44) or ltp (8) packet has NO depth (None), never an empty depth that reads as "no liquidity".
2. The latest depth per instrument kept beside the quote in the live book, with the frame's own exchange time; removed
   with the quote (same `remove`/`park`/`restore` rules - no depth outlives its subscription, REQ-049 AC-4).
3. One reader for the app: `latest_depth(instrument_id, now) -> Depth | None` that returns the domain `Depth` (build it
   through `depth_from_quote` or a sibling constructor in `executable_price.py` - one Depth type, no copy), `None` when
   there is no full frame, the feed is not healthy, or the depth is older than the staleness limit the quote book
   already applies to prices (reuse it; do not invent a new number). Say which subscription mode the live feed uses
   today; if it is not `full`, the subscription change is part of this item (the recorder used full).
4. Tests on the real cut frame: parse -> 5+5 levels with the exact values; `executable_limit` on it; a quote packet
   -> no depth; a price-0 level dropped; stale / unhealthy -> None; removed on unsubscribe.

## Reviewer checklist (each red when mutated; write these first)
- Price 0 kept as a level -> red. Paise divided wrongly (x10) -> red (exact Decimal equality to the REST quote).
- A quote-mode packet giving an empty Depth instead of None -> red.
- Depth readable after `remove` -> red; readable when the feed is unhealthy or older than the limit -> red.
- Bid and ask sides swapped -> red (BUY must walk asks: 3.35 for 65).
- No float anywhere (the parser uses integers / Decimal).

## Rules
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/marketdata/ tests/engine/ tests/test_*.py`
  and `python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_kite_ws.py tests_app/test_kite_ws_resubscribe.py tests_app/test_strategy_live_push.py`
  (no database: if one needs it, skip and say so). Grep `tests/` and `tests_app/` for `bid`, `ask`, `QuoteBook`,
  `PACKET_FULL` and add every file that names what you change. `python scripts/orchestrator/atool.py <your worktree>
  W-097 --no-tests` (read its exit and every ` rc ` line); `python scripts/ruff_ratchet.py` must not rise.
- Do NOT wire the Execute route (W-095 does, in parallel; it codes against `latest_depth`). No UI. No kit or `spec/`
  edit, no `views/`, no findings INDEX, no regenerated files, no `evidence/`. Never edit the recording.
- Commit and push `build/W-097-live-depth`. No PR.
