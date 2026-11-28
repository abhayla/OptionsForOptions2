"""#858 (Lane FD2): ``_tracked_first`` (the playbook test preview) catches only the expected "not of this type" case. A
database error is raised (shown), never turned into "not of the type" with a debug line, which also dropped every
strategy after it once the shared session was aborted. Fakes only."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from ofo_app.adjustment_readers import TrackedExited, TrackedUnreadable
from ofo_app.routes import playbooks
from sqlalchemy.exc import OperationalError


def _seams(reader):
    return SimpleNamespace(tracked_reader=reader, rates=None)


async def test_a_strategy_whose_legs_are_not_readable_is_not_of_the_type():
    async def unreadable(_sid, _rates):
        raise TrackedUnreadable("not a whole-lot option leg")

    async def exited(_sid, _rates):
        raise TrackedExited("no open option leg", closed_at=None)

    assert await playbooks._tracked_first(_seams(unreadable), SimpleNamespace(id=1)) is None
    assert await playbooks._tracked_first(_seams(exited), SimpleNamespace(id=2)) is None


async def test_a_readable_strategy_is_returned_as_read():
    async def read(sid, _rates):
        return ("tracked", sid)

    assert await playbooks._tracked_first(_seams(read), SimpleNamespace(id=3)) == ("tracked", 3)


@pytest.mark.parametrize("error", [OperationalError("SELECT 1", {}, Exception("connection lost")),
                                   RuntimeError("anything else unexpected"), KeyError("leg")])
async def test_a_database_or_other_fault_is_raised_never_read_as_not_of_the_type(error):
    async def broken(_sid, _rates):
        raise error

    with pytest.raises(type(error)):
        await playbooks._tracked_first(_seams(broken), SimpleNamespace(id=4))
