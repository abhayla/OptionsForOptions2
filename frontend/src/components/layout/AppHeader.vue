<!-- Adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/layout/KiteHeader.vue (ADR-047).
     Renamed and restyled with our tokens (ADR-049); broker switching and market-data source toggles removed (ADR-012);
     the nav is built from the route table (REQ-009) and the avatar opens Account & Settings (AC-8). -->
<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { SECTIONS, ACCOUNT_ITEMS, ACCOUNT_LABEL } from '@/router/nav'

const menuOpen = ref(false)
const accountWrap = ref(null)
const route = useRoute()
watch(() => route.fullPath, () => { menuOpen.value = false })

// Close the account menu on Escape and on a click outside it (W-054 review follow-up).
function onKeydown(e) {
  if (e.key === 'Escape') menuOpen.value = false
}
function onDocumentClick(e) {
  if (menuOpen.value && accountWrap.value && !accountWrap.value.contains(e.target)) menuOpen.value = false
}
onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('click', onDocumentClick)
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('click', onDocumentClick)
})
</script>

<template>
  <header class="border-b border-line bg-surface" data-testid="app-header">
    <div class="mx-auto flex max-w-5xl items-center gap-3 px-4 py-2">
      <router-link to="/home" class="font-semibold text-accent" data-testid="brand">OptionsForOptions</router-link>
      <nav class="min-w-0 flex-1 overflow-x-auto" aria-label="Primary" data-testid="primary-nav">
        <ul class="flex gap-1 whitespace-nowrap">
          <li v-for="s in SECTIONS" :key="s.key">
            <router-link
              :to="`/${s.key}`"
              class="block rounded px-3 py-1.5 text-ink-muted hover:bg-accent-soft"
              active-class="bg-accent-soft font-medium text-accent"
              :data-testid="`nav-${s.key}`"
              >{{ s.label }}</router-link
            >
          </li>
        </ul>
      </nav>
      <div ref="accountWrap" class="relative shrink-0">
        <button
          type="button"
          aria-controls="account-menu"
          class="flex h-8 w-8 items-center justify-center rounded-full border border-line bg-surface-muted text-xs font-medium"
          aria-label="Account menu"
          :aria-expanded="menuOpen"
          data-testid="avatar-menu"
          @click="menuOpen = !menuOpen"
        >
          You
        </button>
        <div
          v-if="menuOpen"
          id="account-menu"
          class="absolute right-0 z-10 mt-2 w-60 rounded border border-line bg-surface py-1 shadow-sm"
          data-testid="account-menu"
        >
          <router-link to="/settings" class="block px-3 py-1.5 font-medium" data-testid="account-menu-title">{{ ACCOUNT_LABEL }}</router-link>
          <ul class="border-t border-line">
            <li v-for="[slug, label] in ACCOUNT_ITEMS" :key="slug">
              <router-link :to="`/settings/${slug}`" class="block px-3 py-1.5 text-ink-muted hover:bg-accent-soft" data-testid="account-menu-item">{{ label }}</router-link>
            </li>
          </ul>
        </div>
      </div>
    </div>
  </header>
</template>
