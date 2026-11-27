STATUS: items 1-3 built in cloud (tests green); full-suite gate and browser check recorded below; Opus review pending. Not pushed to main.

# Lane FA (round 2): Exit dialog and stops panel
Branch fix/r2-exit-stops-1128 from origin/integration/conflicts-1127 (16c536f). Paper only. Spec basis: ADR-330 (58), (60), REQ-049, ADR-212, ADR-017.
Note: `.claude/skills/lanes/SKILL.md` ("Standing rules for every lane") does not exist in this checkout; the brief's own rules were followed.

| Item | State | Evidence |
|---|---|---|
| I-17 price age line | Passed in cloud | tests/exit-dialog-age-r2-fa.test.js: red 17 failed / 1 passed before the fix, green 18 of 18 after |
| I-18 Placing exit + result in view | Passed in cloud | tests/exit-dialog-placing-r2-fa.test.js 5 of 5; tests/exit-unknown-resend-adr017.test.js 8 of 8 still green |
| I-29 index exit rule after the close | Passed in cloud | tests/stops-index-closed-r2-fa.test.js 12 of 12 (8 were red before the fix) |

## I-17
`priceAgeLine(rows, {nowMs, notLive})` in lib/priceState.js is the one as-of formatter; the dialog shows its result in `paper-price-age`. States, each its own wording and test: no price ("No price for N of M legs; the server prices the exit when you confirm."), time absent ("The time of the price is not available."), time unreadable ("... could not be read."), not live ("Prices are not live. Last price as of 10:35:00 IST, 7 minutes ago."), fresh/stale by seconds, minutes, hours, days (days carry the date). The OLDEST quote is told. A quote dated after now is never "ago". The time comes from each row's `price_at`, which the book / strip already carries; no backend change needed. The per-row "about 42.55, as of 10:41:20" text is unchanged.
## I-18
`EXIT_PLACING_TEXT` ("Placing exit...") in lib/usePaperExit.js, shown in the pinned status slot only while `busy` and the dialog holds an exit row; it is replaced, never joined, by the result. EXIT_DONE_TEXT stays the only done sentence (test: Placing never contains it). The status slot is scrolled into view (`block: 'nearest'`) when `state` or `error` changes to a result, so also on refusal, unknown outcome and the page's re-read note (EXIT_NOT_STORED_TEXT). Slow-post mock: `busy` held by the page until the post answers.
## I-29
Finding (honest): the "Save disabled" claim does NOT reproduce in the component. `ce-save` / `stop-save-N` read only the typed level (`ceReason`, `stopReason`); the index state never gates them. Tests prove an index exit rule on NIFTY and SENSEX saves with the market closed in three answer shapes (LIVE+closed with value; NOT_CONNECTED+closed with the server's fallback value; NOT_CONNECTED+closed with no value), body `{kind:'conditional_exit', above:'26000'}`. What was wrong is the text: a closed market with no value read "Index values unavailable." (the feed-down word). Now: closed with value keeps "NIFTY last 25,607.20 as of 15:58:01" (pinned by price-notice-adr330-56); closed without value reads "NIFTY: the last close is not available."; and one reference line `stops-reference`: "The market is closed. Levels are judged against the last close." `NOT_LIVE_LABEL` itself is unchanged (the strip, the index page and the builder use it). Stop rules: unchanged (leg-stop POST body pinned by a test).

## Decided for the owner
1. Wording of the age lines and the reference line is new, pending owner read (ADR-330 (60) names no wording for them). Basis: ADR-330 (56) (one as-of), (60).
2. The age is told against the clock of the browser when the dialog opens, not the server's; a skewed PC clock shifts the minutes, not the printed time. Basis: no server "now" in the confirm reply (see For the owner lane).
3. Whole seconds/minutes in priceState.js use a remainder helper (`n - (n % 1)`), not Math.floor/trunc: tests/strategy-table.test.js and tests/test_money_outside_engine.py both flag those in screen files. These are times, not money (ADR-008).

## Gap list (ADR-330 (58))
- One gap: the exit dialog, its not-live rule, the market-closed line and the done sentence exist only in paper code; no real exit door exists (measured 27 Nov). Not built, per the brief. The three fixes above are in the one shared dialog component (`kind` 'paper' | 'real'), so a real door inherits them.

## For the owner lane (not edited)
- Lane FD (routes/paper.py): the exit-confirm reply and `/market/exit-state` carry no server "now"; a `server_time` field would let the age be told against the server's clock. Not needed to ship.
- I-29: if the real server refuses an index exit trigger save after the close, its exact refusal text is needed; none could be produced in cloud (no server). Check on the PC.

## PC steps
Market closed:
1. Positions: open Exit on a strategy with "no price" rows: the dialog opens, shows the age line ("No price for ..."), the market-closed line and Confirm greyed.
2. Stops panel of a paper strategy: type a level above NIFTY, Save. Expect "Saved: exit above ...", the reference line under the index line, no "Index values unavailable.". Repeat with SENSEX. If refused, copy the refusal text to Lane FD.
Live:
3. Exit with live prices: "Price as of HH:MM:SS IST, N seconds ago."; press Confirm: "Placing exit..." then "Exit placed on paper (order N)." in view.
4. Stop the server before Confirm: the unknown line shows in view; Confirm stays locked until the re-read.

SAFE TO CLOSE: yes, nothing runs; nothing is pushed to main or the test branch.
