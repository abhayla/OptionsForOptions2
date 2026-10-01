# Agent provenance

| Agent | Source | Source version | What changed and why |
|---|---|---|---|
| `builder.md` | a legacy project's `builder` agent definition | 1.0.0 | Already generic (work item, requirement and evidence paths matched this template's layout: `work/W-###.md`, `spec/requirements/REQ-###.md`, `evidence/`). Copied unchanged, then (M3 integration) `maxTurns` 60 -> 100 and rule 7 added: commit after each brief item and stop at 80% of the budget, because three builders were cut off at the turn limit with uncommitted work. |
| `verifier.md` | a legacy project's `verifier` agent definition | 1.0.0 | Already generic and read-only (no Edit/Write/MultiEdit/NotebookEdit in its tool list). Copied unchanged, then (kit 1.4.0, REQ-015, OD-47) rule 5 no longer grants writing evidence files and the block format is returned in the reply only, with `requirement:` and `ac_fp:` lines: the old rule 5 contradicted the read-only role and verifiers wrote evidence through their shell four times (finding agent-definition-contradicts-its-role). |
