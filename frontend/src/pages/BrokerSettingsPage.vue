<!-- Settings -> Broker & Market Data (W-089; REQ-015 AC-4, AC-8; ADR-138 (5); REQ-051 AC-1).
     One state, Connected or Reconnect, plus the last sync time (ADR-134: no duplicate of what Zerodha reports). The state is
     the server's account_connection.state from GET /api/broker/status ("connected" = a live, unexpired session); every other
     answer (disconnected, partial, unknown word, missing field, empty reply, failed read) shows Reconnect or the
     unavailable state, never Connected. No token is read, kept or put in a URL here.
     States of the page: loading, ready, unavailable. -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import api from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

const status = ref(null)
const state = ref('loading') // loading | ready | unavailable
const error = ref(null)
const disconnecting = ref(false)
const confirming = ref(false)

const connected = computed(() => status.value?.account_connection?.state === 'connected')
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
      <p class="mt-4 rounded border border-line bg-surface p-3 font-medium" data-testid="connection-state" :data-level="connected ? 'connected' : 'reconnect'">{{ connected ? 'Connected' : 'Reconnect' }}</p>
      <p v-if="!connected" class="mt-2 text-sm" data-testid="reconnect-help">Your Zerodha login is not active (it expires every day). Use Reconnect and log in on Zerodha's own page. We never ask for your password, PIN or OTP.</p>

      <p class="mt-4 text-sm" data-testid="last-sync">
        Last successful sync:
        <span v-if="lastSync" data-testid="last-sync-time">{{ lastSync }}</span>
        <span v-else data-testid="last-sync-none">no successful read from Zerodha is recorded yet</span>
      </p>

      <p class="mt-2 text-sm" data-testid="history-statement">Historical market data: not currently available in this version.</p>

      <div class="mt-4 flex flex-wrap gap-2">
        <a href="/api/broker/zerodha/login" class="rounded border border-line bg-surface px-3 py-2 hover:bg-accent-soft" data-testid="broker-reconnect">{{ connected ? 'Reconnect Zerodha' : 'Reconnect' }}</a>
        <button v-if="connected && !confirming" type="button" class="rounded border border-line bg-surface px-3 py-2 hover:bg-accent-soft" data-testid="broker-disconnect" @click="confirming = true">Disconnect Zerodha</button>
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
