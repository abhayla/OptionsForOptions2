<!-- Copied from abhayla/algochanakya@bf9faf7:docs/specs/option-chain-performance-spec.md on 2026-10-02 (ADR-047). Reference only: spec/ wins on any conflict; legacy facts are unverified for this project. -->

# Spec: Option Chain Performance Optimization

**Author:** Claude Code  
**Date:** 2026-04-15  
**Status:** DRAFT  
**Version:** 1.0  

---

## 1. Problem Statement

The option chain screen takes ~1-3s per request because every request:
1. Creates a new broker adapter (2 DB queries + `connect()`)
2. Hits external broker API (Upstox/SmartAPI) for live quotes
3. Queries DB for instruments
4. Computes IV (Newton-Raphson) and Greeks (Black-Scholes) per strike

After market hours, the data is **static** — yet we still repeat all this work per request. With 1000+ users, this creates unsustainable load on broker APIs, the database, and CPU.

Additionally, the frontend fires `fetchExpiries()` and `fetchOptionChain()` **sequentially**, adding ~200ms unnecessary latency on every tab switch.

## 2. Chosen Approach

**5-component "Full Stack Cache"** — Redis response cache + background fan-out prefetch + platform adapter singleton + frontend parallel fetch + request coalescing.

**Why this over alternatives:**
- **In-process cache (cachetools):** Not shared across workers when scaling to multiple processes. Cache lost on restart. Fine for single-process but dead-end for 1000+ users.
- **DB-only (no Redis):** DB is on remote VPS (~50-200ms per query). Redis on same VPS is faster for key-value lookups (~5-20ms). Pre-computed responses avoid repeated IV/Greeks CPU work.

## 3. Design

### 3.1 Redis Response Cache

**Cache key:** `optionchain:{underlying}:{expiry}` (e.g., `optionchain:NIFTY:2026-04-24`)

**Cached value:** Full JSON response including strikes with CE/PE data, IV, Greeks, and summary (PCR, max pain, ATM strike). ~15-25KB per key, ~750KB total for all indexes × expiries.

**TTL strategy — after-hours only:**

| Market State | TTL |
|---|---|
| Market open (9:15-15:30 IST Mon-Fri, non-holiday) | **No cache** — pass through to broker API |
| Market closed (after 15:30 same day) | Until next trading day 9:15 IST |
| Weekend (Sat/Sun) | Until Monday 9:15 IST (or next trading day if Monday is holiday) |
| Holiday | Until next trading day 9:15 IST |

**New utility function** in `app/utils/market_hours.py`:
```python
def get_next_market_open() -> datetime:
    """Returns the next market open datetime (IST).
    Skips weekends and NSE holidays."""
```

**TTL computation:**
```python
def get_cache_ttl_seconds() -> int | None:
    """Returns seconds until next market open, or None if market is currently open."""
    if is_market_open():
        return None
    next_open = get_next_market_open()
    return int((next_open - datetime.now(IST)).total_seconds())
```

**Fallback:** Redis unavailable or key missing → current flow (DB + broker API). No user-visible error.

**File:** New `app/services/options/option_chain_cache.py`

### 3.2 Background Fan-out Prefetch

**Trigger:** First after-hours request for ANY index triggers prefetch of ALL indexes × ALL active expiries.

**Flow:**
1. User requests `NIFTY 24-Apr` after market close
2. Cache miss → serve this request via normal flow (~1-3s)
3. Simultaneously: `asyncio.create_task(prefetch_all_option_chains(db))`
4. Background task:
   - Queries DB for active expiries per index (5 indexes from `trading.py`)
   - For each (index, expiry) — throttled via `asyncio.Semaphore(1)` + 2s delay:
     - Fetch data from NSE via `NSEFetcher` (primary) or platform adapter (fallback)
     - Compute IV/Greeks for all strikes
     - Store in DB (`EODOptionSnapshot`) + Redis cache
   - Total: ~60-120s for ~30 combos, runs silently in background

