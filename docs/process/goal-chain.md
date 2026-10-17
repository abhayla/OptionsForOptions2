# Goal chain: Stage 4 (4a close-out -> 4b -> 4c) in short goal contracts

Owner-approved 2026-10-16 19:30 IST (plan rev 2 after an independent Opus review). Master plan
`master-plan-2026-10-07.md` stays in force (stage order, gates, delivery rules).

## The one prompt (paste into every new session)

> Run the goal chain for this repo: git pull main, read docs/process/goal-chain.md, and run the contract marked NEXT
> to completion under its rules (ADR-106). Refuse to start if a lock/* branch exists on origin or any row is RUNNING.
> First take the lock (chain rule 2). The goal is MET only when the transcript shows all of:
> (1) a merged PR number on main whose goal-chain.md marks this contract DONE or PARTIAL (parked items named) and the
> next contract NEXT; (2) the next contract checked per chain rule 3, with its findings accepted or rejected; (3) a
> final message with the 5-line summary, the generated scorecard and the evidence table; (4) the lock deleted. The goal
> is IMPOSSIBLE (stop) only when a named stop in the contract needs the owner, or another run holds the lock. Never
> stop for a status report. At the contract's cap: park the unfinished items, then still do the handover step, which
> meets the goal as PARTIAL.

Use it as `/goal <the text above>`. (Changed 2026-10-17 by ADR-106: the lock replaces the RUNNING-row PR; GC-2e ran
on the previous text.)

## Chain

| Id | Status | Closes | When / size | Owner needed | Contract |
|---|---|---|---|---|---|
| GC-1 | DONE (2026-10-16 19:50-21:00 IST; PRs #331, #332, #333) | 4a close-out + 4b core proof | Fri 2026-10-16 night, cap 8 h | No | `goal-contract-GC-1-2026-10-16.md` |
| GC-2a | DONE (2026-10-16 22:22 - 2026-10-17 ~01:15 IST; PRs #334, #327, #336, #335, #337 + this close-out PR; nothing parked; open: #338 deferred, OQ-10 owner) | #327 Linux egress fix (core), then ADR-099 paisa rounding (#297 item 3), then W-081 wired + #273 (if 2.5 h remain), W-075 AC-7 re-verify | Sat, cap 6 h | No | `goal-contract-GC-2a-2026-10-17.md` |
| GC-2b | DONE (2026-10-17 01:23 - ~04:15 IST; PRs #342, #343, #346, #347, #348, #349 + this close-out PR; nothing parked; moved to GC-2c by name: W-091's exit-from-ledger, the in-flight hook's false-block fix) | 4b boundary (GC-1 F-40): W-091 Kite orders/trades/positions -> domain on redacted real-order fixtures (core), W-092 eligibility filled from Zerodha, the in-flight hook's false block (5b), W-081 AC re-verify; ADR-058 delisted-held and W-017 allowlist only behind time gates (W-017 expected to park) | Sat/Sun, cap 6 h | No | `goal-contract-GC-2b-2026-10-17.md` |
| GC-2c | PARTIAL (2026-10-17 05:49 - ~09:10 IST active; the cap passed while the machine slept, close-out 16:53+; PRs #351, #354, #356, #355, #357, #360, #359, #358, #361 + this close-out PR; core DONE (Execute + return routes proven on the real recordings), 5b DONE; PARKED: item 3 remainder (#313: adopted holdings), item 5 carry-overs; MOVED by name: item 4 Execute screen -> GC-2e) | App chain: Execute route -> read-only basket -> return-from-Kite read-back -> reconcile (core); then persisted order book (#313) and the Execute screen (REQ-073 AC-1..3, REQ-057/058/060) behind time gates (expected to park); the caller-supplied-verdict mechanism (5b) | Sun, cap 6 h | No | `goal-contract-GC-2c-2026-10-18.md` (review: `gc-2c-contract-review-2026-10-17.md`) |
| GC-2e | DONE (2026-10-17 17:25 - ~19:45 IST; PRs #363, #364, #366, #368, #369, #367, #371, #365, #372, #373 + this close-out PR; items 1-10 done, nothing parked; carried by name: OQ-11..13 (OQ-13: a strategy without planned entries dead-ends on the Execute screen), #370 deferred e2e flake, the contract's carry-over list) | Live-order preparation (GC-3 draft review: the live run cannot start on what is merged): test-only Execute/return replay, the full cost in the Execute reply (net premium + charges + Zerodha margin), audit events on both routes (`order_prepared` declared), the Execute screen (owner clicks, live subscription), where Kite returns the browser, holdings read; two mechanisms behind time gates | Sun, cap 6 h | No | `goal-contract-GC-2e-2026-10-18.md` (reviews: `gc-3-draft-review-2026-10-17.md`, `gc-2e-contract-review-2026-10-17.md`) |
| GC-3 | PARTIAL (Sat 2026-10-17 21:52 - ~24:00 IST, unattended; PRs #379, #382, #383, #384 + this close-out PR; P0 done: probe script, ofo_dev at head + rates + owner Pro, triage, P0 7 re-verification (F-42: 13 order criteria fail on the live path, #380), W-107, ADR-108 (eight operating rules, 2026-10-27 expiry); PARKED: L1-L4 (#385, need the owner on a trading day) -> GC-3L) | 4b live gate ONLY (owner present): P0 read-only probe/readback script (dry-run on the recordings) -> login -> no-order live probe -> 1-lot ENTRY through the Execute screen, owner places on Kite's page, return closes it filled (partial -> exit the held quantity) -> EXIT the same way -> holdings (eight fields) unchanged, gross P&L = Kite's, audit read back + hash chain verified | a trading day from Mon 2026-10-19; P0 by 09:00, L1 by 11:30, L2 no later than 13:30 IST; ~2 h owner time | **Yes**: Kite login, typed go, every click on Kite's page | `goal-contract-GC-3-2026-10-19.md` (review: `gc-3-contract-review-2026-10-17.md`) |
| GC-3L | NEXT | GC-3's L1-L4 under ADR-108: step 0 re-check (lock, merged PRs, ofo_dev head/rates/Pro, servers) -> login + no-order probe (`probe.py`) -> 1-lot ENTRY of a 2026-10-27 NIFTY CE through the Execute screen, owner places on Kite's page -> EXIT the same way -> holdings unchanged, gross P&L = Kite's, audit chain verified; then the next contract (recommended: a fix contract around #380 before GC-4) | a trading day from Mon 2026-10-19; step 0 by 09:00, L2 by 13:30 IST; ~2 h owner time | **Yes**: Kite login, typed go, every click on Kite's page | `goal-contract-GC-3L-2026-10-19.md` (reviews: `gc-3l-contract-review-2026-10-17.md`) |
| GC-2d | planned | 4a screen gaps off the 4b critical path (GC-1 audit): W-089 Settings -> Broker & Market Data, W-090 range/step + At Expiry/Estimated Now, REQ-063 AC-3 repo-wide money guard, evidence-only verifier passes (REQ-048/049/052) | any free slot before GC-4, ~6 h | No | written by whichever contract runs before it |
| GC-4 | planned | 4c build on the recorded replay: REQ-043 statuses, REQ-041 rules -> REQ-042 alert + prepared basket, REQ-062 in-app Alerts + AC-3 dedupe | ~6 h | No | written by GC-3 |
| GC-5 | planned | 4c live gate: a real rule fires, WhatsApp via the Notifier delivered (terminal status read), core gate (core-invariants section 4) | market hours | **Yes**: Notifier typed go, release record first | written by GC-4 |

## Chain rules

1. **One contract at a time.** Statuses: NEXT / RUNNING / DONE / PARTIAL (parked items named in the row).
2. **Start = take the lock, no PR (ADR-106 item 6):** `git pull` main; `git ls-remote origin 'refs/heads/lock/*'`
   must be empty (a lock older than its cap + 1 h is reported as stale to the owner, never taken over silently). Take
   it with one push: `git push origin $(git commit-tree origin/main^{tree} -p origin/main -m "lock GC-<id> session
   <session id> start <IST time> cap <IST time>"):refs/heads/lock/gc-<id>` - a second push of a different commit is
   rejected, so two sessions cannot both hold it. The row's status changes only in the close-out PR; the close-out
   deletes the lock (`git push origin --delete lock/gc-<id>`).
3. **Only the next contract is written in full, on one page** (items, core proof, stops). Each contract's last item
   writes the next one from its own results and checks it (ADR-106 item 4): always a short precondition check (a
   fresh Sonnet: each "merged"/"exists"/"returns" claim checked against GitHub and main) plus a wiring map; a full
   fresh Opus review when the next contract adds or changes order, money, rounding, cost or reconciliation behaviour,
   or comes before a live real-money run. It marks it NEXT here and merges both (with the handover) on main. A
   contract is DONE only when that PR is merged; a docs PR that will not go green is a stop, reported.
4. **A PARTIAL contract or a failed core proof still writes the next contract**, built around the failure (example:
   the 4b core proof fails on Kite's real fields -> GC-2b becomes "redesign reconcile for the real fields").
5. **End of every contract:** print the prompt above, a 5-line summary (done / parked / what NEXT does) and the
   scorecard from `python scripts/orchestrator/stage_scorecard.py --since <start> --until <end>`. The handover is at
   most about 40 lines: DONE / PENDING / BLOCKED / PARKED / NEXT (ADR-106 item 5); process lessons go to
   `docs/process/lessons.md`.
6. A contract that needs the owner says so at its top; unattended, it does only the preparation and stops at the
   owner step.
7. GC-2a re-creates its W-080 worktree from `origin/land/W-080` (the old one is in an earlier session's scratchpad).

## Process rules (every contract carries these as checkable lines)

1. Local before push = the fast spec checks, `scripts/ruff_ratchet.py`, `scripts/orchestrator/pr_close_check.py`, the
   repo-wide guard tests + `python -m pytest -q -m repo_scan tests` (about 75 s), and the changed files' tests only.
   Full domain and app suites run in CI only (measured 2026-10-16: CI 2-4 min with both suites side by side vs about
   17-20 min locally over the tunnel). Exception: a migration or store change runs that one DB test file.
2. One test layer per role: builder = targeted tests; reviewer = hands-on attacks, no suite re-run; CI = full suites
   once; `merge_audit.py` after merge.
3. Every brief passes `check_brief.py`, says `Common brief: docs/process/builder-brief.md`, and carries only the item
   part: reviewer checklist, attack cases, `Findings checked:` ids, `Threat model:` for a guard, `Copy from:`,
   `Budget:` and `Report: evidence-table`. A fix-round brief = the findings + the original attack list.
4. Tier by data flow and at most 2 review rounds per item - CLAUDE.md "Fast delivery" points 3 and 5 (ADR-106 items
   1-3).
5. Never idle on CI: start the next independent item; `gh pr update-branch N` before the merge gate.
6. Batch: same-area fixes in one PR; docs, findings, handover and decision rows in one docs PR per contract; a
   decision a build needs rides in that build's PR with its regenerated spec files; no other generated files in
   feature PRs.
7. Linux-only behaviour is proven on CI early (no WSL on the laptop).
8. One real-data proof per item, on the 2026-10-16 recordings (`D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/`).
9. Plan by user step, land in small stacked PRs (ADR-106 items 8, 10): an item that needs another item's code is a PR
   based on that item's branch; Tier A PRs stay at about 1,000 lines of product code; a migration is its own PR; the
   step's replay e2e on the recordings is a CI gate.

**Scorecard** (generated, never hand-typed): `stage_scorecard.py` for the run's window - PRs by kind, lines by area,
CI runs and reds, merge-only and round commits - plus one line per item for review rounds and budget overruns. A
broken rule that let a defect reach main is a finding the same turn; any other miss is a line in
`docs/process/lessons.md`.
