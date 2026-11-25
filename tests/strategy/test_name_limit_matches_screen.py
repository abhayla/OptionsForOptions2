"""D-53: the typed-name limit the screens say and stop at (frontend/src/lib/saveDraft.js STRATEGY_NAME_MAX) is the limit
the server enforces on a typed name (definition.STRATEGY_NAME_TYPED_MAX, ADR-183), and the server refuses one more."""
import pathlib
import re

import pytest

from ofo.strategy import definition
from ofo.strategy.stored_form import StoredFormError, check_strategy_name

SAVE_DRAFT_JS = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "saveDraft.js"


def test_screen_limit_is_the_servers_typed_limit() -> None:
    found = re.search(r"export const STRATEGY_NAME_MAX = (\d+)", SAVE_DRAFT_JS.read_text(encoding="utf-8"))
    assert found is not None
    assert int(found.group(1)) == definition.STRATEGY_NAME_TYPED_MAX == 20


def test_server_takes_the_last_allowed_character_and_refuses_the_next() -> None:
    limit = definition.STRATEGY_NAME_TYPED_MAX
    check_strategy_name("x" * limit)
    with pytest.raises(StoredFormError):
        check_strategy_name("x" * (limit + 1))
