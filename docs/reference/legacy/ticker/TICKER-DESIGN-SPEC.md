<!-- Copied from abhayla/algochanakya@bf9faf7:docs/decisions/TICKER-DESIGN-SPEC.md on 2026-10-02 (ADR-047). Reference only: spec/ wins on any conflict; legacy facts are unverified for this project. -->

# Multi-Broker Ticker System - Design Specification

**Status:** Proposed (Documentation Phase)
**Date:** February 14, 2026
**Supersedes:** ADR-003 v2 (original 6-component proposal)

---

## Executive Summary

The multi-broker ticker system will be redesigned from **two hardcoded global singletons (853 lines) + 495-line websocket.py** to a **5-component broker-agnostic architecture**.

**Key Metrics:**
- **websocket.py:** 495 → ~90 lines (82% reduction)
- **Components:** 2 hardcoded singletons → 5 clean components
- **Broker-specific code in routes:** Eliminated entirely
- **Adding new broker:** 1 adapter file + factory registration (zero route changes)
- **Failover:** None → Automatic with make-before-break pattern

---

## 1. Why Redesign from Current ADR-003 v2?

The existing ADR-003 v2 document had valid architectural thinking but:
- **Never implemented** — all components are proposals, not code
- **Designed before broker exploration** — specifics of all 6 broker protocols weren't known
- **Too many components** — credential_manager as separate component adds complexity
- **Failover not integrated** with broker quirks (e.g., Kite requires user OAuth)

---

## 2. New 5-Component Architecture

### Component Reduction: 6 → 5

**Original ADR-003 v2:**
1. TickerAdapter
2. TickerPool
3. TickerRouter
4. HealthMonitor
5. FailoverController
6. **SystemCredentialManager** ← Eliminated

**New Design:**
1. TickerAdapter (per-broker WS connection)
2. TickerPool (lifecycle + **credentials** + ref-counting)
3. TickerRouter (user fan-out)
4. HealthMonitor (active monitoring)
5. FailoverController (make-before-break)

**Key change:** System credentials management moved inside TickerPool, reducing component count and simplifying wiring.

### Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                     FRONTEND (Vue)                            │
│   watchlist.js / optionchain.js / dashboard.js / positions.js│
└──────────────────────────┬───────────────────────────────────┘
                           │ ws://localhost:8001/ws/ticks?token=<jwt>
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                  websocket.py (~90 lines)                     │
│   JWT auth → TickerRouter.register → relay messages          │
└──────────────────────────┬───────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                     TickerRouter                              │
│   user_id → WebSocket mapping                                │
│   canonical_token → Set[user_id] subscription mapping        │
│   Fan out NormalizedTick to all subscribed user WebSockets   │
└──────────────┬───────────────────────┬───────────────────────┘
               │ subscribe/unsubscribe │ dispatch(ticks)
               ▼                       ▲
┌──────────────────────────────────────────────────────────────┐
│                      TickerPool                               │
│   Ref-counted subscriptions per broker                       │
│   Adapter creation / reuse / idle cleanup                    │
│   **System credentials management (integrated)**             │
│   Wires adapter.on_tick → router.dispatch                    │
└─────┬──────────────┬──────────────┬───────────────────────────┘
      │              │              │
      ▼              ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐
│ SmartAPI │  │   Kite   │  │  Upstox  │  ... (Dhan, Fyers, Paytm)
│ Adapter  │  │ Adapter  │  │ Adapter  │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │             │              │
     ▼             ▼              ▼
SmartAPI WS   Kite WS        Upstox WS
(binary)      (binary)       (protobuf)

