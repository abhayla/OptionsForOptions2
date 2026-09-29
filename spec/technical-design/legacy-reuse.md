# Legacy code reuse plan

Decision: ADR-043 (copy/adapt with provenance). Surveys (2026-09-29, independent readers, read-only):
`docs/reference/legacy/algochanakya-survey.md`, `ofo-newofo-survey.md`, `optionsforoptions-csharp-survey.md`.

## Sources
| Repo | Stack | Commit surveyed | Use |
|---|---|---|---|
| `abhayla/algochanakya` (public) | Python 3.13 / FastAPI 0.123, async SQLAlchemy 2, PostgreSQL, Redis; Vue 3.5 + Vite 7 | `2a868db` (origin/main, 2026-08-27) | **Main source**: market data, broker adapter, instrument master, Greeks, templates |
| `abhayla/OFO` (private) | TypeScript / Node + React, Prisma | `ebc5cde` (2025-08-02) | Reference: Kite login handshake, WebSocket + Redis pub/sub pattern |
| `abhayla/NewOFO` (private) | TypeScript / Node + React | 2025-07-25 | Reference: option-chain and positions page layout only (its data path scrapes NSE: not allowed, ADR-012) |
| `abhayla/OptionsForOptions` (private) | C# .NET Framework 4.8 WebForms, MySQL | `3ecd877` | Reference: payoff formula shape, strategy list; nothing copyable (float money, no tests, unsafe SQL) |

## What to copy or adapt (from algochanakya, paths under `backend/app/`)
| # | Source | Verdict | Change needed | Requirements |
|---|---|---|---|---|
| 1 | `ticker/models.py` NormalizedTick, `ticker/adapter_base.py`, `ticker/pool.py`, `ticker/router.py` | ADAPT | Behind our market-data gateway; health states per ADR-015 | REQ-048, REQ-050 |
| 2 | `services/brokers/base.py` order/position/quote types + BrokerAdapter | ADAPT | Mandatory `strategy_id` on every order (ADR-002); margin preview; Zerodha only in V1, seam kept for others | REQ-054 |
| 3 | `ticker/adapters/kite.py` KiteTicker → asyncio bridge | ADAPT | Blocked until Zerodha's written answer (ADR-034) | REQ-048 |
| 4 | `kite_adapter.py` Kite → unified converters | ADAPT | Decimal fields | REQ-054, REQ-060 |
| 5 | `services/options/option_chain_cache.py` Redis cache + request coalescing | ADAPT | No cross-user sharing of one user's Zerodha data until ADR-034 is answered | REQ-050 |
| 6 | `services/options/vectorized_greeks.py` IV + Greeks | ADAPT | Moves inside the one calculation engine; results converted to Decimal at the boundary | REQ-032, REQ-034 |
| 7 | `backend/scripts/seed_strategies.py` 22 templates | ADAPT | Strike offsets per index (ADR-042); decision-support wording (ADR-003) | REQ-028 |
| 8 | `ticker/health.py`, `ticker/token_policy.py` | ADAPT | Drop TOTP auto-login; never hold Zerodha credentials (ADR-020) | REQ-049 |
| 9 | `api/.../auth.py` lines 60–175 Kite OAuth callback | REFERENCE | Rewrite: legacy stores the access token in plaintext | REQ-015 |
| 10 | `services/instrument_master.py` | ADAPT | Add BFO (SENSEX); the ONLY source of lot size and strike gap | REQ-053 |

## Not reused
Every legacy P&L/payoff/scenario calculator (float money, logic copied in several places); positions
exit/add/exit-all endpoints and optional `strategy_id` on orders (break ADR-002); AutoPilot auto-execution
(`execution_mode='auto'` default breaks ADR-009/ADR-017); legacy auth/users; there is no legacy registration,
entitlement, payments or admin code in any repo.

## Risks found in the legacy repos (owner actions)
- `algochanakya` is **public** and two docs files contain a real-format Kite API key and secret (file:line in the
  survey; values never copied). Owner to regenerate the secret in the Kite developer console.
- `algochanakya` recorded Upstox test fixtures contain the owner's email.
- `OptionsForOptions` (private) has a Google client secret, a Telegram bot token and a MySQL password in code.

## Broker adapter boundary (W-026, REQ-036 AC-1..AC-3, ADR-002; added 2026-09-29)
Any broker adapter copied or adapted from `algochanakya` (or written new) plugs in at exactly one point:
- It implements only the private transport `ofo.execution.send_guard._Transport.submit(request) -> broker order id`,
  and it is constructed only inside `ofo/execution/send_guard.py`. It never receives an `Order`, a plan or a
  preparation, only a `_BrokerRequest` built by the broker sink.
- The sink (`_BrokerSink`) derives every broker field from the strategy's bound `StrategyRecord` and the instrument
  catalogue: trading symbol (underlying, instrument type, expiry, strike to the one catalogue entry), side (the leg's
  side; Close uses the opposite), quantity (within the room the record and the fill ledger leave), strategy and
  version. It refuses anything else and then calls the transport.
- The only public route to the sink is `ofo.execution.partial.submit_confirmed`. A runtime test walks every `ofo`
  module and fails if any other public name returns or accepts a request, transport or sink.
- Trust boundary: this stops accidental misuse by platform code. Code running in the same process can still reach
  private names, or import a raw broker client, on purpose; that is out of scope and must be caught in review.
  The adapter must not expose any public "place order" function of its own.
