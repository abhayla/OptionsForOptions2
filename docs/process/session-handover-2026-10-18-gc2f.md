# Session handover 2026-10-18 (GC-2f, build ahead without live data; nothing product merged)

Run: lock `lock/gc-2f` 17:13 IST, cap 23:13 IST; close-out ~18:30-19:00 IST; this close-out PR.
Contract: `goal-contract-GC-2f-2026-10-18.md`. Main has no product commit since 298eab3 (docs only). Every code item
is an OPEN draft PR marked HOLD, merged only by GC-3F step 0 after GC-3L L4.

## DONE (open PR, reviewed, held)
- #393 W-109 My Strategies + Completed (Tier B PASS; fix round; CI green). Completed lists nothing yet: the only
  strategy status today is `draft`.
- #394 #381 return route reads trades before orders; a trade naming a missing order refuses the read (Tier A PASS,
  covers the class; minors fixed; CI green). New user message `return_trade_without_order` pinned "pending owner read".
- #395 #370 root cause: three e2e API processes x default DB pool exhausted the `ofo_app` role's CONNECTION LIMIT 5
  (CI logs: `TooManyConnectionsError`, `GET /strategies 500`); pool budget settings + a repo_scan budget test. CI green.
- #396 W-110 repo-wide money guard (round 2 PASS). Frontend red = the #370 flake (no frontend change).
- #397 W-089 Broker & Market Data (Tier A round 2 PASS; Disconnect now stops the live feed; CI green).
- #399 W-090 user scenario RANGE (step stays Admin, ADR-042; W-090 card corrected); round 2 PASS. Frontend red = the
  same `strategy-save-draft` flake; the PR-body anchor error fixed and lint re-run.
- #159 and #257 closed: already fixed on main (evidence in each).

## PARKED
- #405 W-108 attribution (core proven: 61 tests, 7 ADR-109 cases on the real replies, 24/24 guards killed) - a MAJOR
  after review round 2: an open plan counts 0 held, so the app's own lots can read as outside. W-111 Positions part 1
  (`build/W-111-positions`, stacked) parked with it, unreviewed. GC-3F step 1.
- #404 evidence passes REQ-048/049/052 (need work-item rows and a new test; ~7 h).

## DEFERRED (filed tonight)
#400 ADR-008: ~11 money/P&L figures computed outside the engine on main (table, margin gate, cost, outcome, rules,
orders); #401 Disconnect has no CSRF/owner check; #402 broker-settings wording; #403 Windows local pytest
EgressRefused (pytest-metadata `platform.platform()`).

## PENDING (for the owner)
- Read the new message text in #394 ("A trade at Zerodha names an order that is missing from Zerodha's order list.
  Check with Zerodha again in a minute.").
- Q272 (account-only control) after GC-3L. Funds check before Monday 09:00 (F-44).

## NEXT
GC-3L (Mon 2026-10-19 08:30, owner present): contract + delta + runbook. Then GC-3F (draft
`goal-contract-GC-3F-draft.md`): merge #395 first, then the held PRs; W-108 redesign; #380 option C.
