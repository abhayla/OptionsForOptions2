"""Lane M, 27 Nov 2026: the B-N1 (#194) leg-stop figure, pinned through the one engine (ADR-008, ADR-330 (6)).

The PC book (coordinator, PR #722 comment 7209682005): NIFTY 1 Dec 2026 iron condor, one lot = 65 a leg, net entry
credit 73.35 a unit = 4,767.75 (the leg prices below are chosen to give that credit; only the sum enters the figure):
BUY 25650 PE, SELL 25750 PE, SELL 25950 CE, BUY 26050 CE. Max loss now = 4,767.75 - 100 x 65 = -1,732.25 (screen:
"now Rs 1,732.25"). A stop on the BOUGHT 25650 PE typed "Above 102.55" sells it for 6,665.75, leaving the sold 25750 PE
bare: the worst case is NIFTY at 0, 11,433.50 - 25,750 x 65 = -16,62,316.50 (screen: "Rs 16,62,316.50"). The figure is
right; this test keeps it from moving."""
from __future__ import annotations

import datetime
from decimal import Decimal

from ofo.engine.extremes import ContractTerms, book_extremes, exit_risk
from ofo.engine.legs import Instrument
from ofo.engine.orderbook import PaperOrder, net_positions

D = Decimal
EXPIRY = datetime.date(2026, 12, 1)
AT = datetime.datetime(2026, 11, 27, 4, 30, tzinfo=datetime.UTC)
TERMS = {"1": ContractTerms(Instrument.PE, D(25650), EXPIRY), "2": ContractTerms(Instrument.PE, D(25750), EXPIRY),
         "3": ContractTerms(Instrument.CE, D(25950), EXPIRY), "4": ContractTerms(Instrument.CE, D(26050), EXPIRY)}
BOOK = [PaperOrder("1", "BUY", 65, D("60.00"), "open", AT), PaperOrder("2", "SELL", 65, D("90.00"), "open", AT),
        PaperOrder("3", "SELL", 65, D("100.00"), "open", AT), PaperOrder("4", "BUY", 65, D("56.65"), "open", AT)]
STOP = PaperOrder("1", "SELL", 65, D("102.55"), "exit", AT)


def test_bn1_max_loss_before_and_after_the_long_put_stop_are_the_screens_figures() -> None:
    before = book_extremes(net_positions(BOOK, {}), TERMS, {}).max_loss
    after = book_extremes(net_positions([*BOOK, STOP], {}), TERMS, {}).max_loss
    assert (before, after) == (D("-1732.25"), D("-1662316.50"))


def test_bn1_the_bare_sold_put_is_the_leg_named() -> None:
    risk = exit_risk(BOOK, [STOP], TERMS)
    assert (risk.state, risk.exposed) == ("yes", ("2",))
    assert (risk.max_loss_before, risk.max_loss_after) == (D("-1732.25"), D("-1662316.50"))


def test_bn1_the_contract_year_does_not_enter_the_at_expiry_figure() -> None:
    """The printed "2028-12-01": had every leg carried that year the at-expiry figure would be the same (the expiry
    only groups legs); one leg on another year makes the book two-expiry and the figure absent, never wrong."""
    later = {k: ContractTerms(t.instrument, t.strike, datetime.date(2028, 12, 1)) for k, t in TERMS.items()}
    assert book_extremes(net_positions([*BOOK, STOP], {}), later, {}).max_loss == D("-1662316.50")
    mixed = {**TERMS, "2": later["2"]}
    assert book_extremes(net_positions([*BOOK, STOP], {}), mixed, {}).max_loss is None
