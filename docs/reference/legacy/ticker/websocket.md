<!-- Copied from abhayla/algochanakya@bf9faf7:docs/architecture/websocket.md on 2026-10-02 (ADR-047). Reference only: spec/ wins on any conflict; legacy facts are unverified for this project. -->

# WebSocket Live Prices Architecture

**Status:** ⚠️ **SUPERSEDED** — Market data ticker architecture has been redesigned and implemented.

> **For the current market data WebSocket architecture, see [TICKER-DESIGN-SPEC.md](../decisions/TICKER-DESIGN-SPEC.md).** This file is kept for historical context only.
>
> **For AutoPilot WebSocket (real-time strategy updates), see the [AutoPilot WebSocket](#autopilot-websocket) section below.**

---

## AutoPilot WebSocket

The AutoPilot module has its own WebSocket system for real-time strategy updates, separate from the market data ticker.

**Endpoint:** `ws://host/ws/autopilot?token=<jwt_token>`

**Key files:**
- `backend/app/websocket/routes.py` — WebSocket endpoint, JWT auth, message routing
- `backend/app/websocket/manager.py` — Connection management, broadcasting, strategy subscriptions

**Message types from server:**
- `strategy_update` — Strategy status changes (active, paused, stopped)
- `order_update` — Order placement/fill notifications
- `position_update` — Position changes
- `condition_trigger` — Entry/exit/adjustment condition triggered
- `kill_switch` — Emergency kill switch activated
- `heartbeat` — Keep-alive ping

**Client messages:**
- `ping` — Keepalive (server responds with pong)
- `subscribe` — Subscribe to specific strategy: `{"type": "subscribe", "data": {"strategy_id": 123}}`
- `unsubscribe` — Unsubscribe from strategy updates

**Frontend composable:** `frontend/src/composables/autopilot/useWebSocket.js`

---

## Market Data WebSocket (Legacy — see TICKER-DESIGN-SPEC.md)

AlgoChanakya streams live market data via WebSocket, using a **broker-agnostic architecture** that routes ticks from any supported broker (SmartAPI, Kite, Upstox, Dhan, Fyers, Paytm) to connected users.

**Current implementation:** [TICKER-DESIGN-SPEC.md](../decisions/TICKER-DESIGN-SPEC.md) | [API Reference](../api/multi-broker-ticker-api.md)

**The content below describes the original proposal. The implemented design uses 5 components, credentials integrated into TickerPool, and `websocket.py` at 292 lines.**

---

## Architecture

```
┌────────────────┐    ┌──────────────────────┐    ┌─────────────────────┐
│    Browser      │    │     Backend           │    │   Broker WebSocket  │
│   (Vue App)     │    │    (FastAPI)          │    │  (SmartAPI / Kite)  │
└───────┬─────────┘    └──────────┬────────────┘    └──────────┬──────────┘
        │                        │                             │
        │ ws://localhost:8001    │                             │
        │  /ws/ticks?token=jwt   │                             │
        │───────────────────────>│                             │
        │                        │                             │
        │                        │ 1. Authenticate JWT         │
        │                        │ 2. Lookup user preference   │
        │                        │ 3. TickerRouter.register()  │
        │                        │                             │
        │ {"type":"connected",   │                             │
        │  "source":"smartapi"}  │                             │
        │<───────────────────────│                             │
        │                        │                             │
        │ {"action":"subscribe", │                             │
        │  "tokens":[256265]}    │                             │
        │───────────────────────>│                             │
        │                        │ TickerRouter.subscribe()    │
        │                        │ → TickerPool (ref count)    │
        │                        │ → SmartAPIAdapter.subscribe │
        │                        │─────────────────────────────>
        │                        │                             │
        │                        │         Tick data           │
        │                        │<─────────────────────────────
        │                        │ Adapter._normalize_tick()   │
        │                        │ → TickerPool._on_tick()     │
        │                        │ → TickerRouter.dispatch()   │
        │                        │                             │
        │  {"type":"ticks",      │                             │
        │   "data":[...]}        │                             │
        │<───────────────────────│                             │
```

---

## Connection Flow

1. **Frontend opens** WebSocket: `ws://localhost:8001/ws/ticks?token=<jwt>`
2. **Backend authenticates** JWT, looks up user's `market_data_source` preference from `UserPreferences`
3. **TickerRouter** registers user with their preferred broker type (default: `smartapi`)
4. **User sends subscribe**: `{"action": "subscribe", "tokens": [256265], "mode": "quote"}`
5. **TickerRouter** → **TickerPool** adds subscriptions (ref-counted — if token already subscribed by another user, no duplicate broker subscription)
6. **TickerPool** ensures adapter exists and is connected using platform-level credentials from `backend/.env` (via `SystemCredentialManager`). These are NOT user login credentials and NOT user-level API credentials — they are shared platform credentials that serve all users by default.
7. **Adapter** translates canonical tokens to broker format and subscribes on broker WebSocket
8. **Ticks flow**: Broker WS → Adapter (normalize paise→rupees, broker_token→canonical) → TickerPool → TickerRouter → fan out to all subscribed user WebSockets

---

## Message Protocol

### Client → Server

```javascript
// Subscribe to instruments (canonical Kite tokens)
{"action": "subscribe", "tokens": [256265, 260105], "mode": "quote"}

// Unsubscribe
{"action": "unsubscribe", "tokens": [256265]}

// Keepalive
{"action": "ping"}
```

### Server → Client

```javascript
// Connection confirmed
{"type": "connected", "source": "smartapi"}

// Subscription confirmed
{"type": "subscribed", "tokens": [256265, 260105], "mode": "quote", "source": "smartapi"}

// Live tick data (prices in rupees)
{
  "type": "ticks",
  "data": [{
    "token": 256265,
    "ltp": 24500.50,
    "change": -45.25,
    "change_percent": -0.18,
    "volume": 15000000,
    "oi": 0,
    "ohlc": {"open": 24550.0, "high": 24575.25, "low": 24480.0, "close": 24545.75}
  }]
}

// Data source changed (failover)
{"type": "failover", "from": "smartapi", "to": "kite", "message": "Switched to Kite (SmartAPI recovering)"}

// Unsubscription confirmed
{"type": "unsubscribed", "tokens": [256265]}

// Keepalive response
{"type": "pong"}

// Error
{"type": "error", "message": "Invalid token format"}
```

---

## Subscription Modes

| Mode | Data Included | Availability |
|------|---------------|-------------|
| `ltp` | Last traded price only | All brokers |
| `quote` | LTP + OHLC + volume + OI + change | All brokers (default) |
| `full` / `snap` | Quote + market depth | SmartAPI (snap), Kite (full), varies by broker |

---

## Index Tokens

All tokens use **canonical Kite format** (integer):

| Index | Token | Notes |
|-------|-------|-------|
| NIFTY 50 | `256265` | SmartAPI: translated to `99926000` internally |
| NIFTY BANK | `260105` | SmartAPI: translated to `99926009` internally |
| FINNIFTY | `257801` | SmartAPI: translated to `99926037` internally |
| SENSEX | `265` | SmartAPI: translated to `99919000` (BSE exchange) |

Adapters handle all token translation internally. Frontend always uses canonical tokens.

---

## Failover Behavior

From the user's perspective:
1. **Connection stays open** — no WebSocket reconnect needed
2. **Data source changes** — ticks now come from secondary broker
3. **Frontend notified** — receives `{"type": "failover", "from": "smartapi", "to": "kite"}` message
4. **Brief gap possible** — up to 2 seconds during switchover (make-before-break overlap)
5. **Automatic failback** — when primary recovers (health > 70 for 60s), switches back

Failover is transparent. No user action required.

---

## Connection URLs

| Environment | URL |
|-------------|-----|
| **Development** | `ws://localhost:8001/ws/ticks?token=<jwt>` |
| **Production** | `wss://algochanakya.com/ws/ticks?token=<jwt>` |

**Note**: Production uses `wss://` (TLS via Nginx/Cloudflare). Dev uses `ws://`.

---

## Debugging

### Browser Console

```javascript
// Connect to dev backend
const ws = new WebSocket('ws://localhost:8001/ws/ticks?token=YOUR_JWT')
ws.onmessage = (e) => console.log(JSON.parse(e.data))

// Subscribe to NIFTY
ws.send(JSON.stringify({action: 'subscribe', tokens: [256265], mode: 'quote'}))

// Check connection state
console.log('readyState:', ws.readyState)  // 0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED
```

### Health Endpoint

```bash
curl http://localhost:8001/api/ticker/health
```

Returns adapter health scores, connected users, failover status. See [API Reference Section 14](../api/multi-broker-ticker-api.md#14-health-api-endpoint).

### Common Issues

| Issue | Cause | Solution |
|-------|-------|---------|
| No ticks after subscribe | Adapter not connected | Check health endpoint. Verify platform-level SmartAPI credentials in `backend/.env` (`ANGEL_API_KEY`, `ANGEL_CLIENT_ID`, `ANGEL_PIN`, `ANGEL_TOTP_SECRET`). |
| `{"type":"error"}` on subscribe | Invalid token format | Tokens must be integers (canonical Kite format). |
| Connection drops immediately | JWT expired | Re-authenticate via `/login`. Note: this is the user session JWT, not the market data API credentials. |
| Wrong prices (100x too high) | Adapter not normalizing paise→rupees | Check adapter's `_normalize_tick()` divides by 100. |
| Ticks stop after a while | SmartAPI token expired (8h lifetime) | `SystemCredentialManager` uses platform `.env` credentials for auto-refresh. Check logs. Login credentials are not involved. |

---

## Frontend Integration

### Vue Store Pattern

```javascript
// stores/watchlist.js (example)
import { ref, onUnmounted } from 'vue'

const ws = ref(null)
const ticks = ref({})

function connect(jwtToken) {
  ws.value = new WebSocket(`ws://localhost:8001/ws/ticks?token=${jwtToken}`)

  ws.value.onmessage = (event) => {
    const data = JSON.parse(event.data)

    switch (data.type) {
      case 'ticks':
        data.data.forEach(tick => {
          ticks.value[tick.token] = tick
        })
        break
      case 'connected':
        console.log(`[WS] Connected to ${data.source}`)
        break
      case 'failover':
        console.log(`[WS] Failover: ${data.from} → ${data.to}`)
        break
    }
  }

  ws.value.onclose = () => {
    // Auto-reconnect after 3 seconds
    setTimeout(() => connect(jwtToken), 3000)
  }
}

function subscribe(tokens, mode = 'quote') {
  if (ws.value?.readyState === WebSocket.OPEN) {
    ws.value.send(JSON.stringify({ action: 'subscribe', tokens, mode }))
  }
}

function unsubscribe(tokens) {
  if (ws.value?.readyState === WebSocket.OPEN) {
    ws.value.send(JSON.stringify({ action: 'unsubscribe', tokens }))
  }
}

// CRITICAL: Clean up in onUnmounted
onUnmounted(() => {
  if (ws.value) {
    ws.value.close()
    ws.value = null
  }
})
```

---

## Implementation Files

| File | Purpose |
|------|---------|
| `backend/app/api/routes/websocket.py` | WebSocket endpoint (~90 lines, broker-agnostic) |
| `backend/app/services/brokers/market_data/ticker/router.py` | TickerRouter (user fan-out) |
| `backend/app/services/brokers/market_data/ticker/pool.py` | TickerPool (adapter lifecycle) |
| `backend/app/services/brokers/market_data/ticker/adapter_base.py` | TickerAdapter ABC |
| `backend/app/services/brokers/market_data/ticker/adapters/smartapi.py` | SmartAPI adapter |
| `backend/app/services/brokers/market_data/ticker/adapters/kite.py` | Kite adapter |
| `backend/app/services/brokers/market_data/ticker/health.py` | HealthMonitor |
| `backend/app/services/brokers/market_data/ticker/failover.py` | FailoverController |
| `backend/app/services/brokers/market_data/ticker/credential_manager.py` | System credentials |
| `frontend/src/stores/watchlist.js` | Frontend WebSocket client |

---

## LTP Fallback

When WebSocket is unavailable, use HTTP endpoint:

```http
GET /api/orders/ltp?instruments=NFO:NIFTY24DEC24500CE,NFO:NIFTY24DEC24500PE
Authorization: Bearer <token>
```

---

## Related Documentation

- [ADR-003 v2: Multi-Broker Ticker Architecture](../decisions/003-multi-broker-ticker-architecture.md) — Architecture rationale
- [Multi-Broker Ticker API Reference](../api/multi-broker-ticker-api.md) — Full interface specs
- [Implementation Guide](./multi-broker-ticker-implementation.md) — Step-by-step build guide
- [Broker Abstraction Architecture](./broker-abstraction.md) — Market data + order execution design
- [Authentication Architecture](./authentication.md) — JWT tokens and broker OAuth
