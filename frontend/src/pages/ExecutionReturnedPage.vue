<!-- Where Kite sends the browser back after a basket (W-104 with W-105's redirect; REQ-073 AC-3, ADR-097 (2), F-41).
     Nothing runs on load: the page reads only the locally stored id of the last executed strategy and offers the
     owner's "Check with Zerodha"; with none stored, a link back to the strategies. New file, copy from: none. -->
<script setup>
import ReturnCheck from '@/components/execution/ReturnCheck.vue'
import { readLastExecuted } from '@/lib/execute'

const strategyId = readLastExecuted()
</script>

<template>
  <section class="p-4" data-testid="execution-returned">
    <p>Your orders were handled on Kite's page.</p>
    <ReturnCheck v-if="strategyId !== null" :strategy-id="strategyId" />
    <p v-else class="mt-2" data-testid="returned-no-strategy">
      <RouterLink to="/strategies" class="underline">Back to your strategies</RouterLink>
    </p>
  </section>
</template>
