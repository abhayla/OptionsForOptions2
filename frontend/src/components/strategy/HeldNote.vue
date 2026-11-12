<!-- GC-TRACK1 k10 (ADR-292 (1), (3), (4)): what a condor typed in as held at the user's broker shows. `held` is the reply's block as
     sent (paper list / paper book); heldView gives null for anything that is not a readable held block, and then nothing shows.
     The broker name is shown as given, used for nothing. `note` adds the (`note-only` shows just) "not seen by the app" line next to the order actions. -->
<template>
  <div v-if="view" class="text-xs" data-testid="held-note">
    <template v-if="!noteOnly">
    <p class="font-semibold" data-testid="held-label">{{ view.label }}</p>
    <p data-testid="held-entry">{{ view.entry }}</p>
    <p v-if="view.rules" data-testid="held-rules">{{ view.rules }}</p>
    <p v-if="view.broker" data-testid="held-broker-name">{{ view.broker }}</p>
    </template>
    <p v-if="note || noteOnly" class="mt-1 text-ink-muted" data-testid="held-record-note">{{ HELD_NOTE }}</p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { HELD_NOTE, heldView } from '@/lib/tracking'

const props = defineProps({ held: { type: null, default: null }, note: { type: Boolean, default: false }, noteOnly: { type: Boolean, default: false } })
const view = computed(() => heldView(props.held))
</script>
