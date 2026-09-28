# Skill provenance

| Skill | Source | Source version | What changed and why |
|---|---|---|---|
| `SKILL.md` | the Factory's own intake of a real project, `abhayla/dashcam-youtube` (ADR-001, ADR-002, ADR-003, ADR-004, ADR-005, 2026-09-28) | n/a (first kit release of this skill, 1.2.0) | Generalized from the one-question-per-turn intake actually run for that project: idea in the owner's words, `*Sync-check:*` question with a `Spec basis:` line and a recommended option, an `ADR-###.md` written the same turn (e.g. ADR-001 "Version 1 produces one full trip edit per trip", `source: "Owner intake answer 2026-09-28 (Sync-check 1): 'Full trip edit (Recommended)'"`), stopping to measure real dashcam files instead of asking what they could show, then `CLAUDE.md` / `docs/HANDOVER.md` filled from the decisions, then requirements. Removed every dashcam/trip/video-specific word; kept the order of steps and the shape of each artifact only. |
