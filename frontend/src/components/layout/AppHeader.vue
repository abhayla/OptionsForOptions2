<!-- Adapted from abhayla/algochanakya@bf9faf7:frontend/src/components/layout/KiteHeader.vue (ADR-047).
     Renamed and restyled with our tokens (ADR-049); broker switching and market-data source toggles removed (ADR-012);
     the nav is built from the route table (REQ-009) and the avatar opens Account & Settings (AC-8).
     ADR-193 / UI study a.1 (UI-001..UI-003), Sensibull S-001..S-004, S-012, S-107: a 56 px sticky bar with logo +
     "/ page name" breadcrumb, the seven sections centred, active section = accent text + 3 px underline, and every
     section opens a menu of its REQ-009 items (mega menu for Strategies and Market, a small dropdown for the rest).
     The section name stays a link to its section page (REQ-009 section page, every item listed); the chevron beside it
     is the menu button (Enter/Space/ArrowDown open, arrows move, Esc closes and returns focus). A mouse hovering a
     section opens its menu after 150 ms; touch and pen never hover-open. -->
<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import Icon from '@/components/common/Icon.vue'
import { showInfo } from '@/lib/infoPopup'
import { compareAllUrl } from '@/lib/adjustDrawer'
import { bellCount, dropActive, isLevelWatch, openRecords, readActive, readOpportunities, readStopFired, takeActive, takeOpportunities, takeStopFired } from '@/lib/paperAlerts'
import { plainName } from '@/lib/saveDraft'
import { usePaperRefresh } from '@/lib/usePaperRefresh'
import { ACCOUNT_LABEL, ACCOUNT_MENU_ITEMS, ITEM_DESCRIPTIONS, MEGA_MENUS, MENU_SECTIONS, firstBuiltPath } from '@/router/nav'

const HOVER_DELAY_MS = 150
const SMALL_MENU_WIDTH = 256
const SECTION_ICONS = { home: 'home', strategies: 'layers', positions: 'briefcase', market: 'chart', orders: 'receipt', alerts: 'bell', learn: 'book' }
const ITEM_ICONS = {
  'strategy-builder': 'layers',
  'create-strategy': 'plus',
  'my-strategies': 'list',
  'live-strategies': 'pulse',
  adjustments: 'sliders',
  'completed-strategies': 'check',
  'option-chain': 'table',
  'underlying-index-view': 'chart',
  'market-context': 'globe',
}

