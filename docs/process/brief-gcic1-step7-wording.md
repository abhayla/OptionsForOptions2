# Brief: GC-IC1 step 7 - ADR-003 / REQ-155 AC-8: apply the #629 wording decisions and screen every new text of GC-IC1

Core: every decision in `D:\Abhay\scratch\wording629\owner-decisions.md` (7 HIGH, consistency rules C1-C13 except C6, 55 MED and 34 LOW rewrites as written, with its two builder rules) is applied to the catalogue texts on feature/adjustments, and every text GC-IC1 added (day rules, carry check, A-24..A-38 refusals and labels, guidance label) passes the same rules, with the pins updated.
Proof: step 1 of this brief - the 7 HIGH texts read as decided in `backend/ofo/errors/explanations.py` / `templates.py` and the frontend label sources (grep each new text, show the line), and `python -m pytest -q tests/strategy/test_templates.py tests/errors` is green with the pins updated.
Budget: 60 min wall-clock, 80 tool calls
Report: evidence-table (claim | command run this turn + its result line; under 300 words), then the next command to run
Round: 1/2
Findings checked: gate-output-read-by-eye
Spec quote: REQ-155 AC-8 "is refused with its reason naming the leg"
Threat model: in scope - a text changed in the catalogue but a test, an e2e spec or a frontend copy still asserting the old words (grep `tests/`, `tests_app/`, `frontend/tests/`, `frontend/e2e/` for every old text before changing it); a rewrite that adds a slot with typed hours instead of a source (decision rule 1); advice wording ("you should", "consider", "you may want to"); C6 (tracking vs paper) changed by mistake. Out of scope - product naming (C6), new features.
Sensibull: n/a - wording only.
Reference: none - searched wording, catalogue texts, advice wording
Copy from: none.
Tier: C (texts; CI + the template / guard tests are the gate).
Size: L split guard: texts only, about 10 files, 1 item; if more than 15 files change, stop and report the list.
CI: the backend unit job runs `tests/strategy/test_templates.py`, `tests/errors`; the frontend job runs `frontend` unit tests for label sources; vars: none

## Where
`git switch -c build/gcic1-s7 <sha given in the dispatch>` inside your agent worktree (feature/adjustments, never main, never push). No DB tests.

## Read first
`D:\Abhay\scratch\wording629\owner-decisions.md` (the decisions, 50 lines), `wording-review.md` (the MED / LOW rewrites by id), `pending_texts.json` (ids -> current text, extracted at 396c1eaa: re-check each id still exists at your base; a text changed since is listed, not overwritten blindly), `ADR-003.md` in that folder. Memory note: wording changes also run `tests/strategy/test_templates.py` (AC-5 shape-name guard) and `scripts/ruff_ratchet.py`; shape names live in JSON data.

## Do, in order
1. HIGH 7 first, then C1-C13 (not C6), then MED and LOW as written.
2. Pins: update `tests/errors/template_pins.json` per the decisions ("pending owner read" stays where the decisions file says so; the decided texts are marked as the decisions file states).
3. Every text added by GC-IC1 (grep the pins marked pending owner read added since 37824fb9) screened with the code's own checkers (`find_banned_phrases`, `find_advice_wording`, `find_position_words`) and C1-C13; fix what fails, list each.
4. Run `python -m pytest -q tests/strategy/test_templates.py tests/errors tests/adjustment`, the guard tests `python -m pytest tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py -m repo_scan`, the frontend unit tests for changed label files (`npx vitest run <file>` in `frontend`; `npm ci --prefer-offline` first if node_modules is missing, in your own worktree, no junctions), ruff on changed files, `python scripts/ruff_ratchet.py`.

Standing items:
- B4 (d) every rewritten text with slots: each slot filled from a source; a slot with no source keeps the old text and is listed.
- No new duplicated literal; ruff baselines must not rise; no regenerated aggregates.
- If `git commit` is refused by verifier_inflight_gate, retry at most 3 times, then report files + command. End with the final commit sha on build/gcic1-s7.

Attack list:
1. An e2e spec still asserting "Healthy": grep frontend/e2e; update with the text.
2. "Cr" changed in a cell but a test still expects "Cr": grep.
3. A MED rewrite that adds hours typed in the text: refused per rule 1.
4. A GC-IC1 text with "consider": rewritten.
5. C6 untouched: "tracking" and "paper" texts unchanged (grep count before and after).