**Deduplication:** Module-level `asyncio.Event` prevents duplicate fan-outs:
```python
_prefetch_lock = asyncio.Lock()
_prefetch_done_for_session: str | None = None  # Tracks last trading close timestamp

async def trigger_prefetch_if_needed(db):
    if is_market_open():
        return
    session_key = get_last_trading_close().isoformat()
    if _prefetch_done_for_session == session_key:
        return  # Already prefetched for this session
    async with _prefetch_lock:
        if _prefetch_done_for_session == session_key:
            return  # Double-check after lock
        await prefetch_all_option_chains(db)
        _prefetch_done_for_session = session_key
```

**Partial failure:** Successful fetches are cached; failed ones fall through to on-demand fetch.

**Data source:** NSE v3 API via existing `NSEFetcher` (has complete OI, volume, all strikes). Falls back to `get_platform_market_data_adapter()` if NSE is unreachable.

**File:** New `app/services/options/option_chain_prefetch.py`

### 3.3 Platform Adapter Singleton

**Problem:** `get_user_market_data_adapter()` runs 2 DB queries + `connect()` per request. Option chain data is **not user-specific** — all users see the same NIFTY chain.

**Fix:** Cache a platform-level adapter instance (using existing `get_platform_market_data_adapter()`):
```python
_cached_adapter: tuple[MarketDataBrokerAdapter, float] | None = None
ADAPTER_TTL = 3600  # 1 hour

async def get_cached_platform_adapter(db) -> MarketDataBrokerAdapter:
    global _cached_adapter
    now = time.time()
    if _cached_adapter:
        adapter, created_at = _cached_adapter
        if now - created_at < ADAPTER_TTL and adapter.is_connected:
            return adapter
    adapter = await get_platform_market_data_adapter(db)
    _cached_adapter = (adapter, now)
    return adapter
```

**Usage:** Only in option chain route when market is open (live data needed). After hours, Redis cache serves directly — adapter not called.

**Token refresh:** The adapter's built-in `_with_token_refresh()` handles 401s transparently.

**File:** Add to `app/services/options/option_chain_cache.py`

### 3.4 Frontend Parallel Fetch + Expiry Cache

**Current (sequential):**
```javascript
await store.setUnderlying(ul)     // calls fetchExpiries(): ~200ms
await store.fetchOptionChain()    // chain data: ~1-2.5s
// Total: ~1.5-3s
```

**Proposed (parallel):**
```javascript
const handleUnderlyingChange = async (ul) => {
  store.underlying = ul
  store.chain = []
  
  await Promise.all([
    store.fetchExpiries(ul),
    store.fetchOptionChain(ul, store.expiry || null)
  ])
}
// Total: ~max(200ms, 1-2.5s) = 1-2.5s
```

**Expiry cache** — expiries don't change within a session:
```javascript
const _expiryCache = {}  // { "NIFTY": [...], "BANKNIFTY": [...] }

async function fetchExpiries(underlying) {
  if (_expiryCache[underlying]) {
    expiries.value = _expiryCache[underlying]
    return
  }
  const { data } = await api.get(`/api/options/expiries?underlying=${underlying}`)
  _expiryCache[underlying] = data
  expiries.value = data
}
```

**File:** Modify `frontend/src/stores/optionchain.js` and `frontend/src/views/OptionChainView.vue`

### 3.5 Request Coalescing (Thundering Herd Protection)

**Problem:** 1000 users request the same (NIFTY, 24-Apr) on a cache miss → 1000 broker API calls.

**Fix:** Only the first concurrent request fetches; others await its result:
```python
_inflight: dict[str, asyncio.Future] = {}

async def get_option_chain_cached(underlying, expiry, db, redis):
    cache_key = f"optionchain:{underlying}:{expiry}"
    
    # 1. Redis hit
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # 2. Coalesce concurrent requests
    if cache_key in _inflight:
        return await _inflight[cache_key]
    
    # 3. First request — fetch, cache, serve
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    _inflight[cache_key] = future
    try:
        result = await _compute_option_chain(underlying, expiry, db)
        ttl = get_cache_ttl_seconds()
        if ttl:
            await redis.setex(cache_key, ttl, json.dumps(result, default=str))
        future.set_result(result)
        return result
    except Exception as e:
        future.set_exception(e)
        raise
    finally:
        _inflight.pop(cache_key, None)
```

