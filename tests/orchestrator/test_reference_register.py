"""ADR-176: the reference-product difference register - record checks, the close gate and the generated page.

Every case runs against a temp repo root holding the real builder table, a real requirement (REQ-135, row 27; REQ-006
and REQ-007 share row 17) and a real decision (ADR-176), so the row/REQ cross-check reads the real table shape.
"""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("reference_register",
                                               ROOT / "scripts" / "orchestrator" / "reference_register.py")
rr = importlib.util.module_from_spec(_spec)
sys.modules["reference_register"] = rr
_spec.loader.exec_module(rr)

# ADR-176 (4): the banned name is never written in this file; it is rebuilt from its bytes at run time.
BANNED = bytes([115, 101, 110, 115, 105, 98, 117, 108, 108]).decode()


def good(**over) -> dict:
    rec = {"id": "RD-001", "kind": "COPY", "title": "Days left beside each expiry",
           "reference_behaviour": "Shows a short date and the calendar days left in brackets.",
           "reference_screens": ["catalogue 100", "screen 012"], "reference_label": "27 Oct (6 Days)",
           "ours": "REQ-135 AC-2: raw date 2026-10-27", "req": "REQ-135", "ac": "AC-2", "row": 27, "status": "open",
           "spec_change": False, "bug": False, "recorded": "2026-10-23"}
    rec.update(over)
    return {k: v for k, v in rec.items() if v is not DROP}


DROP = object()


@pytest.fixture
def root(tmp_path) -> Path:
    r = tmp_path / "repo"
    for sub in ("spec/requirements", "spec/decisions", "spec/reference-diffs", "docs/process"):
        (r / sub).mkdir(parents=True)
    for req in ("REQ-135", "REQ-006", "REQ-007", "REQ-053"):
        shutil.copy(ROOT / "spec" / "requirements" / f"{req}.md", r / "spec" / "requirements")
    shutil.copy(ROOT / "spec" / "decisions" / "ADR-176.md", r / "spec" / "decisions")
    shutil.copy(ROOT / "docs" / "process" / "builder-sequence-2026-10-22.md", r / "docs" / "process")
    return r


def put(root: Path, *recs: dict) -> None:
    for rec in recs:  # a missing or malformed id still writes RD-001.json, so only the id check can fail it
        rid = rec.get("id")
        name = rid if isinstance(rid, str) and rr.ID_RE.match(rid) else "RD-001"
        (root / "spec" / "reference-diffs" / f"{name}.json").write_text(json.dumps(rec), encoding="utf-8")


def errors(root: Path) -> list[str]:
    return rr.validate(root)


def test_a_complete_record_is_valid_and_the_rendered_page_makes_check_pass(root, capsys):
    put(root, good())
    assert errors(root) == []
    assert rr.main(["--root", str(root), "--check"]) == 1  # no page yet: stale
    assert "is stale" in capsys.readouterr().out
    assert rr.main(["--root", str(root), "--render"]) == 0
    assert rr.main(["--root", str(root), "--check"]) == 0


@pytest.mark.parametrize("field", rr.REQUIRED)
def test_each_required_field_missing_fails(root, field):
    put(root, good(**{field: DROP}))
    assert any(f"missing field `{field}`" in e for e in errors(root))


def test_an_unknown_field_fails(root):
    put(root, good(Status="open"))
    assert any("unknown field `Status`" in e for e in errors(root))


@pytest.mark.parametrize("kind", rr.KINDS)
def test_every_allowed_kind_passes(root, kind):
    extra = {"adr": "ADR-176"} if kind == "DIFFERENT-BY-DECISION" else {}
    put(root, good(kind=kind, **extra))
    assert errors(root) == []


@pytest.mark.parametrize("kind", ["copy", "Copy", "DIFFERENT", "", None, 1, ["COPY"]])
def test_any_other_kind_fails(root, kind):
    put(root, good(kind=kind))
    assert any("`kind` must be one of" in e for e in errors(root))


@pytest.mark.parametrize("status", rr.STATUSES)
def test_every_allowed_status_passes(root, status):
    put(root, good(status=status, **({"issue": 5} if status == "deferred" else {})))
    assert errors(root) == []


@pytest.mark.parametrize("status", ["Open", "done", "closed", "", None, 0])
def test_any_other_status_fails(root, status):
    put(root, good(status=status))
    assert any("`status` must be one of" in e for e in errors(root))


@pytest.mark.parametrize("field,value", [
    ("id", "RD-1"), ("id", "rd-001"), ("req", "REQ-1350"), ("req", 135), ("ac", "ac-2"), ("adr", "ADR176"),
    ("recorded", "23-10-2026"), ("recorded", "2026-13-40"), ("row", "27"), ("row", 0), ("row", True), ("issue", "#5"),
    ("issue", 0), ("spec_change", "no"), ("bug", 0), ("title", ""), ("ours", "   "), ("reference_behaviour", 7),
    ("reference_screens", "catalogue 100"), ("reference_screens", ["catalogue 1"]), ("reference_screens", ["cat 100"]),
    ("reference_screens", ["screen 012", "screen 012"]), ("reference_screens", []), ("reference_label", ""),
])
def test_every_wrong_field_shape_fails(root, field, value):
    put(root, good(**{field: value}))
    assert errors(root), f"{field}={value!r} passed"


