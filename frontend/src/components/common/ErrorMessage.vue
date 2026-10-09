<!-- The REQ-065 four-part error message: what happened, impact, what is blocked, next action. Text is the catalogue's
     (or the neutral fallback); nothing else from the server is ever shown. -->
<script setup>
defineProps({ parts: { type: Object, required: true } })
</script>

<template>
  <div role="alert" class="rounded border border-line bg-surface p-4" data-testid="error-message">
    <p class="font-medium" data-testid="error-what">{{ parts.what_happened }}</p>
    <dl class="mt-2 space-y-1 text-sm">
      <div><dt class="inline font-medium">What this means: </dt><dd class="inline" data-testid="error-impact">{{ parts.impact }}</dd></div>
      <div><dt class="inline font-medium">What is blocked: </dt><dd class="inline" data-testid="error-blocked">{{ parts.what_is_blocked }}</dd></div>
      <div><dt class="inline font-medium">What to do next: </dt><dd class="inline" data-testid="error-next">{{ parts.next_action }}</dd></div>
    </dl>
  </div>
</template>
