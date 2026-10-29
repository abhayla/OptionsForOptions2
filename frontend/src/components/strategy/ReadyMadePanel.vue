<!-- Ready-made shapes and quick picks (W-125; REQ-079 AC-2, AC-4, AC-5, AC-7, AC-9; Sensibull screens 010-012, 032-038).
     HELD for the Q211 legal answer: rendered ONLY when GET /features lists `platform_strikes` (absent otherwise, never
     greyed). Picking a shape or a quick pick asks the server (POST /strategies/load-template, /strategies/quick-pick);
     strikes are placed on the server, the browser computes nothing. Loading into a builder that has legs asks first
     ("Replace the N legs in the builder?"); legs are never cleared without that answer. Loaded legs carry the server's
     label until their strike is edited (then the row is replaced and the label goes with it).
     W-192 UI-111 (Sensibull 010, 105): chip filters by market view (selected = accent fill), the expiry select on the right,
     and a grid of square shape cards, 4 per row, each with a static payoff-shape icon (GC-UI D-C04: artwork by template id,
     nothing computed) above the name; a hint line with a Learn link sits under the chips (D-C02). The underlying is Region A's (prop), not a select of this tab. -->
<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { daysByExpiry, expiryWithDays } from '@/lib/displayFormat'
import { useHeldFeature } from '@/lib/heldFeatures'
import { instrumentId } from '@/lib/legPicker'
import { LEARN_LINK_TEXT, LEARN_PATH, READY_MADE_HINT, VIEW_GROUPS, builderLeg, replacePrompt, templatesInGroup } from '@/lib/readyMade'
import ShapeIcon from '@/components/strategy/ShapeIcon.vue'

const props = defineProps({
  legs: { type: Array, default: () => [] },
  underlying: { type: String, default: '' }, // Region A's underlying; the legs' own wins once legs exist
})
const emit = defineEmits(['update:legs'])

const on = useHeldFeature('platform_strikes')
const route = useRoute()
const underlying = computed(() => props.legs[0]?.underlying || props.underlying || 'NIFTY')
const templates = ref([])
const expiries = ref([])
const expiry = ref('')
const expiryDays = ref({}) // REQ-135 AC-2: the server's day count by expiry
const group = ref(VIEW_GROUPS[0].key)
const pending = ref(null) // the request waiting for the Replace / Cancel answer
const errorParts = ref(null)
const busy = ref(false)

const shown = computed(() => templatesInGroup(templates.value, VIEW_GROUPS.find((g) => g.key === group.value)))

async function start() {
  try {
    templates.value = (await api.get('/strategy-templates')).data?.templates ?? []
    const reply = (await api.get(`/catalogue/${underlying.value}/expiries`)).data
    expiries.value = reply?.expiries ?? []
    expiryDays.value = daysByExpiry(reply?.expiry_days)
    const own = props.legs.find((l) => l.expiry && expiries.value.includes(l.expiry))?.expiry // the draft's own expiry, when it has legs
    const server = expiries.value.includes(reply?.default_expiry) ? reply.default_expiry : null // ADR-199 (4): the server's default, never list position
    expiry.value = own ?? server ?? expiries.value[0] ?? '' // an older reply without the field falls back to the first listed
    errorParts.value = null
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  }
}

let loadSeq = 0 // a newer load wins: an older reply landing late is dropped

/** ONE planned-entry call for every loaded leg (GC-BM F-1; the same capture as a drawer pick). A leg the capture cannot
 *  price stays unpriced with its reason (ADR-085): never a default, zero or old price. Returns { legs, failure }. */
async function priced(legs, und) {
  if (legs.length === 0) return { legs, failure: null }
  const unpriced = (reason) => legs.map((l) => ({ ...l, reason_code: reason, checked_at: null }))
  try {
    const res = await api.post('/strategies/planned-entry', { underlying: und, instrument_ids: legs.map((l) => l.instrument_id) })
    const entries = res?.data?.entries
    if (!Array.isArray(entries)) return { legs: unpriced('capture_failed'), failure: null }
    return {
      failure: null,
      legs: legs.map((l) => {
        const found = entries.find((e) => instrumentId(e.exchange_segment, e.exchange_token) === l.instrument_id)
        if (found && found.planned_entry != null && found.captured_at != null) {
          return { ...l, planned_entry: found.planned_entry, captured_at: found.captured_at, close_at: found.close_at ?? null, source: found.source ?? l.source, reason_code: null, checked_at: res.data.answered_at ?? null }
        }
        return { ...l, reason_code: found?.reason_code ?? 'no_live_price', checked_at: res.data.answered_at ?? null }
      }),
    }
  } catch (e) {
    return { legs: unpriced('capture_failed'), failure: e?.parts ?? NEUTRAL_PARTS }
  }
}

