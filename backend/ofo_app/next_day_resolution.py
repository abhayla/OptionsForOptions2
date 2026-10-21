"""#352-1: an execution plan left open from an earlier trading day is resolved the next day, never guessed.

Spec basis: ADR-109 (2) (a strategy owns "exactly the fills of orders this app placed"; outside lots are attached
"never automatically"); ADR-109 (4) (the "Kite flat -> mark exited" action); ADR-110 (a same-day open plan waits on
today's book); ADR-111 (a hand close on Kite: "the app records the resulting mismatch"); ADR-016 (Zerodha is the
authority, submitted is not executed); REQ-060 AC-1, AC-4, AC-6; Q222 (the block lifts only through a recorded
resolution).

Copy from: none - extends ``reconcile_attribution`` (the decision, ``decide_earlier_day``) and writes through
``execution_plan_store.close_plan`` and ``reconciliation_store.record_mismatch``.

``resolve_earlier_day_plans`` reads the account itself (``reconcile_attribution.survey_account``: every strategy and
all its plans through the store reader) and, for each earlier-day open plan (created before today's IST date, no tag
in today's book):

- ``nothing_placed`` (the allow-list: on every contract the plan touches, Zerodha's net equals the base of every
  other stored fill plus the standalone, the contract has not expired, no other unsettled plan touches it, one side):
  ``close_plan(reason="nothing_placed")`` stores 0 per order. For an EXIT this frees the strategy for a new EXIT.
- anything else: per unsettled contract, one mismatch for the plan's strategy AND for every strategy holding units
  there by its stored fills (Q224 "blocks every holder"; the store dedupes a repeat), keyed on the contract's one
  stored text (``reconcile_attribution.key_text``: two ids of one contract are one key); then
  ``close_plan(reason="unresolved_from_positions")`` (0 stored per order; the mismatch carries the sticky block until
  a recorded resolution, Q222). Never ``filled`` and never ``exited``: an EXIT whose net is 0 is lifted only by
  ``kite_flat_marked_exited`` (the store checks the recorded Zerodha net is 0).

Mismatch numbers: ``expected_units`` is the base (what the stored fills say without the plan), ``zerodha_units`` the
net. Where those agree but the contract still cannot be settled (expired, shared, mixed sides), ``expected_units`` is
what Zerodha would hold had the plan filled in full (base + planned; base + the plan's gross units there when its
orders cancel), so the stored row is a real disagreement; the report names the reason and both numbers.

The time is the platform clock (``sources.clock``), never a caller's value. Writers other than the two stores are
accepted only under ``APP_ENV=test``. Transaction control (commit) stays with the caller; a failed write raises and the
caller rolls back the whole run. No route is wired here (GC-3F wires it with #380-2). Adopting the next-day net as a
fill is not built (owner question OQ-GC2h-1).
"""
from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field

from ofo_app import execution_plan_store, reconciliation_store
from ofo_app import reconcile_attribution as ra
from ofo_app.config import app_env

#: The mismatch source of this resolution (``reconciliation_store.SOURCES``).
SOURCE = "next_day_resolution"
#: The only APP_ENV under which a non-default writer (a test fake) is accepted.
_TEST_ENV = "test"

ClosePlan = Callable[..., Awaitable[object]]
RecordMismatch = Callable[..., Awaitable[int]]


@dataclass(frozen=True)
class PlanWriter:
    """The write seam: the plan store's close and the reconciliation store's mismatch record."""

    close_plan: ClosePlan = execution_plan_store.close_plan
    record_mismatch: RecordMismatch = reconciliation_store.record_mismatch


@dataclass(frozen=True)
class Resolved:
    """One earlier-day plan as resolved: the close reason written and the mismatch ids recorded (empty for
    ``nothing_placed``), with the decision it rests on."""

    strategy_id: int
    plan_number: int
    action: str
    reason: str
    mismatch_ids: tuple[int, ...]
    decision: ra.EarlierDay = field(repr=False)


