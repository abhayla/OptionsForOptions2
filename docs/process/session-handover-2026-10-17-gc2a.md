# Session handover 2026-10-16/17 night: goal contract GC-2a (basket on Linux, Zerodha money to the paisa, margin gate)

Ran 2026-10-16 22:22 IST -> 2026-10-17 ~01:15 IST under `/goal` (cap 6 h, 04:22). Contract:
`goal-contract-GC-2a-2026-10-17.md`. Next: **GC-2b** (`goal-contract-GC-2b-2026-10-17.md`, marked NEXT).

## DONE
- **RUNNING marker:** PR #334.
- **Item 1, core - #327 W-080 basket + Linux egress fix: MERGED** (954db69, 23:39). The gate allowed `sendmsg`/`sendto`
  with no address only when the socket already has a peer (read with the C-level `getpeername`, so no caller code runs
  in the hook): that reaches nothing a plain `send()` cannot. Tier A Opus review PASS (8 hands-on attacks, 3 mutants
  killed). CI Linux `api` went 132 failed -> 2 -> 0. The 2: (a) a boundary scan flagging the Kite door's outbound
  `httpx.Response` annotations - fixed with a narrow allow-list, its own Tier A review REVISE (1 MAJOR: the
  httpx-module check had no killing test) -> fixed + mutation-proven; (b) the history-finalize scale test timing out -
  an independent Opus builder measured the gate on CI (0.4 ms for 746 events on the DB thread, no `sendmsg`, no
  refusal) and the test passed in the next 3 CI runs. **The 15 s hang itself was never reproduced or explained** (open
  risk, carried to GC-2b; lead: autovacuum on `history_minute_bars`). Core proof: CI run 38943577973 kit suite on Linux
  `... passed, 3 skipped` = main's own 3 skips, so the three Linux-only `sendmsg` tests and the UDP-to-192.0.2.1
  refusal ran and passed (inferred from equal skip counts; the kit CI prints no skip reasons).
- **Item 2 - ADR-099 outcome margin + Zerodha money to the paisa: MERGED** as PR #336 (d0fa11a, 23:54). New decision
  ADR-101 (architect): every Zerodha money figure is rounded half-up to the paisa where it is parsed
  (`ofo.money.zerodha_paise`). Real case: 68498.85000000001 needed vs 68498.85 available no longer shows a shortfall.
  Accepted residual: under one paisa (both sides round); a full paisa short still blocks. Tier A Opus review PASS, 5
  MINOR (4 fixed, 1 noted). CI caught the adapter scan once (a new `kite_*` name and a new Kite-importing module) ->
  renamed helper, reasoned allow-list entry.
- **Item 3 - W-081 wired + #273: MERGED** as PR #337 (b86d0f8, 00:54). `ofo_app/checked_basket.py` is the one production
  path to a basket; `build_basket` takes a Zerodha figure source and decides inside (no verdict crosses the boundary);
  `KiteBasket` / `MarginVerdict` are sealed tuples; the partial-fill re-check uses Zerodha's required margin, the
  planner estimate is display-only (#273's instance; #273 stays open until the Execute route, GC-2c). Real data: funds
  Rs 671.50 vs the condor's Rs 68,498.85 -> no basket, both amounts shown. Tier A round 1 REVISE (MAJOR: a basket could
  be built directly and a passing verdict forged by replace/copy/pickle/setattr), round 2 PASS with 4 MINOR
  (deliberate tricks such as `tuple.__new__` can still forge one - documented, out of scope per ADR-003 Q235, Zerodha
  re-checks on its own page). AC-1/3/4 not yet re-verified on main: GC-2b item 5.
- **Item 4:** W-017 moved to GC-2b by the GC-1 contract review (unchanged).
- **Item 5 - W-075 AC-7 re-verified on main: PASS** (fresh Sonnet verifier; hand round trip 214.95956479500 -> 214.96;
  sentences 8,850.21 / 4,149.79; OQ-4 line verbatim). Evidence `evidence/W-075/AC-7.md`. ADR-082 now carries the
  owner's OQ-4 line (owed since the morning) and a note that its worked figures 221.18 / 8,856.43 were an arithmetic
  slip. Issue 269 D5 NARROWED (comment posted): the remaining breakeven-column question is OQ-10.
- **Item 6 - merge.py writes UTF-8 itself:** red on the old file (`UnicodeEncodeError '✓'`), green on the new.
- **Item 7 - docs batch:** this PR; #30 and #154 closed with comments.
- **Item 8 - GC-2b:** written, independently reviewed (fresh Opus, Explore type: READY WITH CHANGES, 3 MAJOR + 5
  MINOR, all accepted - recordings outside git need redacted fixtures, the exit-from-ledger objective kept in scope,
  W-092 not strictly after W-091, gates with a 1.5 h tail reserve, DB stop restored, ADR-058 item raised to Tier A,
  `fill_timestamp` used directly, cap wording), marked NEXT. A second fresh review of the merged contract (Opus,
  Explore type, 30 tool calls; READY WITH CHANGES, 2 MAJOR + 5 MINOR, all accepted): the plan exceeded the cap ->
  explicit give-way order; no recorded "product download" instrument list exists for 2026-10-16 -> the recorder's real
  list, labelled; snapshot mtime cannot give a call length; W-092 / W-091 cards to align; F-40 cited ADR-099 for
  rounding -> ADR-101 (spec/findings.md fixed); JSON-number variants are built in the test.

