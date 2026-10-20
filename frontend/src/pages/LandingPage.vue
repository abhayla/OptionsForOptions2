<!-- GC-6 row LANDING (REQ-010 AC-1..3; ADR-144, ADR-145). Public page: no api call, no live or delayed value; every
     sample carries the stamp. All text comes from lib/landingText.js. -->
<script setup>
import {
  SAMPLE_STAMP, PRODUCT_NAME, HERO_LINE, NAV_LABELS, HOW_IT_WORKS, PRICING_TITLE, PRICING_TEXT, FOOTER_LINES, FAQ,
  SAMPLE_CHART_LABEL, SAMPLE_PAYOFF_POINTS,
} from '@/lib/landingText'

// GC-6 row LANDING: no sign-in exists yet (Stage 5), so Sign up and Log in both go to /home for now.
const AUTH_TARGET = '/home'
const points = SAMPLE_PAYOFF_POINTS.map(([x, y]) => `${x},${y}`).join(' ')
</script>

<template>
  <div class="min-h-screen bg-surface text-ink" data-testid="landing-page">
    <header class="border-b border-line">
      <div class="mx-auto flex max-w-5xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <span class="font-semibold text-accent" data-testid="landing-brand">{{ PRODUCT_NAME }}</span>
        <nav class="flex flex-1 flex-wrap gap-x-4 gap-y-1" aria-label="Sections">
          <a href="#how-it-works" class="text-ink-muted">{{ NAV_LABELS.howItWorks }}</a>
          <a href="#pricing" class="text-ink-muted">{{ NAV_LABELS.pricing }}</a>
          <a href="#faq" class="text-ink-muted">{{ NAV_LABELS.faq }}</a>
        </nav>
        <router-link :to="AUTH_TARGET" class="text-accent" data-testid="landing-login">{{ NAV_LABELS.logIn }}</router-link>
      </div>
    </header>

    <main class="mx-auto max-w-5xl px-4 py-8">
      <section class="grid gap-6 md:grid-cols-2 md:items-center">
        <div>
          <h1 class="text-2xl font-semibold" data-testid="landing-hero"><span data-testid="page-title">{{ HERO_LINE }}</span></h1>
          <router-link :to="AUTH_TARGET" class="mt-4 inline-block rounded bg-accent px-4 py-2 text-surface" data-testid="landing-signup">{{ NAV_LABELS.signUp }}</router-link>
        </div>
        <figure class="min-w-0" data-testid="landing-sample">
          <svg viewBox="0 0 200 100" class="w-full max-w-full rounded border border-line bg-surface-muted" role="img" :aria-label="SAMPLE_CHART_LABEL" data-testid="landing-sample-chart">
            <polyline :points="points" fill="none" stroke="currentColor" stroke-width="2" class="text-accent" />
          </svg>
          <figcaption class="mt-1 text-xs text-ink-muted" data-testid="landing-sample-stamp">{{ SAMPLE_STAMP }}</figcaption>
        </figure>
      </section>

      <section id="how-it-works" class="mt-10" data-testid="landing-how">
        <h2 class="text-lg font-semibold">{{ NAV_LABELS.howItWorks }}</h2>
        <div class="mt-3 grid gap-3 md:grid-cols-3">
          <div v-for="c in HOW_IT_WORKS" :key="c.title" class="rounded border border-line p-3" data-testid="landing-how-card">
            <h3 class="font-medium">{{ c.title }}</h3>
            <p class="mt-1 text-ink-muted">{{ c.body }}</p>
          </div>
        </div>
      </section>

      <section id="pricing" class="mt-10" data-testid="landing-pricing">
        <h2 class="text-lg font-semibold">{{ PRICING_TITLE }}</h2>
        <p class="mt-2" data-testid="landing-pricing-text">{{ PRICING_TEXT }}</p>
      </section>

      <section id="faq" class="mt-10" data-testid="landing-faq">
        <h2 class="text-lg font-semibold">{{ NAV_LABELS.faq }}</h2>
        <dl class="mt-3 space-y-3">
          <div v-for="item in FAQ" :key="item.q" data-testid="landing-faq-item">
            <dt class="font-medium">{{ item.q }}</dt>
            <dd class="mt-1 text-ink-muted">{{ item.a }}</dd>
          </div>
        </dl>
      </section>
    </main>

    <footer class="border-t border-line bg-surface-muted" data-testid="landing-footer">
      <div class="mx-auto max-w-5xl space-y-2 px-4 py-4 text-xs text-ink-muted">
        <p v-for="line in FOOTER_LINES" :key="line" data-testid="landing-footer-line" class="break-words">{{ line }}</p>
      </div>
    </footer>
  </div>
</template>
