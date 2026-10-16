# Session handover 2026-10-16: night build (00:00-06:30 IST), Stage 4b core first

## Afternoon update (12:00-15:40 IST, owner present, market open): read this first
Plan: `C:\Users\itsab\.claude\plans\here-is-the-note-logical-kahn.md` (use the open market; record it for the weekend).

**Owner decisions:** OQ-1 = (a) pro rata -> ADR-095; OQ-7 = (a) build now -> ADR-096; real 1-lot test order today ->
ADR-097 (options only, NRML/LIMIT, owner presses Execute, holdings never sold, read before/after). All in PR #307.

**Merged (CI green, Tier A/B reviewed as listed in each PR):**
- #308 ADR-094 margin top-up (option BUY premium up to the limit; `zerodha_total` vs `required_total`).
- #309 #296 live market picks up a login made after start (fingerprint of the socket's token; re-read once on
  session end). Issue #296 stays OPEN until the live login proof (below).
- #310 ADR-095 pro-rata price protection (`backend/ofo/engine/price_protection.py`; not wired into the basket yet).
- #311 W-075 charges in the money sentences + OQ-4 (a) line; charges rounded UP to the paisa once (CI caught money
  leaving the API as "4539.65173942700").
- #312 ADR-096 order-free adopt into an existing strategy; also W-083 create-new had no order-free open. Adopted
  holdings now sit in the order book; the book is in memory only -> #313 (deferred).
