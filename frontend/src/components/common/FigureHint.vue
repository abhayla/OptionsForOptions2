<!-- REQ-136 (W-160) AC-1/AC-2: an info mark beside a figure's label. The definition is DOM text from the one catalogue
     (lib/figureDefinitions.js), shown on mouse hover, keyboard focus or a tap; Escape or a second tap closes it. No title=
     attribute (touch screens never show one) and no v-html. An id the catalogue does not hold draws nothing. -->
<script setup>
import { computed, ref } from 'vue'
import { FIGURES } from '@/lib/figureDefinitions'

const props = defineProps({ id: { type: String, required: true } })
const figure = computed(() => (Object.hasOwn(FIGURES, props.id) ? FIGURES[props.id] : null))
const panelId = `figure-hint-${props.id}-${Math.random().toString(36).slice(2, 8)}`

const hovered = ref(false)
const focused = ref(false)
const pinned = ref(false)
const open = computed(() => hovered.value || focused.value || pinned.value)

const onEnter = () => { hovered.value = true }
const onLeave = () => { hovered.value = false }
const onFocus = () => { focused.value = true }
const onBlur = () => { focused.value = false; pinned.value = false }
// A tap also hovers and focuses the mark, so closing by a second tap clears all three (else the panel stays open).
const onClick = () => {
  pinned.value = !pinned.value
  if (!pinned.value) { focused.value = false; hovered.value = false }
}
const onKey = (e) => {
  if (e.key === 'Escape') { hovered.value = false; focused.value = false; pinned.value = false }
}
</script>

<template>
  <span v-if="figure" class="relative inline-block align-middle" data-testid="figure-hint" :data-figure="id" @keydown="onKey">
    <button
      type="button"
      class="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full text-gray-400 hover:text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
      :aria-label="`What is ${figure.label}?`"
      :aria-expanded="open ? 'true' : 'false'"
      :aria-describedby="open ? panelId : undefined"
      data-testid="figure-hint-mark"
      @pointerenter="onEnter"
      @pointerleave="onLeave"
      @focus="onFocus"
      @blur="onBlur"
      @click="onClick"
    >
      <svg class="h-4 w-4" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <circle cx="8" cy="8" r="6.5" />
        <path d="M8 7v4M8 5v.01" stroke-linecap="round" />
      </svg>
    </button>
    <span
      v-if="open"
      :id="panelId"
      role="tooltip"
      class="absolute left-0 top-full z-20 mt-1 w-64 max-w-[80vw] rounded border border-line bg-white p-2 text-xs font-normal normal-case text-gray-700 shadow"
      data-testid="figure-hint-text"
    >{{ figure.text }}</span>
  </span>
</template>