const route = useRoute()
const router = useRouter()
const total = computed(() => bellCount())
// ADR-330 (3), REQ-170 AC-3: ONE announcer, fed by GET /alerts/active, once per (id, escalated_at): a new alert or a later
// escalation of the same one; never two pop-ups for one plan stop. D-67 (ADR-326 (5)): the quiet rule is the popup_due of the
// open adjustment record with the same id (absent record or field = due). An adjustment-rule alert keeps the Open button
// (IC e2e B4: it opens that trade's compare); the other kinds stay in Active and the bell.
const isDue = (a) => openRecords.list.find((r) => r.id === a.id)?.popup_due !== false
function announceActive(fresh) {
  const line = (a) => [plainName(a.strategy_name), a.text].filter(Boolean).join(': ')
  const worse = (as) => as.map((a) => a.worse_line).filter(Boolean).map((w) => ` ${w}`).join('')
  for (const a of fresh.filter((x) => x.kind !== 'adjustment_rule')) showInfo(`${line(a)}${worse([a])}`)
  // Issue 8: one Open pop-up per trade with a new adjustment-rule alert, naming the trade and every rule (the server's words)
  const rules = fresh.filter((x) => x.kind === 'adjustment_rule')
  for (const sid of new Set(rules.map((a) => a.strategy_id))) {
    const mine = rules.filter((a) => a.strategy_id === sid)
    const ids = openRecords.list.filter((r) => r.strategy_id === sid).map((r) => r.id)
    const what = [plainName(mine[0].strategy_name), mine.map((a) => a.text).filter(Boolean).join('; ')].filter(Boolean).join(': ')
    showInfo(`New adjustment opportunity${what ? ` - ${what}` : ''}.${worse(mine)} Open it?`, { onClick: () => router.push(compareAllUrl(sid, ids.length ? ids : mine.map((a) => a.id))) })
  }
}
// ADR-330 (4): the bell's count is the server's count of unanswered actionable alerts (GET /alerts/active), re-read on the paper
// refresh tick (no timer of its own); the open adjustment records are read on that same tick for their pop-up only
const { refresh: refreshAlerts } = usePaperRefresh({
  key: () => 'alerts',
  read: async () => {
    const [a, o, f] = await Promise.allSettled([readActive(), readOpportunities(), readStopFired()])
    // fills the records; the pop-up is announceActive's, except a watched level (never in /alerts/active): ADR-242 (3), once per record id
    for (const w of takeOpportunities(o.status === 'fulfilled' ? o.value : null).filter(isLevelWatch)) {
      showInfo([plainName(w.strategy_name), w.text].filter(Boolean).join(': '))
    }
    // ADR-330 (3)(b): a fired stop's informational row pops once (never counted, never in the bell); a failed read pops nothing
    if (f.status === 'fulfilled') for (const r of takeStopFired(f.value)) showInfo([plainName(r.strategy_name), r.text].filter(Boolean).join(': '))
    if (a.status === 'rejected') throw a.reason
    return a.value
  },
  onData: (data) => announceActive(takeActive(data, isDue)),
  onError: dropActive,
})
onMounted(refreshAlerts)
const header = ref(null)
const menuOpen = ref(false)
const accountWrap = ref(null)
const avatarButton = ref(null)
const openKey = ref(null)
const menuLeft = ref(0)
const panel = ref(null)
const toggles = {}
const sectionItems = {}
let hoverTimer = null
// true while the open menu was opened by a mouse hover: the click that usually follows must not close it again
let openedByHover = false

const pageTitle = computed(() => route.meta?.title ?? '')
const activeSection = computed(() => route.meta?.section ?? null)
const openSection = computed(() => MENU_SECTIONS.find((s) => s.key === openKey.value) ?? null)
const isMega = computed(() => Boolean(openKey.value && MEGA_MENUS[openKey.value]))

function item(section, slug) {
  const found = section.items.find(([s]) => s === slug)
  return {
    slug,
    label: found ? found[1] : slug,
    to: `/${section.key}/${slug}`,
    description: ITEM_DESCRIPTIONS[`${section.key}/${slug}`] ?? '',
    icon: ITEM_ICONS[slug] ?? SECTION_ICONS[section.key],
  }
}
// Column groups for the open menu: the mega layout from nav.js, or one column of the section's items in REQ-009 order.
const groups = computed(() => {
  const s = openSection.value
  if (!s) return []
  if (MEGA_MENUS[s.key]) return MEGA_MENUS[s.key].map((g) => ({ title: g.title, items: g.items.map((slug) => item(s, slug)) }))
  return [{ title: '', items: s.items.map(([slug]) => item(s, slug)) }]
})

