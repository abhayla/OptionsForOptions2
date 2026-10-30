<!-- Review-adjustment drawer (GC-ADJ1 step 3; REQ-046 AC-1..AC-3, REQ-045 AC-5; ADR-214 (1)).
     Layer 1 why detected, layer 2 current state, layer 3 generic approaches with tick boxes and NO figure per approach.
     One read when it opens: POST /strategies/{id}/adjustment-approaches asking for No change only (the current position), which
     answers `available` (name, one line, whether it applies) and the current state's figures. Display only: nothing is computed
     here and no approach text lives in the browser. Compare opens the compare with the picks. No outcome is recorded (GC-ADJ2). -->
<template>
  <div v-if="open" class="fixed inset-0 z-40" data-testid="adjust-drawer-root">
    <div class="absolute inset-0 bg-black/40" data-testid="adjust-drawer-scrim" @click="close" />
    <aside
      role="dialog" aria-modal="true" aria-labelledby="adjust-drawer-title" tabindex="-1"
      class="absolute right-0 top-0 flex h-full w-full flex-col bg-surface shadow-xl sm:max-w-md" data-testid="adjust-drawer" @keydown.esc="close"
    >
      <header class="flex items-center justify-between border-b border-line p-3">
        <h2 id="adjust-drawer-title" class="text-lg font-semibold">Review adjustment</h2>
        <button ref="closeBtn" type="button" class="rounded border border-line px-2 py-1 text-sm" data-testid="adjust-drawer-close" @click="close">Close</button>
      </header>
      <div class="flex-1 overflow-y-auto p-3">
        <section data-testid="drawer-why">
          <h3 class="text-sm font-semibold">1 · Why detected</h3>
          <p v-for="l in lines" :key="l" class="mt-1 text-sm" data-testid="drawer-why-line">{{ l }}</p>
          <p v-if="!detected" class="mt-1 text-sm" data-testid="drawer-lapsed">{{ LAPSED_TEXT }}</p>
        </section>
        <section class="mt-4" data-testid="drawer-state">
          <h3 class="text-sm font-semibold">2 · Current state</h3>
          <dl class="mt-1 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
            <template v-for="r in rows" :key="r.id">
              <dt class="text-ink-muted">{{ r.label }}</dt>
              <dd class="text-right tabular-nums" :data-testid="`drawer-state-${r.id}`">{{ r.value }}</dd>
            </template>
          </dl>
        </section>
        <section class="mt-4" data-testid="drawer-approaches">
          <h3 class="text-sm font-semibold">3 · Possible approaches</h3>
          <p class="mt-1 text-xs text-ink-muted" data-testid="drawer-pick-note">{{ PICK_NOTE }}</p>
          <p v-if="state === 'loading'" class="mt-2 text-sm text-ink-muted" data-testid="drawer-loading">{{ LOADING_TEXT }}</p>
          <ErrorMessage v-else-if="state === 'error'" :parts="errorParts" compact prefix="drawer-error" data-testid="drawer-error" />
          <ul class="mt-2 flex flex-col gap-2">
            <li v-for="a in approaches" :key="a.id" class="rounded border border-line p-2" :data-applicable="a.applicable ? 'true' : 'false'">
              <label class="flex items-start gap-2">
                <input v-model="ticked" type="checkbox" :value="a.id" :disabled="a.id === NO_CHANGE_ID || !a.applicable" class="mt-1 h-4 w-4" :data-testid="`drawer-approach-${a.id}`" />
                <span>
                  <span class="block text-sm font-medium">{{ a.name }}</span>
                  <span class="block text-xs text-ink-muted">{{ a.explanation }}</span>
                  <span v-if="!a.applicable" class="block text-xs text-ink-muted" :data-testid="`drawer-reason-${a.id}`">{{ refusalText({ refusal: a.reason }) }}</span>
                </span>
              </label>
            </li>
          </ul>
        </section>
      </div>
      <footer class="sticky bottom-0 border-t border-line bg-surface p-3">
        <button type="button" class="h-10 w-full rounded-lg bg-accent px-3 font-medium text-white" data-testid="drawer-compare" @click="compare">Compare</button>
      </footer>
    </aside>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import { NO_CHANGE_ID, refusalText } from '@/lib/adjustCompare'
import { CURRENT_STATE_BODY, LAPSED_TEXT, LOADING_TEXT, PICK_NOTE, availableOf, compareUrl, replyRows } from '@/lib/adjustDrawer'

const props = defineProps({
  open: { type: Boolean, default: false },
  strategyId: { type: [String, Number], required: true },
  lines: { type: Array, default: () => [] }, // layer 1: the detection's own texts, as the card shows them
  detected: { type: Boolean, default: true }, // false when the detection lapsed while the drawer was open
  cardRows: { type: Array, default: () => [] }, // layer 2, the part the card has: [{id, label, value}]
  client: { type: Object, default: () => api }, // the api module; a test passes a stand-in
})
const emit = defineEmits(['close', 'compare']) // compare: { ids, url }

const closeBtn = ref(null)
const ticked = ref([NO_CHANGE_ID])
const state = ref('loading') // loading | ready | error
const reply = ref(null)
const errorParts = ref(NEUTRAL_PARTS)
const approaches = computed(() => availableOf(reply.value))
const rows = computed(() => [...props.cardRows, ...replyRows(reply.value)])

async function load() {
  state.value = 'loading'
  reply.value = null
  ticked.value = [NO_CHANGE_ID]
  try {
    const res = await props.client.post(`/strategies/${props.strategyId}/adjustment-approaches`, CURRENT_STATE_BODY)
    reply.value = res.data
    state.value = 'ready'
    ticked.value = approaches.value.filter((a) => a.applicable).map((a) => a.id) // every applicable approach starts ticked
    if (!ticked.value.includes(NO_CHANGE_ID)) ticked.value.unshift(NO_CHANGE_ID)
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
    state.value = 'error'
  }
}
watch(() => props.open, async (now) => {
  if (!now) return
  const reading = load()
  await nextTick()
  closeBtn.value?.focus()
  await reading
}, { immediate: true, flush: 'post' })
const close = () => emit('close')
function compare() {
  const ids = [NO_CHANGE_ID, ...ticked.value.filter((x) => x !== NO_CHANGE_ID)]
  emit('compare', { ids, url: compareUrl(props.strategyId, ids) })
}
</script>
