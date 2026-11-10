<!-- ADR-285: shown on every screen of the logged-in shell from 30 days before the market calendar's last date, and on a date
     the calendar does not cover. One read of the index reply when the shell opens (no socket); absent otherwise. -->
<script setup>
import { onMounted, ref } from "vue";
import { readCalendarNotice } from "@/lib/calendarNotice";

const text = ref(null);
onMounted(async () => {
  text.value = await readCalendarNotice();
});
</script>

<template>
  <div
    v-if="text"
    role="status"
    class="w-full bg-warn px-4 py-1 text-center text-sm font-semibold text-surface"
    data-testid="calendar-banner"
  >
    {{ text }}
  </div>
</template>
