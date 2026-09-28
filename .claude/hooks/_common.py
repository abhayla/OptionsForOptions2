"""Shared helpers for the prod-gate hooks (recorder.py, gate.py).

Stdlib + PyYAML only. Nothing here reads the environment for test knobs: the
date is always the real local date, so no variable can be set to move "today".
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys

CONFIG_REL = os.path.join(".factory", "authority.yaml")
DEFAULT_PHRASE = "AUTHORIZE PROD"
RELEASE_RE = r"R-\d{3,}"
DEFAULT_DEPLOY_TOOLS = r"mcp__.*(deploy|restart|recreate|restore|rollback|publish|dispatch|run_?workflow).*"
DEFAULTS = {
    "authorize_phrase": DEFAULT_PHRASE,
    "deploy_patterns": [],
    "deploy_keywords": [],
    "max_deploys_per_day": 1,
    "records_dir": None,   # None = <state dir>/authorizations (outside the project tree)
    "ledger": None,        # None = <state dir>/deploy-ledger.jsonl
    "protected_paths": [],
    # tool_name regexes (fullmatch, case-insensitive) for MCP/tool calls that deploy or restart
    # production; each needs an unused same-day record and counts toward max_deploys_per_day
    "deploy_tools": [DEFAULT_DEPLOY_TOOLS],
}
HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_APP = "claude-factory"
GOVERNED_MARK = "governed.json"


def state_base() -> str:
    """Per-user state root, outside every project tree so git in a repo cannot touch it."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_STATE_HOME") or os.path.join(os.path.expanduser("~"), ".local", "state")
    return os.path.join(base, STATE_APP)


def project_id(root: str) -> str:
    import hashlib
    key = os.path.normcase(os.path.realpath(os.path.abspath(root)))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def state_dir(root: str) -> str:
    return os.path.join(state_base(), project_id(root))


def mark_governed(root: str) -> None:
    """Remember that `root` is governed, so a vanished authority.yaml fails closed."""
    path = os.path.join(state_dir(root), GOVERNED_MARK)
    if not os.path.isfile(path):
        write_json_atomic(path, {"root": os.path.abspath(root), "since": now_iso()})


def find_governed_marker(start: str | None) -> str | None:
    """Walk up from `start`; return a directory once governed whose authority.yaml is gone."""
    if not start:
        return None
    cur = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(state_dir(cur), GOVERNED_MARK)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


class ConfigError(Exception):
    """authority.yaml exists but cannot be read, parsed, or validated."""


def read_stdin_json() -> dict:
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        raise ValueError("hook input is not a JSON object")
    return data


def today() -> str:
    return _dt.date.today().isoformat()


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def find_project_root(start: str | None) -> str | None:
    """Walk up from `start` to the first directory holding .factory/authority.yaml."""
    if not start:
        return None
    cur = os.path.abspath(start)
    while True:
        if os.path.isfile(os.path.join(cur, CONFIG_REL)):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return None
        cur = parent


def load_config(root: str) -> dict:
    path = os.path.join(root, CONFIG_REL)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    try:
        import yaml  # type: ignore
    except Exception:  # PyYAML missing: accept JSON (a YAML subset) only
        try:
            doc = json.loads(text)
        except ValueError as exc:
            raise ConfigError("PyYAML is not installed and authority.yaml is not JSON") from exc
    else:
        try:
            doc = yaml.safe_load(text)
        except Exception as exc:
            raise ConfigError(f"authority.yaml is not valid YAML: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("production"), dict):
        raise ConfigError("authority.yaml must be a mapping with a 'production' mapping")
    prod = dict(DEFAULTS)
    prod.update(doc["production"])
    if not isinstance(prod["deploy_patterns"], list) or not all(
        isinstance(p, str) for p in prod["deploy_patterns"]
    ):
        raise ConfigError("production.deploy_patterns must be a list of regex strings")
    compiled = []
    for pat in prod["deploy_patterns"]:
        try:
            rx = re.compile(pat, re.IGNORECASE)
        except re.error as exc:
            raise ConfigError(f"bad deploy pattern {pat!r}: {exc}") from exc
        if "release" not in rx.groupindex:
            raise ConfigError(f"deploy pattern {pat!r} has no (?P<release>...) group")
        compiled.append(rx)
    prod["_compiled"] = compiled
    for key in ("deploy_keywords", "protected_paths", "deploy_tools"):
        if not isinstance(prod[key], list) or not all(isinstance(k, str) for k in prod[key]):
            raise ConfigError(f"production.{key} must be a list of strings")
    tools = []
    for pat in prod["deploy_tools"]:
        try:
            tools.append(re.compile(pat, re.IGNORECASE))
        except re.error as exc:
            raise ConfigError(f"bad deploy_tools pattern {pat!r}: {exc}") from exc
    prod["_deploy_tools"] = tools
    try:
        prod["max_deploys_per_day"] = int(prod["max_deploys_per_day"])
    except (TypeError, ValueError) as exc:
        raise ConfigError("production.max_deploys_per_day must be an integer") from exc
    if not isinstance(prod["authorize_phrase"], str) or not prod["authorize_phrase"].strip():
        raise ConfigError("production.authorize_phrase must be a non-empty string")
    for key in ("records_dir", "ledger"):
        if prod[key] is not None and (not isinstance(prod[key], str) or not prod[key].strip()):
            raise ConfigError(f"production.{key} must be a non-empty string or omitted")
    prod["_root"] = root
    prod["_state"] = state_dir(root)
    prod["_records_abs"] = (os.path.abspath(os.path.join(root, prod["records_dir"]))
                            if prod["records_dir"] else os.path.join(prod["_state"], "authorizations"))
    prod["_ledger_abs"] = (os.path.abspath(os.path.join(root, prod["ledger"]))
                           if prod["ledger"] else os.path.join(prod["_state"], "deploy-ledger.jsonl"))
    return prod


def phrase_line_regex(phrase: str, ignore_case: bool = False) -> re.Pattern:
    words = r"\s+".join(re.escape(w) for w in phrase.split())
    flags = re.MULTILINE | (re.IGNORECASE if ignore_case else 0)
    return re.compile(r"^\s*" + words + r"\s+(" + RELEASE_RE + r")\s*$", flags)


def record_path(cfg: dict, date: str, release: str) -> str:
    return os.path.join(cfg["_records_abs"], f"{date}-{release}.json")


def write_json_atomic(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2)
    os.replace(tmp, path)
