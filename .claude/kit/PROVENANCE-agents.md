# Agent provenance

| Agent | Source | Source version | What changed and why |
|---|---|---|---|
| `builder.md` | a legacy project's `builder` agent definition | 1.0.0 | Already generic (work item, requirement and evidence paths matched this template's layout: `work/W-###.md`, `spec/requirements/REQ-###.md`, `evidence/`). Copied unchanged, then (M3 integration) `maxTurns` 60 -> 100 and rule 7 added: commit after each brief item and stop at 80% of the budget, because three builders were cut off at the turn limit with uncommitted work. |
| `verifier.md` | a legacy project's `verifier` agent definition | 1.0.0 | Already generic and read-only (no Edit/Write/MultiEdit/NotebookEdit in its tool list). Copied unchanged, then (kit 1.4.0, REQ-015, OD-47) rule 5 no longer grants writing evidence files and the block format is returned in the reply only, with `requirement:` and `ac_fp:` lines: the old rule 5 contradicted the read-only role and verifiers wrote evidence through their shell four times (finding agent-definition-contradicts-its-role). |
| `Explore.md` | the built-in read-only search agent's role (no source file) | new in 1.7.0 | New project-level agent that overrides the built-in one: model haiku, effort medium (class `lookup` of `.claude/kit/model-routing.yaml`), read-only tools only, `maxTurns` 40. Written for this kit; it states its own model and effort because the built-in one follows the session's model. |

Kit 1.7.0 (REQ-051): `builder.md` gained `effort: medium` and `verifier.md` gained `effort: high`, the effort of their classes in `.claude/kit/model-routing.yaml`. Effort defaults differ silently per model (one model family defaults to high, others to medium), so every agent file states its own. A test fails an agent whose model or effort differs from its class.
