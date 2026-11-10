<script setup>
// #689: the in-page toasts (useToast); never a native dialog, so the page keeps updating while a toast is shown
import { dismissToast, openToast, toasts } from '@/composables/useToast'
</script>

<template>
  <div class="fixed right-4 top-16 z-40 flex w-80 flex-col gap-2" aria-live="polite" data-testid="toast-host">
    <div
      v-for="t in toasts"
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
