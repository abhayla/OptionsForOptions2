<!-- GC-ALERT1 item 5 (REQ-170 Q-AD-2): the strategy's alert style on the plan sheet. GET /api/strategies/{id}/alert-style
     gives the label, the choices (Automatic (now <style>) / Intraday / Weekly / Monthly) and the pin; picking one PUTs
     {style} (null = Automatic) and shows the server's new answer. The style in force is the server's (alert_presets.style_for);
     the browser computes nothing. States: loading, ready, unavailable (the read failed: no style is shown), refused (the
     server's reason, verbatim). -->
<template>
  <div class="mt-3" data-testid="alert-style">
    <p v-if="state === 'unavailable'" class="text-sm text-ink-muted" data-testid="alert-style-unavailable">The alert style could not be read, so none is shown.</p>
    <label v-else-if="state === 'ready'" class="block text-sm font-medium">{{ answer.label }}
      <select class="mt-1 h-10 w-full rounded border border-line px-2" data-testid="alert-style-select" :value="selected" :disabled="busy" @change="pin($event.target.value)">
        <option v-for="c in answer.choices" :key="c.value ?? AUTO" :value="c.value ?? AUTO">{{ c.label }}</option>
      </select>
    </label>
    <p v-if="state === 'ready' && answer.reason_text" class="mt-1 text-xs text-ink-muted" data-testid="alert-style-reason">{{ answer.reason_text }}</p>
    <p v-if="refusal" role="alert" class="mt-1 text-sm text-error" data-testid="alert-style-refusal">{{ refusal }}</p>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import api from '@/services/api'

const props = defineProps({ strategyId: { type: Number, default: null } })
const AUTO = 'automatic' // the select's value for "no pin"; sent as null
const answer = ref(null)
const state = ref('loading') // loading | ready | unavailable
const busy = ref(false)
const refusal = ref('')
const selected = computed(() => answer.value?.pinned ?? AUTO)
const path = () => `/strategies/${props.strategyId}/alert-style`

function readable(body) {
  return body && typeof body.label === 'string' && Array.isArray(body.choices) ? body : null
}

async function load() {
  if (!Number.isInteger(props.strategyId)) return
  state.value = 'loading'
  try {
    answer.value = readable((await api.get(path())).data)
    state.value = answer.value ? 'ready' : 'unavailable'
  } catch {
    state.value = 'unavailable'
  }
}

async function pin(value) {
  busy.value = true
  refusal.value = ''
  try {
    const got = readable((await api.put(path(), { style: value === AUTO ? null : value })).data)
    if (got) answer.value = got
    else await load()
  } catch (e) {
    refusal.value = e?.reason || 'The alert style was not saved. Try again.'
  } finally {
    busy.value = false
  }
}

watch(() => props.strategyId, load, { immediate: true })
</script>
