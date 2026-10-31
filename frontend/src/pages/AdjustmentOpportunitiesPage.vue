<!-- GC-ADJ2 step 5 (REQ-162 AC-1..AC-3, REQ-112 AC-2/AC-6, REQ-045 AC-8; ADR-214 (3)): Positions > Adjustment
     opportunities. One read of GET /api/adjustment-opportunities: groups newest first, each with its strategy, time,
     source label, conditions and outcomes; the outcome counts; the empty text. Every word of a row is the server's; the
     browser counts and computes nothing. An open group links to the compare of its strategy (REQ-156). -->
<template>
  <section class="p-4" data-testid="opportunities-page">
    <h1 class="text-lg font-semibold">Adjustment opportunities</h1>
    <p v-if="state === 'loading'" class="mt-2 text-sm text-ink-muted" data-testid="opp-loading">Loading.</p>
    <ErrorMessage v-else-if="state === 'error'" :parts="errorParts" prefix="opp-error" data-testid="opp-error" />
    <template v-else>
      <ul class="mt-2 flex flex-wrap gap-2" data-testid="opp-counts">
        <li v-for="c in reply.counts" :key="c.outcome" class="rounded border border-line px-2 py-0.5 text-xs" :data-testid="`opp-count-${c.outcome}`">{{ c.text }}: {{ c.count }}</li>
      </ul>
      <p v-if="reply.empty_text" class="mt-4 text-sm" data-testid="opp-empty">{{ reply.empty_text }}</p>
      <div v-else class="mt-3 max-w-full overflow-x-auto" data-testid="opp-scroll">
        <table class="w-full min-w-[640px] text-sm">
          <thead>
            <tr class="border-b border-line text-ink-muted">
              <th scope="col" class="py-1.5 text-left font-medium">Time</th>
              <th scope="col" class="py-1.5 text-left font-medium">Strategy</th>
              <th scope="col" class="py-1.5 text-left font-medium">What happened</th>
              <th scope="col" class="py-1.5 text-left font-medium">Source</th>
              <th scope="col" class="py-1.5 text-left font-medium">Outcome</th>
              <th scope="col" class="py-1.5 text-left font-medium"><span class="sr-only">Link</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in reply.groups" :key="g.group" class="border-b border-line align-top" data-testid="opp-row">
              <td class="py-1.5 tabular-nums" data-testid="opp-time">{{ istTime(g.shown_at) }}</td>
              <td class="py-1.5" data-testid="opp-strategy">{{ g.strategy_name }}</td>
              <td class="py-1.5" data-testid="opp-what">
                <p v-if="g.summary" class="font-medium" data-testid="opp-summary">{{ g.summary }}</p>
                <p v-for="r in g.records" :key="r.id" data-testid="opp-condition">{{ r.condition }}</p>
              </td>
              <td class="py-1.5" data-testid="opp-source">{{ g.label }}</td>
              <td class="py-1.5">
                <p v-for="r in g.records" :key="r.id" :data-outcome="r.outcome" data-testid="opp-outcome">
                  <span class="rounded border border-line px-1.5 text-xs">{{ r.outcome_text }}</span>
                  <span v-if="r.detail" class="ml-1 text-xs text-ink-muted">{{ r.detail }}</span>
                </p>
              </td>
              <td class="py-1.5">
                <RouterLink v-if="g.has_open" :to="linkOf(g)" class="text-accent underline" data-testid="opp-compare">Compare approaches</RouterLink>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import { compareUrl } from '@/lib/adjustDrawer'
import { istTime } from '@/lib/displayFormat'

const props = defineProps({
  client: { type: Object, default: () => api }, // the api module; a test passes a stand-in
})
const state = ref('loading') // loading | ready | error
const reply = ref(null)
const errorParts = ref(NEUTRAL_PARTS)

const linkOf = (g) => compareUrl(g.strategy_id, [], g.records.filter((r) => r.can_act).map((r) => r.id))

onMounted(async () => {
  try {
    reply.value = (await props.client.get('/adjustment-opportunities')).data
    state.value = 'ready'
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    state.value = 'error'
  }
})
</script>
