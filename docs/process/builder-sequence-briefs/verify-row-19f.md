# Verifier brief: row 19 frontend part (W-147, REQ-080 leg picker screen) - checker

Common brief: docs/process/builder-brief.md (checker part). Fresh context, adversarial, read-only: edit no file,
commit nothing; scratch copies for every mutation. The backend reads were checked separately (Opus, verify-row-19b.md:
AC-1/2/5/7/8 pass at the route, AC-6 futures price live check pending).
Checker model: Sonnet - the changed files are frontend only, none in the safety set (builder-brief.md).

Spec basis: REQ-080 AC-1 "with a Strikes tab and a Futures tab"; REQ-080 AC-3 "Done adds them all as legs, each with a
captured planned entry"; REQ-080 AC-4 "lists multiples of the lot size read from the instrument file"; REQ-080 AC-7
"Each leg in the builder has a depth icon that opens a popup"; REQ-080 AC-8 "with the reason, never an empty or old table".
Reference: screens 024, 031, 032, 033, 034, 035, 130, 131, 244, 245 - copy only what each open record says; open RD-032, RD-129, RD-130, RD-131, RD-132, RD-133, RD-134

What was built: chunk head on `build/seq-chunk-2` in `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs` (merge 86264455 of
row 19 frontend 5e649b2a): `frontend/src/components/strategy/LegPicker.vue` (Strikes/Futures tabs, width, ATM highlight,
multi-select Buy/Sell + lots, Done, Lots/Quantity choice, depth icon on each leg in the picker's leg list),
`DepthPopup.vue` (new), `frontend/src/lib/legPicker.js`, tests `leg-picker.test.js`, `depth-popup.test.js`, e2e
`leg-picker.spec.ts` (runs in CI). Frontend tests run in `D:\Abhay\Ventures\OptionsForOptions2-row19\frontend` (has
node_modules; its HEAD 5e649b2a has the same `frontend/` tree as the chunk head - confirm with git diff).

For EVERY AC say which screen shows it (`/strategy/builder`) and whether you exercised it THERE (vitest mount of the page or
the component with responses shaped exactly like `backend/ofo_app/routes/leg_picker.py`'s models - compare field names).

## Per AC (pass / fail / partial / live check pending)
- AC-1 tabs, width 10/20/30/40 (default 10), ATM highlighted; underlying locked while legs exist.
- AC-2 CE/PE LTP, OI, IV, delta rendered as the server sends them (no browser maths).
- AC-3 Buy/Sell and lots per cell; several selected; Done adds them all, each through the planned-entry capture; no order.
- AC-4 Lots/Quantity: quantity mode lists multiples of the lot size from the server data (SENSEX too); lots mode 1, 2, 3.
- AC-5 '-' for a null price with the server's reason above the list; how the list is centred when not live; a leg added
  without a price shows the reprice prompt.
- AC-6 Futures tab: each future with LTP or reason; per option expiry the forward with 'Forward used for pricing'.
- AC-7 JUDGE: the depth icon sits on the leg list inside the picker, not on the strategy table's leg rows. AC-7 says "Each
  leg in the builder has a depth icon". Is a leg on the builder screen outside the open picker reachable to its depth?
  Say pass / partial with the exact screen path a user takes. Popup: 5 levels with quantities, day values, last trade time,
  read time; refresh at most once a second while open, stops when closed; no order button.
- AC-8 'Depth not available' with the reason, never an empty or old table (also after a failed refresh).
Also judge: the picker polls the open tab every 5 s (not in the brief) - load on the server (subscriptions per poll: the
backend holds a lease, 30 s release) and whether it stops on close/unmount.

Attack list:
1. Responses with every reason code the backend models define render a readable reason (no raw code, no blank).
2. SENSEX quantity mode lists SENSEX lot multiples (never a typed 65).
3. Done with zero selected does nothing; Done with three adds three legs with planned entries.
4. A depth refresh failure after a good table shows not available, not the old table.
5. Closing the popup stops all depth requests (fake timers).

Threat model: in scope - a price computed or invented in the browser, a stale table, an order path, a timer that never
stops, a leg without depth access on the builder; out of scope - the backend reads (checked), saving the Lots/Quantity
choice per user (row 40), the futures price itself (live check pending).
Findings checked: verified-on-a-module-the-product-does-not-call, brief-rule-from-memory

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table - per AC: verdict, screen, exercised there yes/no, command, output line; then numbered findings
CRITICAL / MAJOR / MINOR with file:line. Under 450 words.
