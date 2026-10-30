<!-- One page header for every screen (owner 2026-10-30, ADR-193; Sensibull 001 / 050 / 117 / 167): a small muted parent
     label, the page title, an optional one-line note, and an optional actions slot on the right. Every page starts at the
     same left edge and the same top spacing, so the breadcrumb, title and content line up from screen to screen.
     The testids `page-parent`, `page-title` (and `noteTestid` for the note) are the ones the pages used before. -->
<script setup>
defineProps({
  parent: { type: String, default: '' },
  title: { type: String, required: true },
  note: { type: String, default: '' },
  noteTestid: { type: String, default: 'page-note' },
})
</script>

<template>
  <header class="mb-4 flex flex-wrap items-end justify-between gap-x-4 gap-y-2" data-testid="page-header">
    <div>
      <p v-if="parent" class="text-xs leading-4 text-ink-subtle" data-testid="page-parent">{{ parent }}</p>
      <h1 class="text-xl leading-7 font-semibold text-ink" data-testid="page-title">{{ title }}</h1>
      <p v-if="note || $slots.note" class="mt-0.5 text-sm text-ink-muted" :data-testid="noteTestid"><slot name="note">{{ note }}</slot></p>
    </div>
    <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2" data-testid="page-actions"><slot name="actions" /></div>
  </header>
</template>
