STATUS 19:30 | R2 items 1-5: Fixed, not tested in a browser (frontend unit tests green; the full push check is running) | next: item 6 browser walk after Lane R1's stage 2 | blocker: the coordinator send_message was refused ("elevated_session_untrusted_device"), so this STATUS line is the report

# Lane R2 results: real positions get the same screens (frontend), 28 Nov 2026

Spec basis: owner 28 Nov about 18:55 IST ("Paper and real trades are same now ... everything between them should be same"), which withdraws ADR-330 (64); ADR-330 (58); ADR-281 (the hold on real orders stays); ADR-016 to ADR-019; ADR-292 (4), (5); ADR-003.
Branch: feat/real-same-screens-fe-1128, built on origin/integration/weekend-r3-1129 with origin/fix/r3-frontend-2-1128 merged first (clean).

## What was built (frontend only; nothing reaches a broker or a data vendor)
| Item | Done |
|---|---|
| 1 | `lib/positionKind.js`: `isPaperKind` is gone; `isActionableKind` (exactly `paper` or `real`) is the one gate. Unknown, none, missing and odd words stay locked. Also `isRealKind`, `rowLineOf`, `recordLineOf` and the sentence set. |
| 2 | Exit dialog (`PaperConfirmDialog.vue`): kind `real` prints the stored-only sentence BEFORE the press (instead of "This is not a real trade"), "Storing in the app..." while the post runs, "Stored in the app. Not sent to Zerodha. Place it in Kite. Loading the position again." if the re-read fails. Title word is now `Real (stored, not sent)` (was `Real (Zerodha order)`, which told the user an order exists). Done line of a real exit = "Exit stored. Not sent ... stays open here until Zerodha shows it closed." with no order number. The builder passes `tradeMode` as the dialog kind. |
| 3 | `LiveStrategyCard`, `PaperStrategies` (REAL tag, row line, record line, Exit and Stops for a real group, mixed banner), `PlanEntry` (exit rows with the not-sent line; the "cannot be read here yet" branch removed), `paperTriggers.js` (`exitsViewOf(exits, failed)`, real branch removed; `not_applicable` kept only for an unknown kind with a neutral fallback), `PaperStops` (kind prop: real label, full Cancel and Keep, per-row not-sent line), `TrackingPanel` (real row line). |
| 4 | `AlertsPage`: the Exit answer shows for real; real rows carry the not-sent note before the answer and the record line after; records and answered history carry the line. `PositionsPage`: record line under the real group. `MyStrategiesPage`, `HomeOverviewPage`: record line under a real row. |
| 5 | A stored action never changes quantity or P&L text: no code path reads `record.price` into any figure. One test per page (below). No "if filled" P&L anywhere. |

## For the owner lane (not edited here)
- Lane R1 contract I coded against (mocked): `position_kind` (paper|real|unknown|none) and `position_kind_text` on strategy list rows (`/strategies`), paper list rows (`/paper/strategies`) and alert rows (`/alerts/active`); `stored_not_sent: true` and `record {action: exit|stop|add|open|stop_fired, stored_at, price}` on those rows, on trigger rows (`/paper|real/strategies/{id}/triggers`), on `/paper/alerts/records` rows, on the answered history, and on the Positions groups (`/positions`, on the group). Price is a text; the browser never parses it. Please confirm or send the real names.
- The Live card and the alert Exit link route to the paper list (`?tab=paper&exit=<id>`), so `/paper/strategies` must return a REAL strategy as a group (with `position_kind: "real"`) for Exit and Stops to open. If R1 keeps real groups out of that list, the exit door has nothing to draw: needs R1's answer.
- The server text of "monitoring why" (note section 2, Monitoring) is printed as sent by MonitoringBadge; no frontend constant was added for it.
- `TrackingPanel.vue` also reads `realTriggersPath` for a real trade (FC3); left as it is (same reply shape).

## Decided for the owner
- Title word of a real exit is `Real (stored, not sent)`: the old word claimed a Zerodha order, which the owner's rule says must never be believed. The guard in one-door-screens.test.js now pins the new word in one place.
- `not_applicable` stays (unknown kind only), with a neutral fallback sentence: the unknown lock is unchanged (fail closed).
- A real group inside the paper list shows the REAL tag and a mixed banner instead of "not real money".
- A group with `position_kind: "unknown"` in the paper list shows no Exit or Stops and the unread-kind line; a missing tag on the PAPER list reads as paper (it is the paper list).

## Question for the owner
- No clash between two of his rules found. One to read: with real and paper "same", the Live card for a real row still links Exit to the Paper tab of Positions (same route as paper). OK, or a Real tab?

## New wording for the owner to read (all pending owner read; proposals from the note's section 2)
- Dialog: "This stores your exit in the app as a record and a reminder. It does not place an order and does not change your Zerodha position. Place it in Kite."
- Dialog (add): "This stores your add in the app as a record and a reminder. It does not place an order and does not change your Zerodha position. Place it in Kite."
- After Exit: "Exit stored. Not sent to Zerodha. Place it in Kite. This position stays open here until Zerodha shows it closed."
- Stops: "Stop stored for this real position. When it is reached you get an alert. Nothing is sent to Zerodha. Place the exit in Kite."
- Row: "Real position. Zerodha shows its quantity and P&L. Exits and stops you store here are not sent. Place them in Kite."
- Record line: "Exit stored 10:32:00 at 120.50. Not sent to Zerodha. Place it in Kite." (also "Stop reached ..." and "Add stored ...")
- New by this lane: "Storing in the app...", "Stored in the app. Not sent to Zerodha. Place it in Kite. Loading the position again.", mixed banner "Paper trades are not real money. A real position here only stores your actions; nothing is sent to Zerodha.", fallback "Not applicable: this position cannot be read as paper or real.", title word "Real (stored, not sent)".

## New test files (all `*-r2-1128`)
real-same-screens-core-r2-1128 (the Core), position-kind-actionable-r2-1128, alerts-real-r2-1128, stops-real-r2-1128, real-record-pages-r2-1128 (Positions, Paper list, My Strategies, Home), real-dialog-r2-1128.
Rewritten (not deleted): position-kind-adr330-64, alerts-actionable, not-applicable-text-fj2-1128, stops-not-applicable-real-r3-fj, plan-entry-exits-mode, plan-screens-r2-fc3, plan-screens-r3-fj-builder, exit-title-door, chunk-c-round2, one-door-screens (word only).
Core proof: real-same-screens-core-r2-1128 was RED on the build (Exit link missing, old "Real (Zerodha order)" title, "not a real trade" line), then green.

## Not done
- Item 6, the browser walk, waits for Lane R1's stage 2 on origin.
- Adjust components and ExecuteStrategyPage: re-grepped `isPaperKind` and `position_kind`: no real guard exists there, nothing to change.
- Unmerged branches (leftovers-1128, leftovers-2-1128) were not touched.

| task | model | minutes |
|---|---|---|
| all of the above | Sonnet (main session, no helpers) | about 95 |

SAFE TO CLOSE: not yet (item 6 open).
