---
work_item: W-081
ac: AC-4
requirement: REQ-055
ac_fp: "fb96f4697778"
result: pass
verified_by: "verifier (Sonnet, independent, Tier B, 2026-10-17 GC-2b)"
builder: "builder (Opus/Sonnet, PR #337, 2026-10-17)"
date: '2026-10-17'
commands: "same pytest runs as AC-1; python -B -c attack script (display_text of BasketRefused.user_message) (main d61fcfb)"
---

AC: AC-4
result: pass
commands: same pytest runs as AC-1; python -B -c attack script (display_text of BasketRefused.user_message) (main d61fcfb)
observed: Real funds 671.50 vs the real condor: 'Zerodha says this strategy needs ₹68,498.85 of margin; ₹671.50 is available in your account. ... the basket was not built. ... Next step: Reduce the quantity, review the strategy, or add funds in Zerodha, then check again.' Funds exactly 68498.85 built; 68498.84 refused showing both ₹68,498.84 and ₹68,498.85; negative funds show '-₹1.00'; Zerodha unreadable shows the could-not-confirm message.
attack: Boundary equal (builds) and 0.01 short (refuses with both amounts to the paisa); negative and zero funds refuse with the amount shown; a closing basket (final.total -214.5) needs 0 and builds on funds 0; unreadable Zerodha refuses whatever the funds.

Recorded by the orchestrator from the verifier's returned block.
