"""Guard: no test file imports the bare module name `conftest`.

When pytest collects two packages that each have a conftest.py, `conftest` resolves to whichever was imported first,
so `from conftest import X` fails with an ImportError naming the other package's file (issue #532 item 5). Shared
test constants and helpers live in a uniquely named module instead (e.g. tests/engine/engine_fixtures.py).
"""
import pathlib
import re

TESTS = pathlib.Path(__file__).resolve().parent
BARE = re.compile(r"^(from conftest import|import conftest)\b", re.MULTILINE)


def test_no_file_imports_the_bare_conftest_module():
    offenders = [
        str(path.relative_to(TESTS))
        for path in TESTS.rglob("*.py")
        if path != pathlib.Path(__file__).resolve() and BARE.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
