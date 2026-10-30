<!-- W-117 (REQ-009 AC-4; ADR-114, ADR-077): Market context. The live NIFTY 50 / SENSEX strip (W-115) and one status line
     from the index answer's state. No PCR, OI totals, VIX or any figure the API does not send. -->
<script setup>
import PageHeader from '@/components/common/PageHeader.vue'
import IndexStrip from '@/components/layout/IndexStrip.vue'
</script>

<template>
  <section data-testid="market-context">
    <PageHeader parent="Market" title="Market context" />
    <IndexStrip show-status />
  </section>
</template>
