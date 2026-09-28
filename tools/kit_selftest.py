#!/usr/bin/env python3
"""kit_selftest.py — a project's one-command kit self-test (OD-23 item 1), shipped into every
project's tools/ so its own CI can run it without the Factory repo.

Checks, each printing one line, exit 1 if ANY check fails:

  (a) every hook script path wired in the settings file (built from the kit wiring + the project
      addendum, via tools/kit_settings.py — never re-implemented) exists on disk.
  (b) the kit and project rule folders hold only rule files (every `.md` carries a `# Scope:` line
      somewhere in it), and the agents folder holds only agent files (frontmatter with a `name:`
      key).
  (c) context budget: total LF-normalized bytes of every rule file with NO `paths:` frontmatter
      (i.e. always loaded, never path-scoped) across both rule folders, printed, and compared
      against the cap in `.claude/kit/budget.json` (`{"always_loaded_max_bytes": N, "why": "..."}`)
      — over the cap fails this check.
  (d) for each wired kit guard with a known blocking input (GUARD_PROBES below), the guard script
      is piped that input and must exit non-zero (block); a guard named in the project's opt-outs
      file is skipped, printing its reason instead.
  (e) the kit release notes file is present and its top (first) version heading matches the
      project's KIT_VERSION file.
  (f) the project root carries a session entry point: `CLAUDE.md` and `docs/HANDOVER.md`, each a
      real, non-whitespace file (never a directory of the same name, never a 0-byte or
      whitespace-only placeholder) —
      naming whichever is missing.

Usage:
    python tools/kit_selftest.py [ROOT]
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit_settings  # noqa: E402  (the one place the settings file is built)

_CLAUDE_DIR_NAME = "." + "claude"
_OPTOUTS_REL = f"{_CLAUDE_DIR_NAME}/project/optouts.json"
_BUDGET_REL = f"{_CLAUDE_DIR_NAME}/kit/budget.json"
_CHANGELOG_REL = f"{_CLAUDE_DIR_NAME}/kit/CHANGELOG.md"
_CLAUDE_MD_REL = "CLAUDE.md"
_HANDOVER_REL = "docs/HANDOVER.md"

RULE_DIRS = ("rules/kit", "rules/project")
AGENTS_DIR = "agents"

_SCOPE_RE = re.compile(r"^#\s*Scope:", re.MULTILINE)
_VERSION_HEADING_RE = re.compile(r"^##\s+([0-9][^\s]*)", re.MULTILINE)

# (guard script path relative to .claude/hooks/, stdin JSON it must block, description)
# Kept small and honest: only guards whose block decision is DETERMINISTIC from the stdin payload
# alone are listed (git_discard_uncommitted_guard.py also needs an actually-dirty git tree at the
# payload's cwd, which a self-test must never manufacture inside a real project's checkout, so it
# is not probed here — it stays a wired-but-unchecked-by-(d) guard).
GUARD_PROBES = [
    (
        "git_hook_bypass_guard.py",
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git commit --no-verify -m x"},
        },
        "a --no-verify commit",
    ),
    (
        "agent_model_required.py",
        {
            "tool_name": "Task",
            "tool_input": {"description": "x", "prompt": "x"},
        },
        "an Agent/Task dispatch with no model",
    ),
]


class SelfTestFailure(Exception):
    pass


def _fail(msg: str, failures: list[str]) -> None:
    print(f"FAIL: {msg}")
    failures.append(msg)


def check_wired_scripts_exist(root: Path, failures: list[str]) -> None:
    try:
        settings = kit_settings.build(root)
    except kit_settings.BadInput as exc:
        _fail(f"(a) could not build settings to check wired scripts: {exc}", failures)
        return
    scripts: set[str] = set()
    for entries in settings.get("hooks", {}).values():
        for e in entries:
            for h in e.get("hooks", []):
                s = kit_settings.hook_script(h.get("command", ""))
                if s:
                    scripts.add(s)
    missing = sorted(s for s in scripts if not (root / s).exists())
    if missing:
        _fail(f"(a) wired hook script(s) missing on disk: {', '.join(missing)}", failures)
    else:
        print(f"ok: (a) {len(scripts)} wired hook script(s) present")


def check_folder_purity(root: Path, failures: list[str]) -> None:
    problems: list[str] = []
    for rel in RULE_DIRS:
        d = root / _CLAUDE_DIR_NAME / rel
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*")):
            if f.is_dir():
                continue
            if f.name == ".gitkeep":
                continue  # a placeholder for an otherwise-empty tracked folder, not a rule file
            if f.suffix != ".md":
                problems.append(f"{f.relative_to(root).as_posix()}: not a rule file (.md)")
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            if not _SCOPE_RE.search(text):
                problems.append(f"{f.relative_to(root).as_posix()}: missing a '# Scope:' line")

    agents_dir = root / _CLAUDE_DIR_NAME / AGENTS_DIR
    if agents_dir.is_dir():
        for f in sorted(agents_dir.iterdir()):
            if f.is_dir():
                continue
            if f.suffix != ".md":
                continue  # PROVENANCE.md etc. are not agent files and carry no frontmatter contract
            text = f.read_text(encoding="utf-8", errors="replace")
            if not re.match(r"^---\s*\n.*?\bname:\s*\S+", text, re.DOTALL):
                problems.append(f"{f.relative_to(root).as_posix()}: agent file missing 'name:' frontmatter")

    if problems:
        for p in problems:
            _fail(f"(b) {p}", failures)
    else:
        print("ok: (b) rule and agent folders hold only well-formed files")


def _has_paths_frontmatter(text: str) -> bool:
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    if end == -1:
        return False
    frontmatter = text[3:end]
    return bool(re.search(r"^\s*paths\s*:", frontmatter, re.MULTILINE))


def check_context_budget(root: Path, failures: list[str]) -> None:
    budget_path = root / _BUDGET_REL
    if not budget_path.exists():
        _fail(f"(c) budget cap file missing: {_BUDGET_REL}", failures)
        return
    try:
        budget = json.loads(budget_path.read_text(encoding="utf-8"))
        cap = int(budget["always_loaded_max_bytes"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        _fail(f"(c) {_BUDGET_REL} is invalid: {exc}", failures)
        return

    total = 0
    for rel in RULE_DIRS:
        d = root / _CLAUDE_DIR_NAME / rel
        if not d.is_dir():
            continue
        for f in sorted(d.rglob("*.md")):
            text = f.read_bytes().replace(b"\r\n", b"\n")
            if _has_paths_frontmatter(text.decode("utf-8", errors="replace")):
                continue  # path-scoped: never always-loaded
            total += len(text)

    print(f"context budget: {total} bytes always-loaded (cap {cap})")
    if total > cap:
        _fail(f"(c) always-loaded rule bytes {total} exceed cap {cap}", failures)
    else:
        print("ok: (c) within context budget")


def _load_optout_reasons(root: Path) -> dict[str, str]:
    path = root / _OPTOUTS_REL
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    if isinstance(data, list):
        for e in data:
            if isinstance(e, dict) and isinstance(e.get("piece"), str):
                out[e["piece"]] = e.get("reason", "")
    return out


def check_guards_block(root: Path, failures: list[str]) -> None:
    bash = shutil.which("bash")
    if not bash:
        print("skip: (d) no bash on PATH — guard probes not run")
        return
    optouts = _load_optout_reasons(root)
    checked = 0
    for script_name, payload, desc in GUARD_PROBES:
        piece = f"{_CLAUDE_DIR_NAME}/hooks/{script_name}"
        if piece in optouts:
            print(f"skip: (d) {script_name} opted out ({optouts[piece]})")
            continue
        script_path = root / _CLAUDE_DIR_NAME / "hooks" / script_name
        if not script_path.exists():
            print(f"skip: (d) {script_name} not wired in this project")
            continue
        result = subprocess.run(
            [bash, "-c", f'python "{script_path}"'],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            cwd=root,
        )
        checked += 1
        # A kit guard blocks with exit code 2 and nothing else: Claude Code treats any other non-zero
        # exit (a crash, exit 1) as a non-blocking error and runs the tool anyway, and a JSON
        # permissionDecision deny at exit 0 is overridden by another hook's allow (finding
        # json-deny-overridden-by-another-hooks-allow). Either would be a false "blocks".
        blocked = result.returncode == 2
        if not blocked:
            _fail(f"(d) {script_name} did not block {desc} (exit {result.returncode})", failures)
        else:
            print(f"ok: (d) {script_name} blocks {desc} (exit {result.returncode})")
    if checked == 0 and not failures:
        print("ok: (d) no wired guard had a probe to run")


def check_changelog(root: Path, failures: list[str]) -> None:
    changelog = root / _CHANGELOG_REL
    version_file = root / "KIT_VERSION"
    if not changelog.exists():
        _fail(f"(e) {_CHANGELOG_REL} is missing", failures)
        return
    if not version_file.exists():
        _fail("(e) KIT_VERSION is missing", failures)
        return
    text = changelog.read_text(encoding="utf-8")
    m = _VERSION_HEADING_RE.search(text)
    if not m:
        _fail(f"(e) {_CHANGELOG_REL} has no version heading ('## <version> ...')", failures)
        return
    top_version = m.group(1)
    current_version = version_file.read_text(encoding="utf-8").strip()
    if top_version != current_version:
        _fail(
            f"(e) {_CHANGELOG_REL} top version '{top_version}' != KIT_VERSION '{current_version}'",
            failures,
        )
    else:
        print(f"ok: (e) release notes top entry matches KIT_VERSION ({current_version})")


def check_session_entry_point(root: Path, failures: list[str]) -> None:
    missing = []
    for rel in (_CLAUDE_MD_REL, _HANDOVER_REL):
        path = root / rel
        if not path.is_file():
            missing.append(rel)
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            missing.append(rel)
            continue
        if not text.strip():  # 0 bytes AND whitespace-only both count as empty
            missing.append(rel)
    if missing:
        _fail(f"(f) session entry point missing or empty: {', '.join(missing)}", failures)
    else:
        print("ok: (f) session entry point present")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]) if argv else Path(".")

    failures: list[str] = []
    check_wired_scripts_exist(root, failures)
    check_folder_purity(root, failures)
    check_context_budget(root, failures)
    check_guards_block(root, failures)
    check_changelog(root, failures)
    check_session_entry_point(root, failures)

    if failures:
        print(f"kit_selftest: {len(failures)} check(s) failed")
        return 1
    print("kit_selftest: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