def test_the_id_must_equal_the_file_name(root):
    rec = good(id="RD-002")
    (root / "spec" / "reference-diffs" / "RD-001.json").write_text(json.dumps(rec), encoding="utf-8")
    assert any("must equal the file name" in e for e in errors(root))


def test_a_no_screen_record_may_list_no_screen(root):
    put(root, good(kind="NO-SCREEN", reference_screens=[]))
    assert errors(root) == []


@pytest.mark.parametrize("field,limit", [("reference_behaviour", 400), ("reference_label", 40), ("title", 120),
                                         ("ours", 400)])
def test_length_limits(root, field, limit):
    put(root, good(**{field: "x" * limit}))
    assert errors(root) == []
    put(root, good(**{field: "x" * (limit + 1)}))
    assert any(f"at most {limit}" in e for e in errors(root))


def test_too_many_screens_fail(root):
    put(root, good(reference_screens=[f"screen {i:03d}" for i in range(rr.MAX_SCREENS + 1)]))
    assert any("reference_screens" in e for e in errors(root))


def test_different_by_decision_needs_an_existing_adr(root):
    """Attack 1: no `adr`, or an ADR that does not exist, fails; an existing one passes."""
    put(root, good(kind="DIFFERENT-BY-DECISION"))
    assert any("names its `adr`" in e for e in errors(root))
    put(root, good(kind="DIFFERENT-BY-DECISION", adr="ADR-999"))
    assert any("ADR-999 is not in spec/decisions" in e for e in errors(root))
    put(root, good(kind="DIFFERENT-BY-DECISION", adr="ADR-176"))
    assert errors(root) == []


def test_a_missing_requirement_or_ac_fails(root):
    put(root, good(req="REQ-999"))
    assert any("REQ-999 is not in spec/requirements" in e for e in errors(root))
    put(root, good(ac="AC-99"))
    assert any("AC-99 is not an acceptance criterion of REQ-135" in e for e in errors(root))


def test_a_row_belonging_to_another_requirement_fails(root):
    """Attack 2: row 5 is REQ-053's row, so a REQ-135 record on row 5 fails; an unknown row fails too."""
    put(root, good(row=5))
    assert any("`row` 5 belongs to REQ-053, not REQ-135" in e for e in errors(root))
    put(root, good(row=999))
    assert any("`row` 999 is not in" in e for e in errors(root))


def test_a_row_naming_two_requirements_counts_both(root):
    put(root, good(req="REQ-006", ac=DROP, row=17), )
    assert errors(root) == []
    put(root, good(req="REQ-007", ac=DROP, row=17))
    assert errors(root) == []


@pytest.mark.parametrize("field", ["title", "reference_behaviour", "ours", "reference_label"])
@pytest.mark.parametrize("form", [str.lower, str.upper, str.capitalize])
def test_the_banned_name_fails_in_any_field_and_case(root, field, form):
    """Attack 3: the name in any text field, any case, as a whole word, fails."""
    put(root, good(**{field: f"like {form(BANNED)} does"}))
    assert any("names the reference product" in e for e in errors(root))


def test_the_banned_name_fails_in_a_key_or_a_list_too(root):
    raw = json.dumps(good()).replace('"title":', f'"{BANNED}": 1, "title":')
    (root / "spec" / "reference-diffs" / "RD-001.json").write_text(raw, encoding="utf-8")
    assert any("names the reference product" in e for e in errors(root))
    put(root, good(reference_screens=["catalogue 100", f"{BANNED} 100"]))
    assert any("names the reference product" in e for e in errors(root))


def test_a_word_merely_containing_the_name_is_not_a_ban_hit(root):
    """The ban keys on whole words, so its hash check is exact (no substring false alarms)."""
    assert not rr.has_banned_word(f"x{BANNED}y")
    assert rr.has_banned_word(f"see {BANNED.upper()}.")


@pytest.mark.parametrize("name", ["notes.txt", "RD-1.json", "rd-001.json", "RD-001.json.bak"])
def test_a_stray_file_in_the_register_fails_closed(root, name):
    (root / "spec" / "reference-diffs" / name).write_text("{}", encoding="utf-8")
    with pytest.raises(rr.RegisterError):
        rr.validate(root)
    assert rr.main(["--root", str(root), "--close-check", "REQ-135"]) == 2


@pytest.mark.parametrize("raw", ["{not json", "[]", "\"x\"", ""])
def test_an_unreadable_record_fails_closed(root, raw):
    (root / "spec" / "reference-diffs" / "RD-001.json").write_text(raw, encoding="utf-8")
    assert rr.main(["--root", str(root), "--check"]) == 2
    assert rr.main(["--root", str(root), "--close-check", "REQ-135"]) == 2


def test_an_invalid_record_makes_the_gates_fail_closed(root):
    put(root, good(kind="copy"))  # would otherwise read as non-blocking
    assert rr.main(["--root", str(root), "--close-check", "REQ-135"]) == 2
    assert rr.main(["--root", str(root), "--open", "REQ-135"]) == 2


