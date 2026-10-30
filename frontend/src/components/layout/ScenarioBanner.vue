<!-- GC-ADJ1 step 1b (W-196): shown on every screen of the logged-in shell while the API serves a scenario of the
     adjustment library (GET /features `scenario`, dev/test only). Absent otherwise. -->
<script setup>
import { useScenarioBanner } from "@/lib/scenarioMode";

const text = useScenarioBanner();
</script>

<template>
  <div
    v-if="text"
    role="status"
    class="w-full bg-warn px-4 py-1 text-center text-sm font-semibold text-surface"
    data-testid="scenario-banner"
  >
    {{ text }}
  </div>
</template>