## Mechanisms added tonight (Learn-or-block)
- **PR #335 verifier-in-flight hook** (d988ca7, 00:13): while a verifier tool call runs, the main session cannot write
  `work/` `spec/` `evidence/` under the watched roots, cannot run any git command outside a read-only allow-list, and
  the writer scripts refuse themselves. For finding `verifier-guard-watches-every-worktree` (3rd occurrence tonight).
  Tier A: round 1 REVISE (my brief specified a forbidden git list - `guard-as-forbidden-list`, recorded), round 2 PASS.
- **atool.py runs the api job's ruff ratchet and migration guard** (`local-ci-mirror-runs-a-subset`, 3rd occurrence).
- **The ruff ratchet always ends on a FAIL/OK verdict line** (new finding `gate-output-read-by-eye`, 2 occurrences: two
  builders read a failing ratchet as passing).

## PARKED / OPEN
- History-finalize scale-test hang: unexplained, not reproduced (2 failures, 3 later passes). Watch item in GC-2b.
- OQ-10 (`owner-questions-2026-10-17.md`): breakeven columns show about -Rs 215 under a breakeven label since charges
  entered the expiry values. Recommendation (a): move the breakeven levels by the charges (3.31 points for the condor).
- Deferred issue #338: a negative Zerodha balance blocks a closing basket (found by the #337 reviewer;
  the wider shape of `margin-gate-blocks-closing-basket`).
- The verifier-in-flight hook false-blocks after a verifier ends (70 left-behind snapshots; finding
  `liveness-from-a-file-nobody-deletes`): GC-2b item 5b; kit issue #113.

## Owner items (unchanged)
- `rotate-algochanakya-secrets` (overdue); REQ-052 AC-2/AC-4 and F-23; F-35 stamp check; OQ-10 (new).

## Per-PC setup not in git
- A kit tool run inside a scratch worktree must set its cwd (the shell returns to the main checkout after each call):
  GC-2a used a scratch launcher; a digest regeneration landed in main twice before that (restored, content unchanged).

## Misses tonight (each recorded the same turn)
- Merged main into a worktree while a verifier ran -> 18 files copied to quarantine (nothing lost). Mechanism: #335.
- Pushed a merge without running the ruff ratchet -> CI refused (E501 +1). Mechanism: atool.py now runs it.
- My hook brief specified a forbidden list -> review MAJOR. Finding occurrence recorded.
- Item-3 brief did not warn about the adapter scan although I had just met it on #336 -> one more red local run.
- Builders over budget: item 3 88/80 tool calls.

## Scorecard
CI runs = GitHub workflow runs on the branch after 22:20 IST (about 4 per push). Tool calls = used / budget.

| Item | Review rounds | CI runs | Local full-suite runs | check_brief before dispatch | Idle gaps > 10 min | Budget overruns (tool calls) |
|---|---|---|---|---|---|---|
| RUNNING marker (#334) | 0 | 3 | 0 | - | 0 | 0 |
| 1 #327 Linux egress (core) | Tier A 2 (gate PASS; scan REVISE 1 MAJOR -> fixed) | 24 (red: ratchet E501 +1 - my push without the ratchet; 2 failures -> diagnosed) | 0 (one targeted DB scale-test file, once) | y (all 4 briefs) | 0 | builder 23/60; CI-diagnosis builder 80/80 (at cap); reviews 12/30, 13/25 |
| 2 #336 ADR-099 + ADR-101 | Tier A 1 (PASS, 5 MINOR) | 14 (red once: adapter scan) | 0 | y (1 false FAIL: kit #113) | 0 | builder 58/80; review 22/30 |
| 3 #337 W-081 + #273 | Tier A 2 (r1 REVISE MAJOR forgeable basket; r2 PASS, 4 MINOR) | 8+ | 0 | y | 0 | **1**: r1 builder 88/80; r2 70/75; reviews 26/30, 12/30 |
| 5 W-075 AC-7 re-verify | verifier 1 (PASS) | in docs PR | 0 | y | 0 | 0: 29/30 |
| 6 merge.py UTF-8 | 0 (red-then-green shown) | in docs PR | 0 | - | 0 | 0 |
| Mechanism #335 in-flight hook | Tier A 2 (r1 REVISE 2 MAJOR; r2 PASS) | 21 (red twice: ratchet +7 rules; a Linux-only test IndexError) | 0 | y | 0 | builders 27/70, 38/70, lint 23/40; reviews 20/30, 26/30 |
| 8 GC-2b + handover | contract review 1 (Explore/Opus, 29/30; 8 findings accepted) | docs PR | 0 | y | 0 | 0 |

Idle gaps: none over 10 min without other work running (every wait had a builder, reviewer or CI job in flight and a
parallel item started). Broken rules recorded the same turn: push without the ratchet (`local-ci-mirror-runs-a-subset`,
3rd), git merge during a verifier (`verifier-guard-watches-every-worktree`, 3rd -> PR #335), a forbidden list in my own
brief (`guard-as-forbidden-list`), builders reading a gate by eye (`gate-output-read-by-eye`, new), one budget overrun
(item 3 round 1, 88/80; `builder-budget-is-prose` - the builder type's hard cap is 100, so 80 is advisory).
