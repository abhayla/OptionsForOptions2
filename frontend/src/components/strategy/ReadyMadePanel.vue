<!-- Ready-made shapes and quick picks (W-125; REQ-079 AC-2, AC-4, AC-5, AC-7, AC-9; Sensibull screens 010-012, 032-038).
     HELD for the Q211 legal answer: rendered ONLY when GET /features lists `platform_strikes` (absent otherwise, never
     greyed). Picking a shape or a quick pick asks the server (POST /strategies/load-template, /strategies/quick-pick);
     strikes are placed on the server, the browser computes nothing. Loading into a builder that has legs asks first
     ("Replace the N legs in the builder?"); legs are never cleared without that answer. Loaded legs carry the server's
     label until their strike is edited (then the row is replaced and the label goes with it). -->
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { useHeldFeature } from '@/lib/heldFeatures'
import { QUICK_PICK_DISTANCES, VIEW_GROUPS, builderLeg, replacePrompt, templatesInGroup } from '@/lib/readyMade'

const props = defineProps({ legs: { type: Array, default: () => [] } })
const emit = defineEmits(['update:legs'])

const on = useHeldFeature('platform_strikes')
const route = useRoute()
const underlying = ref(props.legs[0]?.underlying ?? 'NIFTY')
const underlyingLocked = computed(() => props.legs.length > 0)
const templates = ref([])
const expiries = ref([])
const expiry = ref('')
const group = ref(VIEW_GROUPS[0].key)
const side = ref('SELL')
const pending = ref(null) // the request waiting for the Replace / Cancel answer
const errorParts = ref(null)
const busy = ref(false)

const shown = computed(() => templatesInGroup(templates.value, VIEW_GROUPS.find((g) => g.key === group.value)))
const distances = computed(() => QUICK_PICK_DISTANCES[underlying.value] ?? [])

async function start() {
  try {
    templates.value = (await api.get('/strategy-templates')).data?.templates ?? []
    expiries.value = (await api.get(`/catalogue/${underlying.value}/expiries`)).data?.expiries ?? []
    expiry.value = expiries.value[0] ?? ''
    errorParts.value = null
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  }
}

async function run(request) {
  busy.value = true
  try {
    const { data } = await api.post(request.path, request.body)
    errorParts.value = null
    emit('update:legs', data.legs.map((leg, i) => builderLeg(leg, data.underlying, i)))
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS // the server's catalogue message; the legs on screen stay as they are
  } finally {
    busy.value = false
  }
}

function ask(request) {
  if (props.legs.length > 0) pending.value = request // AC-5: never clear legs without the answer
  else run(request)
}
const loadTemplate = (id) => ask({ path: '/strategies/load-template', body: { underlying: underlying.value, template_id: id, expiry: expiry.value } })
const quickPick = (kind, distance) =>
  ask({ path: '/strategies/quick-pick', body: { underlying: underlying.value, kind, distance, side: side.value, expiry: expiry.value } })
const replace = () => { const request = pending.value; pending.value = null; run(request) }
const cancel = () => { pending.value = null }

async function onUnderlying(value) {
  underlying.value = value
  await start()
}

onMounted(async () => {
  await start()
  // AC-9: "Open in Builder" from a Learn page arrives with ?template=<id>; loaded for the nearest expiry.
  const id = route?.query?.template
  if (typeof id === 'string' && id && on.value && expiry.value) loadTemplate(id)
})
</script>

<template>
  <section v-if="on" class="mt-4 rounded border border-line p-3" data-testid="ready-made">
    <h2 class="text-lg font-semibold">Ready-made shapes</h2>
    <div class="mt-2 flex flex-wrap items-end gap-3 text-sm">
      <label>Underlying
        <select :value="underlying" :disabled="underlyingLocked" class="ml-1 rounded border border-line p-1" data-testid="rm-underlying" @change="onUnderlying($event.target.value)">
          <option value="NIFTY">NIFTY</option>
          <option value="SENSEX">SENSEX</option>
        </select>
      </label>
      <label>Expiry
        <select v-model="expiry" class="ml-1 rounded border border-line p-1" data-testid="rm-expiry">
          <option v-for="e in expiries" :key="e" :value="e">{{ e }}</option>
        </select>
      </label>
    </div>

    <nav class="mt-3 flex gap-1 text-sm" aria-label="Market view" data-testid="rm-groups">
      <button
        v-for="g in VIEW_GROUPS" :key="g.key" type="button" :data-testid="`rm-group-${g.key}`"
        :aria-pressed="group === g.key" class="rounded border border-line px-2 py-1" :class="group === g.key ? 'bg-surface font-semibold' : ''"
        @click="group = g.key">{{ g.title }}</button>
    </nav>
    <ul class="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2" data-testid="rm-templates">
      <li v-for="t in shown" :key="t.id" class="rounded border border-line p-2">
        <button type="button" class="text-left underline" :disabled="busy || !expiry" :data-testid="`rm-template-${t.id}`" @click="loadTemplate(t.id)">{{ t.name }}</button>
      </li>
    </ul>

    <div class="mt-3 text-sm" data-testid="rm-quick">
      <h3 class="font-medium">Quick picks</h3>
      <div class="mt-1 flex gap-2">
        <label><input v-model="side" type="radio" value="BUY" data-testid="rm-side-buy" /> Buy</label>
        <label><input v-model="side" type="radio" value="SELL" data-testid="rm-side-sell" /> Sell</label>
        <button type="button" class="rounded border border-line px-2" :disabled="busy || !expiry" data-testid="rm-straddle" @click="quickPick('straddle', 0)">Straddle</button>
      </div>
      <div class="mt-1 flex flex-wrap gap-2">
        <span>Strangle</span>
        <button
          v-for="d in distances" :key="d" type="button" class="rounded border border-line px-2" :disabled="busy || !expiry"
          :data-testid="`rm-strangle-${d}`" @click="quickPick('strangle', d)">{{ d }} points</button>
      </div>
    </div>

    <div v-if="pending" class="mt-3 rounded border border-line p-2" role="alertdialog" data-testid="rm-replace">
      <p data-testid="rm-replace-text">{{ replacePrompt(legs.length) }}</p>
      <button type="button" class="mr-2 rounded border border-line px-2" data-testid="rm-replace-yes" @click="replace">Replace</button>
      <button type="button" class="rounded border border-line px-2" data-testid="rm-replace-no" @click="cancel">Cancel</button>
    </div>

    <ErrorMessage v-if="errorParts" class="mt-3" :parts="errorParts" prefix="rm-error" data-testid="rm-error" />
    <p v-for="l in legs.filter((x) => x.fixed_rule_label)" :key="l.id" class="mt-1 text-xs text-ink-muted" data-testid="rm-label">{{ l.fixed_rule_label }}</p>
  </section>
</template>