function clearHover() {
  if (hoverTimer) clearTimeout(hoverTimer)
  hoverTimer = null
}
function placeMenu(key) {
  const li = sectionItems[key]
  const head = header.value
  if (!li || !head || MEGA_MENUS[key]) {
    menuLeft.value = 0
    return
  }
  // The section's offset only; the clamp to the header's edges is CSS clamp() on the panel (ADR-008: no browser maths).
  menuLeft.value = li.getBoundingClientRect().left - head.getBoundingClientRect().left
}
function openMenu(key, byHover = false) {
  clearHover()
  openedByHover = byHover
  menuOpen.value = false
  placeMenu(key)
  openKey.value = key
}
function closeMenu(focusTrigger = false) {
  clearHover()
  const key = openKey.value
  openKey.value = null
  if (focusTrigger && key) toggles[key]?.focus()
}
function toggleMenu(key) {
  if (openKey.value === key && openedByHover) openedByHover = false
  else if (openKey.value === key) closeMenu()
  else openMenu(key)
}
// A keyboard press (Enter/Space gives a click with detail 0) also moves focus to the first item; a mouse click does not.
function onToggleClick(e, key) {
  toggleMenu(key)
  if (openKey.value === key && e.detail === 0) focusItem(0)
}
// The label is a link to the section's first path; when the page is already there, the click toggles the menu instead
// of a no-op navigation that would close it. Elsewhere it navigates as before, with the menu closed.
function onLabelClick(e, key) {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button) return
  if (route.path === firstBuiltPath(key)) {
    e.preventDefault()
    toggleMenu(key)
  } else {
    closeMenu()
  }
}
function menuLinks() {
  return panel.value ? [...panel.value.querySelectorAll('[role="menuitem"]')] : []
}
async function focusItem(index) {
  await nextTick()
  const links = menuLinks()
  if (!links.length) return
  links[(index + links.length) % links.length].focus()
}
function onToggleKey(e, key) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    openMenu(key)
    focusItem(0)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    openMenu(key)
    focusItem(-1)
  }
}
function onPanelKey(e) {
  const links = menuLinks()
  const at = links.indexOf(document.activeElement)
  if (e.key === 'Escape') {
    e.preventDefault()
    closeMenu(true)
  } else if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
    e.preventDefault()
    focusItem(at + 1)
  } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
    e.preventDefault()
    focusItem(at - 1)
  } else if (e.key === 'Home') {
    e.preventDefault()
    focusItem(0)
  } else if (e.key === 'End') {
    e.preventDefault()
    focusItem(-1)
  } else if (e.key === 'Tab') {
    closeMenu()
  }
}
// Hover-open only for a mouse: a touch or pen "hover" is the start of a tap and must not open a menu under the finger.
function onSectionEnter(e, key) {
  if (e.pointerType !== 'mouse') return
  clearHover()
  if (openKey.value === key) return
  hoverTimer = setTimeout(() => openMenu(key, true), HOVER_DELAY_MS)
}
function onSectionLeave(e) {
  if (e.pointerType !== 'mouse') return
  clearHover()
  if (openKey.value) hoverTimer = setTimeout(() => closeMenu(), HOVER_DELAY_MS)
}
// A menu opened by click stays open only while focus is on its toggle or inside it; focus moving to any other control closes it.
function onHeaderFocusout(e) {
  const key = openKey.value
  const next = e.relatedTarget
  if (!key || !next) return
  if (panel.value?.contains(next) || toggles[key]?.contains(next)) return
  closeMenu()
}
function onPanelEnter(e) {
  if (e.pointerType === 'mouse') clearHover()
}

watch(
  () => route.fullPath,
  () => {
    menuOpen.value = false
    closeMenu()
  },
)

function toggleAccount() {
  closeMenu()
  menuOpen.value = !menuOpen.value
}
// Close the account menu on Escape and on a click outside it (W-054 review follow-up); same for a section menu.
function onKeydown(e) {
  if (e.key !== 'Escape') return
  if (menuOpen.value) {
    menuOpen.value = false
    avatarButton.value?.focus()
  }
  if (openKey.value) closeMenu(true)
}
function onDocumentClick(e) {
  if (menuOpen.value && accountWrap.value && !accountWrap.value.contains(e.target)) menuOpen.value = false
  if (openKey.value && header.value && !header.value.contains(e.target)) closeMenu()
}
onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  document.addEventListener('click', onDocumentClick)
})
onBeforeUnmount(() => {
  clearHover()
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('click', onDocumentClick)
})
</script>

