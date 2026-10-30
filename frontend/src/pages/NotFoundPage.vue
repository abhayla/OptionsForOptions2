<script setup>
import PageHeader from '@/components/common/PageHeader.vue'
</script>

<template>
  <section data-testid="not-found">
    <PageHeader title="Page not found" />
    <div class="rounded-lg border border-line bg-surface px-4 py-8 text-center">
      <p class="text-sm text-ink-muted">This address does not exist.</p>
      <router-link to="/home" class="btn btn-primary mt-4">Go to Home</router-link>
    </div>
  </section>
</template>
