<!-- Skeleton only (ADR-030): an empty placeholder naming the section's sub-items. No feature screen, no form. -->
<script setup>
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <section data-testid="placeholder-page">
    <p v-if="route.meta.parent" class="text-xs text-ink-muted" data-testid="page-parent">{{ route.meta.parent }}</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">{{ route.meta.title }}</h1>
    <p v-if="route.meta.note" class="mt-1 text-ink-muted" data-testid="page-note">{{ route.meta.note }}</p>
    <p class="mt-2 text-ink-muted">This page is a placeholder. It is built in a later work item.</p>
    <ul v-if="route.meta.subItems" class="mt-4 divide-y divide-line rounded border border-line bg-surface">
      <li v-for="item in route.meta.subItems" :key="item.to">
        <router-link :to="item.to" class="block px-3 py-2 hover:bg-accent-soft" data-testid="subitem-link">{{ item.label }}</router-link>
      </li>
    </ul>
  </section>
</template>
