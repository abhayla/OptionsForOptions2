<!-- Where a successful Zerodha login lands (issue #159; W-058 CONNECTED_FRONTEND_PATH). Plain confirmation. Wording is
     decision-support (ADR-003). -->
<template>
  <section data-testid="broker-connected">
    <h1 class="text-xl font-semibold" data-testid="page-title">Zerodha is connected</h1>
    <p class="mt-2" data-testid="connected-what">Your Zerodha account is now linked to this platform for today.</p>
    <p class="mt-2 text-sm text-ink-muted">You can now plan a strategy and see its outcome using market data from your account. Nothing is ordered until you choose to.</p>
    <router-link to="/strategy/builder" class="mt-4 inline-block rounded border border-line bg-surface px-3 py-2 hover:bg-accent-soft" data-testid="to-builder">Open the Strategy Builder</router-link>
  </section>
</template>
