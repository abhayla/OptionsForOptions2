"""ADR-119 / MKT-HOURS MINOR-1: the holiday data file is validated at load; every bad shape answers "no calendar"
(the gate's 'could not confirm' block), never an exception and never "open"."""
from __future__ import annotations

import datetime
import json

import pytest

from ofo import market_calendar as mc
from ofo.market_calendar import DATA_FILE, MarketStatus, market_status, next_open
from ofo.timeutil import IST

WHEN = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=IST)


def _good() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _first(raw: dict) -> list:
    return raw["holidays"]["2026"][0]


def _mutations() -> dict[str, object]:
    """Bad shapes generated from the real file (each rule the loader enforces, broken one way), not hand-listed JSON."""
    def with_(change) -> dict:  # noqa: ANN001
        raw = _good()
        change(raw)
        return raw
    return {
        "top-level-not-object": [],
        "unknown-key": with_(lambda r: r.update(extra=1)),
        "no-holidays-key": with_(lambda r: r.pop("holidays")),
        "holidays-not-object": with_(lambda r: r.update(holidays=[])),
        "no-years": with_(lambda r: r.update(holidays={})),
        "empty-year-key": with_(lambda r: r["holidays"].update({"": r["holidays"].pop("2026")})),
        "non-numeric-year-key": with_(lambda r: r["holidays"].update({"abcd": r["holidays"].pop("2026")})),
        "year-without-rows": with_(lambda r: r["holidays"].update({"2026": []})),
        "rows-not-a-list": with_(lambda r: r["holidays"].update({"2026": "x"})),
        "row-not-a-pair": with_(lambda r: r["holidays"]["2026"].append(["2026-02-02"])),
        "row-name-blank": with_(lambda r: _first(r).__setitem__(1, "")),
        "date-not-iso": with_(lambda r: _first(r).__setitem__(0, "15 Jan 2026")),
        "date-outside-its-year": with_(lambda r: _first(r).__setitem__(0, "2027-01-14")),
        "duplicate-date": with_(lambda r: r["holidays"]["2026"].append(list(_first(r)))),
    }


@pytest.fixture
def install(tmp_path, monkeypatch):  # noqa: ANN001, ANN201
    def put(payload: object) -> None:
        path = tmp_path / "market_calendar.json"
        path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
        monkeypatch.setattr(mc, "DATA_FILE", path)
        mc._load.cache_clear()
    yield put
    mc._load.cache_clear()


def test_the_shipped_file_passes_its_own_validation(install) -> None:  # noqa: ANN001
    install(_good())
    assert mc._load()[2026] and market_status(WHEN) is MarketStatus.OPEN


@pytest.mark.parametrize("name", sorted(_mutations()))
def test_minor1_every_bad_shape_is_no_calendar(name: str, install) -> None:  # noqa: ANN001
    install(_mutations()[name])
    with pytest.raises(mc.CalendarError):
        mc._load()
    assert market_status(WHEN) is MarketStatus.NO_CALENDAR and next_open(WHEN) is None


@pytest.mark.parametrize("text", ["", "{not json", "\x00"])
def test_minor1_unreadable_text_is_no_calendar(text: str, install) -> None:  # noqa: ANN001
    install(text)
    assert market_status(WHEN) is MarketStatus.NO_CALENDAR


def test_minor1_missing_file_is_no_calendar(install, tmp_path, monkeypatch) -> None:  # noqa: ANN001
    install(_good())
    monkeypatch.setattr(mc, "DATA_FILE", tmp_path / "absent.json")
    mc._load.cache_clear()
    assert market_status(WHEN) is MarketStatus.NO_CALENDAR
