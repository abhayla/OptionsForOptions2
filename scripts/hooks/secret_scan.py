"""PreToolUse hook (Write|Edit|MultiEdit): refuse file content that looks like a real secret.

Adapted from abhayla/algochanakya@bf9faf7:.claude/hooks/secret-scanner.py (ADR-047). Changes: Markdown and text files
are scanned too (algochanakya leaked a Kite key and a Postgres password in its docs), placeholders are allowed, the
input is read from stdin with no helper module, and the patterns are a module-level list the tests import.
Exit 0 = allow, 2 = block (the message on stderr is shown to the session).
"""
from __future__ import annotations

import json
import re
import sys

BINARY_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip")

PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"), "private key (PEM)"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"), "GitHub token"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "Google API key"),
    (re.compile(r"xox[baprs]-[0-9a-zA-Z\-]{10,}"), "Slack token"),
    (re.compile(r"(?:sk|pk)_(?:test|live)_[0-9a-zA-Z]{24,}"), "Stripe key"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"), "Anthropic API key"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_\-]{10,}"), "JWT"),
    (re.compile(r"(?i)(?:postgres(?:ql)?(?:\+asyncpg)?|mysql|mongodb|redis)://[^:/\s@]+:([^@\s]+)@"),
     "database URL with a password"),
    (re.compile(r"(?i)(?:api_key|apikey|api_secret|access_token|auth_token|secret_key|client_secret)"
                r"\s*[=:]\s*[\"']([A-Za-z0-9_\-]{16,})[\"']"), "API key or token assignment"),
    (re.compile(r"(?i)(?:password|passwd|pwd)\s*[=:]\s*[\"']([^\"']{8,})[\"']"), "hardcoded password"),
]

# A captured value made only of these words (or a ${VAR} / <...> template) is a placeholder, not a secret.
PLACEHOLDER = re.compile(
    r"(?i)^(?:\$\{[^}]+\}|<[^>]+>|\*+|x+|\.+|"
    r".*(?:password|changeme|example|placeholder|your[_-]|dummy|test|fake|redacted|replace|xxx|secret).*)$")


def scan(text: str) -> list[str]:
    """Labels of every secret-like pattern in `text`, placeholders excluded."""
    found = []
    for pattern, label in PATTERNS:
        for m in pattern.finditer(text):
            value = m.group(1) if m.groups() else m.group(0)
            if pattern.groups and PLACEHOLDER.match(value):
                continue
            found.append(label)
            break
    return found


def _contents(tool_input: dict) -> list[str]:
    parts = [tool_input.get("content"), tool_input.get("new_string")]
    parts += [e.get("new_string") for e in tool_input.get("edits") or [] if isinstance(e, dict)]
    return [p for p in parts if isinstance(p, str) and p]


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0  # fail open on input this hook cannot read
    tool_input = data.get("tool_input") or {}
    path = str(tool_input.get("file_path") or "")
    if path.lower().endswith(BINARY_EXTENSIONS):
        return 0
    labels = sorted({label for text in _contents(tool_input) for label in scan(text)})
    if not labels:
        return 0
    sys.stderr.write(
        f"BLOCKED by secret_scan: '{path}' looks like it contains: {', '.join(labels)}.\n"
        "Put real values in a gitignored .env (project) or D:\\Abhay\\GLOBAL.env (shared), never in a file.\n"
        "If this is a placeholder, write it as ${VAR}, <value> or a word like 'example'.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