- #316 #297 items 1, 2, 4 (no raw symbols / duplicate notices; Loss line only over loss). #297 stays open for item 3
  (product question: show Zerodha's margin on the outcome screen? the spec says nothing).
- #317 #294 edit-lint hook (closed #294). #314/#319 coverage rows; #315 findings + afternoon live proofs.
- #320 check_brief requires the repo guard tests and `Findings checked:` ids (mechanism for two repeated classes).

**Real 1-lot order (ADR-097):** BUY NIFTY26O1923650CE 65 NRML LIMIT 5.45, filled 5.10 at 12:20:50 (order
261016170576173, tag OFS1V1L0 came back). Funds 1,003 -> 671.50. Holdings unchanged. Basket built offline by W-080's
`build_basket`; the owner pressed Execute on Kite's page.
**Exit (15:09:52):** SELL 65 @ 3.10 (order 261016170858845, tag OFS1V2L0), position flat, holdings unchanged, funds
873.00. Gross -130.00; charges ours 47.74 vs Kite 47.73 (exit matches exactly; entry differs only by stamp 0.0099, F-35:
settle against tonight's contract note). Net about -177.73.
- The exit exposed #321: Kite gives a closing basket a NEGATIVE margin (-214.50) and our gate refused it - fixed in
  PR #322 (Tier A PASS). The owner first asked the assistant to place the exit itself; Kite refused the API order
  (`403 No IPs configured for this app`): this app has no static IP, so no API placement is possible (ADR-054 does not
  need it; registering an IP is the owner's call). The exit went through a basket page the owner pressed.

**Live proofs on main:** ADR-094 (top-up 650.00 = 2 x 65 x 5; gate blocks on real funds), ADR-095 (Rs 300 -> 292.50
allowed, every leg fills on live depth) - `docs/research/live-proofs-2026-10-16/afternoon/`.

**W-080 PARKED again (#271, last comment):** rounds 9-10; AC-1/AC-2 PASS, AC-4 FAIL - the runtime gate trusts a frame
by its `co_filename` string and stdlib compilers (`code`, `codeop`, ...) forge it. Next design: trust by
`frame.f_globals is <trusted module __dict__>` (identity). No real risk today (no app code sends orders). Blocks the
in-app basket and W-081 integration (#273). Noqa cleanup #318.

**Recorded for the weekend (outside the repo, `D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/`):** full-chain websocket
frames (1,293 NIFTY + SENSEX contracts, 12:07 -> close), REST every 20 min (basket margins for 10 shapes x bumps
0/2/5, charges, funds, positions; 92 calls/round, all 200), live outcome pushes every 10 min, real-order files.

**Misses (recorded):** idle between items until the owner asked; briefs dispatched before `check_brief.py`; issue
#313 filed without `--stage` (extra PR); repo guard tests skipped twice by builders; W-080 round 10 designed without
reading `guard-by-banned-shapes`; `merge_when_green` refuses BEHIND branches (4 extra CI runs; kit #104).

## Day update (08:00-11:45 IST): night plan status - read this first
**Night plan: complete except W-080 (PARKED) and the real 4b order (blocked on W-080, funds and the owner's yes).**
The owner will write a new plan for the rest; nothing outside the night plan is started.

- **Gate 4a: PASSED** (10:25, main 48d75a7; #304; evidence `docs/research/gate4a-2026-10-16/rerun/`). The first
  re-run (09:20) failed on D-1 (frozen live prices). The fixes:
  - #300 D-1: a released-then-taken instrument keeps ticking;
  - #302 D-2: the leg picker holds unheld legs until the first quote;
  - #299 D-3: a last price of 0 is no live price.
- **Live proofs (morning step 3): done**, #305, `docs/research/live-proofs-2026-10-16/`:
  - margin gate refused Rs 263.25 against funds -497;
  - executable price 26/26, including walks through 2-3 depth levels;
  - charges equal Kite's except stamp on buys (up to Rs 0.47, the F-35 exception);
  - F-39: Kite's basket margin = qty x min(limit, live price), so ADR-094 was recorded. **Its code is NOT built**
    (next plan).
- **W-080 PARKED for the owner** (#271): 8 rounds, the last two a runtime egress gate after two independent
  re-designs. Remaining class: caller-supplied callables (httpx `extensions={"trace": f}`) run inside door context.
  Branch `land/W-080-r8`; worktree `scratchpad/wt-w080`. Also 160 `# noqa` comments to clean up.
- **Owner decisions today:**
  - W-080 refuse non-ASCII hosts;
  - OQ-4 (a) STT line: built on branch `land/W-075`, NOT merged; W-075 was held for the gate, which has now passed;
  - OQ-9 superseded by ADR-091 (weekly freeze refresh, 8-day warning; #291);
  - OQ-2 ADR-092 never split (#292; code is issue 255);
  - still open: OQ-1, OQ-7.
- **Process now on main:**
  - REQ-075/ADR-093 coding standards (#293), with the edit-time lint hook and 6 path rules;
  - one home per constant + ruff ratchet (#295);
  - fast delivery rule (#301): full suites in CI only;
  - `land.py` one-command landing (#303).
- **Owner setup:** the user-level hook `owner-question-business-only.py` is wired in the owner's user settings (valid
  JSON checked 10:20); it takes effect in a new session.
- **Account:** Kite funds -497 at 08:58; the real order needs about Rs 1,000 added and the owner's yes.
- **Running at hand-over:** the API on 8765 (main 48d75a7, LIVE_MARKET=1, ofo_dev), started from the scratchpad
  `run_api_dev.py`. Stop it by PID before closing the session.
- **Issues filed today:** #294 (edit hook minors), #296 (live market reads the session only at start), #297 (gate
  minors).

Owner brief (2026-10-16 ~00:00): build everything that needs no live market, test it offline, market tests from 09:15;
no questions while asleep (parked in `docs/process/owner-questions-2026-10-16.md`, OQ-1..OQ-9). Plan: core first
(ADR-087). Plan file: `C:\Users\itsab\.claude\plans\confirm-you-are-in-fluffy-hinton.md`.

## DONE (merged to main, CI green on every PR)
- Decisions: ADR-087 (4b built ahead of the 4a gate), ADR-088 ("Checked at"), ADR-089 (breakeven labels), ADR-090
  (REQ-073 approved, AC-5 aligned with ADR-060) - #251, #254.
- W-074 charges rate table + calculator (#261, migration 0012). W-076 freeze limit from the NSE contract file (#264,
  migration 0013, F-36). W-077 "Checked at" + #249/#244/#213, closes W-072 / REQ-039 AC-3 (#262). W-078 executable
  price, NRML/MIS product, circuit band (#267). W-082 breakeven labels from loss regions (#268). W-085 expiry
  settlement (#280). W-086 expiry-day entry warning + short-leg acknowledgement (#276).
- W-081 margin gate merged as a COMPONENT (#274): card BLOCKED, no AC claimed (needs basket #271, a live funds read,
  #273).
- W-083 PARTIAL (#277): AC-1, AC-4 verified; AC-2 waits on OQ-7.
- Fixes: #259 (#278); #237 Save Draft e2e now runs in CI (#282); #263 items 1-3 (#283); #279 items 2-3 (#284, REQ-060
  clarification + OQ-8); #275 all five items + unique error-code guard (#286); #279 item 1, settle before reconcile
  (#287, Tier A: 6,000-case differential, only fewer blocks); #285 MARKET_DATA_120 renumbered, guard without
  exceptions (#288).
- Mechanism: PR close-keyword check (#289 - see the status table in the final report; merges on green).
- Docs batches #252 #253 #256 #258 #260 #265 #266 #270 #272 #281 and this batch (F-37, OQ-9, two findings, briefs).

## PARKED (owner decisions waiting, each with a recommendation)
- W-075 (#269) charges in money sentences: verified except D5; sentence vs expiry table with STT on exercise = OQ-4.
  Branch held, not merged. ADR-082's "about Rs 221" example is wrong (correct 214.96); fixed with W-075.
- W-080 (#271) basket: AC-1/AC-2 pass; AC-4 failed 3 times (urllib door accepts a Unicode-dot host). Options:
  idna-normalise the host or refuse non-ASCII - owner call.
- #257 freeze-limit maximum age = OQ-9 (needs a trading calendar; recommend 4 calendar days now).
- OQ-1 price-protection split, OQ-2 #255 "never split", OQ-7 add-to-existing order-free (recommend a); OQ-3/5/6/8
  information only.

## STILL OPEN (deferred, not started)
#263 item 4 (plan version on the basket tag), #273 (margin check on the platform estimate - with #271), #279 item 4
(persist awaiting/settled/retired state - before any scheduler), #255, #107 (needs a host), REQ-025 (legal Q261),
#199/#234/#200.

## Morning (owner present)
1. F-37 is recorded: the token stopped at about 04:30 IST (not 6 AM). The watcher (PID 14884) exited after the first
   failure. Re-run it on two more nights before relying on the minute.
2. 09:10 API on 8765 from main against ofo_dev (`scripts/orchestrator/dev_run.py`, APP_ENV=development,
   LIVE_MARKET=1, run as a background task - Start-Process is blocked); send the login link; login in a PRIVATE
   window (redirect `http://127.0.0.1:8765/kite/callback`). ofo_dev is migrated to 0011; apply 0012/0013 to ofo_dev
   before the charges/freeze live proofs.
3. 4a gate re-run (harness `D:\Abhay\Ventures\ofo-kite-ticks\2026-10-15\gate4a\`): D8 incl. TOTAL rows, draft
   save/reopen, 8 screenshots, #232 item 1 -> `docs/research/gate4a-2026-10-16/` + verdict in
   `docs/process/gate-4a-review-2026-10-15.md`.
4. Live proofs: margin `/user/margins` + `/margins/basket` (W-081), depth limit (W-078), charges reply (W-074), freeze
   block on the live catalogue (W-076).

## Misses (recorded)
- Partial-fix PR bodies closed whole issues 3 times (#263, #275, #279; reopened) despite a memory - finding
  `pr-text-closes-issue-unintended`; mechanism #289. Even the mechanism's own PR body first quoted examples that would
  have re-closed #237 and #263; the checker caught it before push.
- Two templates shared one error code twice (221 across branches; MARKET_DATA_120 on main) - finding
  `identifier-unique-only-by-convention`, guarded (#286, #288).
- Targeted test runs missed guard tests twice - occurrence 5 on `targeted-tests-miss-dependent-files`; every landing
  now runs the FULL domain suite.
- Local Python 3.13 vs CI 3.12 - finding `local-python-differs-from-ci`.
- My brief errors: short futures limited to options (#275 round 1); ADR-082's example taken as correct (W-075);
  expected PR #282 to pass the close check (it correctly fails). Builders ran over budget several times.
- Two builder worktrees (W-086, W-074) are locked by this session's process and could not be removed; they go when the
  session ends (`agentwt.py <id> release` otherwise).
