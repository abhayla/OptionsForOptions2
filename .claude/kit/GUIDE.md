# Kit guide

This file is kit-owned: every kit upgrade replaces it, so it never goes stale. Your `CLAUDE.md` points here in one
line; read it before pushing or touching process files.

## Commands (mirror CI before every push)
- `pip install pyyaml jsonschema pytest` (once)
- `python tools/kit_settings.py . --check`
- `python tools/factory_lint.py .`
- `python tools/trace_check.py .`
- `python tools/build_order.py . --check` (regenerate without `--check`; before starting work: `--may-start REQ-###`)
- `python tools/run_smoke.py .` (the walking skeleton's smoke commands)
- `python tools/build_spec_index.py . --check` (requirements by section; regenerate without `--check`)
- `python tools/spec_dupes.py .` (blocks restated spec text; before writing a spec line: `python tools/spec_similar.py . "<text>"`)
- `python tools/build_findings_index.py . --check` (once `knowledge/findings/*.json` exists)
- `python tools/check_spec_refs.py .`
- `python -m pytest -q -p no:cacheprovider` (once `tests/` exists; run single files while iterating)
- `python tools/kit_selftest.py .`
- `python tools/kit_drift.py . --ci` (for a pull request, check against its base: `python tools/kit_drift.py . --ci --base <sha>`)
- `python tools/check_pr_spec_block.py` (pull requests only; needs the PR body)
- Merge a PR: `python tools/merge_when_green.py <pr>`

## Kit files: never edit them in the project
`.claude/rules/kit/`, `.claude/kit/` (this guide included), `.claude/README.md`, `.claude/hooks/`, `.claude/agents/`,
`.claude/skills/deliver/`, `.claude/skills/intake/`, `tools/`, `factory/schemas/`, `.github/workflows/ci.yml`,
`.github/pull_request_template.md`, `KIT_VERSION`. A kit defect, or a lesson every project should get, is filed as a
GitHub issue labelled `harvest` in `abhayla/Startup-Factory`; never edit kit files here. A kit upgrade replaces them.

## Where kit rules, skills and agents live
- Rules: `.claude/rules/kit/` (kit-owned; three always loaded, the rest load when a file they govern is touched).
  Your own rules go in `.claude/rules/project/`.
- Skills: `.claude/skills/deliver/` and `.claude/skills/intake/`.
- Agents: `.claude/agents/`.
- Hook wiring and each file's owner: `.claude/README.md`; release notes: `.claude/kit/CHANGELOG.md`.