┌──────────────────────────────────────────────────────────────┐
│                   HealthMonitor                               │
│   Observes all adapters (5s heartbeat loop)                  │
│   Health score = 0.3*latency + 0.3*tick_rate + 0.2*error_rate│
│                + 0.2*staleness                                │
│   Notifies FailoverController when health < 30               │
└──────────────────────────┬───────────────────────────────────┘
                           │ on_health_degraded callback
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                  FailoverController                           │
│   Make-before-break: secondary up BEFORE primary down        │
│   Flap prevention: 120s minimum between failover events      │
│   Auto-failback: primary health > 70 sustained 60s           │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. NormalizedTick Data Model

**Universal output format** — every adapter converts broker-specific data to this:

```python
@dataclass
class NormalizedTick:
    """Universal tick format. All adapters convert to this."""
    token: int                    # Canonical Kite instrument token (e.g., 256265)
    ltp: Decimal                  # Last traded price in RUPEES (not paise)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal                # Previous close
    change: Decimal               # ltp - close
    change_percent: Decimal       # ((ltp - close) / close) * 100
    volume: int
    oi: int                       # Open interest (0 for non-F&O)
    timestamp: datetime           # IST timezone
    broker_type: str              # Source broker ("smartapi", "kite", etc.)
```

**Key design decision:** Uses `Decimal` (not `float`) for prices in RUPEES. All adapters normalize paise→rupees where needed.

---

## 4. Component Specifications

### TickerAdapter (Abstract Base)

**File:** `backend/app/services/ticker/adapters/base.py`

**Responsibilities:**
- Per-broker WebSocket connection
- Binary/JSON/Protobuf parsing (broker-specific)
- Token translation (broker format ↔ canonical Kite format)
- Price normalization (paise→rupees where needed)
- Tick conversion to NormalizedTick
- Thread→asyncio bridge (for SmartAPI/Kite/Dhan)

**Key methods:**
```python
async def connect(self, credentials: dict) -> None
async def disconnect(self) -> None
async def reconnect(self, max_retries: int = 5) -> bool
async def subscribe(self, canonical_tokens: List[int], mode: str = "quote") -> None
async def unsubscribe(self, canonical_tokens: List[int]) -> None
def on_tick(self, callback: Callable[[List[NormalizedTick]], None]) -> None

# Abstract (broker-specific implementation)
@abstractmethod
async def _connect_ws(self, credentials: dict) -> None
@abstractmethod
async def _disconnect_ws(self) -> None
@abstractmethod
async def _subscribe_ws(self, broker_tokens: list, mode: str) -> None
@abstractmethod
async def _unsubscribe_ws(self, broker_tokens: list) -> None
@abstractmethod
def _parse_tick(self, raw_data: Any) -> List[NormalizedTick]
```

### TickerPool (Singleton)

**File:** `backend/app/services/ticker/pool.py`

**Responsibilities:**
- Adapter lifecycle (lazy creation, reuse, idle cleanup)
- **System credentials loading and refresh** (integrated, not separate component)
- Ref-counted subscription aggregation
- Adapter→Router tick dispatching
- Failover subscription migration

**Key methods:**
```python
async def initialize(self, router: TickerRouter, health_monitor: HealthMonitor) -> None
async def load_system_credentials(self) -> None   # NEW: Integrated credential loading
async def shutdown(self) -> None

async def subscribe(self, broker_type: str, tokens: List[int], mode: str) -> None
async def unsubscribe(self, broker_type: str, tokens: List[int]) -> None

async def get_or_create_adapter(self, broker_type: str) -> TickerAdapter
async def remove_adapter(self, broker_type: str) -> None
async def refresh_credentials(self, broker_type: str) -> None  # NEW: Per-broker refresh
async def migrate_subscriptions(self, from_broker: str, to_broker: str) -> None
```

