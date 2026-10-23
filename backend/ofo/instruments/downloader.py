"""Download Zerodha's public instrument list over the network.

Kept separate from `ofo.instruments.parser` (pure, offline) so the parser and catalogue can be
tested without network access. This module is never imported by the test suite (see
`ofo.instruments.sources.SOURCES["instrument_list_url"]` for the cited source + capture date).
"""
from __future__ import annotations

from io import StringIO

from ofo.broker import rate_limit
from ofo.broker.kite_http import open_url
from ofo.instruments.models import Contract
from ofo.instruments.parser import parse_instruments_stream
from ofo.instruments.sources import get as get_source

_TIMEOUT_SECONDS = 30


def download_instruments_csv() -> str:
    """Fetch the raw instrument-list CSV text from Zerodha's public endpoint."""
    url = get_source("instrument_list_url").url
    with rate_limit.background(), open_url(url, timeout=_TIMEOUT_SECONDS) as response:  # allow-list first
        return response.read().decode("utf-8")


def download_instruments() -> list[Contract]:
    """Download and parse the current instrument list into `Contract` records."""
    raw_csv = download_instruments_csv()
    return parse_instruments_stream(StringIO(raw_csv))
