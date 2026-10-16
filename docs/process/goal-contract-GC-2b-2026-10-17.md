# Goal contract GC-2b (Sat/Sun 2026-10-17/18): the 4b boundary - Kite replies into the domain, eligibility from Zerodha

Chain: `goal-chain.md` (rules, process rules 1-8, scorecard). Written by GC-2a from its results (2026-10-17 night).
Owner needed: **no** (recordings only; no Kite login; no order; DB steps only through `scripts/orchestrator/db_run.py`
on ofo_test). **Cap: 6 h wall-clock** - this contract's cap governs even though the chain prompt mentions 8 h; at the
cap, unfinished items are parked and named, then item 8 still runs. **Tail reserve: 1.5 h** for items 5-8 (docs
batch, GC-2c and its review, merge): every time gate below is "item estimate + 1.5 h remain", checked when the
previous item merges, with the clock read (`date`), and the reading written in the handover.

Core: W-091 - the recorded real Kite replies of the owner's 1-lot order (orders / trades / positions at 122104 =
after entry and 151006 = after exit, `D:/Abhay/Ventures/ofo-kite-ticks/2026-10-16/real-order/`) pass through ONE
product adapter into the fill ledger and reconcile, with no scaffolding.
Proof: `docs/research/core-proof-4b-2026-10-16/proof.py` re-run with its four throwaway adapters replaced by the
product adapter: 0 mismatches after entry (65 long NIFTY26O1923650CE) and after exit (flat), the position's P&L equal
to Kite's own flat row (`positions-151006.json`: `pnl -130`, `unrealised -130`, `realised 0` - the test names which
Kite field it compares, and the paisa quantization is the item's first decision row, written BEFORE the assertion),
trade ids 4484194 and 5966618 each entered once; then the same rows as JSON numbers (`parse_float=Decimal`) and as SDK
floats (`Decimal(str(v))`). The recordings live OUTSIDE git (`proof.py` reads `OFO_KITE_TICKS`), so step 1 first
copies the six reply files (orders/trades/positions at 122104 and 151006) into `tests/fixtures/kite_replies/` with the
owner's client id (`placed_by` / `account_id` "DA1707", and any user name or email) replaced by a placeholder, and a
header note naming the source file and the redaction; CI then runs the test.

## Why (from GC-1 and GC-2a results)
- F-40 (GC-1, `docs/research/core-proof-4b-2026-10-16/RESULT.md`): the domain is right on the real order, but every
  real row is refused at the boundary: `positions.py:53` refuses string and float prices, the flat row (quantity 0,
  average_price 0) has no reconcile path while `grouping.py:295` skips it, `orders/model.py:260` refuses the trade
  price string, and nothing turns a Kite trade into a `FillEvent` or a tradingsymbol into a reconcile contract key
  (issue 115). The recording stores money as STRINGS (the recorder's, not Kite's): the adapter must be proven on all
  three shapes (string, JSON number, SDK float).
- W-092 (GC-1 audit, REQ-053 AC-3 PARTIAL): no app code records an `EligibilityStatus`, so the safety gate refuses
  every leg as unconfirmed; GC-3 (the live 1-lot order) cannot pass without it.