<template>
  <header ref="header" class="sticky top-0 z-30 h-14 border-b border-line bg-surface" data-testid="app-header" @focusout="onHeaderFocusout">
    <div class="flex h-full items-stretch gap-4 px-4">
      <div class="flex min-w-0 shrink-0 items-center gap-2">
        <router-link to="/home" class="flex items-center gap-2 text-[15px] font-semibold text-ink" data-testid="brand">
          <span class="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-xs font-bold text-surface" aria-hidden="true">OF</span>
          <span class="hidden sm:inline">OptionsForOptions</span>
        </router-link>
        <span v-if="pageTitle" class="hidden min-w-0 items-center gap-2 text-[15px] font-medium text-ink-muted lg:flex" data-testid="breadcrumb">
          <span aria-hidden="true">/</span>
          <span class="whitespace-nowrap" data-testid="breadcrumb-title">{{ pageTitle }}</span>
        </span>
      </div>

      <nav class="min-w-0 flex-1 overflow-x-auto" aria-label="Primary" data-testid="primary-nav">
        <ul class="mx-auto flex h-full w-max items-stretch whitespace-nowrap">
          <li
            v-for="s in MENU_SECTIONS"
            :key="s.key"
            :ref="(el) => (sectionItems[s.key] = el)"
            class="relative flex items-stretch"
            @pointerenter="onSectionEnter($event, s.key)"
            @pointerleave="onSectionLeave"
          >
            <router-link
              :to="firstBuiltPath(s.key)"
              class="flex items-center pl-3 text-[15px] leading-5 font-medium"
              :class="activeSection === s.key ? 'text-accent' : 'text-ink hover:text-accent'"
              :data-testid="`nav-${s.key}`"
              @click="onLabelClick($event, s.key)"
              >{{ s.label }}</router-link
            >
            <button
              :ref="(el) => (toggles[s.key] = el)"
              type="button"
              class="flex items-center pr-2 pl-0.5 text-ink-subtle hover:text-accent focus-visible:outline-2 focus-visible:outline-accent"
              :aria-label="`${s.label} menu`"
              aria-haspopup="true"
              :aria-expanded="openKey === s.key ? 'true' : 'false'"
              :aria-controls="`nav-menu-${s.key}`"
              :data-testid="`nav-menu-toggle-${s.key}`"
              @click="onToggleClick($event, s.key)"
              @keydown="onToggleKey($event, s.key)"
            >
              <Icon name="chevron" :size="16" />
            </button>
            <span
              v-if="activeSection === s.key"
              class="pointer-events-none absolute inset-x-2 bottom-0 h-[3px] rounded-t bg-accent"
              aria-hidden="true"
              data-testid="nav-active-bar"
            />
          </li>
        </ul>
      </nav>

      <div class="flex shrink-0 items-center gap-2">
        <router-link
          to="/alerts/active"
          class="relative flex h-9 w-9 items-center justify-center rounded-full text-ink-muted hover:bg-surface-muted hover:text-ink"
          :aria-label="total > 0 ? `Alerts, ${total} unread` : 'Alerts'"
          data-testid="alerts-bell"
        >
          <!-- UI-002 / GC-TP step 7b: the badge is the server's unread paper-alert count (GET /paper/alerts), hidden at 0. -->
          <Icon name="bell" />
          <span
            v-if="total > 0"
            class="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-loss px-1 text-center text-[10px] font-semibold leading-4 text-white"
            data-testid="alerts-bell-count"
          >{{ total }}</span>
        </router-link>
        <div ref="accountWrap" class="relative">
          <button
            ref="avatarButton"
            type="button"
            aria-controls="account-menu"
            class="flex items-center gap-1 rounded-full text-ink-muted hover:text-ink"
            aria-label="Account menu"
            :aria-expanded="menuOpen"
            data-testid="avatar-menu"
            @click="toggleAccount"
          >
            <span class="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-surface-muted text-xs font-semibold text-ink">You</span>
            <Icon name="chevron" :size="16" />
          </button>
          <div
            v-if="menuOpen"
            id="account-menu"
            class="absolute right-0 z-40 mt-2 w-60 rounded-lg border border-line bg-surface py-1 shadow-menu"
            data-testid="account-menu"
          >
            <router-link
              to="/settings"
              class="flex h-10 items-center gap-2 px-3 text-sm font-semibold text-ink hover:bg-surface-muted"
              data-testid="account-menu-title"
              >{{ ACCOUNT_LABEL }}</router-link
            >
            <ul class="border-t border-line py-1">
              <li v-for="[slug, label] in ACCOUNT_MENU_ITEMS" :key="slug">
                <router-link
                  :to="`/settings/${slug}`"
                  class="flex h-10 items-center px-3 text-sm text-ink-muted hover:bg-surface-muted hover:text-ink"
                  data-testid="account-menu-item"
                  >{{ label }}</router-link
                >
              </li>
            </ul>
            <div class="border-t border-line pt-1">
              <!-- UI-003: Log out. Sign-in does not exist yet (Stage 5), so the action is disabled and says why. -->
              <button
                type="button"
                disabled
                class="flex h-10 w-full cursor-not-allowed items-center gap-2 px-3 text-left text-sm text-ink-muted opacity-40"
                title="Sign-in is not built yet, so there is no session to log out of."
                data-testid="account-logout"
              >
                <Icon name="logout" :size="16" />Log out
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="openSection"
      :id="`nav-menu-${openSection.key}`"
      ref="panel"
      role="menu"
      :aria-label="openSection.label"
      class="absolute top-full z-40 border border-line bg-surface shadow-menu"
      :class="isMega ? 'inset-x-0 border-x-0 border-t-0 px-4 py-4' : 'mt-0 w-64 rounded-b-lg py-1'"
      :style="isMega ? undefined : { left: `clamp(8px, ${menuLeft}px, max(8px, calc(100% - ${SMALL_MENU_WIDTH}px - 8px)))`, maxWidth: 'calc(100vw - 16px)' }"
      :data-section="openSection.key"
      data-testid="nav-menu"
      @keydown="onPanelKey"
      @pointerenter="onPanelEnter"
      @pointerleave="onSectionLeave"
    >
      <div :class="isMega ? 'mx-auto grid max-w-[1200px] gap-6 sm:grid-cols-3' : ''">
        <div v-for="(g, gi) in groups" :key="gi" class="min-w-0" :class="isMega && groups.length === 1 ? 'sm:col-span-3' : ''">
          <p v-if="g.title" class="mb-1 px-3 text-xs font-medium tracking-wide text-ink-subtle uppercase">{{ g.title }}</p>
          <div :class="isMega && groups.length === 1 ? 'grid gap-1 sm:grid-cols-3' : ''">
            <router-link
              v-for="it in g.items"
              :key="it.slug"
              :to="it.to"
              role="menuitem"
              tabindex="-1"
              class="flex gap-3 rounded-md px-3 text-ink hover:bg-surface-muted focus:bg-accent-soft focus:outline-none"
              :class="it.description ? 'py-2' : 'h-10 items-center'"
              data-testid="nav-menu-item"
              @click="closeMenu()"
            >
              <span class="text-ink-muted" :class="it.description ? 'pt-0.5' : ''"><Icon :name="it.icon" /></span>
              <span class="min-w-0">
                <span class="block text-[15px] leading-5 font-medium">{{ it.label }}</span>
                <span v-if="it.description" class="block text-[13px] leading-[18px] text-ink-muted">{{ it.description }}</span>
              </span>
            </router-link>
          </div>
        </div>
      </div>
      <p v-if="openSection.note" class="mt-1 border-t border-line px-3 pt-2 text-xs text-ink-muted" data-testid="nav-menu-note">{{ openSection.note }}</p>
    </div>
  </header>
</template>
