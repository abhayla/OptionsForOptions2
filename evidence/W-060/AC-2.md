---
work_item: W-060
ac: AC-2
requirement: REQ-072
ac_fp: "d0a6b6685613"
result: pass
verified_by: "verifier (sonnet, fresh context)"
builder: "builder (opus round 3, sonnet round 4)"
date: '2026-10-08'
commands: "git diff --stat f654d39 43919f1; python tools/ac_fp.py REQ-072 AC-2 --yaml; python -m pytest -q -p no:cacheprovider; python -m pytest -q -p no:cacheprovider tests/engine/test_pricing_scan.py; python r3s/attack.py <worktree>; python -B inline violations() probes; python -B inline probes of StrategyInput/ModelInputs/build_table/build_level_set/implied_vol/greeks with bad spot"
---

AC: AC-2
result: pass
commands: git diff --stat f654d39 43919f1; python tools/ac_fp.py REQ-072 AC-2 --yaml; python -m pytest -q -p no:cacheprovider; python -m pytest -q -p no:cacheprovider tests/engine/test_pricing_scan.py; python r3s/attack.py <worktree>; python -B inline violations() probes; python -B inline probes of StrategyInput/ModelInputs/build_table/build_level_set/implied_vol/greeks with bad spot
observed: Full suite 1784 passed; scan tests 45 passed. attack.py: stale label on scenario_values/payoff_graph/build_table/IV/Greeks/estimate; unhealthy spot -> SpotRefused; missing forward -> ForwardUnavailable; mismatched level_set refused. violations() flags getattr(model,'_bs'), ModelInputs.__new__(ModelInputs), object.__new__ via alias, subclassing (direct, via module, ExpiryModel), importing bs_price/estimate_now/black_scholes, import_module of engine, _TOKEN import, ._make. StrategyInput without spot -> TypeError; bare Decimal spot/model_inputs/implied_vol/greeks -> ValueError; StrategyInput passed to build_level_set/build_table -> ValueError.
attack: Judged against ADR-065 (guards stop accidental misuse; the CI scan flags deliberate reaching-in). Deliberate runtime forging (object.__new__ + object.__setattr__, subclass, _make with _TOKEN) succeeds at runtime but every one of those shapes is flagged by the scan. Scan misses x.__class__.__new__(x.__class__) and type('E',(ModelInputs,),{}) - deliberate-forging shapes, accepted under ADR-065 (review plus best-effort scan). copy.copy and dataclasses.replace are refused at runtime.

Recorded by the orchestrator from the verifier's returned block.
Recorded 2026-10-08 at PR #135 head 43919f1. History: verifier red twice on this class (rounds 1-2), independent root-cause review, round 3 type redesign, round-3 review (1 MAJOR, 3 MINOR), round 4 (owner-approved last fix), final verifier red on deliberate forging, owner decision ADR-065, scan fix, this verifier PASS.
