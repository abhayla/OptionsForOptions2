# Verifier brief: row 20 backend part (W-148, REQ-076 leg rows) - checker

Common brief: docs/process/builder-brief.md (checker part). Fresh context, adversarial, read-only: edit no file,
commit nothing; scratch copies for every mutation. No database over the tunnel (DB tests run in CI on draft PR #531).
Checker model: Sonnet - the changed files are not in the safety set (builder-brief.md); the builder did NOT run the
mutation gate, so you run the mutants below yourself (`python scripts/orchestrator/mutation_gate.py <checkout copy>
<mutants.json> <results.jsonl>`, each mutant `{id, file, find, replace, test}` with `find` unique in `file`).

Spec basis: REQ-076 AC-1 "never strike plus a typed constant"; REQ-076 AC-2 "the other legs keep theirs"; REQ-076 AC-4
"setting it back to 1 returns every leg to its base lots"; REQ-076 AC-7 "The tick state is never saved and never
reaches the execution plan"; REQ-076 AC-9 "The shape name is a label only".
Reference: screens 025, 103, 111, 244 - copy only what each open record says; open RD-031, RD-091, RD-097, RD-139, RD-140, RD-141

What was built: chunk head on `build/seq-chunk-2` in `D:\Abhay\Ventures\OptionsForOptions2-builder-reqs` (row 20 commits
17a9d596, 6a2aeac6, a7b1b4a9, merged): `backend/ofo/strategy/leg_edit.py` (step, multiplier, freeze block, include,
matching + protective), `backend/ofo_app/routes/leg_edit.py` (POST /api/strategies/leg-edit: step, multiplier, include,
price, reset_prices), catalogue protective flags, loader/model/matching/template schema, errors templates. Taken from
branch `build/W-126-a1-leg-rows` WITHOUT its REQ-078 parts. REQ-076 AC-6's example was corrected today (0744041e): the
bought CE wing out gives Unlimited; the bought PE wing out stays finite (a naked short put is bounded by its strike) -
confirm the engine agrees on both with numbers.

Scope now: backend ACs at the route/domain - AC-1, AC-2, AC-4, AC-5, AC-6 (numbers), AC-7 (tick never saved / never in
the plan), AC-8, AC-9, AC-10 (no-live behaviour). AC-3's screen part and the leg rows UI are the row's frontend part.

## Per AC (pass / fail / partial)
- AC-1 step to the next LISTED strike for that underlying and expiry (an instrument-list slice with a 50 -> 100 gap far
  from ATM); refused at the first/last listed strike; no step on a futures leg; an unlisted strike is refused, not rounded.
- AC-2 a stepped leg re-captures its planned entry (LTP, else mid) with a new time; others keep theirs; no price -> unpriced.
- AC-4 multiplier 1-50 (0, 51, 2.5, '3' refused); 1 restores base lots; engine max loss scales x3 for multiplier 3.
- AC-5 quantity = lots x the lot size from the instrument data (SENSEX too); above the freeze limit -> the ADR-092 block
  reason on that leg, never split.
- AC-6 unticked leg excluded from summary, payoff, table, margin, Greeks; stays in the reply marked left out; the
  corrected example (CE wing -> Unlimited; PE wing -> finite, show the number).
- AC-7 the tick state never reaches the saved definition (save/stored form) or the execution plan (Execute builds from
  the saved definition) - prove with the real save and execute-plan code paths, not a fake.
- AC-8 / AC-9 matched template name ('Custom Strategy' when none) and server hedge marks; a type change -> Custom with no
  marks; the name never changes legs.
- AC-10 no-live: steps, multiplier and tick work; a number needing a missing price shows unavailable with its reason.
Also: grep that no REQ-078 code was taken (shift, width, hedge controls, MAX_HEDGE_LEGS, strike_step, /leg-controls).
Mutants (run them): step uses strike + 50 instead of the listed grid; edge refusal removed; multiplier upper bound 51;
freeze block removed; include ignored in the engine call; tick written into the saved definition. Each must be killed.

Threat model: in scope - a typed gap or lot size, an old price after a step, a multiplier outside 1-50, a freeze bypass or split, the tick saved or sent to Execute, REQ-078 code taken; out of scope - the leg rows UI (frontend part), late replies (row 23).
Findings checked: verified-on-a-module-the-product-does-not-call, brief-rule-from-memory

Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py tests/errors/test_producer_inventory.py; python -m pytest -q -p no:cacheprovider -m repo_scan tests
Budget: 20 min wall-clock, 40 tool calls
Report: evidence-table - per AC: verdict, route/function, exercised there yes/no, command, output line; mutation results;
numbered findings CRITICAL / MAJOR / MINOR with file:line. Under 500 words.
