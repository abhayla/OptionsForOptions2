<!-- Shown when the Zerodha login callback refuses (issue #159). The four parts are the reviewed catalogue message the
     callback answered with (REQ-065), handed over as `history.state.error` or the `ofo.lastError` session entry by the
     app that received it; without one, the neutral message is shown. Nothing else from the server is displayed. -->
<script setup>
import { catalogueParts, NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

function handedOver() {
  try {
    const fromState = window.history.state?.error
    const fromSession = JSON.parse(window.sessionStorage.getItem('ofo.lastError') || 'null')
    return catalogueParts(fromState) || catalogueParts(fromSession)
  } catch {
    return null
  }
}
const parts = handedOver() || { ...NEUTRAL_PARTS, what_happened: 'The Zerodha login was not completed.' }
</script>

<template>
  <section data-testid="broker-refused">
    <h1 class="text-xl font-semibold" data-testid="page-title">Zerodha login not completed</h1>
    <ErrorMessage class="mt-4" :parts="parts" />
    <router-link to="/settings/zerodha-connection" class="mt-4 inline-block rounded border border-line bg-surface px-3 py-2 hover:bg-accent-soft" data-testid="to-connection">Back to the Zerodha connection page</router-link>
  </section>
</template>