**Credential management:**
```python
# Inside TickerPool:
self._credentials: Dict[str, dict] = {}  # broker_type → credentials
self._refresh_tasks: Dict[str, asyncio.Task] = {}  # Per-broker refresh loops

async def load_system_credentials(self) -> None:
    # Load from database: system_broker_credentials table
    # For each broker with is_active=True:
    #   1. Decrypt credentials
    #   2. Authenticate (SmartAPI: auto-TOTP, others: validate token)
    #   3. Store in self._credentials[broker_type]
    #   4. Schedule refresh loop if token expires

async def refresh_credentials(self, broker_type: str) -> None:
    # Per-broker refresh logic:
    # SmartAPI: 30 min before 5AM IST expiry
    # Upstox/Fyers/Paytm: Standard OAuth refresh
    # Dhan: No refresh (static token)
    # Kite: Log limitation (user OAuth only)
```

### TickerRouter (Singleton)

**File:** `backend/app/services/ticker/router.py`

**Responsibilities:**
- User WebSocket connection management
- Token→User mapping for tick fan-out
- Cached tick delivery on subscribe (instant UI update)
- Failover user routing changes

**Key methods:**
```python
async def register_user(self, user_id: str, ws: WebSocket, broker_type: str) -> None
async def unregister_user(self, user_id: str) -> None
async def subscribe(self, user_id: str, tokens: List[int], mode: str) -> None
async def unsubscribe(self, user_id: str, tokens: List[int]) -> None
async def dispatch(self, ticks: List[NormalizedTick]) -> None  # HOT PATH
async def switch_users_broker(self, from_broker: str, to_broker: str) -> None
def get_subscribed_tokens(self, broker_type: str) -> Set[int]
```

### HealthMonitor

**File:** `backend/app/services/ticker/health.py`

**Responsibilities:**
- 5-second heartbeat loop
- Per-adapter health scoring
- Consecutive low-score tracking
- Failover callback notification

**Health score formula (updated):**
```
health_score = (
    latency_score      * 0.30 +    # 30%: Average tick latency
    tick_rate_score    * 0.30 +    # 30%: Ticks per minute during market hours
    error_score        * 0.20 +    # 20%: Error rate in last 5 min
    staleness_score    * 0.20      # 20%: Time since last tick
)
```

**Component scoring:**
- `latency_score`: 100 if <100ms, 50 if 100-500ms, 0 if >1000ms
- `tick_rate_score`: min(100, tick_count_1min * 2)  // Expected ~50 ticks/min
- `error_score`: max(0, 100 - error_count_5min * 20)
- `staleness_score`: 100 if last_tick <10s ago, else max(0, 100 - seconds*2)

### Auth-Aware Error Classification

The health pipeline classifies broker auth errors via `token_policy.py` into 4 categories:

| Category | Health Impact | Action |
|----------|-------------|--------|
| RETRYABLE | Gradual decay (3 errors over 15s) | Exponential backoff, max 3 retries |
| RETRYABLE_ONCE | Gradual decay | 30s TOTP wait + 1 retry |
| NOT_RETRYABLE | Instant health=0 | Immediate failover (config error) |
| NOT_REFRESHABLE | Instant health=0 | Immediate failover + frontend notification |

**Auto-refreshable brokers**: SmartAPI (pyotp TOTP), Upstox (upstox-totp)
**Manual refresh required**: Kite (OAuth), Dhan (portal), Fyers (OAuth), Paytm (portal)

Flow: `Adapter._report_auth_error()` → `Pool._on_adapter_error()` → `HealthMonitor.record_auth_failure()` → `classify_auth_error()` → instant failover or gradual decay.

TickerPool auto-refreshes expired credentials before reconnecting (SmartAPI/Upstox only). FailoverController verifies primary credentials before failback.

### FailoverController

**File:** `backend/app/services/ticker/failover.py`

**Responsibilities:**
- Automatic broker failover (primary → secondary)
- Make-before-break pattern execution
- Flap prevention (120s cooldown)
- Auto-failback when primary recovers

