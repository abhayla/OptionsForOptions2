<!-- ADR-193 / UI study UI-002, UI-003: one small set of line icons (stroke = currentColor, so colour comes from the
     text token around it). Decorative only: aria-hidden; the label beside it carries the meaning. -->
<script setup>
import { computed } from "vue";

const PATHS = {
  home: "M4 10.5 12 4l8 6.5V20h-5v-6h-6v6H4z",
  layers: "M12 4 3 9l9 5 9-5zM3 14l9 5 9-5",
  plus: "M12 5v14M5 12h14",
  list: "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",
  pulse: "M3 12h4l3-7 4 14 3-7h4",
  sliders: "M4 7h10M18 7h2M4 17h4M12 17h8M14 5v4M8 15v4",
  check: "M4 12.5 9 17.5 20 6.5",
  table: "M4 5h16v14H4zM4 10h16M10 10v9",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
  depth: "M4 6h16M4 10h12M4 14h16M4 18h9",
  chart: "M4 19h16M6 15l4-5 3 3 5-7",
  globe:
    "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3.5 3 14.5 0 18M12 3c-3 3.5-3 14.5 0 18",
  briefcase: "M4 8h16v11H4zM9 8V5h6v3",
  receipt: "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6",
  bell: "M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 20h4",
  book: "M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2zM4 5v16",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  logout: "M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10",
  chevron: "M6 9l6 6 6-6",
  close: "M6 6l12 12M18 6 6 18",
  info: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v6M12 7.5v.01",
  trash: "M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6",
  pencil: "M4 20h4L19 9l-4-4L4 16zM13 7l4 4",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  gear: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6",
};

const props = defineProps({
  name: { type: String, required: true },
  size: { type: Number, default: 20 },
});
const d = computed(() => PATHS[props.name] ?? PATHS.list);
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
    class="shrink-0"
  >
    <path :d="d" />
  </svg>
</template>
