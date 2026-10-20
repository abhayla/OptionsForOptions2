<!-- GC-6 ST-EMPTY. Generic: a message and at most one next-step button (rendered only when `actionLabel` is given; goes to `actionTo` when set). -->
<script setup>
import { getCurrentInstance } from 'vue'

const props = defineProps({
  message: { type: String, required: true },
  actionLabel: { type: String, default: null },
  actionTo: { type: [String, Object], default: null }, // optional route (path or { name }) the button goes to (ADR-130)
})
const emit = defineEmits(['action'])
const router = getCurrentInstance()?.appContext.config.globalProperties.$router
function onAction() {
  emit('action')
  if (props.actionTo && router) router.push(props.actionTo)
}
</script>

<template>
  <div class="rounded border border-line bg-surface p-4 text-sm" data-testid="empty-state">
    <p data-testid="empty-state-message">{{ message }}</p>
    <button v-if="actionLabel" type="button" class="mt-3 min-h-[44px] rounded border border-line px-3" data-testid="empty-state-action" @click="onAction">{{ actionLabel }}</button>
  </div>
</template>
