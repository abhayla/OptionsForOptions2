<!-- Core proof page (W-054): shows the live database status read through the same-origin /api proxy from GET /health.
     Neutral cues only: green/yellow/orange/red are reserved for strategy health (ADR-010, ADR-049). -->
<script setup>
import { onMounted, ref } from 'vue'
import api from '@/services/api'

// 'loading' | 'ok' | 'unavailable'
const state = ref('loading')
const database = ref('')

onMounted(async () => {
  try {
    const { data } = await api.get('/health')
    database.value = String(data?.database ?? '')
    state.value = data?.database === 'connected' && data?.status === 'healthy' ? 'ok' : 'unavailable'
  } catch {
    state.value = 'unavailable'
  }
})
</script>

<template>
  <section data-testid="health-page">
    <h1 class="text-xl font-semibold" data-testid="page-title">System health</h1>
    <div class="mt-4 rounded border border-line bg-surface p-4" :data-state="state" data-testid="health-status">
      <p v-if="state === 'loading'" data-testid="health-loading">Checking...</p>
      <p v-else-if="state === 'ok'" class="font-medium" data-testid="health-database">database: ok</p>
      <p v-else class="font-medium" data-testid="health-unavailable">Status unavailable</p>
    </div>
  </section>
</template>
