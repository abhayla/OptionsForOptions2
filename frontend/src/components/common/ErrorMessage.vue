<!-- The REQ-065 four-part error message: what happened, impact, what is blocked, next action. Text is the catalogue's
     (or the neutral fallback); nothing else from the server is ever shown. W-072 (ADR-086): `compact` is the smaller form
     used inside the leg picker and the Save Draft bar - it still shows all four parts under their labels. `prefix` names the
     inner test ids (`<prefix>-what`, `-impact`, `-blocked`, `-next`) so two messages on one page do not collide.
     ADR-193 UI-020: a card with a 4 px loss-colour left border on the soft loss fill, the parts as 13 px label:value lines;
     compact keeps all four parts with 110 px labels and wrapping text. Never a toast. -->
<script setup>
defineProps({
  parts: { type: Object, required: true },
  compact: { type: Boolean, default: false },
  prefix: { type: String, default: 'error' },
})
</script>

<template>
  <div
    role="alert"
    :class="compact ? 'rounded-md border-l-4 border-loss bg-loss-soft p-2 text-[13px]' : 'rounded-md border-l-4 border-loss bg-loss-soft p-4 text-sm'"
    data-testid="error-message"
  >
    <p class="font-semibold text-ink" :data-testid="`${prefix}-what`">{{ parts.what_happened }}</p>
    <dl class="mt-2 space-y-1 text-[13px] leading-[18px] text-ink">
      <div :class="compact ? 'grid grid-cols-[110px_1fr] gap-x-2' : ''"><dt class="inline font-medium text-ink-muted">What this means: </dt><dd class="inline" :data-testid="`${prefix}-impact`">{{ parts.impact }}</dd></div>
      <div :class="compact ? 'grid grid-cols-[110px_1fr] gap-x-2' : ''"><dt class="inline font-medium text-ink-muted">What is blocked: </dt><dd class="inline" :data-testid="`${prefix}-blocked`">{{ parts.what_is_blocked }}</dd></div>
      <div :class="compact ? 'grid grid-cols-[110px_1fr] gap-x-2' : ''"><dt class="inline font-medium text-ink-muted">What to do next: </dt><dd class="inline" :data-testid="`${prefix}-next`">{{ parts.next_action }}</dd></div>
    </dl>
  </div>
</template>
