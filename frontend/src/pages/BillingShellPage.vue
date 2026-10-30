<!-- GC-6 BILLING-SHELL (ADR-146): Subscription & Billing, Free Eligibility and Referrals while the paid plan is held
     (ADR-055). Text only, from lib/billingText.js: no Subscribe / Apply / Invite control, no trial countdown. -->
<script setup>
import PageHeader from '@/components/common/PageHeader.vue'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { BILLING_PAGES } from '@/lib/billingText'

const route = useRoute()
const lines = computed(() => BILLING_PAGES[String(route.path).split('/').pop()] ?? [])
</script>

<template>
  <section data-testid="billing-shell-page">
    <PageHeader :parent="route.meta.parent ?? ''" :title="route.meta.title" />
    <!-- Owner 2026-10-30 (Sensibull 167): the lines sit in one settings card -->
    <div class="grid gap-2 rounded-lg border border-line bg-surface p-6 text-sm">
      <p v-for="(line, i) in lines" :key="i" class="break-words" data-testid="billing-line">{{ line }}</p>
    </div>
  </section>
</template>
