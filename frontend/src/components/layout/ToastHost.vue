<script setup>
// Issue 689: the in-page toasts (useToast); never a native dialog, so the page keeps updating while a toast is shown
import { dismissToast, openToast, toasts } from '@/composables/useToast'
</script>

<template>
  <!-- u506: in the page flow, right under the header row, so it pushes the page down and never covers the Search box or
       the bell; sticky keeps it in view while scrolling; several stack downward. -->
  <div class="sticky top-14 z-30 flex flex-col" aria-live="polite" data-testid="toast-host">
    <div
      v-for="t in toasts"
      :key="t.id"
      role="status"
      class="mx-4 mt-2 rounded-lg border border-line bg-surface p-3 text-sm text-ink shadow-lg"
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
