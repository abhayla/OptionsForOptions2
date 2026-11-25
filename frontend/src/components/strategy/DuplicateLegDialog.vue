<!-- F6 (Phase 5, D-60, ADR-328 (1)): the ONE question for a leg that lands on a held contract. Same test ids as before
     (dup-dialog, dup-question, dup-increase, dup-separate, dup-cancel). Same action: Increase quantity / Keep separate / Cancel.
     Other side (a move, ADR-328 (1)): Keep both / Cancel only. Escape, x and the overlay are Cancel. Decision-support wording. -->
<script setup>
import Modal from '@/components/common/Modal.vue'
import { DUP_QUESTION, OPPOSITE_NOTE, OPPOSITE_QUESTION } from '@/lib/legDoor'

defineProps({ door: { type: Object, required: true } })
</script>

<template>
  <Modal :open="door.pending.value !== null" title="Already in this strategy" @close="door.cancel()">
    <div data-testid="dup-dialog">
      <p data-testid="dup-question">{{ door.pending.value ? (door.pending.value.kind === 'opposite' ? OPPOSITE_QUESTION(door.pending.value.name, door.pending.value.heldAction) : DUP_QUESTION(door.pending.value.name)) : '' }}</p>
      <p v-if="door.pending.value?.kind === 'opposite'" class="mt-2 text-ink-muted" data-testid="dup-note">{{ OPPOSITE_NOTE }}</p>
    </div>
    <template #actions>
      <button v-if="door.pending.value?.kind !== 'opposite'" type="button" class="rounded border border-line px-2 py-1" data-testid="dup-increase" @click="door.answer('increase')">Increase quantity</button>
      <button type="button" class="rounded border border-line px-2 py-1" data-testid="dup-separate" @click="door.answer('separate')">{{ door.pending.value?.kind === 'opposite' ? 'Keep both' : 'Keep separate' }}</button>
      <button type="button" class="col-span-2 rounded border border-line px-2 py-1" data-testid="dup-cancel" @click="door.cancel()">Cancel</button>
    </template>
  </Modal>
</template>
