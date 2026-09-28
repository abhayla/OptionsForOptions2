#!/usr/bin/env python3
"""prod-gate recorder: UserPromptSubmit hook.

Writes a single-use production authorization record when, and only when, the
OWNER typed `AUTHORIZE PROD R-###` on its own line in an attended CLI session:

  * env CLAUDE_CODE_SESSION_ATTENDED == "1"   (Claude-launched children see "0")
  * env CLAUDE_CODE_ENTRYPOINT == "cli"       (children see "sdk-cli")
  * no agent_id in the hook input             (never from a subagent)

Record: <state dir>/authorizations/<YYYY-MM-DD>-<release>.json, where the state dir is
        %LOCALAPPDATA%/claude-factory/<project-id> (Windows) or
        $XDG_STATE_HOME/claude-factory/<project-id> - outside the repo, so git cannot touch it.
        production.records_dir overrides it (relative to the project root).
        {release, date, session_id, prompt_id, created_at, used: false}

No deploy_patterns: prints "production gate NOT CONFIGURED for <project>" once per session.
A lower-case phrase gets "phrase must be upper case: AUTHORIZE PROD R-###".

Never blocks the prompt. Exits 0 on every path, including errors.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _common as c  # noqa: E402


def _emit(msg: str) -> None:
    print(json.dumps({
        "systemMessage": msg,
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": msg},
    }))


def is_attended(data: dict) -> tuple[bool, str]:
    if os.environ.get("CLAUDE_CODE_SESSION_ATTENDED") != "1":
        return False, "session is not attended (CLAUDE_CODE_SESSION_ATTENDED != 1)"
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") != "cli":
        return False, "entrypoint is not the interactive CLI (CLAUDE_CODE_ENTRYPOINT != cli)"
    if data.get("agent_id") or data.get("agent_type"):
        return False, "message came from a subagent"
    if data.get("hook_event_name") not in (None, "UserPromptSubmit"):
        return False, "not a UserPromptSubmit event"
    return True, ""


def not_configured_first_time(cfg: dict, data: dict) -> bool:
    """True once per session (per project): the NOT CONFIGURED notice is not repeated."""
    sid = str(data.get("session_id") or "no-session")
    path = os.path.join(cfg["_state"], "not-configured-notice.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            seen = json.load(fh)
    except (OSError, ValueError):
        seen = {}
    if not isinstance(seen, dict):
        seen = {}
    if sid in seen:
        return False
    seen[sid] = c.now_iso()
    try:
        c.write_json_atomic(path, dict(list(seen.items())[-200:]))
    except OSError:
        pass
    return True


def main() -> int:
    data = c.read_stdin_json()
    prompt = data.get("prompt")
    if not isinstance(prompt, str):
        return 0
    root = c.find_project_root(data.get("cwd") or os.getcwd())
    if root is None:
        return 0  # project not governed
    cfg = c.load_config(root)
    try:
        c.mark_governed(root)
    except Exception:
        pass
    notice = ""
    if not cfg["_compiled"] and not_configured_first_time(cfg, data):
        notice = (f"prod-gate: production gate NOT CONFIGURED for {root} - authority.yaml has no "
                  "deploy_patterns, so shell deploy commands are NOT gated. Declare the exact "
                  "deploy form in deploy_patterns (shown once per session). ")
    releases = c.phrase_line_regex(cfg["authorize_phrase"]).findall(prompt)
    if not releases:
        if c.phrase_line_regex(cfg["authorize_phrase"], ignore_case=True).search(prompt):
            notice += (f"prod-gate: phrase must be upper case: '{cfg['authorize_phrase']} R-###' "
                       "(R upper case too); no authorization recorded.")
        elif cfg["authorize_phrase"].lower() in prompt.lower():
            notice += (f"prod-gate: '{cfg['authorize_phrase']}' seen but not on its own line as "
                       f"'{cfg['authorize_phrase']} R-###'; no authorization recorded.")
        if notice:
            _emit(notice.strip())
        return 0
    if not cfg["_compiled"] and not cfg["_deploy_tools"]:
        _emit((notice + "prod-gate: NOT CONFIGURED - no deploy_patterns and no deploy_tools, so "
               "there is nothing to authorize; no authorization recorded.").strip())
        return 0
    ok, why = is_attended(data)
    if not ok:
        _emit(f"prod-gate: production authorization REFUSED ({why}). "
              "Only the owner typing in an attended session can authorize a production deploy.")
        return 0
    date = c.today()
    done = []
    for release in dict.fromkeys(releases):
        path = c.record_path(cfg, date, release)
        if os.path.exists(path):
            done.append(f"{release} (already recorded today; not reset)")
            continue
        c.write_json_atomic(path, {
            "release": release,
            "date": date,
            "session_id": data.get("session_id"),
            "prompt_id": data.get("prompt_id"),
            "created_at": c.now_iso(),
            "used": False,
        })
        done.append(release)
    _emit(notice + f"prod-gate: production authorization recorded for {', '.join(done)} on {date} "
          "(single use, today only).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never block the owner's prompt
        print(f"prod-gate recorder error (no record written): {exc}", file=sys.stderr)
        sys.exit(0)
