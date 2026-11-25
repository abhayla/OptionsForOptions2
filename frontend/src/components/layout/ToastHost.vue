<script setup>
// Issue 689: the in-page toasts (useToast); never a native dialog, so the page keeps updating while a toast is shown
import { computed } from 'vue'
import { dismissToast, openToast, toasts } from '@/composables/useToast'
const newestFirst = computed(() => [...toasts].reverse())
</script>

<template>
  <!-- D-67 (owner decision, binding; replaces the u506 fixed bottom-right overlay): AppLayout renders this INSIDE the sticky header block,
       so a pop-up raised while the trader is scrolled down is still on screen, and nothing is fixed over the page content. The
       aria-live region is always rendered (empty with no pop-up) so the first announcement is read. Newest first (top). -->
  <div class="mx-auto flex w-full max-w-[1200px] flex-col gap-2 px-4" :class="newestFirst.length ? 'py-2' : ''" aria-live="polite" data-testid="toast-host">
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
