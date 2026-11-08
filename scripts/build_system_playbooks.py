"""build_system_playbooks.py [--check]: writes backend/ofo/adjustment/system_playbooks.json, the seed migration 0031
reads, from tests/fixtures/adjust_scenarios/_playbooks.json through ofo.adjustment.playbook_eval.body_from_fixture
(the one derivation). Name "<shown name>: system default" (the catalogue's playbook_type label); status approved
for the iron condor (ADR-216), draft for the rest. `--check` exits 1 when the file differs from what it would write.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ofo.adjustment.playbook_eval import body_from_fixture  # noqa: E402
from ofo.adjustment.playbook_types import APPROVED_SYSTEM_TYPES, SHOWN_NAMES, TYPE_KEYS  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "adjust_scenarios" / "_playbooks.json"
OUT = ROOT / "backend" / "ofo" / "adjustment" / "system_playbooks.json"


def _refuse_float(text: str) -> None:
    raise ValueError(f"_playbooks.json holds a float ({text})")


def build() -> str:
    playbooks = json.loads(FIXTURE.read_text(encoding="utf-8"), parse_float=_refuse_float)
    rows = []
    for key in TYPE_KEYS:
        body = body_from_fixture(playbooks, key)
        status = "approved" if key in APPROVED_SYSTEM_TYPES else "draft"
        if body.get("status") != status:
            raise ValueError(f"{key}: the fixture's status {body.get('status')!r} is not {status!r}")
        rows.append({"strategy_type": key, "name": f"{SHOWN_NAMES[key]}: system default", "status": status,
                     "body": body})
    doc = {"schema": 1, "source": "scripts/build_system_playbooks.py from tests/fixtures/adjust_scenarios/"
           "_playbooks.json (do not edit by hand)", "playbooks": rows}
    return json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    text = build()
    if "--check" in argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print(f"{OUT.relative_to(ROOT)} differs from what scripts/build_system_playbooks.py writes")
            return 1
        print("OK: system_playbooks.json is current")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(TYPE_KEYS)} playbooks)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