**File:** Part of `app/services/options/option_chain_cache.py`

## 4. Requirement Tiers

### Must (MVP)
- **M1:** Redis response cache with dynamic TTL (after-hours only, until next market open)
- **M2:** `get_next_market_open()` utility respecting weekends + NSE holidays
- **M3:** Background fan-out prefetch triggered by first after-hours request
- **M4:** Request coalescing to prevent thundering herd on cache miss
- **M5:** Platform adapter singleton for option chain route
- **M6:** Graceful fallback to current flow when Redis is unavailable

### Nice (follow-up)
- **N1:** Frontend parallel fetch (`Promise.all`) for expiries + chain
- **N2:** Client-side expiry cache in optionchain store
- **N3:** Redis cache for live market with short TTL (2-5s) — deferred per user's decision
- **N4:** Cache warming on backend startup (if market is closed when server starts)
- **N5:** Metrics/logging for cache hit rate and prefetch completion

### Out of Scope
- **W1:** Cron job for periodic prefetch — user explicitly rejected
- **W2:** Per-user cache (data is identical for all users)
- **W3:** WebSocket-based live option chain updates (separate feature)
- **W4:** Caching during live market hours (user's explicit decision)

## 5. New Files & Modified Files

### New Files
| File | Purpose |
|---|---|
| `backend/app/services/options/option_chain_cache.py` | Redis cache, coalescing, adapter singleton |
| `backend/app/services/options/option_chain_prefetch.py` | Background fan-out logic |

### Modified Files
| File | Change |
|---|---|
| `backend/app/utils/market_hours.py` | Add `get_next_market_open()` |
| `backend/app/api/routes/optionchain.py` | Integrate cache layer before computation |
| `backend/app/database.py` | Verify Redis dependency injection works |
| `frontend/src/stores/optionchain.js` | Expiry cache, parallel-friendly fetch |
| `frontend/src/views/OptionChainView.vue` | `Promise.all` for tab switch |

## 6. Open Questions

1. **Holiday list maintenance:** `_NSE_HOLIDAYS_2026` is hardcoded. Should we add 2027 holidays now, or build a mechanism to fetch/update them?
2. **Cache invalidation on manual trigger:** Should there be an admin endpoint to force-clear the option chain cache (e.g., if NSE data was wrong)?
3. **Live market caching (future):** If we add 2-5s TTL cache during market hours later, should the fan-out also run during market hours for popular indexes?

## 7. Success Criteria

| Metric | Target |
|---|---|
| After-hours cache-hit latency | < 50ms (p95) |
| After-hours first-request latency | ≤ current (~1-3s), triggers background prefetch |
| Background prefetch completion | All 5 indexes × all active expiries cached within 2 minutes |
| Concurrent users on cache miss | 1 broker API call regardless of user count |
| Tab switch perceived latency | ~200ms improvement via parallel fetch |
| Redis failure impact | Zero — graceful fallback to current DB + broker flow |

## 8. Implementation Order

```
Phase 1 (Backend core):
  ├─ get_next_market_open() in market_hours.py
  ├─ option_chain_cache.py (Redis cache + coalescing + adapter singleton)
  └─ Integrate into optionchain.py route

Phase 2 (Prefetch):
  ├─ option_chain_prefetch.py (fan-out logic)
  └─ Wire trigger into option chain route

Phase 3 (Frontend):
  ├─ Expiry cache in optionchain store
  └─ Promise.all in OptionChainView

Phase 4 (Testing & Verification):
  ├─ Unit tests for cache TTL, coalescing, prefetch
  ├─ Integration test: cache hit/miss flow
  └─ Manual verification: tab switch speed
```
