<!-- R2 FC2 (board I-86, TD defect D-TD-2): the ONE failed-load state of every list page. The server sent no message of its own (the API
     is down, the answer timed out or could not be read; `parts` is empty or the neutral fallback): ONE shared sentence and a Retry button, the
     same words on every list. The server did send its message (a refusal such as "connect your account"): that four-part message stays,
     and Retry sits under it. Ids are `<prefix>-error` / `<prefix>-retry` (LoadFailed) or `<prefix>-retry` under the message.
     Pending owner read: LIST_FAILED_TEXT. -->
<script setup>
import { computed } from 'vue'
import { NEUTRAL_PARTS } from '@/services/api'
import ErrorMessage from '@/components/common/ErrorMessage.vue'
import LoadFailed from '@/components/common/LoadFailed.vue'
import { RETRY_LABEL } from '@/lib/sharedStateText'
import { LIST_FAILED_TEXT } from '@/lib/listFailed'

const props = defineProps({ parts: { type: Object, default: null }, prefix: { type: String, required: true }, compact: { type: Boolean, default: false } })
defineEmits(['retry'])
const neutral = computed(() => !props.parts || props.parts === NEUTRAL_PARTS)
</script>

<template>
  <LoadFailed v-if="neutral" :text="LIST_FAILED_TEXT" :prefix="prefix" @retry="$emit('retry')" />
  <div v-else>
    <ErrorMessage :parts="parts" :compact="compact" :prefix="prefix" />
    <button type="button" class="mt-2 rounded border border-line bg-surface px-2 py-1 text-xs font-medium text-ink" :data-testid="`${prefix}-retry`" @click="$emit('retry')">{{ RETRY_LABEL }}</button>
  </div>
</template>
