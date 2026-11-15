<script setup>
// Issue 689: the in-page toasts (useToast); never a native dialog, so the page keeps updating while a toast is shown
import { computed } from 'vue'
import { dismissToast, openToast, toasts } from '@/composables/useToast'
const newestFirst = computed(() => [...toasts].reverse())
</script>

<template>
  <!-- u506: an overlay fixed at the BOTTOM RIGHT, where no page has a control (the Search boxes are top right). It takes no
       room, so no page content moves; flex-col-reverse puts the newest (first in the DOM) nearest the corner and stacks the
       older ones upward. bottom-24 clears a one-row sticky bar (OptionChainPage.vue:292). z-30 is below the modal and the
       common drawer (z-50) and the adjust drawer (z-40), so a pop-up never covers a Confirm or Cancel. -->
  <div class="fixed bottom-24 right-4 z-30 flex w-80 flex-col-reverse gap-2" aria-live="polite" data-testid="toast-host">
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
