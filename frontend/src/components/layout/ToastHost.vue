<script setup>
// Issue 689: the in-page toasts (useToast); never a native dialog, so the page keeps updating while a toast is shown
import { computed } from 'vue'
import { dismissToast, openToast, toasts } from '@/composables/useToast'
const newestFirst = computed(() => [...toasts].reverse())
</script>

<template>
  <!-- D-67 (owner decision, binding; replaces the u506 fixed bottom-right overlay, which still covered page buttons): the pop-ups are an
       ordinary block in the page flow, between the header and the page content, in the page's own column width. Being in the flow
       it can overlay nothing: the page content is laid out below it (the same way the scenario and calendar banners are). It takes
       no room with no pop-up. Newest first (top). -->
  <div v-if="newestFirst.length" class="mx-auto flex w-full max-w-[1200px] flex-col gap-2 px-4 pt-3" aria-live="polite" data-testid="toast-host">
    <div
      v-for="t in newestFirst"
      :key="t.id"
      role="status"
      class="rounded-lg border border-line bg-surface p-3 text-sm text-ink shadow-lg"
      data-testid="toast"
    >
      <p>{{ t.icon }} {{ t.message }}</p>
      <div class="mt-2 flex justify-end gap-2">
        <button v-if="t.onClick" type="button" class="rounded bg-accent px-2 py-1 text-white" data-testid="toast-open" @click="openToast(t.id)">Open</button>
        <button type="button" class="rounded border border-line px-2 py-1" data-testid="toast-dismiss" @click="dismissToast(t.id)">Dismiss</button>
      </div>
    </div>
  </div>
</template>
