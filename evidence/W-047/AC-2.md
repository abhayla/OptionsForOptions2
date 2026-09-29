---
work_item: W-047
ac: AC-2
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (sonnet)"
date: '2026-09-29'
commands: "python -m pytest -q -p no:cacheprovider tests/strategy/test_library.py; python -m pytest -q -p no:cacheprovider; python -c load_templates() + print level/views/objectives; python -c with pytest.main and patched model.LEVELS / model.OBJECTIVES; python -c dataclasses.replace(bad labels); python -c load_templates(tmp yaml with null/string/empty/dup labels)"
---

AC: AC-2
result: pass
commands: python -m pytest -q -p no:cacheprovider tests/strategy/test_library.py; python -m pytest -q -p no:cacheprovider; python -c load_templates() + print level/views/objectives; python -c with pytest.main and patched model.LEVELS / model.OBJECTIVES; python -c dataclasses.replace(bad labels); python -c load_templates(tmp yaml with null/string/empty/dup labels)
observed: 20 passed (test_library); 1386 passed full suite; 21 templates loaded, each with one level, >=1 view, >=1 objective; the verifier's own Q251 mapping agrees with all 21 levels; missing, unknown, wrong-case, empty, duplicate, null, string and list-of-levels values raise TemplateError via the loader; direct model with bad labels raises TemplateError
attack: Widened model.LEVELS with 'Expert' and model.OBJECTIVES with 'speculation': the direct-model tests failed, so both guards are covered. Direct-model objectives=None raises TypeError not TemplateError (the schema catches it first via the loader; minor). No naked short leg beyond straddle/strangle in a non-Advanced template. Six unplaced templates are ambiguous but defensible (synthetic long/short could arguably be Intermediate) and are listed for the owner per Q251.

Recorded by the orchestrator from the verifier's returned block.
