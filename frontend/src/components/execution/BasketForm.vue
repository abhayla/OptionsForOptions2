<!-- The read-only Kite basket as an HTML form (W-104; REQ-073 AC-1, ADR-054, ADR-097 (2): "no app code or assistant
     action sends an order"). The form's action and its two hidden inputs `api_key` and `data` are the Execute reply's
     `basket` fields verbatim - nothing is rebuilt in the browser. It is submitted ONLY inside the owner's click handler
     (target _blank: Kite's own page opens in a new tab), once per reply; mounting or receiving the reply submits nothing.
     The strategy id is stored for the landing page Kite sends the browser back to. New file, copy from: none. -->
<script setup>
import { computed, ref } from 'vue'
import { basketFields, rememberExecuted } from '@/lib/execute'

const props = defineProps({
  reply: { type: Object, required: true },
  strategyId: { type: String, required: true },
})
const emit = defineEmits(['sent'])

const form = ref(null)
const sent = ref(false)
const fields = computed(() => basketFields(props.reply))

function placeOnKite() {
  if (sent.value || !fields.value || !form.value) return
  sent.value = true
  rememberExecuted(props.strategyId)
  form.value.submit()
  emit('sent')
}

// The browser may block the new tab. Re-posting opens Kite's page again with the SAME reply's fields (the same sealed
// basket, the same plan): no new Execute call, so no second plan is reserved. Only the owner's click posts it.
function openAgain() {
  if (!sent.value || !fields.value || !form.value) return
  form.value.submit()
}
</script>

<template>
  <div data-testid="basket">
    <form v-if="fields" ref="form" method="post" :action="fields.url" target="_blank" data-testid="basket-form">
      <input type="hidden" name="api_key" :value="fields.api_key" />
      <input type="hidden" name="data" :value="fields.data" />
    </form>
    <button
      v-if="fields && !sent"
      type="button"
      data-testid="place-on-kite"
      class="mt-2 rounded px-4 py-2 text-white bg-[#387ed1]"
      @click="placeOnKite"
    >
      Open Kite to place these orders
    </button>
    <p v-if="sent" class="mt-2 text-sm" data-testid="basket-sent">Kite's order page opened in a new tab. Place or close the orders there, then check with Zerodha below.</p>
    <button v-if="fields && sent" type="button" data-testid="open-kite-again" class="mt-2 rounded border border-line px-3 py-1" @click="openAgain">
      Open Kite's page again
    </button>
  </div>
</template>
