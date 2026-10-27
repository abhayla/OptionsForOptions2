<!-- ADR-193 UI-009: a flat card (surface, 1 px line border, 8 px radius, no shadow). Optional header row (48 px): title
     left, the `actions` slot right. Padding 16 px unless `flush` (a table that runs edge to edge). -->
<script setup>
defineProps({
  title: { type: String, default: "" },
  flush: { type: Boolean, default: false },
});
</script>

<template>
  <section class="rounded-lg border border-line bg-surface" data-testid="card">
    <header
      v-if="title || $slots.actions"
      class="flex h-12 items-center justify-between gap-3 border-b border-line px-4"
    >
      <h2
        class="text-base leading-[22px] font-semibold text-ink"
        data-testid="card-title"
      >
        {{ title }}
      </h2>
      <div class="flex items-center gap-2"><slot name="actions" /></div>
    </header>
    <div :class="flush ? '' : 'p-4'"><slot /></div>
  </section>
</template>
