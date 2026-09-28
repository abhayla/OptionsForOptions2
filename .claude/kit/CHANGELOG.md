# Kit release notes

One entry per kit version (OD-23). The version in force is the project's `KIT_VERSION` file; a kit upgrade
replaces kit-owned files and adds an entry here.

## 1.2.0 — intake kit and session entry point (finding new-project-has-no-session-entry-point)

1. RCA: `new_project.py` shipped a project with no `CLAUDE.md` and no `docs/HANDOVER.md` at its root, and no
   reusable way to turn an owner's idea into decisions — two of two real copier projects
   (`factory-testbed`, `dashcam-youtube`) were built without either, so a fresh session in a new project had
   no recorded purpose, no decisions to read first, and no next step, and had to be told everything again by
   whoever started it.
2. Fix: a new `intake` skill (`.claude/skills/intake/`, kit-owned) takes the owner's idea, asks one question
   per turn with a `Spec basis:` line and a recommendation, records each answer as the next
   `spec/decisions/ADR-###.md` in the same turn, stops asking what a real-input core proof can measure, then
   fills the project's `CLAUDE.md` and `docs/HANDOVER.md` before writing requirements. The template now ships
   project-owned `CLAUDE.md` and `docs/HANDOVER.md` skeletons (`<fill in>` placeholders); `new_project.py`
   writes both with owner `project` in the lock, same as any other project-owned file.
3. `kit_selftest.py` gained check (f): it fails, naming the file, when `CLAUDE.md` or `docs/HANDOVER.md` is
   missing or empty at the project root, and passes once both exist — the check that makes the skeletons a
   requirement of every project, not just a convention.
4. `kit_upgrade.py` never creates or touches either file: both are project-owned (the default owner for any
   path not listed in `new_project.py`'s `OWNERSHIP` table), so an upgrade only ever replaces kit-owned files.
   A project made before 1.2.0 without these two files (the M3 testbed) fails check (f) after upgrading until
   it adds them; that is the check doing its job, not a regression.
5. Fix round 1 (Tier A review, MAJOR): the template's own `CLAUDE.md` was auto-loaded by Claude Code into a
   Factory session working on this repo (any `CLAUDE.md` on the path from cwd up to the drive root is
   auto-loaded), contradicting the real Factory `CLAUDE.md`. The template file is now `CLAUDE.md.tmpl`;
   `new_project.py`'s copier writes it into every project as `CLAUDE.md` (lock `path: CLAUDE.md`,
   `owner: project`, `source:` the `.tmpl` path) — the project still gets a plain `CLAUDE.md`, only the
   Factory's own tracked copy is renamed.