**Failover sequence:**
```
1. HealthMonitor detects primary health < 30 for 3 consecutive checks (15s)
2. FailoverController checks: last failover >120s ago → proceed
3. Make-before-break:
   a. TickerPool.get_or_create_adapter(secondary) → connect + auth
   b. Get primary's subscribed tokens
   c. secondary.subscribe(tokens) → secondary now receiving ticks
   d. Wait 2s overlap (both adapters active, ticks from secondary)
   e. TickerRouter.switch_users_broker(primary, secondary)
   f. primary.unsubscribe(all) → cleanup
4. Broadcast to all users: {"type":"failover","from":"primary","to":"secondary"}
5. Set active_broker = secondary, is_failed_over = True
```

**Failback sequence:**
```
1. HealthMonitor detects primary health > 70 sustained for 60s
2. Execute reverse failover (same make-before-break)
3. Broadcast: {"type":"failback","from":"secondary","to":"primary"}
4. Set is_failed_over = False
```

---

## 5. Per-Broker Adapter Specifications

| Adapter | WS Library | Token Format | Price Normalization | Threading Model |
|---------|-----------|--------------|---------------------|-----------------|
| **SmartAPI** | `SmartWebSocketV2` (binary) | String ("99926000") | ÷ 100 (paise→rupees) | threading.Thread + asyncio bridge |
| **Kite** | `KiteTicker` (binary) | Integer (256265) = canonical | ÷ 100 (paise→rupees) | Library manages thread |
| **Upstox** | Custom protobuf | String ("NSE_FO\|12345") | None (already rupees) | asyncio-native |
| **Dhan** | Custom binary | String ("1234") | None (already rupees) | threading.Thread |
| **Fyers** | JSON WebSocket | String ("NSE:NIFTY50") | None (already rupees) | asyncio-native |
| **Paytm** | JSON WebSocket | String (RIC format) | None (already rupees) | asyncio-native |

**Full adapter details:** See plan Section 2.6

---

## 6. System Credentials Design

### Database Table: `system_broker_credentials`

```sql
CREATE TABLE system_broker_credentials (
    id SERIAL PRIMARY KEY,
    broker_type VARCHAR(20) UNIQUE NOT NULL,
    credentials_encrypted TEXT NOT NULL,    -- JSON encrypted with app/utils/encryption.py
    is_active BOOLEAN DEFAULT TRUE,
    last_refreshed TIMESTAMP,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Per-Broker System Credential Support

| Broker | System Creds? | Auth Method | Refresh Strategy |
|--------|--------------|-------------|------------------|
| **SmartAPI** | YES | Auto-TOTP (existing `smartapi_auth.py`) | 30 min before 5AM IST expiry |
| **Kite** | NO (user OAuth only) | Use first connected user's token | Expires 24h, user must re-login |
| **Upstox** | YES | OAuth2 app-level | Standard refresh |
| **Dhan** | YES | Static access_token | No refresh (never expires) |
| **Fyers** | YES | App-level access_token | Standard refresh |
| **Paytm** | YES | App-level tokens | Standard refresh |

**Kite limitation:** Kite Connect requires per-user OAuth. System uses first connected user's token as shared fallback. If no Kite users connected, Kite adapter cannot start.

---

## 7. Simplified websocket.py (~90 lines)

**File:** `backend/app/api/routes/websocket.py`

**Before (495 lines):** Hardcoded broker logic, token dictionaries, credential fetching, broker selection if/else.

**After (~90 lines):**
```python
@router.websocket("/ws/ticks")
async def websocket_ticks(websocket: WebSocket, token: str = Query(...)):
    # 1. Accept WebSocket
    # 2. Authenticate JWT → get user_id
    # 3. Lookup user's market_data_source preference (default: "smartapi")
    # 4. TickerRouter.register_user(user_id, websocket, broker_type)
    # 5. Send {"type": "connected", "source": broker_type}
    # 6. Message loop:
    #    - "subscribe" → TickerRouter.subscribe(user_id, tokens, mode)
    #    - "unsubscribe" → TickerRouter.unsubscribe(user_id, tokens)
    #    - "ping" → send {"type": "pong"}
    # 7. On disconnect: TickerRouter.unregister_user(user_id)
