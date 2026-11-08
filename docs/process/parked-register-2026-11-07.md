# Parked-work register, OptionsForOptions2

Date: 2026-11-07. Main reference point: `a4b9b339` (feature/adjustments tip, "main history after PR #665").
Purpose: start parked work from its resume ref, never from scratch: `git checkout -b <new> <resume ref>`, merge main in, run its tests.

Legend for "Resume ref":
- `TAG <name>` = permanent archive tag (annotated; `git rev-parse <tag>^{commit}` gives the commit).
- `MAIN <sha12>` = sha is an ancestor of a4b9b339 (in main history after PR #665), checked with `git merge-base --is-ancestor`.
- `NO PERMANENT REF` = only reachable from a branch/remote or not at all; see the last section.
- `no code` = parked before any code, or the remainder was never started.
Sources: 44 issues (label `parked` + title/body search union) plus #605 expanded into its 14 held PRs. Issue text read via `gh issue view`; PR heads via `gh pr view`.

| Issue | State | What was parked | Why parked (key phrase) | Done / left | Branch (PR) | Resume ref | Notes |
|---|---|---|---|---|---|---|---|
| #12 | CLOSED | W-007 entitlement engine (REQ-017) | "third red of the class 'entitlement ledger accepts out-of-domain inputs'" | AC-1,2,5 pass; AC-3,4 failed; later fixed in round 7 | build/W-007-entitlements @66b9679; fixed in build/W-007-r7 (PR #111 merged) | MAIN 66b9679 / MAIN 0a4e85648ed5 (PR #111 head) | Done and on main. |
| #21 | CLOSED | W-004 strategy table (REQ-035) | "two fix rounds failed" (AC-7: 24 identical Guided headers, caused by the brief) | AC-1,2,6 pass; AC-7 needs level value as column heading | build/W-004-table-model @5cbf2fd | MAIN 5cbf2fd | Recommended one small change then one verifier round. |
| #30 | CLOSED | W-024 error messages (REQ-065) | "AC-2 failed its third red after the reviewed round" | AC-1 passes; later merged as round 10; door remainder moved to #200 | build/W-024-error-catalogue @63e8d08 (r3), @adda683 (r4); r8-r10 branches | adda683 and a3ef79a: TAG archive/2026-10-29/build/W-024-error-catalogue; 63e8d08: TAG `archive/2026-11-07/build/W-024-error-catalogue-r3` (tagged 2026-11-07) | Superseded: round 10 is on main; 63e8d08 is old, low value. |
| #33 | CLOSED | W-021 reconciliation with Zerodha (REQ-060) | "Two fix rounds have failed (run-discipline A1)" | AC-2,3,5,6,7 pass; AC-1 (shared contract false block) + 1 small defect left | build/W-021-reconciliation @66bbce0 | TAG `archive/2026-11-07/build/W-021-reconciliation` (tagged 2026-11-07) 66bbce0 | Superseded: later merged (PR #40, merge 66100880, in main). Resume from main. |
| #37 | CLOSED | W-023 partial execution, no auto retry (REQ-058) | "went red a third time, after an independent review" | Code held; 2 duplicate-order guards not locked by tests | build/W-023-partial-execution @6038e94 | TAG `archive/2026-11-07/build/W-023-partial-execution` (tagged 2026-11-07) 6038e94 | Superseded: later merged (PR #39, merge 8315c89b, in main). |
| #38 | CLOSED | Stale test_answer_has_no_advice_words labels | Filed as deferred, then "closed as filed in error" | Fixed inside W-024 | none | no code | Deferred, not truly parked. |
| #89 | CLOSED | Three user-text paths not on the shared wording checker | Deferred by W-046 builder | Route safety.py, disconnect.py, rules/templates.py through check_platform_text | none (the parked W-024 branch wired them) | no code | Deferred, not truly parked. |
| #140 | CLOSED | W-060 index spot + parity forward (AC-2) | "four DELIBERATE forging shapes the pricing scan does not flag" | AC-3 pass; AC-2 flag made fail-closed and merged | build/W-060-forward @f654d39 (PR #135 merged, head b64a6162e4ee) | MAIN f654d39 | Done and on main; AC-1 DB segment CHECK followed as migration 0008. |
| #155 | CLOSED | Hook: failing step must stop commit/push (pipe-masks-gate) | "PARKED 2026-10-10 under run-discipline B1 (two fix rounds failed Tier A)" | Partial hook blocks both historical shapes; items 1-5 follow-up | fix/155-gate-before-commit @6a6ef73 | MAIN 6a6ef73 | Owner decision item 6 in owner-questions-2026-10-10. |
| #165 | CLOSED | W-061 Save Draft (REQ-038 AC-5) | "Park it, wrap up" after Tier A failure | Round-trip works; 3 defects (ADR-069 only at API body, etc.) fixed in round 3 | build/W-061-save-draft @3f14653 (PR #134 merged, head 2481b77bf384) | MAIN 3f14653 | Done and on main. |
| #172 | CLOSED | W-066 outcome text from catalogue (REQ-034 AC-7) | "one final bounded round; any red after it parks W-066" | Catalogue renders done; bounded loss split by one zero point crashes | build/W-066-on-main @dae3b54 (PR #170 merged, head 6e9766fe3f05) | MAIN dae3b54 | Done and on main via #170. |
| #200 | OPEN | Response door: module rebinding and seal reuse not flagged by CI (REQ-065 AC-2) | "after 9 fix rounds on W-070 / #197" | N1-N5 attacks unflagged in CI; ADR-074 open exception | build/W-070 line; fix/200-door-remainder (PR #229 merged, head ab3e17ba72e5); verifier at af5222c | MAIN af5222c | Needs a CI source scan for `errors.*` rebinding. |
| #247 | OPEN | #242 remainder: atool route selector misses two-hop dependents | "parked after round 2"; selects 0 files, exits 0 | Merged part is better than before; transitive closure + fail-closed on 0 left | #242 merged part; remainder (head 8b0dfac) | MAIN 8b0dfac | Code is in `scripts/orchestrator/select_app_tests.py`. |
| #269 | OPEN | W-075 charges in max-loss/max-profit sentences (ADR-082 part 2) | "PARKED on owner question OQ-4" | Verified rows and sentences; AC-7 mismatch of Rs 68 (rounding) + breakeven label open | build/W-075-charges-sentences @00e9024 | MAIN 00e9024 | Business question; owner-questions-2026-10-16.md. |
| #271 | CLOSED | W-080 read-only Kite basket (REQ-073) | "PARKED after a third red in the same failure class" (AC-4 placement guard, Unicode-dot Kite host) | AC-1, AC-2 pass; later merged via land/W-080 (PR #327) | build/W-080-kite-basket @23a5edc | MAIN 23a5edc | Residual guard issue #318 (noqa cleanup). |
| #385 | CLOSED | GC-3 live steps L1-L4 | "need the owner present on a trading day" | P0 done (#379, #382, #383, #384); live steps carried as GC-3L | none | no code | Not code, an owner-present live run. |
| #404 | OPEN | Evidence passes REQ-048 AC-1/AC-5, REQ-049 AC-4, REQ-052 AC-1 | "these are not 'evidence-only'" (each needs a work item naming the AC) | ~7 h of evidence + work items left | none | no code | Parked by GC-2f. |
| #405 | OPEN | W-108 attribution (and W-111 stacked) | "MAJOR on Tier A code after review round 2" | Core proven (24/24 mutants killed); open plans count 0 not held | build/W-108-attribution @0db9fa9 (PR #398 merged, head 0ad7fec8d6ed); W-111 PR #498 merged | MAIN 0db9fa9 | Check issue text: both later merged. |
| #433 | OPEN | Home REQ-008 AC-2 state 3, AC-3, AC-1 | "the data does not exist yet" (strategy status only `draft`) | W-115 states 1-2, AC-4, AC-5 built | build/W-115-home (PR #431 merged, head 85f4dca04b9d) | MAIN 85f4dca04b9d | Remainder = no code. |
| #434 | OPEN | Strategy screen Live Position tab (REQ-044 AC-2) | "no strategy is ever 'after execution' on main" | Nothing built | none | no code | Reuse LiveStrategyCard.vue. |
| #488 | OPEN | TRIM-STRUCT structural list guard (GC-3F item 4) | "Tier A MAJOR after review round 2"; daily reload never gets NSE's file | Guard built; evidence from real 2026-10-15 to 10-21 lists | gc3f/trim-struct @e7cee4b9e7d7 (no PR) | TAG archive/2026-10-29/gc3f/trim-struct | Branch already deleted. |
| #517 | OPEN | Row 6 (REQ-048 AC-5) credential scans | "after two failed Tier A verify rounds" | AC-1..4 pass; name-list scan not closed | build/seq-chunk-1 @4cf8f47d, 06c5c958 | MAIN 4cf8f47d | Redesign as reply-field inventory. |
| #519 | OPEN | Row 8 (REQ-050 AC-1/AC-3) cache keys | "30 of 40 key parts unguarded" | shared_compute.py built; keys correct | build/seq-chunk-1; build/gcmu-key @bdd5516c; 5a72453d, b9b5cb32 | MAIN bdd5516c | Build keys from the engine call. |
| #558 | OPEN | Row 31 (REQ-085) builder warnings, futures expiry | "Builder vs Execute disagree on futures expiry (Tier A round 2 MAJOR)" | Backend (31b) + frontend (31f) built | build/c4-row-31b @44cacfdc (PR #557); build/c4-row-31f @6fc7f935 | TAG archive/2026-11-07/build/c4-row-31b; TAG archive/2026-10-29/build/c4-row-31f | Backend branch still on origin. |
| #560 | OPEN | Row 30 (REQ-078) AC-1 live half | "needs the owner's live Kite session" | Code merged (#552, #554); 50-edit p95 <= 1,000 ms run left | build/c4-row-30b (#552), c4-row-30f (#554) | MAIN b3918266 | |
| #561 | OPEN | Row 32 (REQ-136) info marks for 5 figures | Depends on rows 26, 37, 38 not built | W-160 merged (#547); marks left | build/c4-row-32 (PR #547 merged, head c8454fca441b) | MAIN c8454fca441b | Remainder = no code. |
| #592 | CLOSED | G-069 phone width verdict | "no Sensibull phone study" | Our top bar clipped at 390 px measured | none | no code | Owner later said desktop only. |
| #596 | OPEN | Saved strategy loses close label | "PARKED after two fix rounds" | Numbers right; migration + save/load paths left | build/gcbm-must-have (PR #604 merged, head 39956262d07e) | MAIN 39956262d07e | Remainder = no code. |
| #603 | OPEN | GC-UI deferred items (execute.py DB conn, history-guard reuse, etc.) | Found outside done list, deferred (C4) | List of 6+ items | none | no code | Not parked code; deferred list. |
| #606 | OPEN | GC-TPL live run, L5 partial | "Not closing this issue, because L5 is PARTIAL" | Live run done as GC-LIVE; contract on docs/gclive-2026-10-30 | docs/gclive-2026-10-30 @c197aee3; live/2026-10-30 @ad289338 | docs: TAG archive/2026-11-07/docs/gclive-2026-10-30; live/2026-10-30: `archive/2026-11-07/live/2026-10-30` (tagged 2026-11-07 22:5x) | See last section. |
| #613 | OPEN | Checker target breakevens off 0.11 points (GC-LIVE F-6) | "parked after 2 rounds" | Rounds 1-2 fixed on live/2026-10-30 (acf123b3, c3a396ef); remainder 1 of 3 runs | live/2026-10-30; fix/live-checker-target-q @c3a396ef | TAG `archive/2026-11-07/live/2026-10-30` (tagged 2026-11-07) acf123b3, c3a396ef | Manifest: CONTAINED (patch-equivalent in main, cherry+ 0). |
| #616 | OPEN | After close: Paper no banner, no-IV text; index read nulls | Observed in GC-LIVE2 M4 | Fixes partly in #612/#619 | live2/2026-10-30 @b15416e1 (merged #619) | MAIN b15416e1 | Verified ancestor. |
| #624 | OPEN | A1 liquidity limits (ADR-230) | "PARKED after 2 rounds"; unreadable playbook fails open | A1 merged into build/gcmu (17d98038) | build/gcmu | MAIN 17d98038 | Add strike flags in adjust drawer. |
| #627 | OPEN | GC-MU step 4 remainder (background margin T-16, T-13 open price, restart/heartbeat) | "These parts are NOT built, or known short" | Core proven: record 0.40-0.61 s after price | build/gcmu-bg @b5264ccc, 3761b4f4, 68cf98c2 | MAIN b5264cccd4c8 | |
| #632 | OPEN | GC-SET2 market hours/order facts as settings | Parked by owner decision 2026-11-01 ("Go with your recommended option A") | Draft contract only | docs on feature/adjustments (goal-contract-GC-SET2-DRAFT.md) | no code | Tier A. |
| #634 | OPEN | merge_preflight PR to main | "owner decision after two review rounds" | Script built; review not clean | build/merge-preflight @04d88102 | MAIN 04d88102 | Business/owner decision. |
| #636 | OPEN | Background role: opportunity within 1.0 s of crossing | "after 2 fix rounds on the speed class" | Fixes 7c804264, ba6f43dd, f7d2088b... landed; DB round trips remain | build/gcalert1-636r4 @5bf1db31; build/gcic1-636r5 @97f219e4 | MAIN 97f219e49c77 | |
| #638 | OPEN | GC-ALERT1 step 5: 3 worker tests red | "2 fix rounds used" | 10 pass, 3 red (30/60 gaps, plan change, day rollover) | build/gcalert1-step5-tests @44f0d4c9 | MAIN 44f0d4c9d771 | |
| #645 | OPEN | Suggestion outcomes never follow real Zerodha order | One class behind four FAILs (REQ-112 AC-2/3, REQ-162 AC-2) | Evidence W-201/W-209 | feature/adjustments 989623c9; evidence ceb37f0b | MAIN 989623c9 | |
| #656 | CLOSED | Step 3 live stops via settings + migration 0040 | "Parked after round 3: 4 MAJOR findings" | Nothing merged; round-3 tip fails own tests | fix/cfg-step3-one-history @30d6a531; fix/cfg-source-chips @8d2e33e4; base bd0adae2 | MAIN 30d6a531 | Served code is 0603f418. |
| #661 | OPEN | IC rules in background worker (T-19, S-12, T-11) | "Two fix rounds used" | Strict-blocker tests in tests_app/test_ic_rules_worker_paths.py | feature/adjustments merge 34a687ac | MAIN 34a687ac | |
| #662 | OPEN | Second adjustment: no T-18 after max adjustments | "Two DB rounds used" | Strict xfail in test_ic_second_adjustment.py | feature/adjustments af4527ed | MAIN af4527ed | |
| #664 | OPEN | Fix batch 1 items 1+2: entry baseline lacks Greeks/premiums | "red after 2 fix rounds" | Core test passes; migration 0045 up/down; T-03/T-09 hidden | park/b1-rule-baseline @9f4a2df1 (merge of 533b4a84), local only | MAIN 9f4a2df16c69 | Branch not pushed. |
| #605 row 1 | PR #394 CLOSED | #381 return route reads trades before orders | Held for live Kite gate (GC-3L/GC-6) | Rebuild order 1 | build/fix-381-257 @03d595d5c1ec | TAG archive/2026-11-07/build/fix-381-257 | |
| #605 row 2 | PR #418 CLOSED | #338 closing basket vs negative balance + #353 allow-list | Same | Order 2 | build/338-353-gate-fixes @58b70c7e6f8c | TAG archive/2026-11-07/build/338-353-gate-fixes | |
| #605 row 3 | PR #420 CLOSED | Never split: block above stored freeze limit (ADR-092) | Same | Order 3 | build/255-never-split @57f989fd381c | TAG archive/2026-11-07/build/255-never-split | |
| #605 row 4 | PR #456 CLOSED | gc6/422-freeze-types, stacked on #420 | Same | Order 4 | gc6/422-freeze-types @ba413d7708bf | TAG archive/2026-11-07/gc6/422-freeze-types | |
| #605 row 5 | PR #421 CLOSED | 352-1 next day, stacked on #419 + #398 | Same | Order 5 | build/352-1-next-day @9703f1236051 | TAG archive/2026-11-07/build/352-1-next-day | |
| #605 row 6 | PR #453 CLOSED | Expired token mid-return | Same | Order 6 | gc6/token-return @ed3e020d2d79 | TAG archive/2026-11-07/gc6/token-return | |
| #605 row 7 | PR #454 CLOSED | One tag on two broker orders blocks | Same | Order 7 | gc6/dup-tag @e258e4c790cb | TAG archive/2026-11-07/gc6/dup-tag | |
| #605 row 8 | PR #455 CLOSED | Execute only 09:15-15:30 IST (ADR-119) | Same | Order 8 | gc6/mkt-hours @1520cbef390d | TAG archive/2026-11-07/gc6/mkt-hours | |
| #605 row 9 | PR #463 CLOSED | Kill switch, stacked on #455 (ADR-127/128) | Same | Order 9 | gc6/kill-switch @1150788c0512 | TAG archive/2026-11-07/gc6/kill-switch | |
| #605 row 10 | PR #459 CLOSED | Execute blocked unless today's instrument list loaded | Same | Order 10 | gc6/instr-fresh @03d12b15a209 | TAG archive/2026-11-07/gc6/instr-fresh | |
| #605 row 11 | PR #470 CLOSED | F-55 net roundtrip | Same | Order 11 | gc6/net-roundtrip @85e9ed6a4388 | TAG archive/2026-11-07/gc6/net-roundtrip | |
| #605 row 12 | PR #478 CLOSED | One reconciler in both money routes (F-42) | Same | Order 12 | gc6/380-2 @3bbf99ee1c61 | TAG archive/2026-11-07/gc6/380-2 | |
| #605 row 13 | PR #509 CLOSED | W-124 option chain values | Same; "much of it superseded by GC-UI; re-check before rebuild" | Order 13 | build/W-124-a3-chain @57a30ca033d2 | TAG archive/2026-11-07/build/W-124-a3-chain | |
| #605 row 14 | PR #557 CLOSED | Row 31 backend warnings (also #558) | Same | Order 14 | build/c4-row-31b @44cacfdc8b4f | TAG archive/2026-11-07/build/c4-row-31b | |

Note: #605 itself is the OPEN umbrella issue; it has no code of its own. Other archive tags exist for earlier deleted branches (`archive/2026-10-29/*`, 22 tags) and 17 under `archive/2026-11-07/*`.

## Needs a tag before deletion

Done 2026-11-07: all four heads below were tagged and pushed (`archive/2026-11-07/live/2026-10-30` also contains acf123b3 and c3a396ef). Nothing is left without a permanent ref.


Every sha below is NOT an ancestor of a4b9b339 and has no archive tag (verified with `git merge-base --is-ancestor` and `git tag --contains`).

| Branch | Full sha | Issue | Note |
|---|---|---|---|
| live/2026-10-30 (also origin/live/2026-10-30) | ad28933834bca965029652b7eac7912338237725 | #606, #613 | 18 commits not ancestors of a4b9b339; manifest says CONTAINED (patch-equivalent, cherry+ 0), so lower risk, but tag anyway. Carries acf123b3 and c3a396ef. |
| (commit on live/2026-10-30) | acf123b358decbf56056d229da0101bfbe6471ba | #613 | F-6 round 1 (checker target Greeks use echoed q). |
| fix/live-checker-target-q (also origin/) | c3a396efd252db9147ddb68b75d4e19c4a7869f2 | #613 | F-6 round 2; branch tip. |
| build/W-024-error-catalogue (r3, deleted) | 63e8d08db68896040d3a691a3afe114c33ebb8ff | #30 | Unreachable from any ref; superseded by round 10 on main. Tag only if the history matters. |
| build/W-021-reconciliation (deleted) | 66bbce05899aea6eb222daa3436611a5b685e25d | #33 | Unreachable; superseded by PR #40 in main. |
| build/W-023-partial-execution (deleted) | 6038e948317f1eec3e37b73950d221c8deda20ce | #37 | Unreachable; superseded by PR #39 in main. |

Not NO-REF but still local-only: `park/b1-rule-baseline` (#664) is an ancestor of a4b9b339, so it is safe to delete.
