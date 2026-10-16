# Goal chain: Stage 4 (4a close-out -> 4b -> 4c) in short goal contracts

Owner-approved 2026-10-16 19:30 IST (plan rev 2 after an independent Opus review). Master plan
`master-plan-2026-10-07.md` stays in force (stage order, gates, delivery rules).

## The one prompt (paste into every new session)

> Run the goal chain: `git pull` main, read `docs/process/goal-chain.md`, and run the contract marked NEXT to
> completion under its rules (refuse if a row is RUNNING). Do not stop for status reports; stop only at the
> contract's named stops.

## Chain

| Id | Status | Closes | When / size | Owner needed | Contract |
|---|---|---|---|---|---|
| GC-1 | NEXT | 4a close-out + 4b core proof | Fri 2026-10-16 night, cap 8 h | No | `goal-contract-GC-1-2026-10-16.md` |
| GC-2a | planned | #327 Linux egress fix, ADR-099 paisa rounding, W-017 on real responses, W-081 wired + #273 | Sat, 4-6 h | No | written by GC-1 |
| GC-2b | planned | App chain: Execute route -> read-only basket -> return-from-Kite read-back -> reconcile -> audit; persisted order book (#313); Execute screen (REQ-073 AC-1..3, REQ-057/058/060) | Sun, 5-6 h | No | written by GC-2a |
| GC-3 | planned | 4b live gate: 1-lot order through the product (ADR-097 guardrails), reconcile, P&L = ADR-008 on the fill, audit chain read back | Mon 09:15, ~2 h | **Yes**: Kite login, typed go, Execute press | written by GC-2b |
| GC-4 | planned | 4c build on the recorded replay: REQ-043 statuses, REQ-041 rules -> REQ-042 alert + prepared basket, REQ-062 in-app Alerts + AC-3 dedupe | ~6 h | No | written by GC-3 |
| GC-5 | planned | 4c live gate: a real rule fires, WhatsApp via the Notifier delivered (terminal status read), core gate (core-invariants section 4) | market hours | **Yes**: Notifier typed go, release record first | written by GC-4 |

## Chain rules

1. **One contract at a time.** Statuses: NEXT / RUNNING / DONE / PARTIAL (parked items named in the row).
2. **Start:** `git pull` main; if any row is RUNNING, do not start - report it (ask the owner if present). Set your row
   RUNNING in your first commit.
3. **Only the next contract is written in full.** Each contract's last item writes the next contract from its own
   results, gets it independently reviewed, marks it NEXT here, and merges both (with the handover) on main. A
   contract is DONE only when that PR is merged; a docs PR that will not go green is a stop, reported.
4. **A PARTIAL contract or a failed core proof still writes the next contract**, built around the failure (example:
   the 4b core proof fails on Kite's real fields -> GC-2b becomes "redesign reconcile for the real fields").
5. **End of every contract:** print the prompt above, a 5-line summary (done / parked / what NEXT does) and the
   scorecard.
6. A contract that needs the owner says so at its top; unattended, it does only the preparation and stops at the
   owner step.
7. GC-2a re-creates its W-080 worktree from `origin/land/W-080` (the old one is in an earlier session's scratchpad).

## Process rules (every contract carries these as checkable lines)

1. Local before push = the fast spec checks, `scripts/ruff_ratchet.py`, `scripts/orchestrator/pr_close_check.py`, and
   the changed files' tests only. Full domain and app suites run in CI only (measured 2026-10-16: CI 2-4 min with
   both suites side by side vs about 17-20 min locally over the tunnel). Exception: a migration or store change runs
   that one DB test file.
2. One test layer per role: builder = targeted tests; reviewer = hands-on attacks, no suite re-run; CI = full suites
   once; `merge_audit.py` after merge.
3. Every brief passes `check_brief.py` and carries the reviewer checklist, attack cases, `Findings checked:` ids,
   `Copy from:`, `Budget:` and `Report: evidence-table`.
4. One review round by tier (Opus only for money, orders, auth, secrets, migrations, hooks); a 2nd round only on a
   CRITICAL/MAJOR; two failed rounds -> independent redesign; a third -> park.
5. Never idle on CI: start the next independent item; `gh pr update-branch N` before the merge gate.
6. Batch: same-area fixes in one PR; docs, findings and decision rows in one docs PR per contract; no generated files
   in feature PRs.
7. Linux-only behaviour is proven on CI early (no WSL on the laptop).
8. One real-data proof per item, on the 2026-10-16 recordings (`D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/`).

**Scorecard** (in the handover, one row per item): review rounds, CI runs, local full-suite runs (target 0),
check_brief before dispatch (y/n), idle gaps over 10 min, budget overruns. A broken rule is recorded as a finding the
same turn.