```

**Eliminated:**
- `KITE_TO_SMARTAPI_INDEX` / `SMARTAPI_TO_KITE_INDEX` dicts
- `get_user_broker_connection()` helper
- `get_smartapi_credentials()` helper
- `fetch_initial_index_quotes()` helper
- All broker selection if/else logic
- All token translation code

**Zero broker-specific code remains in routes.**

---

## 8. Data Flow Examples

### Flow 1: User Subscribes to NIFTY

```
1. Frontend → ws: {"action":"subscribe","tokens":[256265],"mode":"quote"}
2. websocket.py → TickerRouter.subscribe(user_id="42", tokens=[256265], mode="quote")
3. TickerRouter → TickerPool.subscribe(broker_type="smartapi", tokens=[256265], mode="quote")
4. TickerPool checks ref count:
   - Token 256265 ref_count was 0 → needs broker subscription
   - ref_count becomes 1
5. TickerPool → SmartAPIAdapter.subscribe([256265])
6. Adapter: 256265 → TokenManager → "99926000" (SmartAPI token)
7. Adapter → SmartAPI WS: subscribe(mode=2, tokens=[{"exchangeType":1,"tokens":["99926000"]}])
8. websocket.py → user: {"type":"subscribed","tokens":[256265],"source":"smartapi"}
```

### Flow 2: Tick Arrives

```
1. SmartAPI WS → binary tick data (background thread)
2. SmartAPIAdapter._parse_tick(): extract token "99926000", ltp 2450050 (paise)
3. Adapter._parse_tick():
   - TokenManager: "99926000" → 256265 (canonical)
   - Price: 2450050 → Decimal("24500.50")
   - Build NormalizedTick(token=256265, ltp=Decimal("24500.50"), ...)
4. Adapter._dispatch_from_thread() → asyncio.run_coroutine_threadsafe
5. TickerPool._on_adapter_tick("smartapi", [NormalizedTick(...)])
6. HealthMonitor.record_tick("smartapi")
7. TickerRouter.dispatch([NormalizedTick(...)])
8. Router: token 256265 → {user_42, user_78} → send JSON to each WebSocket
```

### Flow 3: Startup Sequence

```
1. main.py lifespan → startup
2. Create singletons: TickerRouter(), TickerPool(), HealthMonitor(), FailoverController()
3. Wire: pool.initialize(router, health_monitor)
4. Wire: failover.set_dependencies(pool, router, health_monitor)
5. health_monitor.on_health_degraded(failover.on_health_degraded)
6. pool.load_system_credentials():
   - SmartAPI: authenticate with auto-TOTP → store tokens
   - Dhan: validate static token
   - Fyers: validate access token
   - Kite: log "requires user OAuth — will use first connected user's token"
7. health_monitor.start() → begin 5s loop
8. Log: "Ticker system ready. Primary: smartapi"
9. No adapters created yet (lazy — created on first user subscription)
```

### Flow 4: Failover (SmartAPI → Fyers)

```
1.  HealthMonitor: SmartAPI health = 25 (below 30) for 3 consecutive checks
2.  HealthMonitor → FailoverController.on_health_degraded("smartapi", 25)
3.  Controller: last failover was 180s ago (>120s cooldown) → proceed
4.  Controller._select_fallback_broker(exclude="smartapi"):
    - Check ranking: ["smartapi","fyers","dhan","upstox","paytm","kite"]
    - "fyers" has system credentials + health OK → selected
5.  Execute make-before-break:
    a. pool.get_or_create_adapter("fyers") → connect with system credentials
    b. tokens = pool.get_subscribed_tokens("smartapi") → {256265, 260105, ...}
    c. pool.subscribe("fyers", tokens, "quote") → Fyers adapter now receiving ticks
    d. asyncio.sleep(2) → overlap period, both adapters active
    e. router.switch_users_broker("smartapi", "fyers") → users get Fyers ticks
    f. pool.unsubscribe("smartapi", tokens) → clean up SmartAPI
