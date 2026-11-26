<!-- D-21 (ADR-320 (3)): the "What changes" block of one approach: the position as it stands against the position after
     the approach, eight measures each marked up or down, and one plain reason line where the server sent one.
     Every text is the server's; nothing is computed here. No verdict is drawn. -->
<template>
  <section class="rounded-lg border border-line bg-surface p-3" :data-testid="`adjust-wc-${id}`">
    <h4 class="text-sm font-semibold" :data-testid="`adjust-wc-title-${id}`">{{ block.title }}</h4>
    <p class="text-xs text-ink-muted">{{ name }}</p>
    <div class="mt-2 min-w-0 overflow-x-auto">
      <table class="w-full border-collapse text-sm">
        <thead>
          <tr>
            <th scope="col" class="p-1 text-left text-xs font-semibold">Measure</th>
            <th scope="col" class="p-1 text-left text-xs font-semibold">Before</th>
            <th scope="col" class="p-1 text-left text-xs font-semibold">After</th>
            <th scope="col" class="p-1 text-left text-xs font-semibold">Direction</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in block.rows" :key="r.id" :data-testid="`adjust-wc-${id}-${r.id}`">
            <th scope="row" class="p-1 text-left font-normal">{{ r.label }}</th>
            <td class="p-1 align-top tabular-nums" data-testid="adjust-wc-before">{{ r.before_text }}</td>
            <td class="p-1 align-top tabular-nums">
              <span data-testid="adjust-wc-after">{{ r.after_text }}</span>
              <div v-if="r.unavailable_reason" class="text-xs text-ink-muted" data-testid="adjust-wc-unavailable">{{ r.unavailable_reason }}</div>
            </td>
            <td class="p-1 align-top" data-testid="adjust-wc-direction">{{ r.direction_text }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="block.reason_line" class="mt-2 text-sm" :data-testid="`adjust-wc-reason-${id}`">{{ block.reason_line }}</p>
  </section>
</template>

<script setup>
defineProps({
  id: { type: String, required: true },
  name: { type: String, default: '' },
  block: { type: Object, required: true }, // { title, rows: [{ id, label, before_text, after_text, direction, direction_text, unavailable_reason }], reason_line }
})
</script>
