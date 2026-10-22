"""REQ-001 AC-2 (W-129): the catalogue's INDEX row is not a CE/PE/FUT leg. Saving it as a leg is refused by the same
path as an unknown contract id, never an `Instrument('INDEX')` crash. Needs the test database."""
from __future__ import annotations

import pytest
from sqlalchemy import text

from ofo.engine.legs import Action
from ofo.strategy import stored_form as sf
from ofo_app import strategy_store as store


async def test_an_index_row_as_a_leg_is_refused_not_a_crash(app_engine) -> None:
    async with app_engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT id FROM public.catalogue_contracts WHERE instrument_type = 'INDEX' ORDER BY id LIMIT 1"))).first()
        if row is None:
            pytest.skip("the test catalogue holds no INDEX row")
        with pytest.raises(sf.StoredFormError) as caught:
            await store.build_definition(conn, "NIFTY", [sf.LegChoice(int(row[0]), Action.BUY, 75)])
        assert not isinstance(caught.value, ValueError) or isinstance(caught.value, sf.StoredFormError)
