<!-- ADR-329 (2): "Leave the builder? The N unsaved legs will be lost." with Stay and Leave. Escape, x and the overlay are Stay, never
     Leave. Used by the builder page and the Option Chain page, from one composable (useLeaveBuilder). -->
<script setup>
import Modal from '@/components/common/Modal.vue'
import { leaveQuestion } from '@/composables/useLeaveBuilder'

defineProps({ leave: { type: Object, required: true } })
</script>

<template>
  <Modal :open="leave.question.value !== null" title="Leave the builder?" @close="leave.stay()">
    <div data-testid="leave-dialog"><p data-testid="leave-question">{{ leave.question.value ? leaveQuestion(leave.question.value.count, leave.question.value.pending) : '' }}</p></div>
    <template #actions>
      <button type="button" class="rounded border border-line px-2 py-1" data-testid="leave-stay" @click="leave.stay()">Stay</button>
      <button type="button" class="rounded border border-line px-2 py-1" data-testid="leave-leave" @click="leave.leave()">Leave</button>
    </template>
  </Modal>
</template>
