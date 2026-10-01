#!/usr/bin/env python3
"""ac_fp.py — print the fingerprint of one acceptance criterion's current text (REQ-014 AC-1).

Usage:
    python tools/ac_fp.py <REQ-id> <AC-id> [--root ROOT]

Prints the first 12 hex characters of spec_text.fingerprint(<the criterion's text>) — the same function the spec
checks use — and exits 0. The deliver skill writes this value as `ac_fp:` into every new evidence file, so a later
edit of the criterion makes that evidence stale (tools/trace_check.py). An unknown requirement, an unknown criterion
or an unreadable requirement file exits 1 with a message naming it; nothing is ever printed as a fingerprint then.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spec_text  # noqa: E402  (the one fingerprint function)

AC_FP_RE = re.compile(r"^[0-9a-f]{12}$")


def ac_fingerprint(text: str) -> str:
    """The evidence fingerprint of one criterion text (one definition: spec_text.fingerprint)."""
    return spec_text.fingerprint(str(text))


def criteria(data: dict) -> dict[str, str]:
    """AC id -> text for every well-formed criterion of a requirement's frontmatter."""
    out: dict[str, str] = {}
    for ac in data.get("acceptance_criteria") or []:
        if isinstance(ac, dict) and isinstance(ac.get("id"), str) and isinstance(ac.get("text"), str):
            out[ac["id"]] = ac["text"]
    return out


def lookup(root: Path, req_id: str, ac_id: str) -> tuple[str | None, str | None]:
    """(fingerprint, None) or (None, error message naming what is missing)."""
    if not re.fullmatch(r"REQ-\d{3,}", req_id):
        return None, f"ac_fp: {req_id!r} is not a requirement id (REQ-###)"
    path = root / "spec" / "requirements" / f"{req_id}.md"
    if not path.is_file():
        return None, f"ac_fp: unknown requirement {req_id} (no {path.as_posix()})"
    data, _body, err = spec_text.parse_frontmatter(path.read_text(encoding="utf-8"))
    if err or data is None:
        return None, f"ac_fp: {req_id} is unreadable: {err or 'no YAML frontmatter'}"
    acs = criteria(data)
    if ac_id not in acs:
        known = ", ".join(acs) or "none"
        return None, f"ac_fp: unknown criterion {ac_id} in {req_id} (its criteria: {known})"
    return ac_fingerprint(acs[ac_id]), None


UNPINNED_LIST = ("spec", "traceability", "unpinned-before-tracing.txt")   # read by tools/trace_check.py


def freeze_unpinned(root: Path, force: bool = False) -> int:
    """Write the list of evidence files that lack ac_fp (evidence written before fingerprints existed). Run ONCE,
    when a project adopts fingerprints; refuses to overwrite an existing list unless force."""
    out = root.joinpath(*UNPINNED_LIST)
    if out.exists() and not force:
        print(f"ac_fp: {out.as_posix()} already exists; it is written once (use --force to rewrite it)",
              file=sys.stderr)
        return 1
    paths = []
    for p in sorted((root / "evidence").glob("W-*/AC-*.md")):
        data, _body, err = spec_text.parse_frontmatter(p.read_text(encoding="utf-8"))
        if err or data is None or "ac_fp" not in data:
            paths.append(p.relative_to(root).as_posix())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("# Evidence written before fingerprints existed (REQ-014): the only files allowed to lack ac_fp.\n"
                   "# Written once by `python tools/ac_fp.py --freeze-unpinned .`; never add new evidence here.\n"
                   + "".join(x + "\n" for x in paths), encoding="utf-8", newline="\n")
    print(f"ac_fp: wrote {out.as_posix()} ({len(paths)} evidence files unpinned: before tracing)")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--freeze-unpinned" in argv:
        fz = argparse.ArgumentParser(description="Write the list of evidence files written before fingerprints.")
        fz.add_argument("--freeze-unpinned", metavar="ROOT", required=True)
        fz.add_argument("--force", action="store_true")
        f = fz.parse_args(argv)
        return freeze_unpinned(Path(f.freeze_unpinned), f.force)
    ap = argparse.ArgumentParser(description="Print the fingerprint of one acceptance criterion's current text.")
    ap.add_argument("req_id")
    ap.add_argument("ac_id")
    ap.add_argument("--root", default=".", help="project root (default: the current directory)")
    ap.add_argument("--yaml", action="store_true",
                    help='print the two evidence lines `requirement: REQ-###` and `ac_fp: "<hex>"` (quoted: an all-digit '
                         'hex would load as a number)')
    a = ap.parse_args(argv)
    fp, err = lookup(Path(a.root), a.req_id, a.ac_id)
    if err:
        print(err, file=sys.stderr)
        return 1
    print(f'requirement: {a.req_id}\nac_fp: "{fp}"' if a.yaml else fp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
