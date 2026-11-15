<script setup>
// Issue 689: the in-page toasts (useToast); never a native dialog, so the page keeps updating while a toast is shown
import { dismissToast, openToast, toasts } from '@/composables/useToast'
</script>

<template>
  <!-- u506: a reserved slot right under the header row. Its height is fixed whether or not a toast shows, so a toast never
       covers the Search box or the bell and never moves the page under the user's cursor (a click could land on a
       Confirm); further toasts stack downward and scroll inside the slot. -->
  <div class="flex h-16 flex-col overflow-y-auto" aria-live="polite" data-testid="toast-host">
    <div
      v-for="t in toasts"
      :key="t.id"
      role="status"
      class="mx-4 mt-1 flex shrink-0 items-center gap-3 rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink shadow-lg"
      data-testid="toast"
    >
      <p class="min-w-0 flex-1">{{ t.icon }} {{ t.message }}</p>
      <div class="flex shrink-0 gap-2">
        <button v-if="t.onClick" type="button" class="rounded bg-accent px-2 py-1 text-white" data-testid="toast-open" @click="openToast(t.id)">Open</button>
        <button type="button" class="rounded border border-line px-2 py-1" data-testid="toast-dismiss" @click="dismissToast(t.id)">Dismiss</button>
      </div>
    </div>
  </div>
</template>
