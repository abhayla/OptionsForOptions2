# Builder brief: W-098 One seal for every proof object, and a repo test that every gate's proof type refuses forgery (Tier A: a guard on the order gates)

Core: a repo test discovers the parameter types of the order gates (`ofo.execution.safety.check_pre_execution`,
`ofo.execution.basket.build_basket`, `ofo_app.checked_basket.checked_basket`) that are proof objects (today:
`KiteBasket`, `MarginVerdict`, `ZerodhaEligibility`, `ListState`) and proves each refuses construction outside its
minting function, `copy.copy`, `copy.deepcopy`, `pickle.dumps`, `dataclasses.replace` and `object.__setattr__`; a
planted open `@dataclass` proof type added to a gate signature in a scratch copy makes the test red.
Proof: step 1 is `tests/test_sealed_proof_objects.py` written FIRST and run against today's code (it should pass for
the four types - if one fails, that is a real hole: report it), then the planted-dataclass mutation (red), then the
refactor onto one helper with the test still green.

Tier: A (the guard that stops a forged verdict reaching an order gate). Model: sonnet.
Budget: 50 min wall-clock, 56 tool calls. HARD limit: at call 52 commit, push, report done / not done / next command.
Report: evidence-table (`| Claim | Evidence (command run this turn) |`), under ~300 words, plus the list of proof
types found and each guard with its killing test.
Copy from: none - spec/technical-design/legacy-reuse.md has no sealing row (searched: seal, verdict, immutable).
Findings checked: caller-supplied-verdict-trusted, sealed-object-mutable-after-seal, guard-as-forbidden-list,
guard-by-banned-shapes, guard-without-killing-test, domain-test-imports-app-package
Tests: python -m pytest -q -p no:cacheprovider tests/test_*.py tests/errors/test_write_allowlist.py

Read first: `docs/process/builder-brief.md` (every line applies), `CLAUDE.md`, the two finding files
`knowledge/findings/caller-supplied-verdict-trusted.json` and `sealed-object-mutable-after-seal.json`,
`backend/ofo/execution/basket.py` (`KiteBasket`), `backend/ofo/execution/margin_gate.py` (`MarginVerdict`),
`backend/ofo/instruments/eligibility.py` (`ListState`, `ZerodhaEligibility`), `backend/ofo/execution/safety.py`
(`check_pre_execution` signature), `backend/ofo_app/checked_basket.py`.

## Spec basis
- Finding caller-supplied-verdict-trusted (6 occurrences; GC-2c contract item 5b): its mechanism is this item.
- ADR-016: "use the instrument master, what Zerodha data shows, and Zerodha's order response as final" - the
  eligibility and margin proofs carry Zerodha's answers, so a forged one would replace Zerodha's answer.

## Work card (commit FIRST as `work/W-098.md`, frontmatter shape of `work/W-091.md`)
id W-098; title "One seal for proof objects and a repo test that every gate proof type refuses forgery (finding
caller-supplied-verdict-trusted)"; requirement_ids [REQ-059]; tier A; status in_progress; depends_on []; affected
[backend/ofo/, tests/]; tests_required ['AC-1: tests/test_sealed_proof_objects.py']; core/proof = the lines at the top;
review_status 'not reviewed'; next_action 'Tier A review'. Add `W-098: 4b` under `work_items:` in
`docs/process/coverage-stages.yaml`.

## What to build
1. `backend/ofo/sealed.py` (standard library): the ONE seal helper the four types use - a base or decorator that gives
   an immutable tuple with no attribute storage, a mint path only the owning module can use, and refusing
   `__copy__` / `__deepcopy__` / `__reduce__` / `__reduce_ex__` / `__setattr__` / `__init_subclass__` (no subclass can
   reopen it). Move the four types onto it with NO behaviour change (their existing tests stay green unchanged).
2. `tests/test_sealed_proof_objects.py`: discovery by signature, not a hand list - walk the three gates'
   `inspect.signature` / type hints; every parameter type that is not a plain value type (str, int, Decimal, bool,
   date/datetime, Enum, Callable, the domain's plain input dataclasses that the gate RE-CHECKS itself - list those
   explicitly with a one-line reason each, as an ALLOW-list) must be a sealed proof type and pass every refusal. A
   new proof type added to a gate without the seal fails the test. The test imports `ofo_app.checked_basket` only if
   the domain test tree may (finding domain-test-imports-app-package: if not, put that part in `tests_app/`).
3. The planted mutation: a scratch copy where a gate takes a new open `@dataclass(frozen=True)` proof type -> red
   (frozen dataclasses still allow `dataclasses.replace` and `object.__setattr__`). Do not commit the mutation.

## Reviewer checklist (each red when mutated; write these first)
- Remove one refusal (e.g. `__deepcopy__`) from the helper -> red for all four types.
- A subclass of a sealed type that overrides `__setattr__` -> refused at class creation.
- `object.__new__(KiteBasket)` / `tuple.__new__(KiteBasket, ...)` outside the mint -> refused or unusable (say which).
- The allow-list of re-checked plain inputs: delete one entry -> red; add an unknown type to a gate -> red.

## Rules
- Targeted tests only: `python -m pytest -q -p no:cacheprovider tests/test_sealed_proof_objects.py tests/execution/ tests/instruments/ tests/test_*.py`
  and `python -m pytest -q -p no:cacheprovider -c pytest-app.ini tests_app/test_checked_basket.py tests_app/test_eligibility_from_zerodha.py`
  (skip a DB file and say so). Grep `tests/` and `tests_app/` for each of the four class names and add every file.
  `python scripts/orchestrator/atool.py <your worktree> W-098 --no-tests` (read its exit and every ` rc ` line);
  `python scripts/ruff_ratchet.py` must not rise.
- Do not edit `backend/ofo_app/routes/`, `execution_plan_store.py`, `kite_reads.py`, `marketdata/` (parallel items).
  No kit or `spec/` edit, no `views/`, no findings INDEX, no regenerated files, no `evidence/`.
- Commit and push `build/W-098-sealed-proofs`. No PR.
