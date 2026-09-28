# <fill in: project name>

<fill in: one or two sentences — what this project does, for whom>. Built on the Startup-Factory kit
(version in `KIT_VERSION`); the kit's rules in `.claude/rules/kit/` always apply.

## Read first
1. `spec/decisions/ADR-*.md` — the owner's decisions. They win over everything else.
2. `docs/HANDOVER.md` — where the work stands and the next step.
3. `knowledge/findings/` — proven failure classes; check before designing a mechanism.

## Hard rules
- <fill in: this project's own hard rules — anything a decision (ADR) made non-negotiable, e.g. what
  never enters git, what must pass before a production action, what a decision explicitly forbids>.
- Kit files (`.claude/rules/kit/`, `.claude/kit/`, `.claude/README.md`, `.claude/hooks/`,
  `.claude/agents/`, `.claude/skills/deliver/`, `.claude/skills/intake/`, `tools/`,
  `factory/schemas/`, `.github/workflows/ci.yml`, `.github/pull_request_template.md`,
  `KIT_VERSION`) are never edited here; a kit defect or a lesson every project should get
  is filed as a GitHub issue labelled `harvest` in `abhayla/Startup-Factory` — never edit kit files
  here.

## Commands (mirror CI before every push)
- `python tools/kit_settings.py . --check`
- `python tools/factory_lint.py .`
- `python tools/trace_check.py .`
- `python tools/build_findings_index.py . --check` (once `knowledge/findings/*.json` exists)
- `python tools/check_spec_refs.py .`
- `python -m pytest -q -p no:cacheprovider` (once `tests/` exists; run single files while iterating)
- `python tools/kit_selftest.py .`
- `python tools/kit_drift.py . --ci` (add `--base <sha>` when checking a pull request against its base)
- `python tools/check_pr_spec_block.py` (pull requests only — needs the PR body)
- Merge a PR: `python tools/merge_when_green.py <pr>`
