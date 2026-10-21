# GC-3L owner runbook: Monday 2026-10-19, one real 1-lot NIFTY CE in and out

Built from `goal-contract-GC-3L-2026-10-19.md`, `goal-contract-GC-3P-2026-10-18.md` (item 8) and ADR-108, and the Execute screen on main (W-104). Claude never places an order and never clicks on Kite's page: you click every button there (ADR-097, ADR-100). Everything runs on the dev database (ofo_dev), never ofo_test.

## Timeline (IST)
| Time | What happens | Who |
|---|---|---|
| 08:30 | Lock taken, step 0 checks | Claude |
| 08:45 | Catalogue reload (fresh 2026-10-27 contracts) | Claude |
| 09:00 | API up. You log in: private window, `http://127.0.0.1:8765/broker/zerodha/login`, you must land on `/broker/connected`. Holdings saved before the open | You + Claude |
| **09:00** | **Funds gate.** Kite read Rs 0 on Sunday (F-44). `equity.net` must be at least 65 x premium + Rs 100 (GC-3L L1: "premium x 65 + Rs 100 <= funds (#338)"); before the strike is picked that means at least Rs 425 (Rs 5 x 65 + Rs 100). If not: STOP before any click and add funds | Claude reports, you add funds |
| 09:20 | Contract probe and strike pick: NIFTY CE, expiry 2026-10-27, premium Rs 5-11 (owner 2026-10-18, GC-3P contract); prefer Rs 10 or less, because ADR-108 (2) says "about Rs 650 or less" and Rs 11 x 65 = Rs 715 is about 10% above it; the funds rule re-checked against the picked premium (Rs 11 needs Rs 815) | Claude |
| 09:20 | **ADR-108 rule 5 check:** you open Kite's Positions and Orders pages: no row for the chosen symbol today; screenshot `0920-positions-before.png` | You |
| ~10:00 | L2 ENTRY (deadline 13:30) | You |
| right after the fill | L3 EXIT (deadline 14:30) | You |
| ~12:00 | L4 read-back checks | Claude |

## Click by click
1. Strategy Builder: pick the one BUY leg, click **Save Draft** while the feed is live. Then click **Execute Strategy** (the link only exists for a saved strategy).
2. The Execute screen says "Waiting for live prices for every leg..." and then shows two buttons. Click **Prepare entry orders**.
3. Read the screen: Plan number, the orders table (Side, Quantity, Contract, Order type, Price, Tag), then Net premium, Charges, Funds available (Zerodha), Margin required (Zerodha). Expect quantity 65 and LIMIT (the screen has no product column: confirm NRML on Kite's page, without editing). Tell Claude the values and type **go** only for those exact values. Claude records your "go" with its time.
4. Click **Open Kite to place these orders**. Kite's page opens in a new tab in the SAME private window.
5. On Kite's page check the user id equals the connected user, change nothing (no quantity or price edit), and place the order yourself.
6. Kite normally sends the browser to `/execution/returned` ("Back from Kite"). The API drops the query when it
   forwards, and a private window keeps no history, so BEFORE placing: on Kite's tab press F12 -> Network -> tick
   "Preserve log". After the return, read the `/kite/callback` request's query KEYS (not the `request_token` value)
   into the handover (F-41). If Kite does not redirect, or lands on the login-refusal page, that is NOT a stop: go back to the Execute tab and use its button. Note which case happened.
7. Open Kite's Orders page. Only when the order shows COMPLETE, CANCELLED or REJECTED, click **Check with Zerodha**. Click it a second time (rule 2). Expect the plan `filled` and "Mismatches: 0".
8. EXIT: only AFTER Check shows `filled` (or `partial`), reload the Execute Strategy tab (F5): the Prepare buttons are
   hidden while the page still holds the ENTRY's order list (`ExecuteStrategyPage.vue:104`). Never reload before the
   Check, or the Check button is gone. Wait for live prices, click **Prepare exit orders**, and repeat steps 3 to 7
   (SELL the held quantity, money received and charges shown).

## L4 read-back (Claude, about 12:00)
After the exit, Claude runs `python scripts/live/probe.py pnl --tag-prefix <prefix> --save-dir D:/Abhay/Ventures/ofo-kite-ticks/2026-10-19/replies-after-exit` (the folder must not exist yet or be empty). It saves the raw Orders, Trades and Positions replies there (`orders-saved.json`, `trades-saved.json`, `positions-saved.json`) for GC-3F, and `probe.py --replay <that folder> pnl --tag-prefix <prefix>` reads them back with no Kite call.

## Never place twice
Click **Open Kite's page again** ONLY if no Kite tab opened AND Kite's Orders page shows no order with the strategy's tag. If an order exists, never open it again. Never retry an ENTRY (ADR-017).

## The eight ADR-108 rules, in plain words
1. "press "Check with Zerodha" only after Kite's Orders page shows the order COMPLETE, CANCELLED or REJECTED".
2. "press it again and Execute only on 0 mismatches, not blocked, the expected state".
3. ""nothing placed" while Kite shows a fill is a STOP".
4. "Kite's user id on the basket page equals the connected user, one private window".
5. "net 0 on the chosen contract and one strategy only before L2".
6. "no quantity or price edit on Kite's page (Cancel only, on the 15-minute branch)".
7. "Kite's rejection text copied into the handover".
8. "STOP on any mismatch, holdings difference or P&L difference".

## When something goes wrong
- **No fill in 15 minutes (ENTRY):** cancel on Kite's Orders page only, no edit. Click **Check with Zerodha** once Kite shows CANCELLED. There is no exit. Go to the 12:00 checks.
- **Partial fill:** cancel the rest on Kite. **Check with Zerodha** closes the plan `partial`. The EXIT sells exactly the quantity held, not 65.
- **Rejection:** copy Kite's rejection text word for word into the handover (rule 7). No retry.
- **EXIT refused by the screen, or not filled:** no cancel and no second EXIT (ADR-017; Cancel is allowed only on the ENTRY's 15-minute branch). The LIMIT order stays to the close. An unfilled day order ends at the close and the position carries over as NRML, loss capped at the premium. Screenshot Kite's Orders and Positions pages and the screen's refusal message. No further ENTRY. The next contract exits it first (next session Wed 2026-10-21, Tuesday is a holiday): GC-3F fixes #352 and the exit goes through the Execute screen; if that fix is not merged by **Mon 2026-10-26 12:00**, you sell the lot by hand on Kite that day (ADR-111, your answer 2026-10-18). Never hold it to expiry (2026-10-27).
- **EXIT partly filled:** the unfilled rest follows the line above; **Check with Zerodha** closes the plan `partial`.
- **Check with Zerodha shows an error, or Kite does not answer:** no click on Kite. Press Check again up to 3 times, a minute apart (it only reads). If your Kite session dropped, log in once more in the same private window. Still failing: follow the carry-over line above and tell Claude.
- **Funds below Rs 425 at 09:00:** add funds, tell Claude to re-run the funds check, and continue once it passes. Not passed by 12:00: today's order steps are parked.
- **Any ADR-108 STOP** (mismatch, holdings or P&L difference, "nothing placed" while Kite shows a fill): place nothing more and tell Claude. Login fails or drops: retry once, then park.

## Screenshots
GC-3L names no folder (it only asks for Kite's Orders and Positions screenshots, and Holdings and Positions if a probe fails at L4). Save them in `D:\Abhay\Ventures\ofo-kite-ticks\2026-10-19\shots\` (next to the recordings, outside the repo: they show your account), named with the time (for example `1004-orders-entry.png`). Claude lists them in the handover.
