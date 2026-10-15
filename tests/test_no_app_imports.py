"""Domain tests never import the application package (W-067 round 3, finding: importing ofo_app installs the W-024 root
log redaction, which strips exc_info from later tests' records in the same process; CI run 38021452764).

Tests that need ofo_app live in tests_app/. A string that merely mentions the name is not an import and stays allowed."""
import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent


def app_imports(path: pathlib.Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "ofo_app" for a in node.names):
            lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] == "ofo_app":
            lines.append(node.lineno)
    return sorted(lines)


def test_no_module_under_tests_imports_ofo_app():
    bad = {str(p.relative_to(ROOT)): app_imports(p) for p in ROOT.rglob("*.py") if app_imports(p)}
    assert bad == {}, f"move these to tests_app/: {bad}"


def test_the_guard_catches_every_import_form_and_ignores_strings(tmp_path):
    f = tmp_path / "t.py"
    f.write_text("from ofo_app import x\n", encoding="utf-8")
    assert app_imports(f) == [1]
    f.write_text("import ofo_app.history_store\nimport os\ndef f():\n    from ofo_app.kite_ws import y\n", encoding="utf-8")
    assert app_imports(f) == [1, 4]
    f.write_text('NAME = "from ofo_app import x"  # ofo_app is only mentioned\nimport ofo\n', encoding="utf-8")
    assert app_imports(f) == []