# ---------------------------------------------------------------- close gate: every state (standing item (d))
@pytest.mark.parametrize("over,code", [
    ({}, 1),                                                   # open COPY
    ({"status": "built"}, 1),                                  # built, not verified
    ({"status": "verified"}, 0),
    ({"status": "deferred", "issue": 7}, 0),
    ({"status": "decided"}, 0),
    ({"kind": "MATCH"}, 0),                                    # open MATCH never blocks
    ({"kind": "NO-SCREEN"}, 0),
    ({"kind": "DIFFERENT-BY-DECISION", "adr": "ADR-176"}, 0),
    ({"kind": "MATCH", "spec_change": True}, 1),               # open spec_change blocks whatever its kind
    ({"kind": "MATCH", "spec_change": True, "status": "decided"}, 0),
])
def test_close_check_states(root, capsys, over, code):
    """Attack 4: exit 1 for an open COPY or open spec_change record, 0 once verified, deferred with issue, decided."""
    put(root, good(**over))
    assert rr.main(["--root", str(root), "--close-check", "REQ-135"]) == code
    out = capsys.readouterr().out
    assert ("RD-001" in out) is (code == 1)


def test_close_check_with_no_record_passes(root):
    assert rr.main(["--root", str(root), "--close-check", "REQ-135"]) == 0
    shutil.rmtree(root / "spec" / "reference-diffs")
    assert rr.main(["--root", str(root), "--close-check", "REQ-135"]) == 0


def test_deferred_without_an_issue_is_invalid_and_still_blocks(root):
    rec = good(status="deferred")
    put(root, rec)
    assert any("names its `issue`" in e for e in errors(root))
    assert rr.is_blocking(rec) is True
    assert rr.main(["--root", str(root), "--close-check", "REQ-135"]) == 2


def test_close_check_only_reads_the_named_requirements(root, capsys):
    put(root, good(), good(id="RD-002", req="REQ-053", ac=DROP, row=5))
    assert rr.main(["--root", str(root), "--close-check", "REQ-053"]) == 1
    out = capsys.readouterr().out
    assert "RD-002" in out and "RD-001" not in out
    assert rr.main(["--root", str(root), "--open", "REQ-135", "REQ-053"]) == 0
    assert capsys.readouterr().out == "RD-001\nRD-002\n"


def test_a_bad_requirement_argument_is_a_usage_error(root):
    assert rr.main(["--root", str(root), "--close-check", "135"]) == 2


# ---------------------------------------------------------------- the page
def _all_kinds(root: Path) -> None:
    put(root,
        good(id="RD-005", kind="MATCH", status="verified"),
        good(id="RD-004", kind="DIFFERENT-BY-DECISION", adr="ADR-176", status="decided"),
        good(id="RD-003", kind="NO-SCREEN", reference_screens=[], title="Capture the lost-feed banner"),
        good(id="RD-002", kind="COPY", req="REQ-053", ac=DROP, row=5, title="Earlier row copy"),
        good(id="RD-006", kind="MATCH", spec_change=True, title="Extra refusal choices"),
        good())


def test_render_sections_in_order_with_counts(root):
    _all_kinds(root)
    page = rr.render(root)
    heads = ["Records: 6 (COPY 2, DIFFERENT-BY-DECISION 1, NO-SCREEN 1, MATCH 2)", "## SPEC CHANGE batch for the owner",
             "## NO-SCREEN capture list", "## COPY by builder row", "## DIFFERENT-BY-DECISION", "## MATCH"]
    positions = [page.index(h) for h in heads]
    assert positions == sorted(positions)
    spec_change = page.split("## SPEC CHANGE batch")[1].split("## NO-SCREEN")[0]
    assert "RD-006" in spec_change and "RD-001" not in spec_change
    copies = page.split("## COPY by builder row")[1].split("## DIFFERENT")[0]
    assert copies.index("| 5 | RD-002") < copies.index("| 27 | RD-001")  # by builder row
    assert "| RD-004 | REQ-135 | ADR-176 |" in page
    assert "2 record(s) match the reference product." in page


def test_render_is_deterministic_regardless_of_file_order(root, tmp_path):
    _all_kinds(root)
    first = rr.render(root)
    other = tmp_path / "other"
    shutil.copytree(root, other)
    for p in sorted((other / "spec" / "reference-diffs").iterdir(), reverse=True):
        p.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")  # rewrite in reverse order
    assert rr.render(other) == first == rr.render(root)


def test_an_edited_page_is_stale(root, capsys):
    put(root, good())
    rr.main(["--root", str(root), "--render"])
    page = root / rr.PAGE
    page.write_text(page.read_text(encoding="utf-8") + "hand edit\n", encoding="utf-8")
    assert rr.main(["--root", str(root), "--check"]) == 1
    assert "is stale" in capsys.readouterr().out


def test_render_refuses_an_invalid_register(root):
    put(root, good(kind="DIFFERENT-BY-DECISION"))
    assert rr.main(["--root", str(root), "--render"]) == 1
    assert not (root / rr.PAGE).exists()
