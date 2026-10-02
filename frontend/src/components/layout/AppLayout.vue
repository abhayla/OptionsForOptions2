<!-- Adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/layout/KiteLayout.vue (ADR-047).
     Renamed, restyled with our tokens (ADR-049); watchlist/auth stores and WebSocket bootstrap removed. -->
<script setup>
import AppHeader from './AppHeader.vue'
</script>

<template>
  <div class="min-h-screen bg-surface-muted text-ink" data-testid="app-layout">
    <AppHeader />
    <main class="mx-auto max-w-5xl px-4 py-6" data-testid="app-content">
      <slot />
    </main>
  </div>
</template>
