<!-- GC-ADJ2 step 5 (REQ-162 AC-1..AC-3, REQ-112 AC-2/AC-6, REQ-045 AC-8; ADR-214 (3)): Positions > Adjustment
     opportunities. One read of GET /api/adjustment-opportunities: groups newest first, each with its strategy, time,
     source label, conditions and outcomes; the outcome counts; the empty text. Every word of a row is the server's; the
     browser counts and computes nothing. An open group links to the compare of its strategy (REQ-156). -->
<template>
  <section ref="root" class="p-4" data-testid="opportunities-page">
    <h1 class="text-lg font-semibold">Adjustment opportunities</h1>
    <p v-if="state === 'loading'" class="mt-2 text-sm text-ink-muted" data-testid="opp-loading">Loading.</p>
    <ErrorMessage v-else-if="state === 'error'" :parts="errorParts" prefix="opp-error" data-testid="opp-error" />
    <template v-else>
      <ul class="mt-2 flex flex-wrap gap-2" data-testid="opp-counts">
        <li v-for="c in reply.counts" :key="c.outcome" class="rounded border border-line px-2 py-0.5 text-xs" :data-testid="`opp-count-${c.outcome}`">{{ c.text }}: {{ c.count }}</li>
      </ul>
      <p v-if="reply.empty_text" class="mt-4 text-sm" data-testid="opp-empty">{{ reply.empty_text }}</p>
      <div v-else class="relative mt-3 max-w-full overflow-x-auto" data-testid="opp-scroll">
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
            <tr v-for="g in reply.groups" :key="g.group" class="border-b border-line align-top" data-testid="opp-row" :data-strategy-id="g.strategy_id" :data-picked="picked === String(g.strategy_id) ? 'true' : 'false'">
              <td class="py-1.5 tabular-nums" data-testid="opp-time">{{ istTime(g.shown_at) }}</td>
              <td class="py-1.5" data-testid="opp-strategy">{{ plainName(g.strategy_name) }}</td>
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
                <!-- GC-MU A3 r2 (ADR-230 (2)): Dismiss the group's open records, optional reason from the server's closed list -->
                <div v-if="openIds(g).length" class="mt-1 flex flex-wrap items-center gap-2" data-testid="opp-dismiss-box">
                  <label class="text-sm">Reason
                    <select v-model="reasonOf[g.group]" class="ml-1 rounded border border-line px-1 py-0.5 text-sm" data-testid="opp-dismiss-reason">
                      <option value="">-</option>
                      <option v-for="r in reply.dismiss_reasons ?? []" :key="r.id" :value="r.id">{{ r.text }}</option>
                    </select>
                  </label>
                  <button type="button" class="h-9 rounded-lg border border-line px-3 text-sm font-medium" :disabled="busy[g.group]" data-testid="opp-dismiss" @click="dismiss(g)">Dismiss</button>
                  <ErrorMessage v-if="errorOf[g.group]" :parts="errorOf[g.group]" compact prefix="opp-dismiss-error" data-testid="opp-dismiss-error" />
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <!-- GC-IC1 step 10 fix (REQ-170 AC-4): crossings the alert gate held, in the server's words with their time; never a
           record, so no Compare and no Dismiss -->
      <section v-if="reply.held && reply.held.length" class="mt-4" data-testid="opp-held">
        <h2 class="text-sm font-medium">Held crossings</h2>
        <ul class="mt-1 text-sm">
          <li v-for="h in reply.held" :key="h.id" class="border-b border-line py-1" :data-reason="h.reason" data-testid="opp-held-row">
            <span class="tabular-nums" data-testid="opp-held-time">{{ istTime(h.held_at) }}</span>
            <span class="ml-2" data-testid="opp-held-strategy">{{ plainName(h.strategy_name) }}</span>
            <span class="ml-2 rounded border border-line px-1.5 text-xs" data-testid="opp-held-text">{{ h.text }}</span>
          </li>
        </ul>
      </section>
    </template>
  </section>
</template>

<script setup>
import { inject, nextTick, onMounted, reactive, ref } from 'vue'
import { RouterLink, routeLocationKey } from 'vue-router'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import { compareUrl } from '@/lib/adjustDrawer'
import { istTime } from '@/lib/displayFormat'
import { plainName } from '@/lib/saveDraft'

const props = defineProps({
  client: { type: [Object, Function], default: () => api }, // the api module; a test passes a stand-in
})
const state = ref('loading') // loading | ready | error
const reply = ref(null)
const root = ref(null)
const errorParts = ref(NEUTRAL_PARTS)

// GC-MU A3: the Live Strategies card links here with ?strategy=<id>; that strategy's first row is scrolled into view
const picked = inject(routeLocationKey, null)?.query?.strategy ?? null
const linkOf = (g) => compareUrl(g.strategy_id, [], g.records.filter((r) => r.can_act).map((r) => r.id))

async function load() {
  try {
    reply.value = (await props.client.get('/adjustment-opportunities')).data
    state.value = 'ready'
    return true
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    state.value = 'error'
    return false
  }
}
onMounted(async () => {
  if (!(await load())) return
  await nextTick()
  root.value?.querySelector('[data-picked="true"]')?.scrollIntoView?.()
})

// GC-MU A3 r2: per-group Dismiss, the drawer's way (AdjustDrawer.vue): one post per open record, the server's refusal shown as it came
const reasonOf = reactive({})
const busy = reactive({})
const errorOf = reactive({})
const openIds = (g) => g.records.filter((r) => r.can_act).map((r) => r.id)
async function dismiss(g) {
  busy[g.group] = true
  errorOf[g.group] = null
  const body = reasonOf[g.group] ? { reason: reasonOf[g.group] } : {}
  let done = 0
  for (const id of openIds(g)) {
    try {
      await props.client.post(`/adjustment-opportunities/${id}/dismiss`, body)
      done += 1
    } catch (e) {
      errorOf[g.group] = e?.parts ?? NEUTRAL_PARTS
    }
  }
  busy[g.group] = false
  if (done) await load() // the list shows the truth: dismissed rows read "You dismissed this"
}
</script>
