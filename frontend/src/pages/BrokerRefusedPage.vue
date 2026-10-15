<!-- Where a refused Zerodha login lands (issue #163; W-058 REFUSED_FRONTEND_PATH). The callback redirects here with
     `?code=<closed refusal code>` and nothing else. The page asks the API for the reviewed catalogue message of that
     code (REQ-065 AC-2, ADR-003 Q226) and shows its four parts. The code itself is never shown; no code, an unknown
     code or a failed fetch shows the neutral message. Nothing else from the server is displayed. -->
<script setup>
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api, { catalogueParts, NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'

const NEUTRAL = { ...NEUTRAL_PARTS, what_happened: 'The Zerodha login was not completed.' }
const CODE_SHAPE = /^[a-z_]{1,64}$/

const route = useRoute()
const parts = ref(null)
const loading = ref(true)

onMounted(async () => {
  const raw = route.query.code
  const code = typeof raw === 'string' && CODE_SHAPE.test(raw) ? raw : null
  try {
    if (code) {
      const { data } = await api.get(`/broker/refusals/${code}`)
      parts.value = catalogueParts(data?.message)
    }
  } catch {
    parts.value = null
  }
  loading.value = false
})
</script>

<template>
  <section data-testid="broker-refused">
    <h1 class="text-xl font-semibold" data-testid="page-title">Zerodha login not completed</h1>
    <p v-if="loading" class="mt-4 text-sm text-ink-muted" data-testid="refused-loading">Loading the details.</p>
    <ErrorMessage v-else class="mt-4" :parts="parts || NEUTRAL" />
    <router-link to="/settings/zerodha-connection" class="mt-4 inline-block rounded border border-line bg-surface px-3 py-2 hover:bg-accent-soft" data-testid="to-connection">Back to the Zerodha connection page</router-link>
  </section>
</template>
