"""REQ-060 AC-2 (W-037): the linear compare() gives exactly the pre-W-037 result on every configuration.

W-037 changed HOW compare() finds each contract's holders, the other holders' units, the platform breakdown and each
strategy's broker share (an index built once per run instead of a scan of every strategy per contract). It must not
change WHAT it reports: which strategies are blocked (Q199, Q224: a shared contract that disagrees blocks every
holder), each mismatch's kind, states, breakdown, difference and next action, and every strategy's broker share.

The oracle is ``compare_reference.py``, the origin/main comparison logic frozen verbatim. 600 seeded random accounts
over a small contract universe (so contracts are shared, strikes/expiries collide and move) mix active, pending,
proposal-only, never-active and exited strategies with standalones and external changes; every report must be equal
field for field, and an input either run refuses must be refused by both with the same message.
"""
from __future__ import annotations

import random
from decimal import Decimal as D

import pytest

from compare_reference import compare_reference
from ofo.engine import Action, Instrument
from ofo.reconciliation.compare import MismatchKind, ReconciliationError, compare
from ofo.strategy.definition import DefinitionLeg, StrategyDefinition
from ofo.strategy.versions import ExecutionResult, Position, ResultStatus, StrategyRecord
from recon_fixtures import EXPIRY, NEXT_EXPIRY, T0, at, clock

SEED = 20260929
CASES = 600
STRIKES = ("22800", "23000", "23200", "23400")
EXPIRIES = (EXPIRY, NEXT_EXPIRY)
UNIVERSE = [("NIFTY", i, D(s), e) for i in (Instrument.CE, Instrument.PE) for s in STRIKES for e in EXPIRIES]
STATES = ("active", "active", "active+pending", "proposal-only", "never-active", "exited")


def _definition(rng: random.Random) -> StrategyDefinition:
    contracts = rng.sample(UNIVERSE, rng.randint(1, 3))
    return StrategyDefinition("NIFTY", tuple(
        DefinitionLeg(rng.choice((Action.BUY, Action.SELL)), inst, strike, expiry, rng.choice((25, 50, 75)))
        for _, inst, strike, expiry in contracts
    ))


def _record(rng: random.Random, state: str, reference: str) -> StrategyRecord:
    rec = StrategyRecord(_definition(rng), at=T0, clock=clock)
    if state == "never-active":
        return rec
    v1 = rec.propose_execution(at=at(1))
    rec.confirm(v1.number, at=at(2))
    if state == "proposal-only":
        return rec
    rec.apply_result(ExecutionResult(1, ResultStatus.COMPLETE, v1.intended_position, at(3), reference))
    if state == "active+pending":
        proposal = None
        while proposal is None:  # an edit identical to the active version proposes nothing; draw again
            proposal = rec.edit(_definition(rng), at=at(4), reason="adjust")
        rec.confirm(proposal.number, at=at(5))
    elif state == "exited":
        rec.observe_broker_position(Position(), at=at(4), reference=f"{reference}-flat")
        rec.mark_exited(at=at(5), actor="user", resolution="closed in Kite")
    return rec


def _account(rng: random.Random) -> tuple[dict, dict, dict, dict]:
    strategies = {f"S{i:02d}": _record(rng, rng.choice(STATES), f"e{i}") for i in range(rng.randint(0, 8))}
    standalone = {c: rng.choice((-50, -25, 25, 50)) for c in rng.sample(UNIVERSE, rng.randint(0, 2))}
    # Start from the true platform picture, then perturb it the ways Zerodha can differ.
    broker = dict(standalone)
    for rec in strategies.values():
        if rec.active_version is not None and not rec.exited:
            for contract, units in rec.active_version.intended_position.as_dict().items():
                broker[contract] = broker.get(contract, 0) + units
    for _ in range(rng.randint(0, 3)):
        contract = rng.choice(UNIVERSE)
        move = rng.choice(("set", "zero", "strike", "expiry", "flip"))
        units = broker.pop(contract, 0)
        if move == "set":
            broker[contract] = rng.choice((-150, -75, -50, -25, 25, 50, 75, 150))
        elif move == "flip":
            broker[contract] = -units
        elif move in ("strike", "expiry"):
            _, inst, strike, expiry = contract
            target = (("NIFTY", inst, D(rng.choice(STRIKES)), expiry) if move == "strike"
                      else ("NIFTY", inst, strike, rng.choice(EXPIRIES)))
            broker[target] = broker.get(target, 0) + units
    broker = {c: u for c, u in broker.items() if u}
    external = {c: rng.choice((-25, 25)) for c in rng.sample(UNIVERSE, rng.randint(0, 2))}
    return broker, strategies, standalone, external


def _outcome(run, broker, strategies, standalone, external):
    try:
        return run(broker, strategies, standalone, at=at(10), external=external, clock=clock)
    except ReconciliationError as exc:
        return ("refused", str(exc))


def test_ac2_linear_compare_equals_the_pre_w037_compare_on_600_seeded_accounts():
    """AC-2 (W-037): 600 seeded random accounts; the new compare() and the frozen origin/main compare give equal
    reports (blocked strategies, every mismatch field, every broker share) or the same refusal."""
    rng = random.Random(SEED)
    kinds, blocked_total, shared_blocks, agreeing = set(), 0, 0, 0
    for case in range(CASES):
        broker, strategies, standalone, external = _account(rng)
        new = _outcome(compare, broker, strategies, standalone, external)
        old = _outcome(compare_reference, broker, strategies, standalone, external)
        assert new == old, f"case {case}: {broker=} {standalone=} {external=}"
        if isinstance(new, tuple):
            continue
        assert new.blocked_strategy_ids == old.blocked_strategy_ids
        assert new.shares == old.shares and new.mismatches == old.mismatches
        assert all(new.share(sid) == position for sid, position in old.shares)  # the indexed lookup, per strategy
        kinds.update(m.kind for m in new.mismatches)
        blocked_total += len(new.blocked_strategy_ids)
        shared_blocks += sum(1 for m in new.mismatches if len(m.strategy_ids) > 1)
        agreeing += not new.mismatches
    # The generator must reach the cases that matter, or the equality above proves little. Measured with this seed
    # (2026-09-29): all 9 kinds, 243 blocked strategies, 55 multi-holder (Q224) mismatches, 340 agreeing runs.
    assert kinds == set(MismatchKind), set(MismatchKind) - kinds
    assert blocked_total >= 200 and shared_blocks >= 40 and agreeing >= 100, (blocked_total, shared_blocks, agreeing)


def test_ac2_equivalence_oracle_is_not_the_product_code():
    """AC-2 (W-037): guard against a vacuous oracle -- the reference must be separate code, not an alias."""
    assert compare_reference is not compare
    assert compare_reference.__module__ == "compare_reference"


@pytest.mark.parametrize("state", sorted(set(STATES)))
def test_ac2_generator_builds_every_strategy_state(state):
    """AC-2 (W-037): each record state the equivalence test mixes really is that state."""
    rec = _record(random.Random(1), state, "e-x")
    expected = {
        "active": (True, False, False), "active+pending": (True, True, False), "proposal-only": (False, True, False),
        "never-active": (False, False, False), "exited": (True, False, True),
    }[state]
    assert (rec.active_version is not None, rec.proposed_version is not None, rec.exited) == expected
