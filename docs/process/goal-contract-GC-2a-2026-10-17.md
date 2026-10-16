# Goal contract GC-2a (Sat 2026-10-17): land the basket, round Kite money to the paisa, wire the margin gate

Chain: `goal-chain.md` (rules, process rules 1-8, scorecard). Written by GC-1 from its results (2026-10-16 night).
Owner needed: **no** (offline; no Kite login; no order). **Cap: 6 h wall-clock**; at the cap, unfinished items are
parked and named, then item 8 still runs.

Core: the W-080 basket (PR #327) passes CI's Linux `api` job with the egress gate still refusing every send to a
non-allowed destination - everything else in this contract (W-081 wiring, #273, the margin line) sits on that branch.
Proof: one CI run of #327 on Linux after the fix: the `api` job green, plus a test in that run that sends UDP to
192.0.2.1 and is refused, and a test that `sendmsg(None)` on an UNCONNECTED UDP socket is refused.

## Why (from GC-1's results)
- #327 is verified (evidence/W-080 AC-1/2/4 PASS at 26eff25, Tier A integration PASS at 858c7b6) but red on Linux
  only: `socket.sendmsg to None refused` at `backend/ofo/broker/egress.py:254` (CI run 38897947228, 132 failed). The
  laptop cannot reproduce it (no WSL, owner rule) - CI Linux is the only proof.
- The GC-1 audit (`4a-closeout-audit-2026-10-16.md`) placed these 4a/4b gaps here: REQ-053 AC-4 (#273: the
  pre-execution margin check still uses the platform's estimate), REQ-054 AC-1 margin (W-081 has no caller), REQ-063
  AC-5 (24 of 33 audit event types refused; W-017's card blocker was stale and is corrected), #297 item 3 (ADR-099
  margin line: Kite float noise flips the shortfall flag), W-075's AC-7 never re-verified after its rounding change.
- GC-1's 4b core proof (F-40) showed the domain is right and the reply boundary is missing; that adapter is GC-2b
  (W-091), not here; W-017 (REQ-063 AC-5) moves there too (contract review: no login reply recorded; over the cap).

## Done list (order: 1 -> 2 -> 3, each after the previous merges - they share `kite_margin.py` and `live_market.py`;
## only items 5 and 6 run in parallel with them)

1. **#327 Linux egress fix (Tier A, core).** FIRST remove the old scratchpad worktree `wt-w080` (it holds
   `land/W-080`, so git refuses a second checkout; check it is clean and in sync with origin, then remove it with the
   worktree helper), then re-create the worktree from `origin/land/W-080` (chain rule 7). Fix per
   #327's last comment: in `egress.py`'s audit hook allow `socket.sendmsg` / `socket.sendto` whose address is `None`
   ONLY on a socket whose connect was already gated; keep refusing a send WITH an address to a non-loopback,
   non-database destination. Tests first: UDP to 192.0.2.1 refused; `sendmsg(None)` on an unconnected UDP socket
   sends no packet (assert that nothing leaves - on Linux the OS itself may raise `OSError` before the gate does);
   asyncpg's send on its connected socket allowed. Prove on CI Linux (push, read the `api` job). Tier A Opus
   review aimed at: can any caller reach a non-allowed host through `sendmsg(None)` without a gated connect. Merge
   with `land.py` / `merge.py`. This closes W-080 (REQ-073 AC-1/2/4) and the ADR-098 bar.
2. **ADR-099 outcome margin + paisa rounding (Tier A; #297 item 3), after item 1 merges.** Branch
   `build/ADR-099-outcome-margin` at 289824e (worktree `agent-aaeeac57d668b7254`, 8 commits behind main): merge main
   only AFTER #327 is on main (both touch `kite_margin.py` / `live_market.py`; #327 puts `kite_margin` behind the Kite
   door). Fix per #297's last comment: one helper in `ofo/money.py` rounding a Kite money figure HALF-UP to the paisa,
   called where each Kite figure is parsed (`_final_total`, `_premium` in `backend/ofo/execution/margin_gate.py`;
   `_money` in `backend/ofo_app/kite_margin.py`), then the ADR-094 top-up. Attack: Zerodha 68498.85000000001 needed vs
   68498.85 available must show no shortfall; 68498.84999999999 available must read 68498.85. It moves the REQ-055 gate
   (`required_from_basket_reply`) and REVERSES a deliberate choice: `margin_gate.py:141` keeps Kite's float noise
   because it "errs on the safe side"; half-up rounding can let through a basket short by under Rs 0.005. Record that
   as a decision row (technical, Tier A) and add the attack test: a basket short by Rs 0.01 still blocks. Gate tests +
   Tier A review. Real data: the basket replies under `rest/` (`margins/basket` calls, with float tails) for needed;
   `real-order/margins-*.json` are funds replies (`equity.net`) for available.
3. **W-081 wired + #273 (Tier A; REQ-055, REQ-053 AC-4, REQ-054 AC-1 margin), after item 2 merges; start only if at
   least 2.5 h of the cap remain, else park it to GC-2b with a note.** `build_basket` (on `land/W-080` only until #327
   merges)
   takes the margin verdict from Zerodha's basket figure (not the platform estimate); the W-081 card's blockers
   (basket #271, live funds read, #273) are re-checked against main first. Real data: `margins-122104.json` /
   `margins-151006.json` and the `rest/` margin replies. Write its own brief (`brief-W-080-integrate.md` has no
   margin, W-081 or #273 content).
4. **W-017 moved to GC-2b** (contract review 2026-10-16): it does not fit the cap, and its card's core needs a
   real Kite LOGIN reply that no recording holds (`access_token` / `enctoken` / `public_token`: zero hits under
   `ofo-kite-ticks/` and `tests/fixtures`). GC-2b declares the order / trade / position types from their two
   real samples each and writes the session type `unproven for type session`; the login reply is captured, secrets
   redacted, at GC-3's login.
5. **W-075 AC-7 re-verify (Tier B verifier only, ~30 min)** on main: charges in the money sentences, the OQ-4 (a)
   line, and the round-up to the paisa (`to_paise_up`); record the evidence; then read issue 269's D5 and close or
   narrow it.
6. **W-088 (#159) if GC-1 did not merge it**: finish its Tier A round, merge; the live check (a real login lands on
   `/broker/connected`) is GC-3's first step.
7. **Docs batch (one PR):** close #30 (superseded by #200) and #154 (the BEHIND refusals recorded 2026-10-16 are the
   red-then-green proof) with a comment each; evidence files; card statuses; regenerated digest / findings index /
   coverage register; this contract's row DONE or PARTIAL.
8. **Write GC-2b** from the results (the 4b boundary: core = W-091 Kite reply adapter on the real-order recordings,
   replacing the four scaffolding adapters of `docs/research/core-proof-4b-2026-10-16/proof.py`; then W-092
   eligibility and ADR-058's delisted-held -> reconciliation; the Execute chain is GC-2c), get it independently
   reviewed, mark it NEXT, merge with the handover; print the prompt, the 5-line summary and the scorecard.

## Process rules (checkable lines; `goal-chain.md` process rules 1-8 apply in full)
- Chain rule 2: `git pull` main, refuse if a row is RUNNING, set this row RUNNING in the first commit.
- Before every merge gate: `gh pr update-branch N`; after every merge: `python scripts/orchestrator/merge_audit.py`.
- Local before push: the fast spec checks, `scripts/ruff_ratchet.py`, `scripts/orchestrator/pr_close_check.py`, the
  changed files' tests. No local full suite (target 0). Item 1's Linux proof is CI's.
- Every brief: `check_brief.py`, the reviewer checklist + attack cases, `Findings checked:` ids (at least
  `money-parsed-through-float`, `sealed-object-mutable-after-seal`, `broker-reply-shape-unproven-at-domain-boundary`
  where they bear), `Copy from:`, `Budget:`, `Report: evidence-table`.
- No card, spec or evidence write while a verifier is in flight, in ANY worktree (finding
  `verifier-guard-watches-every-worktree`; kit issue Startup-Factory 110).
- One review round by tier; a second only on CRITICAL/MAJOR; two failed rounds -> independent redesign; third -> park.
- Read-only audits and reviews go to an agent type with a hard turn cap (`verifier`: 40, `builder`: 100, `Explore`), not
  `general-purpose`, which has none: a `Budget:` line alone is prose (finding `builder-budget-is-prose`, 8 occurrences;
  GC-1's three audits used 104 / 66 / 57 calls of 40). The scorecard reads each dispatch's tool-use count.

## Stops
- None needs the owner. DB steps through `scripts/orchestrator/db_run.py` (ofo_test) / `dev_run.py` (ofo_dev); tunnel
  down = park that item, continue the offline ones.
- A choice that changes what a user sees beyond the spec goes to `owner-questions-2026-10-17.md` with a
  recommendation; the run continues.
- Park rule: two failed rounds or an outside blocker -> a `parked` issue via `gh_issue.py --stage`, named in the
  handover.
