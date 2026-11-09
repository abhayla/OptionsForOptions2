# Owner questions 2026-11-09 (GC-ICTRACK, parked at night by the question guard)

## Q1 (01:47 IST): a private account figure reached the public repo; how far to clean it?

**What happened (my mistake):** the session handover committed and pushed at 01:45 IST to the public branch
`build/gc-ictrack` (commit 67dd4b42) recorded the owner's Zerodha available-margin figure from the 20:05 read-only
probe. It is removed from the file in commit e777a1fc (not pushed) and kept out of the PR text. The old commit still
holds it in the branch history on GitHub.

**Held until you answer:** the PR is NOT opened (a PR's commit list is permanent on GitHub) and nothing more is pushed.

Business call: this is your account data on a public site, and the full clean-up rewrites a public branch
(force-push), which is outward-facing and cannot be undone.
Spec basis: none: the spec says nothing about account figures in public repo files (searched: margin, public,
privacy, account data); nearest rule: CLAUDE.md "never copy ... into this public repo".

- **A (recommended): rewrite the branch.** Rebuild `build/gc-ictrack` as one squashed commit of the cleaned tree on top
  of main, force-push it, run the full gate on it (~30 min), then open the PR. The figure leaves the branch and never
  reaches main; GitHub may keep the old commit reachable by its sha for a while.
- **B: fix forward only.** Push the redaction on top, open the PR and squash-merge it. Main never holds the figure, but
  the PR's commit list shows the old commit permanently.

Why A: B leaves the figure on a permanent public page; A costs one gate run.

# GC-ICGUIDE (2026-11-09 afternoon): parked questions and decisions taken for the owner

The owner said at about 15:00 IST: "Do not wait for my inputs. Wherever you have question, go with your
recommendation." Items below were decided that way, or are parked here for a later read. None blocks the run.

## Parked for the owner (non-blocking)

1. **Task 25: read the 23 new texts** in `docs/process/gc-icguide-new-texts-2026-11-09.md`.
   Recommendation: accept as written. Until read, their pins stay "pending owner read" (not "owner read").
   Also there: the proposed wording "Already true when adjustment {n} was placed." for the after-adjustment line.

## Owner answers given in the question tool today (process, not product: no decision row)

1. Instrument list refused by the 10 % guard (Zerodha narrowed NIFTY strike ranges): force one load on ofo_dev.
   Done: added 350, delisted 2,261 (`apply_update(force=True, reason, actor)`). Guard gap: issue #680.
2. DB role `ofo_app` limit 10 cannot hold the live stack plus a test-data stack: stop the live stack (feed, API
   8765, live checker, started 08:10) for the test-data work; restart it from the main checkout before the live
   tasks 35-37. Issue #682.

## Decided under the owner's delegation (spec-conformant; also in the PR body)

1. Paper exit price (C10): the server prices every paper exit from the live price; outside market hours a paper exit
   stays REFUSED (ADR-212 "What stays": "No fill at a closing price"). CORRECTION 19:1x IST: a first version of this
   line said "the last close after hours (ADR-212)"; that misread ADR-212 (only its title was read), the Tier B
   review caught it, and the fix round restores the refusal.
2. C6 real-leg settlement: the settlement source answers "no price" until an exchange-sourced settlement price is
   stored (ADR-083: the source is unproven), so an expired real leg shows "awaiting settlement" by name instead of
   looking open. Never a guessed price.
3. Weekly test-data type (ADR-282 (2)) uses expiry 17 Nov, entered 11 Nov (6 days): in Zerodha's real list 23 Nov is
   the November monthly, so no weekly 23 Nov contract exists.

## Parked at 23:1x IST (night guard): restart the DB run that was stopped for low memory?

The session runner stopped the last DB test run (`test_paper_adjustment_limit`, `test_paper_save_paths_fx2`,
`test_paper_routes` on c6b3c044) because the PC was critically low on memory (2.6 GB of 15.7 GB free afterwards;
biggest: an older assistant session from 7 Nov, PID 9320, 913 MB; Chrome about 1.4 GB). Its note says to restart only on
the owner's OK. Recommendation: in the morning, close the 7 Nov session if it is not needed, then run the 3 files one at
a time under Desktop Commander, then the gate (task 33) and one PR (task 34), before the live tasks at 09:15.

## VPS / tunnel check (owner asked 22:2x)

Measured read-only: 1 SSH process and 1 TCP connection from this PC (`D:\tools\vps-db-tunnel.cmd`, reconnected at
22:17 after one drop); 7 client connections on the VPS Postgres (limit 100). The slowness is round-trip time (39-156 ms,
median 97 ms; connect 581 ms) times the 50 migrations each throwaway test database runs. 8 throwaway databases older
than 24 h remain (`ofo_test_tmp_202611070...` / `202611080...`); dropping them was refused by the permission check (a
permanent delete on the production database server): the owner can run
`python D:/Abhay/Ventures/OptionsForOptions2/scripts/orchestrator/db_run_fresh.py --sweep`. Proposed speed fix (separate
PR): build each test database as a copy of a pre-migrated template instead of running 50 migrations over the tunnel.