- GC-2a landed the W-080 basket and the Linux egress fix (PR #327), Zerodha money rounded to the paisa at parse
  (ADR-101, PR #336, helper `ofo.money.zerodha_paise` - the adapter reuses it for every Kite money figure), and the
  verifier-in-flight hook (PR #335). W-081 is wired (PR #337): `ofo_app/checked_basket.py` is the one production path
  to a basket, `build_basket` takes a Zerodha figure source and decides inside, `KiteBasket`/`MarginVerdict` are
  sealed; the partial-fill re-check uses Zerodha's required margin (#273's instance; #273 stays open until the Execute
  route fills `ExecutionContext` from the same figure, GC-2c).

## Done list (order 1 -> 2; 3 and 4 only if their time gate holds; 5-8 always)

1. **W-091 Kite reply adapter (Tier A, core; estimate 2-2.5 h).** Step 1 IS the core proof above, as a test on the
   redacted real fixtures (`tests_app/test_kite_replies_to_domain.py`, the card's tests_required). One adapter module per endpoint at the app
   boundary (`backend/ofo_app/`): money via `zerodha_paise` on `Decimal(str(v))` / `parse_float=Decimal` values (never
   float arithmetic); a flat-row rule shared with `grouping.py:295` (one helper, not a copy); tradingsymbol/token ->
   reconcile contract key from the catalogue (issue 115); trade rows -> `FillEvent` with IST timestamps taken from the
   trade's own `fill_timestamp` (a full datetime, "2026-10-16 12:20:50"; `order_timestamp` is time-only and is not
   used; never the wall clock). The card's last objective is IN scope: the strategy record's exit is driven from the
   ledger reaching 0 (RESULT.md gap (e)); if it cannot fit, it is moved out BY NAME to GC-2c in the handover. Decide as architect and record (decision rows): realised P&L quantized to the paisa; out-of-order fills
   (F-40 attack A1: an exit seen before its entry must not read as a side flip - reject or hold, never flip). Tier A
   Opus review aimed at: any Kite field reaching the domain unparsed or through float; the flat row; a replayed
   trade id; a contract key that matches two catalogue rows.
2. **W-092 eligibility from Zerodha (Tier A; estimate 1.5-2 h).** Its decision step runs in parallel with item 1's
   review (it does not need the adapter: eligibility comes from the instrument list and the margin reply); the build
   waits for item 1's merge only where they touch the same files. First, as architect and recorded: which Zerodha
   replies count as "what Zerodha data allows" (REQ-053 AC-1/AC-3; the spec does not name them - audit B). Likely the
   day's Kite instrument list (listed, not expired; the product's own instrument download, NOT the recorder's
   `instruments.json`, which is a symbol/group map) + the basket-margin reply (an order Zerodha would refuse shows
   there); the decision row says how this keeps the catalogue stored separately from current eligibility (REQ-053
   AC-2);
   if the choice changes what a user sees, it goes to `owner-questions-<the run's date>.md` and the run continues with the
   spec-conformant part. Core: the real NIFTY26O1923650CE of 2026-10-16 is let in from that day's instrument list
   (recorded fixture of the product's download); a contract absent from it is blocked at add time; the "again just before execution" check is wired in the domain now, and its caller (the
   Execute route) lands in GC-2c - say so in the card. A catalogue-store change runs only its own DB test file through
   `db_run.py`; tunnel down = park the item, continue the offline ones.
3. **ADR-058 delisted-held -> reconciliation (Tier A: a raised reconciliation blocks execution, ADR-019 - order
   safety), only if 1 h + the 1.5 h tail remain after item 2.** ADR-058: "A
   delisted contract held by a live strategy raises that strategy's reconciliation (ADR-018)". Today the catalogue
   marks it delisted; nothing raises the reconciliation. One real case or "no real case in N days" in the brief.
4. **W-017 audit allowlist for the order / trade / position event types (REQ-063 AC-5, Tier A), only if 2 h + the 1.5 h
   tail remain; else parked to GC-2c with a note (expected: it parks).** Declare the payload allowlist from the TWO real samples each
   (122104 and 151006); the session (login) type stays `unproven for type session` until GC-3 captures a login reply
   (zero hits for access_token / enctoken / public_token in the recordings).
5. **Carry-overs from GC-2a** (each a line in the handover): W-081 AC-1/AC-3/AC-4 have no evidence file yet - one
   fresh verifier pass on main (Tier B verifier only, ~30 min, after item 1; its round 1 review blocks were on the
   pre-fix code); for GC-2c, written into it: the Execute route type-checks the basket and builds it again on every
   request (#337 round 2 MINORs), and deferred issue #338 (a negative Zerodha balance blocks a closing basket); the history-finalize
   scale-test hang (two unexplained CI failures, runs 38897947228 and 38938587984; two later runs green; lead:
   autovacuum on `history_minute_bars`) - if it recurs on any CI run, open a `deferred` issue with the run id, do not
   retry blindly; OQ-10 (breakeven columns vs charges) waits for the owner, not this contract.
5b. **The verifier-in-flight hook false-blocks after a verifier ends (finding `liveness-from-a-file-nobody-deletes`,
   Tier A hook, ~45 min, before item 2 if a verifier will run in this contract).** The kit guard leaves snapshots
   behind (70 in 24 h), so the hook holds guarded writes up to 15 min after every verifier. Measure the longest single
   verifier tool call from tonight's snapshots' timestamps first, then pick the fix (finding's options a-c); a kit
   issue for option (c). Until fixed: delete the named snapshot ONLY after confirming no verifier agent is running.
6. **Kit issue Startup-Factory #113 (filed by GC-2a):** running a kit tool inside a linked worktree outside the project
   folder is blocked and the bare form runs against main; `check_brief.py` false FAIL next to an ADR-named branch.
   Until the kit answers, use a launcher that sets `cwd` (GC-2a's `kit_in.py` pattern, like `atool.py`). Nothing to
   build here; check the issue once and note its state in the handover.
7. **Docs batch (one PR):** evidence files, card statuses, decision rows, findings, regenerated digest / findings
   index / coverage register, this contract's row DONE or PARTIAL.
8. **Write GC-2c** from the results (the app Execute chain: Execute route -> read-only basket through the W-081 path ->
   return-from-Kite read-back through the W-091 adapter -> reconcile -> audit; persisted order book #313; Execute
   screen REQ-073 AC-1..3, REQ-057/058/060), get it independently reviewed, mark it NEXT, merge with the handover;
   print the prompt, the 5-line summary and the scorecard.

## Process rules (checkable lines; `goal-chain.md` process rules 1-8 apply in full)
- Chain rule 2: `git pull` main, refuse if a row is RUNNING, set this row RUNNING in the first commit.
- Before every merge gate: `gh pr update-branch N` (or `merge.py`, which does it); after every merge of main into a
  branch: `python scripts/orchestrator/merge_audit.py . <branch-tip> <main-ref> <merged-head>`.
- Local before push: `python scripts/orchestrator/atool.py <worktree> --no-tests` (from GC-2a's docs PR it also runs
  the api job's ruff ratchet and migration guard, and the ratchet ends on a FAIL/OK verdict line; a stale digest shows as `build_spec_digest rc 1` AND `kit_drift rc 1` - regenerate the
  digest, then both clear), `scripts/orchestrator/pr_close_check.py`, the changed files' tests. No local full suite.
  The kit CI runs the WHOLE domain suite: a repo-wide scan (`tests/marketdata/test_provider_replaceable.py`, the
  door/boundary scans) can fail on a new file or a new `kite_*` name - run `tests/marketdata/` and `tests/test_*.py`
  locally when adding an `ofo_app` module (GC-2a: PR #336 went red on it once).
- Kit tools in a scratch worktree: the shell returns to the main checkout after each call, so a bare
  `python tools/<x>.py .` runs against MAIN. Use `atool.py` (checks) or a launcher that sets `cwd` (GC-2a measured:
  a digest regeneration landed in main twice).
- Every brief: `check_brief.py`, the reviewer checklist + attack cases, `Findings checked:` ids (at least
  `broker-reply-shape-unproven-at-domain-boundary`, `money-parsed-through-float`, `held-without-platform-fill-
  invisible-to-ledger`, `trust-broker-status-word` where they bear), `Copy from:`, `Budget:` (at most 80 % of the agent
  type's turn cap), `Report: evidence-table`.
- Verifier in flight: the `verifier_inflight_gate` hook refuses guarded writes and non-read-only git; do not work around
  it - start an item that writes elsewhere.
- One review round by tier; a second only on CRITICAL/MAJOR; two failed rounds -> independent redesign; third -> park.
- Read-only audits and reviews go to an agent type with a hard turn cap (`verifier`: 40, `builder`: 100, `Explore`),
  never `general-purpose`; use `Explore` for a review that must not open a verifier write-guard window while another
  agent writes cards.
- A builder's "ratchet only fell" or "tests pass" is a claim: re-run the ratchet and the named tests before pushing
  (GC-2a: a builder read "rose" lines as "fell").

## Stops
- None needs the owner. A choice that changes what a user sees beyond the spec goes to
  `owner-questions-<the run's date>.md` with a recommendation; the run continues.
- DB steps through `scripts/orchestrator/db_run.py` (ofo_test) only; tunnel down = park that item, continue the
  offline ones.
- Park rule: two failed rounds or an outside blocker -> a `parked` issue via `gh_issue.py --stage`, named in the
  handover.
