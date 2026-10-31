# Brief: GC-MU A1 - ADR-230 (1) / F-78: playbook liquidity limits flag strikes and refuse an over-limit roll

Core: the three saved playbook limits (`hide_oi_below`, `hide_spread_pct_of_mid_above`, `roll_debit_limit`) are READ and applied by one new module to a real candidate set.
Proof: step 1 of this brief - on a generated scenario with one thin strike, the new module flags exactly that strike and passes the rest; a roll whose debit is above the limit is refused with the reason.
Budget: 45 min wall-clock, 60 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Class: setting-saved-but-never-applied - every playbook guard key stored in system_playbooks.json and labelled in the editor; before: 3 liquidity keys with 0 readers; after: each of the 3 has a reader plus a test that fails for any guard key without one.
Round: 1/2
Findings checked: F-78, F-12 (catalogue), knowledge/findings grep for liquidity, low_oi, roll_debit
Spec quote: ADR-230 "it is never removed silently"
Threat model: in scope - a strike that breaks a saved OI or spread limit shown without a flag, a live strike with unknown OI shown as passing, an over-limit roll not refused, a saved guard key with no reader; out of scope - a user editing the JSON by hand, and limits GC-SET owns (admin settings).
Sensibull: no screen captured; study ARCHITECTURE.md lines 172-174 (per-leg liquidity codes high-bid-offer-spread, no-bid-offer shown beside the leg) - copy the per-leg flag shown beside the strike, never hiding it.
Reference: none - searched liquidity, open interest (only the architecture note above, no screen); open records: RD-096 (shape detection, not touched by this brief)
Copy from: none - no legacy-reuse map row for playbook liquidity guards (new in GC-ADJ3).
Tier: B (Sonnet reviewer, diff-only).

## Where
Worktree `D:\Abhay\Ventures\OptionsForOptions2-gcmu-liq`, branch `build/gcmu-liq` (from `build/gcmu`). Commit there only. Never push. Never touch `main`, `feature/adjustments`, `build/settings`, any `build/gcset-*` tree. `frontend/node_modules` is a junction to the run tree: never delete it, never run `npm ci`/`npm install`.

## The decision (ADR-230 (1), spec/decisions/ADR-230.md - read it)
- A strike whose open interest is below the playbook's OI limit (editor label: Hide strikes with open interest below), or whose bid-ask spread is above its percent-of-mid limit, stays visible in the adjust drawer and the Compare and is flagged with the text `Below your liquidity limit`; it is never removed silently.
- A roll whose debit is above the limit (editor label: Most debit paid for one roll) is refused, with the reason.
- While no live source gives a strike's open interest, a live strike is shown with the text `OI not known`, never as passing (F-78: `low_oi_blocked` has no live source).

## Do, in order
1. CORE PROOF: new module `backend/ofo/adjustment/liquidity.py` (stdlib + existing engine types; Decimal only per ADR-008). Functions: evaluate one strike against a playbook's limits -> state per limit; check a roll's debit against `roll_debit_limit`. Note `roll_debit_limit` is stored as TEXT like `Rs 500 or 10% of max profit` (`system_playbooks.json`) - parse it with one parser; a value the parser cannot read fails closed (refused as limit-not-readable, never treated as no limit). Answer states for each limit, each with a test: stated and passes; stated and breaks (flag / refuse); OI absent in live mode (`OI not known`, never passing); limit not set on the playbook (no flag); limit unreadable (fail closed); empty candidate list. Add a scenario ADJ-50 (ids ADJ-50..ADJ-69 only) via `tests/adjust_scenarios_gen.py` with one thin strike, regenerate its fixture with the generator only. Test: flags exactly that strike, passes the rest.
2. Wire with THIN call sites only (a few lines each; another session edits these files on its branch): the Compare candidate rows (`backend/ofo/adjustment/compare.py`) and the adjust drawer's strike list get a per-strike liquidity state; the roll path refuses an over-limit roll through the existing refusal mechanism (`backend/ofo/adjustment/approaches.py` `_refusal`). Any new user text goes through `backend/ofo/errors/templates.py` with its pin updated per the repo's template-pin process; ADR-003 wording (decision support, never advice). Frontend: the drawer and Compare show the flag `Below your liquidity limit` / `OI not known` beside the strike (find the drawer component under `frontend/src`; keep the change small).
3. Class guard: a test that walks every guard key in every playbook in `system_playbooks.json` (and the editor's label list in `backend/ofo/errors/explanations.py`) and fails for a key with no reader in a known reader registry (a dict in `liquidity.py` or a new small module naming the reader of each key). Keys GC-SET owns or that are already applied elsewhere go in the registry with their existing reader; a key with genuinely no reader today goes in an explicit `KNOWN_UNREAD` list with a one-line reason, and the report lists them.
4. Tests: run in full each test file you added or changed, plus `tests/strategy/test_templates.py` and `python scripts/ruff_ratchet.py` (wording rule REQ-028 AC-5), plus guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`; vitest only the changed component's spec (`npx vitest run <file>`). Output to a log file, read the tail.

## Standing items
- One test per acceptance criterion; targeted files only; a skipped test counts as not run.
- Every test file you changed is run in full.
- Answer states listed in step 1, each tested.
- A change to a shown value greps every test tree (e2e included) for the old value.
- Known bypasses written in the module docstring.
- No new duplicated literal; reuse existing helpers; ruff/mypy baselines must not rise; no regenerated files other than the ADJ-50 fixture made by the generator.
- REPORT every file you changed that is in this list (shared with another session; I log each one): `backend/ofo/adjustment/compare.py`, `backend/ofo_app/adjustment_check.py`, `backend/ofo_app/live_market.py`, `backend/ofo_app/playbook_store.py`, `backend/ofo_app/routes/outcome.py`, `frontend/src/pages/AdjustmentsPage.vue`, `frontend/src/router/nav.js`, `tests/adjust_scenarios_gen.py`, `tests/fixtures/adjust_scenarios/`, `tests/errors/template_pins.json`, `tests/strategy/test_templates.py`, `backend/ofo/errors/templates.py`, `backend/ofo/adjustment/adjust_money.py`, `backend/ofo_app/playbook_eval.py` - with the line ranges changed.
- Commit after each step passes. End the report with the final commit sha on build/gcmu-liq.