6. Fix round 1 (Tier A review, MAJOR, pre-existing, fixed here because W-004's core proof depends on it):
   `kit_live_proof.py` built its throwaway project under `$TEMP`, which sits under the user's home folder, so
   Claude Code's ancestor-directory memory walk loaded `~/.claude/CLAUDE.md` and `~/.claude/rules/*.md` as if
   they were the project's own memory (mislabeled `memory_type: Project`), making the "no user-level
   contribution" check pass falsely. The live-proof project now builds under a folder on the Factory repo's
   own drive, outside any git checkout and outside the user's home folder (`--root` overrides it), and a new
   hard check fails naming any `InstructionsLoaded` `file_path` that resolves outside the project folder at
   all — proven offline with a fake event log carrying such a path.
7. Fix round 2 (Tier A review, MAJOR (k)): the round-1 fix for item 6 shipped without a mutation test —
   reverting the default root or the project path to a bare `tempfile.mkdtemp()`/`tempfile.gettempdir()`
   stayed green. Added unit tests asserting the default root is neither under `Path.home()` nor inside a git
   checkout, and that the run's project path resolves under that root (killed).
8. Fix round 2 (MINOR, real cost): live-proof cleanup used `shutil.rmtree(..., ignore_errors=True)`, which
   silently left every read-only `.git` object file behind (126 per run, measured, at the drive root). Cleanup
   now clears the read-only bit and retries on failure (`onexc`/`onerror`), removes the run folder itself, and
   prints a `WARNING` naming the path on a genuine failure instead of staying silent.
9. Fix round 2 (MINOR): `kit_selftest.py` check (f) now strips whitespace before the emptiness test, so a
   whitespace-only `CLAUDE.md` or `docs/HANDOVER.md` counts as missing, same as 0 bytes.
10. Fix round 2 (MINOR): on non-Windows, the default live-proof root is `/tmp/kit-live-proof-tmp` (writable,
    outside the home folder), not the unwritable-by-normal-users `/kit-live-proof-tmp`; a non-writable default
    root now refuses with a message pointing at `--root` instead of silently falling back under the home
    folder.

## 1.1.4 — guards split shell commands only outside quotes (finding segment-split-before-quotes)

1. RCA: the three git guards' shared `_git_shell.py` and `kit-file-guard`'s own segment split both matched a
   separator regex (`&&`/`||`/`;`/`|`/`&`/`{`/`}`/`(`/`)`/newline) over the raw command TEXT before any quote was
   recognized, so a separator character INSIDE a single- or double-quoted argument (a `-m` commit message, a
   test loop's quoted case string) split the string in two and the quoted words on either side were read as
   their own command segments — a quoted bypass word could reach the parser as if it were a real, separate
   command, and (in `kit-file-guard`) a harmless quoted decoy could make an otherwise read-only command look
   like a real write and get denied instead.
2. Fix: `_git_shell.split_segments`/`split_segments_with_start` and `kit-file-guard`'s local segment scanner now
   walk the command character by character and only treat a separator as a boundary while it is NOT inside an
   open quote; an unterminated quote fails safe (the remainder of the command is kept as one segment).
   `git-stash-worktree-guard` was updated to call the shared `split_segments_with_start` instead of the module's
   former private `_SPLIT_RE` attribute.
3. Swept `full-suite-guard` and `pipe-exit-guard`: both still split on raw separator text before tokenizing, but
   neither is wired into this template yet — left as-is, to be fixed at the sweep that adopts them.

## 1.1.3 — git guards catch every spelling (issue #14); budget guard checks the agent's turn limit

1. `git-discard-uncommitted-guard`, `git-hook-bypass-guard`, `git-stash-worktree-guard`: the git program is now
   matched as `git`, `git.exe`, or any path ending in `/git(.exe)` or `\git(.exe)`, case-insensitively; `&` (the
   PowerShell call operator), `{`, `}`, `(`, `)` are segment boundaries, and a backtick line-continuation is
   collapsed before scanning.
2. `git-hook-bypass-guard` also blocks `-n` on `commit`/`merge` (the short form of `--no-verify`), leaving it
   unblocked on `push`/`clean` where `-n` means `--dry-run`.
3. `git-discard-uncommitted-guard` now catches a whole-tree `git checkout .` with no `--` separator, the same way
   it already caught `git restore .`.
4. `agent-budget-required` refuses a `Budget: N min, M tool calls` line whose `M` exceeds 80% of the target
   agent's own `maxTurns` (read from `.claude/agents/<subagent_type>.md`), naming both numbers; an unknown agent
   or a file with no `maxTurns` skips this check.
5. Tier A round 2 (same issue #14 review, RCA: raw-text regexes let a quoted program path, bundled short flags,
   an unambiguous long-option prefix, a mixed-case config key or an env-var config mechanism slip through): the
   three git guards now tokenize each shell segment into real words (shared `_git_shell.py`) and reason about
   PROGRAM + ARGV instead of scanning text. `git-hook-bypass-guard` now also blocks any unambiguous prefix of
   `--no-verify` (from `--no-v` up), `-n` bundled into commit's short flags (`-nm`, `-anm`) — commit only, since
   merge's `-n` means `--no-stat`, not a bypass — a case-insensitive `-c core.hooksPath=`, and
   `GIT_CONFIG_PARAMETERS`/`GIT_CONFIG_KEY_*` setting `core.hooksPath`. `git-discard-uncommitted-guard` now also
   blocks `git checkout -f`/`--force` with no explicit path (discards every dirty file, like `checkout -- .`).
   `git-stash-worktree-guard` now treats every stash flag except `-h`/`--help` as a mutating push option (`-u`,
   `-m wip` used to be misread as read-only) and recognizes `Set-Location`/`pushd`/`chdir` as `cd`.
6. Tier A round 3 (same review, sweep): `git-stash-worktree-guard` kept its own quote-stripping/regex program
   match instead of going through the shared `_git_shell.py`, so a quoted program path with spaces
   (`& "<full path to git.exe>" stash`) was allowed inside a linked worktree; the program is now
   identified only via `_git_shell.py`, matching the other two git guards.

## 1.1.2 — the self-test counts a guard as blocking only on exit 2

1. `kit_selftest.py` check (d) accepts only exit code 2 as a block. A crash (exit 1) is a non-blocking error to
   Claude Code, and a JSON deny at exit 0 can be overridden by another hook's allow; both used to read as "blocks".

## 1.1.1 — kit-file-guard lets kit tools run; frontmatter split fixed; caches ignored; merge and upgrade reports

1. kit-file-guard: a shell segment running a kit tool (`python tools/<name>.py`) is no longer treated as a
   write to it; write forms into `tools/` still refuse.
2. `factory_lint.py` and `trace_check.py` split frontmatter only on a line that is exactly `---`, never on a
   `---` inside a quoted value.
3. The copier's `.gitignore` now ignores `__pycache__/` and `*.pyc`, so a fresh project's `git status` stays
   clean after running the shipped tools.
4. `merge_when_green.py` re-reads the PR state after `gh pr merge`; MERGED is reported as success even if
   local branch cleanup fails.
5. `kit_upgrade.py`'s summary reports "changed" and "identical" kit files separately, and skips rewriting an
   identical file.
6. The deliver skill: a headless (`claude -p`) run merges through `merge_when_green.py` in the foreground.

## 1.1.0 — kit ships merge_when_green.py (refuses conflicted PRs; zero checks = wait); the deliver skill merges only through it

## 1.0.0 — first kit release

Fixes made during M3, before the first release:

- The git guards also check PowerShell commands, not only Bash.
- Both agent guards also check the `Task` tool, not only `Agent`.
- The hook presence check also reads the local settings file.
- The production seatbelt is opt-in (the copier's `--seatbelt`); without it every call is allowed.
- The evidence guard starts log-only; the project turns blocking on after reading its log.
- The copier refuses to overwrite files, to write through a link, into the home folder or a drive root, and
  records a dirty template in the lock.
- The drift check confines every lock path to its base folder.
- Provenance hashes are taken over LF-normalized content, so Windows and Linux checkouts agree.
- The banned-term scan covers every text file in the kit; agent-guard messages are generic.
- OD-22 layout: kit rules in `.claude/rules/kit/`, project rules in `.claude/rules/project/`; the settings
  file is generated by `tools/kit_settings.py` from the kit wiring (`.claude/kit/settings.kit.json`) plus the
  project addendum (`.claude/project/hooks.json`), minus opt-outs with a reason (`.claude/project/optouts.json`).
