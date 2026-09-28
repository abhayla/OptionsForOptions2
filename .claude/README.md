# .claude

Every file here has one owner (OD-22), recorded per file in the project's lock by the copier:

- **kit** (Factory-owned, locked; never edit or delete, only a kit upgrade replaces them): `rules/kit/`, `hooks/`, `agents/`, `skills/deliver/`, `kit/` (`settings.kit.json` = the kit's hook wiring, provenance, `CHANGELOG.md`), this README.
- **project** (yours): `rules/project/` for new rules (add or tighten, never loosen a kit rule); `project/hooks.json` for extra hooks and permissions; `project/optouts.json` to opt out of a kit hook, one `{"piece": "<kit path>", "reason": "<why>"}` line each — never by deleting it.
- **generated** (never edit by hand): the settings file Claude Code reads, written by `python tools/kit_settings.py .` = kit wiring + your addendum appended (kit entries never replaced) − opt-outs; CI runs it with `--check`.
- **owner** (only the human owner edits it; Claude is blocked, and the drift check reports any change loudly): the production seatbelt's config file in the project's hidden Factory folder.
- The addendum may add or tighten, never loosen: `deny`/`ask` rules are free; each `allow` rule is `{"rule": "Tool(specifier)", "reason": "<why, 10+ chars>"}` and never blanket (`Bash(*)`, `Edit`); hook entries must have the documented shape and a known event; opt-out reasons are 10+ characters, and the seatbelt scripts and the hook-presence check cannot be opted out.
- Known remaining risk: when two hooks return different decisions for one tool call, Claude Code's precedence was not confirmed for this kit, so a project hook could still approve or rewrite a tool call's input after a kit guard let it through. Review project hooks with that in mind.
- To change hook wiring: edit `project/hooks.json` or `project/optouts.json`, then regenerate.
- Kit rules and project rules share one always-loaded budget (at most 5 files, under the byte cap).
- Kit changes arrive only by a Factory kit upgrade; see `kit/CHANGELOG.md`.

## Hook wiring

`hooks/` carries the kit's hook scripts (see `hooks/PROVENANCE.md`) and their SessionStart presence
check. Every wired command does nothing when its script file is missing, and the presence check names
any wired script that is gone. With the production seatbelt installed (copier `--seatbelt`), the
generator also adds permission-deny rules protecting the seatbelt's own folder.

## Evidence-claim guard starts log-only

`evidence_claim_guard.py` (the Stop hook that checks a turn's done/pass/green claims against an
evidence table) ships wired **log-only**: a claim miss is appended to its log file, never blocked.
Read that log for about 3 days on a real project; once it reads clean, turn blocking on without
touching kit files: opt out of `.claude/hooks/evidence_claim_guard.py` in `project/optouts.json`
(reason: "replaced by the blocking form in project/hooks.json") and add a Stop hook in
`project/hooks.json` running the same script with `EVIDENCE_CLAIM_BLOCK=1` set, then regenerate.

## Tracked under a global ignore

The project's own `.gitignore` re-includes this whole dotfolder (`!.claude/`, `!**/.claude/`), because a
user-level git ignore that excludes it project-wide would otherwise leave a fresh `git add -A` silently
dropping the kit.