def _check_writer(writer: object) -> PlanWriter:
    if type(writer) is not PlanWriter:
        raise ra.AttributionError(f"writer must be a PlanWriter, got {writer!r}")
    is_default = (writer.close_plan is execution_plan_store.close_plan
                  and writer.record_mismatch is reconciliation_store.record_mismatch)
    if not is_default and app_env() != _TEST_ENV:
        raise ra.AttributionError("a writer other than the plan and reconciliation stores is accepted only under "
                                  "APP_ENV=test")
    return writer


def mismatch_numbers(contract: ra.EarlierDayContract) -> tuple[int, int]:
    """(expected_units, zerodha_units) for the stored mismatch row; never an agreeing pair (module docstring)."""
    if contract.expected_units != contract.zerodha_units:
        return contract.expected_units, contract.zerodha_units
    delta = contract.planned_units or contract.gross_units  # gross >= 1: every order's quantity is positive
    return contract.expected_units + delta, contract.zerodha_units


def _report(decision: ra.EarlierDay, contract: ra.EarlierDayContract, at: datetime.datetime) -> dict[str, object]:
    return {"plan_number": decision.plan_number, "action": decision.action, "reason": contract.reason,
            "expected_without_plan": contract.expected_units, "zerodha_units": contract.zerodha_units,
            "planned_units": contract.planned_units, "instrument_ids": list(contract.instrument_ids),
            "tags": list(contract.tags), "at": at.isoformat()}


def mismatch_holders(decision: ra.EarlierDay, contract: ra.EarlierDayContract, survey: ra.Survey) -> tuple[int, ...]:
    """Who gets a stored mismatch for one unsettled contract (Q224 "blocks every holder", #352-1 round 2 MAJOR 1): the
    plan's strategy and every strategy holding units there by its stored fills (``survey.known``, read from the
    stores), each once, in id order."""
    return tuple(sorted({decision.strategy_id, *ra.holders(survey.known, contract.key)}))


async def resolve_earlier_day_plans(  # noqa: PLR0913 the attribution's inputs plus the writer
    account: ra.Account,
    standalone: Mapping[ra.ContractKey, int],
    broker_net: Mapping[ra.ContractKey, int],
    order_book: Sequence[ra.OrderRow],
    sources: ra.Sources,
    *,
    writer: PlanWriter | None = None,
) -> tuple[Resolved, ...]:
    """Close every earlier-day open plan of the account: ``nothing_placed`` on the allow-list, else the mismatch
    records and ``unresolved_from_positions`` (module docstring). Inputs are the attribution's: Zerodha's net and
    today's order book as the reply adapter parsed them, the recorded standalone units."""
    checked = _check_writer(PlanWriter() if writer is None else writer)
    if not isinstance(sources, ra.Sources):
        raise ra.AttributionError(f"sources must be a Sources, got {sources!r}")
    at = sources.clock()
    survey = await ra.survey_account(account, standalone, broker_net, order_book, sources, at=at)
    done = []
    for decision in survey.earlier:
        ids: list[int] = []
        if decision.outcome == ra.EARLIER_NOTHING_PLACED:
            await checked.close_plan(account.conn, account.user_ref, decision.strategy_id, decision.plan_number,
                                     reason=ra.EARLIER_NOTHING_PLACED)
        else:
            for contract in decision.contracts:
                if not contract.reason:
                    continue
                expected, zerodha = mismatch_numbers(contract)
                key = ra.key_text(sources.catalogue, contract.key)
                for holder in mismatch_holders(decision, contract, survey):
                    report = {**_report(decision, contract, at), "strategy_id": holder,
                              "role": "plan" if holder == decision.strategy_id else "holder"}
                    ids.append(await checked.record_mismatch(
                        account.conn, account.user_ref, holder, contract_key=key, expected_units=expected,
                        zerodha_units=zerodha, report=report, source=SOURCE))
            await checked.close_plan(account.conn, account.user_ref, decision.strategy_id, decision.plan_number,
                                     reason=ra.EARLIER_UNRESOLVED)
        done.append(Resolved(decision.strategy_id, decision.plan_number, decision.action, decision.outcome,
                             tuple(ids), decision))
    return tuple(done)


__all__ = ["SOURCE", "PlanWriter", "Resolved", "mismatch_holders", "mismatch_numbers", "resolve_earlier_day_plans"]
