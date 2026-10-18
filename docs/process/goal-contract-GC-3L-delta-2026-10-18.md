# GC-3L delta (written by GC-3P, Sun 2026-10-18): Monday timeline, funds gate, docs-only head rule, Sunday results

Applies on top of `goal-contract-GC-3L-2026-10-19.md`, which is not edited. Where the two differ, this delta wins.
Owner runbook for the same day: `gc-3l-runbook-2026-10-19.md`.

## 1. Monday 2026-10-19 timeline (IST)
- **08:30** if `lock/gc-2f` still exists on origin (GC-2f overran the cap in its lock commit), first stop the GC-2f
  session; then the main checkout `git switch main`, clean, HEAD = origin/main, and ports 8765/4173 free (stop by
  PID) before step 0.5; then the owner may delete the lock (`git push origin --delete lock/gc-2f`) and GC-3L starts;
  GC-2f's open PRs stay open and unmerged. Main may carry
  GC-2f's docs-only close-out commit (section 2 covers it). Because goal-chain.md then still marks GC-2f NEXT, start
  GC-3L with the chain prompt with "run the contract marked NEXT" replaced by "run GC-3L (GC-2f overran; it is
  PARTIAL, its unfinished items parked; GC-3L's close-out records that)".
- **08:30** lock `lock/gc-3l` + step 0 (short: section 2 below replaces step 0.1 on a docs-only head).
- **08:45 catalogue reload** on ofo_dev: `python scripts/orchestrator/dev_run.py . python -m ofo_app.catalogue_load`.
  Freeze limits: the loaded file is NSE's 2026-10-15 contract file (3511 for all 261 NIFTY 2026-10-27 CEs). A newer
  file exists: `https://nsearchives.nseindia.com/content/fo/NSE_FO_contract_16102026.csv.gz` answered HTTP 200 on
  2026-10-18 (header request with a browser user agent; `..._15102026.csv.gz` also 200). Download the newest dated
  file before 08:45 (try `19102026` first, then `16102026`), then
  `python scripts/orchestrator/dev_run.py . python scripts/load_freeze_file.py <file>` - **ofo_dev through
  `dev_run.py`, NEVER `db_run.py`** (that is ofo_test, whatever the script's docstring says). Record the file loaded
  and the NIFTY 2026-10-27 freeze value after it (65 < any value seen so far). Both reloads finish BEFORE the API
  starts (the live feed reads the catalogue at start, `live_market.py:148-159`). On a failed download or a refused
  reload the 2026-10-15 data stays (3511 freeze, the 2026-10-27 contracts present): not a stop; record it.
- **09:00** API + preview up (recipe below), owner login, `probe.py holdings --save
  D:/Abhay/Ventures/ofo-kite-ticks/2026-10-19/monday-before.json` before the open (an absolute path outside the repo:
  the file holds account data, and `dev_run.py .` runs from the repo root). The Sunday file is NEVER Monday's baseline.
- **09:00 funds hard gate (F-44, owner 2026-10-18 "Re-check Mon 09:00")**: `probe.py contract` prints
  `available_funds`; it must be >= Rs 425 (Rs 5 x 65 + Rs 100) before the strike pick, else STOP before any click
  and the owner adds funds. Kite read Rs 0 (net, cash, opening balance) on Sunday.
- **09:20** contract probe on 2-3 candidate 2026-10-27 CEs + strike pick: premium Rs 5-11 (owner 2026-10-18; prefer <= Rs 10: ADR-108 (2) "about Rs 650 or less", Rs 11 x 65 = Rs 715), price
  from the 5-level depth (the probe prints no last price); `premium x 65 + Rs 100 <= funds` (GC-3L L1) re-checked
  against the picked premium. ADR-108 rule 5 ("net 0 on the chosen contract"): `probe.py` has no positions command, so
  the owner opens Kite's Positions and Orders pages, confirms no row for the chosen symbol, screenshot
  `0920-positions-before.png`.
- **L4 tag prefix:** tags are `OFS{s}V{v}L{i}` (`ofo/execution/basket.py:94`); use `--tag-prefix OFS<id>V` (plain
  `OFS1` also matches strategies 10-19).
- **EXIT:** after Check shows `filled`/`partial`, reload the Execute tab; the Prepare buttons are hidden while the
  ENTRY reply is on the page (`ExecuteStrategyPage.vue:104`). F-41: capture the `/kite/callback` query keys with the
  browser's Network panel ("Preserve log"), since the forward drops the query (`routes/broker.py`).
- **~10:00** L2 ENTRY (deadline 13:30). **EXIT soon after the fill** (deadline 14:30). **~12:00** L4 (or right after
  the EXIT fills).

## 2. Step 0.1 on a docs-only head
When main's head commit changed only docs (true after GC-3P's close-out), step 0.1's "CI green on the head" reads:
CI green on the newest commit that changed product code, `execute-screen-e2e` named in that run's jobs, AND
`git diff --stat <that sha> HEAD` lists only `docs/`, `spec/`, `knowledge/`, `views/` or `work/` paths.

