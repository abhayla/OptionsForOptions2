<!-- GC-6 ST-EMPTY. Generic: a message and at most one next-step button (rendered only when `actionLabel` is given; goes to `actionTo` when set).
     ADR-193 UI-021 restyle (Sensibull S-010, S-050, S-171): centred, a 120 px muted circle holding a 48 px line icon, an
     optional 15 px/600 `title`, the message as one 14 px muted sentence, and the one optional button. -->
<script setup>
import { getCurrentInstance } from 'vue'
import Icon from '@/components/common/Icon.vue'

const props = defineProps({
  message: { type: String, required: true },
  title: { type: String, default: '' },
  icon: { type: String, default: 'list' },
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
  <div class="flex flex-col items-center rounded-lg border border-line bg-surface px-4 py-8 text-center" data-testid="empty-state">
    <div class="flex size-30 items-center justify-center rounded-full bg-surface-muted text-ink-subtle" aria-hidden="true"><Icon :name="icon" :size="48" /></div>
    <p v-if="title" class="mt-4 text-[15px] leading-5 font-semibold text-ink" data-testid="empty-state-title">{{ title }}</p>
    <p class="mt-2 text-sm text-ink-muted" data-testid="empty-state-message">{{ message }}</p>
    <button
      v-if="actionLabel"
      type="button"
      class="mt-4 min-h-[44px] rounded-md bg-accent px-4 text-sm font-medium text-surface hover:bg-accent-hover"
      data-testid="empty-state-action"
      @click="onAction"
    >
      {{ actionLabel }}
    </button>
  </div>
</template>
