<!-- Adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/layout/KiteLayout.vue (ADR-047).
     Renamed, restyled with our tokens (ADR-049); watchlist/auth stores and WebSocket bootstrap removed.
     ADR-193 / UI-004: the builder and the option chain (route meta.fullWidth) use the full width with 16 px gutters;
     every other page sits in a centred 1200 px column. Page background --bg. -->
<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from './AppHeader.vue'
import ScenarioBanner from './ScenarioBanner.vue'

const route = useRoute()
const fullWidth = computed(() => Boolean(route.meta?.fullWidth))
</script>

<template>
  <div class="min-h-screen bg-bg text-ink" data-testid="app-layout">
    <ScenarioBanner />
    <AppHeader />
    <main
      class="px-4 py-6"
      :class="fullWidth ? 'w-full' : 'mx-auto max-w-[1200px]'"
      :data-width="fullWidth ? 'full' : 'column'"
      data-testid="app-content"
    >
      <slot />
    </main>
  </div>
</template>
