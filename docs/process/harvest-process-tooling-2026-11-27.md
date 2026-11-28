# Harvest: process tooling that should become kit files (27 Nov 2026, Lane P1)

For the Startup-Factory kit. The issue is not filed; the coordinator files it.

1. `.claude/skills/lanes/check_brief.py` and `brief-template.md`. Any project that runs parallel cloud sessions writes a
   brief per lane, and 18 briefs here each repeated about 500 words of the same rules. The template makes the first
   line a pointer to one "Standing rules" section, and the checker fails a brief that lacks a Budget line, branch and
   base, file ownership, a queue, or a core and proof, or that repeats the rules at length. It is pure Python, so it
   fits the kit's no-dependency rule. The project-specific rule text stays in each project's own lanes skill.

2. `.claude/skills/owner-decision/` (SKILL.md, `add_decision_row.py`, `spec_search.py`). Every project with an owner
   and a decision log repeats the same six steps for each answer (search the spec, ask one question with a spec basis,
   write the row, tell the lane, commit, queue the push); 17 answers cost 68 manual steps here. The row tool takes
   the house style from the file it edits (the width and the last point number), so it needs no per-project setting.
   `spec_search.py` is the line-level companion to `tools/spec_similar.py` (which ranks whole sentences).

3. `scripts/hooks/friction_log_due.py` (Stop hook). The friction rule's counter had no check. The hook reminds once, at
   the end of a session over 60 minutes with no friction row written, never blocks twice, honours `stop_hook_active`
   and fails open. A kit rule that asks sessions to log friction needs this check to be real.

4. A tools-present check and a cloud-services start (Lane G2's `tools_present.py` and `cloud_services.sh`, wired by a
   SessionStart line guarded by `CLAUDE_CODE_REMOTE=true`). Every fresh cloud container lost a run to a missing tool
   or built PostgreSQL by hand. The SessionStart line belongs in the kit's generated hook set with the guard, so a
   project's own start-up runs only in the cloud.
