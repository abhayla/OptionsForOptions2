# Session handover 2026-11-09: GC-ICGUIDE (written 21:0x IST, run still open)

Contract: `docs/process/goal-contract-GC-ICGUIDE-2026-11-09.md`. Status page (the one page, add never replace):
https://claude.ai/artifact/LcMTSr5xx8LvAYVniotkxK, db collection `tasks`, rows `g01..g38` + added `g04b`, `g04r`, `g26f`
(kind `icguide`; the GC-ICGUIDE table is the THIRD section of the page, below the GC-ICTRACK tables).
Branch `build/gc-icguide`, worktree `D:\Abhay\Ventures\OptionsForOptions2-OptionsForOptions2-gc-icguide`, tip 5140da78
(nothing pushed, no PR yet).

## DONE / PENDING / BLOCKED / PARKED / NEXT
- DONE: g02-g21, g23, g24, g26-g29 (g29 partial: no roll-to-next-expiry picture, PATH-63 holds one expiry), g31, g32
  (fix round merged: FX1 ADR-283 baseline stored at every fill + migration 0050; FX2 one checked save path, feed-key
  exit prices, ADR-212 after-hours refusal, closed refusal, Completed figures), g04b, g04r, g26f.
- PARKED: g22 (#684, real-leg settle row + on-screen awaiting), g30 (#686, app calendar holds 2026 only: every 2027 day
  reads closed - REAL impact from 1 Jan 2027).
- WAITING ON OWNER (non-blocking): g25, read the 23+ new texts (`docs/process/gc-icguide-new-texts-2026-11-09.md`, add
  'paper_strategy_closed', 'Already true after adjustment {n}.', pins "pending owner read").
- RUNNING at handover: integration DB pass on f8e129bb (background shell; logs `D:\Abhay\scratch\icguide\intdb-*.log`).
  Reds so far: `test_strategy_closed_status` 2 failed (partial exit refused 'plan unreadable' - ValidationError in the
  plan read when the route has no market context; commit 5140da78 already makes "no playbook" = no limit; the test
  setup still needs a plan or market); `test_paper_routes` fixed in 460bafb9.
- NEXT: (1) one Sonnet builder fixes every integration red (list from the logs); (2) re-run the reds; (3) g33
  `python tools/ci_local.py` once, marker for HEAD; (4) g34 one PR (Spec-deviation block: ADR-283 implements ADR-258;
  after-hours refusal restored), merge on green, `wt-rm.ps1` for every agent worktree (count packages before/after);
  (5) restart the LIVE stack from the main checkout (commands in `session-handover-2026-11-08-gc-ictrack.md`, ofo_dev
  is at 0050) before g35-g36 (market hours 10 Nov); g37 on Tue 17 Nov; g38 verifier.

## Owner decisions today (process; no decision row)
Instrument list forced once on ofo_dev (#680); live stack stopped for test-data work (#682, role cap 10); "do not wait
for my inputs, go with your recommendation" (~15:00). Product decisions written: ADR-281, ADR-282, ADR-283; REQ-046
AC-2 margin line; F-102, F-103. Owner-questions: `docs/process/owner-questions-2026-11-09.md` (GC-ICGUIDE section).

## Findings and issues filed today
#680 instrument-list guard; #681 builder real-clock days (partly fixed 48295ebc, rest in #685); #682 DB pool deadlock /
role cap; #683 opportunities list leaks live strategies in test mode; #684 C6 remainder; #685 screen findings (record
thresholds from another stage than the panel, records with no condition text / below their rule, Completed tab,
chain shows +-500 strikes only, wording); #686 calendar 2027.

## Lessons (this run)
- I cited ADR-212 by its title and reversed a correct builder (after-hours exits); the review caught it. Read the
  decision body and 'What stays' before citing (memory read-adr-body-not-title).
- Two status writes were stamped before the clock answered; a status write is a separate step after `date`.
- Builders burn their budget waiting on 4-7 min DB files; give DB-heavy items to the orchestrator's one sequential
  pass instead of each builder.
- A scenario frame jump past a candle close is needed for records; scenario frames must not be closer than the
  freshness limit when they claim 'spot missing'.
