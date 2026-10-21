<!-- GC-6 BILLING-SHELL (ADR-146): Subscription & Billing, Free Eligibility and Referrals while the paid plan is held
     (ADR-055). Text only, from lib/billingText.js: no Subscribe / Apply / Invite control, no trial countdown. -->
<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { BILLING_PAGES } from '@/lib/billingText'

const route = useRoute()
const lines = computed(() => BILLING_PAGES[String(route.path).split('/').pop()] ?? [])
</script>

<template>
  <section data-testid="billing-shell-page">
    <p v-if="route.meta.parent" class="text-xs text-ink-muted" data-testid="page-parent">{{ route.meta.parent }}</p>
    <h1 class="text-xl font-semibold" data-testid="page-title">{{ route.meta.title }}</h1>
    <p v-for="(line, i) in lines" :key="i" class="mt-2 break-words" data-testid="billing-line">{{ line }}</p>
  </section>
</template>
