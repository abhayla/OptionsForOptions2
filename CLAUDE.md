# CLAUDE.md

OptionsForOptions2: NIFTY/SENSEX options strategy platform (`spec/vision/vision.md`), built on the Startup-Factory kit.

## Read first
1. `spec/decisions/ADR-*.md` win over everything; `views/spec-digest.md` lists them.
2. Newest `docs/process/session-handover-*.md`, then `docs/HANDOVER.md`; open items in `spec/open-questions.md`.
3. `knowledge/findings/` before designing a mechanism.
4. How to build, test, brief, merge: `docs/process/runbook.md` (delivery per ADR-189). Before pushing or touching
   process files, read `.claude/kit/GUIDE.md`.
5. Before any feature: the Sensibull study, `D:\Abhay\Ventures\competitors\sensibull\2026-10-21\INDEX.md` (cite
   screen numbers; never copy its images into this public repo). Broker, orders or market data: first
   `D:\Abhay\Ventures\competitors\multi-broker-architecture\2026-10-21\INDEX.md`.

## Commands (rest in the runbook)
- Pre-push: `python tools/ci_local.py`. Domain test: `python -m pytest tests/<file>.py -k <name>`.
- DB test, one file only (host serves prod): `python scripts/orchestrator/db_run.py . python -m pytest -c pytest-app.ini tests_app/<file>.py`

## Hard rules
- Every order belongs to a strategy; no standalone order entry (ADR-002).
- One engine owns every P&L/payoff number; money is exact decimal, never float (ADR-008).
- Zerodha is the authority; submitted is not executed; no auto retry, no silent substitution; an unresolved
  mismatch blocks execution (ADR-016 to ADR-019).
- Decision-support wording, never advice (ADR-003).
- Browsers never reach a data vendor; broker and payments sit behind adapters (ADR-012, ADR-029).
- Stack Python/FastAPI, PostgreSQL, Redis, Vue 3 (ADR-043); copy first from the legacy-reuse map, never edit legacy
  repos (ADR-047).
- Never edit kit files (list in the GUIDE); file a `harvest` issue in abhayla/Startup-Factory.
- No fix/close/resolve before `#N` in a PR or commit unless the whole issue is done (`Fixes #N` line).
