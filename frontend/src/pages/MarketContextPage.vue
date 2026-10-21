<!-- W-117 (REQ-009 AC-4; ADR-114, ADR-077): Market context. The live NIFTY 50 / SENSEX strip (W-115) and one status line
     from the index answer's state. No PCR, OI totals, VIX or any figure the API does not send. -->
<script setup>
import IndexStrip from '@/components/layout/IndexStrip.vue'
</script>

<template>
  <section data-testid="market-context">
    <p class="text-xs text-ink-muted" data-testid="page-parent">Market</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">Market context</h1>
    <IndexStrip class="mt-3" show-status />
  </section>
</template>
