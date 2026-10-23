<!-- Settings -> Broker & Market Data (W-089; REQ-015 AC-4, AC-8; REQ-051 AC-1).
     Adapted from the algochanakya KiteSettings.vue (ADR-047): the status comes from GET /api/broker/status, and no token
     is ever read, kept or put in a URL here. The server sends closed words (state + fix code); every sentence below is
     this page's text. Four statuses, each Connected / Partially connected (naming what to fix) / Disconnected (with the
     guide); "Last successful sync"; Reconnect and Disconnect; and the V1 statement that history is not available.
     States of the whole page: loading, ready, unavailable (the status could not be read: nothing is shown as connected). -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

const ROWS = [
  ['account_connection', 'Zerodha account connection'],
  ['live_market_data', 'Live market data'],
  ['position_sync', 'Position and account sync'],
  ['order_execution', 'Order-execution readiness'],
]
const LABEL = { connected: 'Connected', partial: 'Partially connected', disconnected: 'Disconnected' }
const FIX = {
  connect_zerodha: 'Zerodha is not connected. Use Connect Zerodha below, log in on Zerodha\'s own page, and come back here.',
  session_expired: 'Your Zerodha login for today has expired. Use Reconnect and log in again on Zerodha\'s own page.',
  live_feed_off: 'Live market data is switched off on the server. Ask whoever runs the server to turn it on.',
  live_feed_not_running: 'The live price feed is not running yet. Open a strategy screen to start it; if it stays off, use Reconnect.',
  live_feed_waiting: 'Connected to Zerodha, but no prices have arrived yet. Wait a few seconds; if this stays, use Reconnect.',
  live_feed_market_closed: 'The market is closed, so no new prices are arriving. Live prices resume at the next market open (9:15 am IST on a trading day).',
  live_feed_idle: 'Live prices start when you open a strategy or option chain screen.',
  live_feed_reconnecting: 'The live price feed dropped and is reconnecting. It resumes by itself while your Zerodha login is valid.',
  live_feed_capped: 'Live prices are not available: Zerodha\'s connection limit for this app is reached.',
  live_feed_session_ended: 'Zerodha ended the live feed. Use Reconnect and log in again.',
  no_read_yet: 'No position read from Zerodha has succeeded since you connected. Open Execute for a strategy to read your positions.',
  live_data_not_connected: 'Orders are not ready until live market data is connected. Fix the live market data row first.',
  positions_not_synced: 'Orders are not ready until your positions have been read from Zerodha. Fix the position sync row first.',
}
const UNKNOWN_FIX = 'Something is not connected. Use Reconnect and log in again.'

const status = ref(null)
const state = ref('loading') // loading | ready | unavailable
const error = ref(null)
const disconnecting = ref(false)
const confirming = ref(false)

const rows = computed(() => ROWS.map(([key, title]) => {
  const item = status.value?.[key] ?? { state: 'disconnected', fix: null }
  const level = LABEL[item.state] ? item.state : 'disconnected'
  return { key, title, level, label: LABEL[level], fix: level === 'connected' ? '' : (FIX[item.fix] ?? UNKNOWN_FIX) }
}))
const anyConnected = computed(() => rows.value.some((r) => r.level !== 'disconnected'))
const lastSync = computed(() => {
  const at = status.value?.last_successful_sync
  return at ? new Date(at).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) + ' IST' : null
})

async function load() {
  state.value = 'loading'
  try {
    const { data } = await api.get('/broker/status')
    status.value = data
    state.value = 'ready'
  } catch (e) {
    error.value = e?.parts ?? null
    status.value = null
    state.value = 'unavailable'
  }
}

async function disconnect() {
  disconnecting.value = true
  try {
    await api.post('/broker/disconnect')
    confirming.value = false
    await load()
  } catch (e) {
    error.value = e?.parts ?? null
    state.value = 'unavailable'
  } finally {
    disconnecting.value = false
  }
}

onMounted(load)
</script>

<template>
  <section data-testid="broker-settings" :data-state="state">
    <h1 class="text-xl font-semibold" data-testid="page-title">Broker &amp; Market Data</h1>
    <p class="mt-1 text-sm text-ink-muted">Zerodha is the only broker. Your strategies, history and account stay here whether or not Zerodha is connected.</p>

    <p v-if="state === 'loading'" class="mt-4 text-sm text-ink-muted" data-testid="broker-loading">Checking the Zerodha connection.</p>

    <div v-else-if="state === 'unavailable'" class="mt-4" data-testid="broker-unavailable">
      <p class="mb-2 font-medium">The Zerodha connection could not be checked, so nothing below is shown as connected.</p>
      <ErrorMessage v-if="error" :parts="error" />
      <button type="button" class="mt-3 rounded border border-line bg-surface px-3 py-2 hover:bg-accent-soft" data-testid="broker-retry" @click="load">Check again</button>
    </div>

    <template v-else>
      <ul class="mt-4 space-y-3" data-testid="broker-rows">
        <li v-for="r in rows" :key="r.key" class="rounded border border-line bg-surface p-3" :data-testid="`row-${r.key}`" :data-level="r.level">
          <div class="flex flex-wrap items-baseline justify-between gap-2">
            <span class="font-medium">{{ r.title }}</span>
            <span class="text-sm font-semibold" :data-testid="`status-${r.key}`">{{ r.label }}</span>
          </div>
          <p v-if="r.fix" class="mt-1 text-sm" :data-testid="`fix-${r.key}`">{{ r.fix }}</p>
        </li>
      </ul>

      <p class="mt-4 text-sm" data-testid="last-sync">
        Last successful sync:
        <span v-if="lastSync" data-testid="last-sync-time">{{ lastSync }}</span>
        <span v-else data-testid="last-sync-none">no successful read from Zerodha is recorded yet</span>
      </p>

      <p class="mt-2 text-sm" data-testid="history-statement">Historical market data: not currently available in this version.</p>

      <div class="mt-4 flex flex-wrap gap-2">
        <a href="/api/broker/zerodha/login" class="rounded border border-line bg-surface px-3 py-2 hover:bg-accent-soft" data-testid="broker-reconnect">{{ anyConnected ? 'Reconnect Zerodha' : 'Connect Zerodha' }}</a>
        <button v-if="anyConnected && !confirming" type="button" class="rounded border border-line bg-surface px-3 py-2 hover:bg-accent-soft" data-testid="broker-disconnect" @click="confirming = true">Disconnect Zerodha</button>
      </div>

      <div v-if="confirming" class="mt-3 rounded border border-line bg-surface p-3" role="alertdialog" aria-label="Confirm disconnect" data-testid="disconnect-confirm">
        <p class="text-sm">Disconnecting keeps your strategies, history, entitlements and account. Live positions, orders, margin and execution are unavailable until you reconnect.</p>
        <div class="mt-2 flex gap-2">
          <button type="button" class="rounded border border-line bg-surface px-3 py-2 hover:bg-accent-soft" :disabled="disconnecting" data-testid="disconnect-yes" @click="disconnect">Yes, disconnect</button>
          <button type="button" class="rounded border border-line bg-surface px-3 py-2 hover:bg-accent-soft" :disabled="disconnecting" data-testid="disconnect-no" @click="confirming = false">Keep connected</button>
        </div>
      </div>
    </template>
  </section>
</template>