async function run(request) {
  const mine = ++loadSeq
  busy.value = true
  try {
    const { data } = await api.post(request.path, request.body)
    const loaded = data.legs.map((leg, i) => builderLeg(leg, data.underlying, i))
    const { legs, failure } = await priced(loaded, data.underlying)
    if (mine !== loadSeq) return
    errorParts.value = failure
    emit('update:legs', legs)
  } catch (e) {
    if (mine !== loadSeq) return
    errorParts.value = e?.parts ?? NEUTRAL_PARTS // the server's catalogue message; the legs on screen stay as they are
  } finally {
    if (mine === loadSeq) busy.value = false
  }
}

function ask(request) {
  if (props.legs.length > 0) pending.value = request // AC-5: never clear legs without the answer
  else run(request)
}
const loadTemplate = (id) => ask({ path: '/strategies/load-template', body: { underlying: underlying.value, template_id: id, expiry: expiry.value } })
const replace = () => { const request = pending.value; pending.value = null; run(request) }
const cancel = () => { pending.value = null }

// a change of Region A's underlying reads that underlying's expiries again
watch(underlying, () => start())

onMounted(async () => {
  await start()
  // AC-9: "Open in Builder" from a Learn page arrives with ?template=<id>; loaded for the nearest expiry.
  const id = route?.query?.template
  if (typeof id === 'string' && id && on.value && expiry.value) loadTemplate(id)
})
</script>

<template>
  <section v-if="on" class="min-w-0" data-testid="ready-made">
    <h2 class="sr-only">Ready-made shapes</h2>
    <div class="flex flex-wrap items-center gap-2 text-sm">
      <nav class="flex flex-wrap gap-2" aria-label="Market view" data-testid="rm-groups">
        <button
          v-for="g in VIEW_GROUPS" :key="g.key" type="button" :data-testid="`rm-group-${g.key}`"
          :aria-pressed="group === g.key" class="h-8 rounded-full border px-3"
          :class="group === g.key ? 'border-accent bg-accent font-medium text-surface' : 'border-line text-ink hover:border-accent'"
          @click="group = g.key">{{ g.title }}</button>
      </nav>
      <label class="ml-auto flex items-center gap-1 text-ink-muted">Expiry
        <select v-model="expiry" class="h-8 rounded border border-line px-1 text-ink" data-testid="rm-expiry">
          <option v-for="e in expiries" :key="e" :value="e">{{ expiryWithDays(e, expiryDays[e]) }}</option>
        </select>
      </label>
    </div>
    <p class="mt-2 text-sm text-ink-muted" data-testid="rm-hint">{{ READY_MADE_HINT }}
      <RouterLink :to="LEARN_PATH" class="ml-2 text-accent underline" data-testid="rm-learn-link">{{ LEARN_LINK_TEXT }}</RouterLink></p>
    <ul class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4" data-testid="rm-templates">
      <li v-for="t in shown" :key="t.id" class="min-w-0">
        <button
          type="button" class="flex aspect-[100/95] w-full flex-col items-center justify-center gap-1 rounded-lg border border-line bg-surface p-2 text-center text-[13px] leading-4 font-medium text-ink hover:border-accent disabled:opacity-40"
          :disabled="busy || !expiry" :data-testid="`rm-template-${t.id}`" @click="loadTemplate(t.id)">
          <ShapeIcon :id="t.id" />
          <span data-testid="rm-card-name">{{ t.name }}</span>
        </button>
      </li>
    </ul>

    <!-- GC-UI 6c D-C08 (S-037, S-038): straddles and strangles are the leg drawer's Straddles / Strangles tabs now -->

    <div v-if="pending" class="mt-3 rounded border border-line p-2" role="alertdialog" data-testid="rm-replace">
      <p data-testid="rm-replace-text">{{ replacePrompt(legs.length) }}</p>
      <button type="button" class="mr-2 rounded border border-line px-2" data-testid="rm-replace-yes" @click="replace">Replace</button>
      <button type="button" class="rounded border border-line px-2" data-testid="rm-replace-no" @click="cancel">Cancel</button>
    </div>

    <ErrorMessage v-if="errorParts" class="mt-3" :parts="errorParts" prefix="rm-error" data-testid="rm-error" />
    <p v-for="l in legs.filter((x) => x.fixed_rule_label)" :key="l.id" class="mt-1 text-xs text-ink-muted" data-testid="rm-label">{{ l.fixed_rule_label }}</p>
  </section>
</template>