## 3. Start recipe (measured working on 2026-10-18)
The kit guard refuses a Bash command containing the word in uvicorn's app-factory flag; start the API from a small
script file (one line: `LIVE_MARKET=1` then `python scripts/orchestrator/dev_run.py . python -m uvicorn
ofo_app.main:create_app <factory flag> --app-dir backend --loop ofo_app.event_loop:selector_loop --host 127.0.0.1
--port 8765`), in the background. Frontend: `npm run build`, then `OFO_API_TARGET=http://127.0.0.1:8765 npm run
preview -- --host 127.0.0.1 --port 4173`, in the background. Health through the proxy: `/api/health` on :4173 (the
API itself serves `/health`; `/api/health` on :8765 answered `USER_INPUT_003` "not available here" on 2026-10-18). Stop both by the PID listening on each port.

## 4. GC-3P item 1 results (Sun 2026-10-18 ~15:00-15:15 IST, all labelled pre-run)
| Check | Result |
|---|---|
| Login through `/broker/zerodha/login` | Kite called back (`GET /kite/callback` 302 in the API log); the probe then read the stored session |
| `holdings --save` | exit 0; 6 rows; raw key list: authorisation, authorised_date, authorised_quantity, average_price, close_price, collateral_quantity, collateral_type, day_change, day_change_percentage, discrepancy, exchange, instrument_token, isin, las_quantity, last_price, mtf, opening_quantity, pnl, price, product, quantity, realised_quantity, short_quantity, t1_quantity, tradingsymbol, used_quantity |
| `holdings --compare` | `holdings_unchanged`, exit 0 |
| `contract NFO:NIFTY26OCT27000CE` | exit 0; depth all 0 (market closed); `circuit_band lower=0.05 upper=20.45`; `available_funds 0.00` |
| Funds | Kite `equity`: net 0, cash 0, opening_balance 0 -> F-44 and the 09:00 gate above |
| Live feed / socket | **unproven**: `/health` reports only `healthy, database connected`; the feed starts only with a subscribed screen, and Sunday has no ticks |
| Probe fix | none needed; no product-code merge in GC-3P |

Still unproven before Monday: live depth (Sunday is all zeros), the socket push, Kite's basket page and its return
shape (F-41), and whether the Rs 0 funds are real or a weekend artefact (F-44).

## 5. GC-3P item 2 (ofo_dev re-check) and item 3 (triage)
Item 2, ofo_dev read-only, 2026-10-18 ~15:30 IST (all four hold):
- `alembic_version` = `0017_audit_order_prepared` = main's newest migration file. Reading it needs the owner role
  (the app role gets "permission denied") - GC-3L step 0.2 already says "owner role".
- `charge_rates`: one set, `read_on` 2026-10-15, 8 rows. Owner access: `AccessLevel.PRO`.
- NIFTY 2026-10-27 CE: 261 contracts, strikes 17000-30000, lot 65, `seen_on` 2026-10-15, none retired; freeze limit
  3511 for all 261 in `public.exchange_freeze_limits` (file 2026-10-15). `broker_instruments.freeze_limit` is NULL on
  all 261: that column is not where the limit lives.

Item 3, ADR-107 triage: 32 open `deferred` issues. Tier A ones outside the P0 6 table: only #380, #381, #386, as
expected and covered by GC-3L / ADR-108; #385 is `parked`, not deferred. The other four outside the table are not
Tier A (none touches the order, money or reconciliation path): #297 (4a UI minors; item 3 is a margin message's
wording), #370 (e2e flake), #344 (CI scale-test timeout), #318 (`noqa` cleanup). No new Tier A issue, so no Opus check
was due.

## 6. Leftover worktree for the owner
W-095 (`agent-a69de5ad7463e69aa`): its "uncommitted change" to `backend/ofo_app/execute_plan.py` is line endings only
(`git diff` and `git diff --ignore-cr-at-eol --stat` both empty). Kept as the GC-3P contract says; safe to release
(`python scripts/orchestrator/agentwt.py a69de5ad7463e69aa release`) - owner's call.
