"""Row-review R1-R5 (docs/process/row-review.md), enforced by machine: every closed row of the builder-sequence table
has a `### Row N` entry in the review log, and every closed row number that is a multiple of 3 has a
`### Meta review after row N` entry. Fails closed: a missing file, an unparseable table or a malformed row is red.

Pure functions over text so the tests can feed broken copies; the repo test reads the two real files."""
import pathlib
import re

import pytest

pytestmark = pytest.mark.repo_scan

REPO = pathlib.Path(__file__).resolve().parents[1]
TABLE = REPO / "docs" / "process" / "builder-sequence-2026-10-22.md"
LOG = REPO / "docs" / "process" / "row-review.md"
HEADER_RE = re.compile(r"^\|\s*#\s*\|\s*W\s*\|", re.M)
CELLS = 8  # | # | W | REQ | Name | Priority | Chunk | Tier | Status |
CLOSED_RE = re.compile(r"^(Done|PARKED)\b")
META_EVERY = 3


def closed_rows(table_text: str) -> tuple[list[int], list[str]]:
    """Closed row numbers (Status starts `Done` or `PARKED`) and the parse problems found in the table."""
    head = HEADER_RE.search(table_text)
    if head is None:
        return [], ["table header `| # | W |` not found"]
    problems: list[str] = []
    closed: list[int] = []
    seen = 0
    for line in table_text[head.end():].splitlines():
        if not line.startswith("|"):
            if seen:
                break  # the table ended
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if set("".join(cells)) <= set("-: "):
            continue  # the |---|---| separator row
        if len(cells) != CELLS or not cells[0].isdigit():
            problems.append(f"malformed table row: {line[:60]}")
            continue
        seen += 1
        if CLOSED_RE.match(cells[-1]):
            closed.append(int(cells[0]))
    if not seen:
        problems.append("no table rows parsed")
    return closed, problems


def review_problems(table_text: str, log_text: str) -> list[str]:
    closed, problems = closed_rows(table_text)
    for n in closed:
        if not re.search(rf"^### Row {n}\b", log_text, re.M):
            problems.append(f"closed row {n} has no `### Row {n}` entry in row-review.md")
        if n % META_EVERY == 0 and not re.search(rf"^### Meta review after row {n}\b", log_text, re.M):
            problems.append(f"closed row {n} has no `### Meta review after row {n}` entry in row-review.md")
    return problems


def files_problems(table: pathlib.Path, log: pathlib.Path) -> list[str]:
    missing = [f"missing file: {p.name}" for p in (table, log) if not p.is_file()]
    if missing:
        return missing
    return review_problems(table.read_text(encoding="utf-8"), log.read_text(encoding="utf-8"))


def test_every_closed_row_has_its_review_entry():
    """Row-review R1-R5: today's real files are green (rows 1-2 Done with entries)."""
    assert files_problems(TABLE, LOG) == []


def _tables(rows: list[str]) -> str:
    head = "| # | W | REQ | Name | Priority | Chunk | Tier | Status |\n|---|---|---|---|---|---|---|---|\n"
    return "Intro\n\n" + head + "\n".join(rows) + "\n\nAfter the table.\n"


def _row(n: int, status: str) -> str:
    return f"| {n} | W-{n} | REQ-{n} | Name | P | 1 | A | {status} |"


LOG_1_2 = "### Row 2 - x\n### Row 1 - y\n"


def test_a_done_row_without_its_entry_is_red():
    problems = review_problems(_tables([_row(1, "Done"), _row(2, "Done"), _row(3, "Not started")]), "### Row 1 - y\n")
    assert problems == ["closed row 2 has no `### Row 2` entry in row-review.md"]


def test_row_10_entry_does_not_satisfy_row_1():
    problems = review_problems(_tables([_row(1, "Done")]), "### Row 10 - y\n")
    assert len(problems) == 1 and "row 1 has no" in problems[0]


def test_row_3_closed_needs_a_meta_review():
    table = _tables([_row(1, "Done"), _row(2, "Done"), _row(3, "Done (note)")])
    log = LOG_1_2 + "### Row 3 - z\n"
    assert review_problems(table, log) == ["closed row 3 has no `### Meta review after row 3` entry in row-review.md"]
    assert review_problems(table, log + "### Meta review after row 3 - m\n") == []


def test_a_parked_row_counts_as_closed():
    problems = review_problems(_tables([_row(1, "PARKED (#9)")]), "")
    assert problems == ["closed row 1 has no `### Row 1` entry in row-review.md"]


def test_open_rows_need_no_entry():
    assert review_problems(_tables([_row(1, "In progress"), _row(2, "Not started")]), "") == []


@pytest.mark.parametrize("bad_row", ["| 4 | W-4 | REQ-4 | Name | P | 1 | A |",
                                     "| x | W-4 | REQ-4 | Name | P | 1 | A | Done |",
                                     "| 4 | W-4 | REQ-4 | Name | P | 1 | A | Done | extra |"])
def test_a_malformed_table_row_is_red(bad_row):
    problems = review_problems(_tables([_row(1, "Done"), bad_row]), "### Row 1 - y\n")
    assert len(problems) == 1 and problems[0].startswith("malformed table row")


def test_an_unparseable_table_is_red():
    assert review_problems("no table here\n", LOG_1_2) == ["table header `| # | W |` not found"]
    assert review_problems(_tables([]), LOG_1_2) == ["no table rows parsed"]


def test_a_missing_or_renamed_file_is_red(tmp_path):
    log = tmp_path / "row-review.md"
    log.write_text(LOG_1_2, encoding="utf-8")
    renamed = tmp_path / "builder-sequence-renamed.md"
    assert files_problems(renamed, log) == ["missing file: builder-sequence-renamed.md"]
    assert files_problems(TABLE, tmp_path / "gone.md") == ["missing file: gone.md"]
    table = tmp_path / "table.md"
    table.write_text(_tables([_row(1, "Done")]), encoding="utf-8")
    assert files_problems(table, log) == []
