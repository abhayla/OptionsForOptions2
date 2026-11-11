<!-- ADR-285: shown on every screen of the logged-in shell from 30 days before the market calendar's last date, and on a date
     the calendar does not cover. One read of the index reply when the shell opens, then every 30 minutes (no socket); absent otherwise.
     Only that reply carries the two calendar fields, so the read stays (a plain read may subscribe the feed on a cold start). -->
<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";
import { readCalendarNotice } from "@/lib/calendarNotice";

// A page left open across a date change or a calendar load follows the server: re-read every 30 minutes.
const REREAD_MS = 30 * 60 * 1000;
const text = ref(null);
let timer = null;
const refresh = async () => {
  text.value = await readCalendarNotice();
};
onMounted(() => {
  refresh();
  timer = setInterval(refresh, REREAD_MS);
});
onBeforeUnmount(() => clearInterval(timer));
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
