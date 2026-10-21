# plans/

Plan records (kit 1.8.0 item 1): one `PL-###.md` per plan, YAML frontmatter validated against
`factory/schemas/plan.schema.json` by `factory_lint.py`. Required fields: `id` (PL-###), `title`, `goal`, `status`
(active / done / dropped), `covers` (REQ-### / W-### ids), `steps` (each `id`, `text`, `status` todo / doing / done /
dropped, `refs`) and `changes` (each `date`, `was`, `now`, `why`). A change to a plan is a new `changes` entry, never a
silent rewrite. The status page reads step statuses for a plan's percent done.

This project's goal contracts still live in `docs/process/` (`goal-chain.md`); no plan record exists yet.
Created by the kit 1.10.1 upgrade (PR #426): the changelog says the kit ships this README, but the upgrade did not
deliver one, so the project wrote it.
