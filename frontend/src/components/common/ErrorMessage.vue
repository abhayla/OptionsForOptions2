<!-- The REQ-065 four-part error message: what happened, impact, what is blocked, next action. Text is the catalogue's
     (or the neutral fallback); nothing else from the server is ever shown. W-072 (ADR-086): `compact` is the smaller form
     used inside the leg picker and the Save Draft bar - it still shows all four parts under their labels. `prefix` names the
     inner test ids (`<prefix>-what`, `-impact`, `-blocked`, `-next`) so two messages on one page do not collide. -->
<script setup>
defineProps({
  parts: { type: Object, required: true },
  compact: { type: Boolean, default: false },
  prefix: { type: String, default: 'error' },
})
</script>

<template>
  <div role="alert" :class="compact ? 'rounded border border-line bg-surface p-2 text-sm' : 'rounded border border-line bg-surface p-4'" data-testid="error-message">
    <p class="font-medium" :data-testid="`${prefix}-what`">{{ parts.what_happened }}</p>
    <dl class="mt-2 space-y-1 text-sm">
      <div><dt class="inline font-medium">What this means: </dt><dd class="inline" :data-testid="`${prefix}-impact`">{{ parts.impact }}</dd></div>
      <div><dt class="inline font-medium">What is blocked: </dt><dd class="inline" :data-testid="`${prefix}-blocked`">{{ parts.what_is_blocked }}</dd></div>
      <div><dt class="inline font-medium">What to do next: </dt><dd class="inline" :data-testid="`${prefix}-next`">{{ parts.next_action }}</dd></div>
    </dl>
  </div>
</template>
