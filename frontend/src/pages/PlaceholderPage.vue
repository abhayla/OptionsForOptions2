<!-- Skeleton only (ADR-030): an empty placeholder naming the section's sub-items. No feature screen, no form.
     ADR-193 (4) (Sensibull 171 / 172): the shared page header, then the shared empty state naming what is coming, then
     the section's sub-items as a list in one card. -->
<script setup>
import { useRoute } from 'vue-router'
import PageHeader from '@/components/common/PageHeader.vue'
import EmptyState from '@/components/states/EmptyState.vue'

const route = useRoute()
</script>

<template>
  <section data-testid="placeholder-page">
    <PageHeader :parent="route.meta.parent ?? ''" :title="route.meta.title" :note="route.meta.note ?? ''" />
    <EmptyState
      :title="`${route.meta.title} is coming`"
      message="This page is a placeholder. It is built in a later work item."
      icon="list"
    />
    <ul v-if="route.meta.subItems" class="mt-4 divide-y divide-line overflow-hidden rounded-lg border border-line bg-surface text-sm">
      <li v-for="item in route.meta.subItems" :key="item.to">
        <router-link :to="item.to" class="block px-4 py-2.5 hover:bg-surface-muted" data-testid="subitem-link">{{ item.label }}</router-link>
      </li>
    </ul>
  </section>
</template>