6.  router.broadcast({"type":"failover","from":"smartapi","to":"fyers"})
7.  active_broker = "fyers", is_failed_over = True
```

---

## 9. Implementation Phases

### Phase T1: Core Infrastructure (6 hours)

**Files to create:**
- `backend/app/services/ticker/__init__.py`
- `backend/app/services/ticker/models.py` — NormalizedTick
- `backend/app/services/ticker/adapters/__init__.py`
- `backend/app/services/ticker/adapters/base.py` — TickerAdapter ABC
- `backend/app/services/ticker/pool.py` — TickerPool (with credentials)
- `backend/app/services/ticker/router.py` — TickerRouter

### Phase T2: SmartAPI + Kite Adapters (8 hours)

**Files to create:**
- `backend/app/services/ticker/adapters/smartapi.py`
- `backend/app/services/ticker/adapters/kite.py`

**Files to modify:**
- `backend/app/api/routes/websocket.py` — Rewrite from 495 to ~90 lines
- `backend/app/main.py` — Add ticker system startup/shutdown

### Phase T3: Health + Failover (6 hours)

**Files to create:**
- `backend/app/services/ticker/health.py` — HealthMonitor
- `backend/app/services/ticker/failover.py` — FailoverController

**Files to modify:**
- `backend/app/services/ticker/pool.py` — Wire health/failover callbacks
- `backend/app/main.py` — Wire FailoverController

### Phase T4: System Credentials + Remaining Adapters (6 hours)

**Files to create:**
- `backend/app/models/system_broker_credentials.py` — DB model
- `backend/alembic/versions/xxx_add_system_broker_credentials.py` — Migration
- `backend/app/services/ticker/adapters/upstox.py` — Stub
- `backend/app/services/ticker/adapters/dhan.py` — Stub
- `backend/app/services/ticker/adapters/fyers.py` — Stub
- `backend/app/services/ticker/adapters/paytm.py` — Stub

**Files to modify:**
- `backend/app/services/ticker/pool.py` — Add credential loading/refresh

### Phase T5: Frontend + Cleanup + Documentation (2 hours)

**Files to modify:**
- `frontend/src/constants/websocket.js` — Add FAILOVER/FAILBACK types
- `frontend/src/stores/watchlist.js` — Handle failover messages
- Deprecate: `backend/app/services/legacy/smartapi_ticker.py`
- Deprecate: `backend/app/services/legacy/kite_ticker.py`

**Total: ~28 hours**

---

## 10. Files to Create/Modify/Deprecate

### Create (Core Components)

- `backend/app/services/ticker/models.py`
- `backend/app/services/ticker/adapters/base.py`
- `backend/app/services/ticker/adapters/smartapi.py`
- `backend/app/services/ticker/adapters/kite.py`
- `backend/app/services/ticker/adapters/upstox.py` (stub)
- `backend/app/services/ticker/adapters/dhan.py` (stub)
- `backend/app/services/ticker/adapters/fyers.py` (stub)
- `backend/app/services/ticker/adapters/paytm.py` (stub)
- `backend/app/services/ticker/pool.py`
- `backend/app/services/ticker/router.py`
- `backend/app/services/ticker/health.py`
- `backend/app/services/ticker/failover.py`
- `backend/app/models/system_broker_credentials.py`
- `backend/alembic/versions/xxx_add_system_broker_credentials.py`

### Modify

- `backend/app/api/routes/websocket.py` (REWRITE ~495→~90 lines)
- `backend/app/main.py` (add ticker lifecycle)
- `frontend/src/constants/websocket.js` (add failover types)
- `frontend/src/stores/watchlist.js` (handle failover messages)
- `docs/decisions/003-multi-broker-ticker-architecture.md` (REWRITE with new design)
- `docs/architecture/websocket.md` (REWRITE)
- `docs/architecture/multi-broker-ticker-implementation.md` (REWRITE)
- `docs/api/multi-broker-ticker-api.md` (REWRITE)
- `backend/CLAUDE.md` (update ticker section)
- `CLAUDE.md` (root - update WebSocket/ticker references)

### Deprecate (mark as legacy)

- `backend/app/services/brokers/market_data/ticker_base.py` — Dead interface, replaced by new adapters
- `backend/app/services/legacy/smartapi_ticker.py` — Mark deprecated
- `backend/app/services/legacy/kite_ticker.py` — Mark deprecated

---

## 11. Success Criteria

- ✅ websocket.py reduced from 495 to ~90 lines
- ✅ Zero broker-specific code in routes
- ✅ Adding new broker requires only 1 adapter file + factory registration
- ✅ Automatic failover works with make-before-break pattern
- ✅ Health endpoint returns adapter scores
- ✅ Frontend handles failover seamlessly (connection stays open)
- ✅ Ref-counted subscriptions work (100 users on NIFTY = 1 broker subscription)
- ✅ System credentials properly separated from user credentials

---

## 12. Key Design Decisions

### 1. System Credentials in TickerPool (Not Separate Component)

**Rationale:** Original ADR-003 v2 had `SystemCredentialManager` as 6th component. Merged into TickerPool because:
- Reduces component count
- Simplifies wiring (no extra dependency injection)
- Credential refresh naturally paired with adapter lifecycle

### 2. NormalizedTick Uses Decimal (Not Float)

**Rationale:** Prices must be exact for display. Decimal prevents floating-point errors. Performance impact is acceptable (ticks are display-only, not order pricing).

### 3. Kite as Failover-Only

**Rationale:** Kite Connect requires per-user OAuth (no system credentials possible). Uses first connected user's token as shared fallback. SmartAPI is primary (has system credentials via auto-TOTP).

### 4. Make-Before-Break Failover Pattern

**Rationale:** Subscribe on secondary BEFORE unsubscribing from primary. Ensures zero-gap tick delivery. 2s overlap allows ticks to flow from secondary before primary cleanup.

### 5. Lazy Adapter Creation

**Rationale:** Adapters created on first user subscription, not on startup. Reduces resource usage when no users connected. Idle cleanup after 300s of zero subscriptions.

---

## 13. Migration Strategy

### Step 1: Parallel Development

Build new ticker system in `backend/app/services/ticker/` (separate from legacy). Both old and new systems coexist during development.

### Step 2: Validation

Phase-by-phase testing:
- T1: All imports work, backend starts
- T2: Full tick pipeline through new architecture
- T3: Failover triggers and completes
- T4: Credential loading works
- T5: Frontend handles failover messages

### Step 3: Cutover

Rewrite `websocket.py` to use new system. Mark legacy singletons as deprecated (don't delete — may need rollback).

### Step 4: Stabilization

Run both systems for 2 weeks. Delete legacy after successful operation.

---

## 14. Rollback Plan

**Phase T1-T2 Rollback:** Drop new ticker directory, revert websocket.py from git
**Phase T3 Rollback:** Keep basic adapters, remove failover components
**Phase T4-T5 Rollback:** Revert websocket.py, reconnect to legacy singletons

**Git Tags:** Tag `pre-ticker-refactor` before Phase T1, `post-phase-{N}` after each phase.

---

## 15. Related Documentation

- `.claude/WORKFLOW-DESIGN-SPEC.md` — Workflow system redesign (Part 1)
- `docs/decisions/003-multi-broker-ticker-architecture.md` — Full ADR (will be rewritten)
- `docs/architecture/websocket.md` — WebSocket architecture (will be rewritten)
- `docs/architecture/multi-broker-ticker-implementation.md` — Implementation guide (will be rewritten)
- `docs/api/multi-broker-ticker-api.md` — API reference (will be rewritten)

---

**End of Design Specification**
