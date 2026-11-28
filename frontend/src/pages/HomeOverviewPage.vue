<!-- W-115 (REQ-008 AC-2..AC-5; ADR-114, ADR-003): Home overview. The state comes only from GET /strategies: none saved ->
     `new` (Create Strategy, Explore Option Chain, Learn first); some saved -> `has-strategies` (My Strategies first, then
     Create Strategy, the three most recently updated). A failed read -> `error` with the server's message. The live index
     strip shows in every state. Zerodha is a quiet line only: no connect control anywhere on this page (AC-5). No money. -->
<script setup>
import { builderLinkOf } from '@/lib/strategyLinks'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import ListLoadFailed from '@/components/common/ListLoadFailed.vue'
import api, { NEUTRAL_PARTS } from '@/services/api'
import IndexStrip from '@/components/layout/IndexStrip.vue'
import Card from '@/components/common/Card.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { istTime, noteShownDate } from '@/lib/displayFormat'
import { plainName, strategyListLabel } from '@/lib/saveDraft'
import { isRunning, strategyStatusWord } from '@/lib/strategyStatus'
import { recordLineOf } from '@/lib/positionKind'
import { FIGURE_READ_FAILED_TEXT, HOME_PNL_LABEL, HOME_RUNNING_LABEL, HOME_UNREAD_LABEL, usePaperPnl } from '@/lib/paperPnl'
import { activeAlerts, bellCount, dropActive, readActive, takeActive } from '@/lib/paperAlerts'
import { PAPER_NO_FIGURE } from '@/lib/paperList'
import { SECTIONS } from '@/router/nav'

const RECENT_COUNT = 3
const TAP = 'inline-flex min-h-11 items-center justify-center' // 44 px tap target, no fixed width
// Owner 2026-10-30 (Sensibull 001): one primary action in the accent, the rest as quiet bordered buttons
const PROMINENT = `${TAP} rounded-md border border-line bg-surface px-4 py-2 text-sm font-medium hover:bg-surface-muted`
const PRIMARY = `${TAP} rounded-md border border-accent bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover`
const SECONDARY = `${TAP} text-accent hover:underline`
const learnItems = SECTIONS.find((s) => s.key === 'learn').items
const LEARN_PATH = `/learn/${learnItems[0][0]}`

const strategies = ref(null) // null until read
const errorParts = ref(null)

const state = computed(() => {
  if (errorParts.value) return 'error'
  if (strategies.value === null) return 'loading'
  return strategies.value.length ? 'has-strategies' : 'new'
})

const recent = computed(() =>
  [...(strategies.value ?? [])]
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
    .slice(0, RECENT_COUNT))

// D-56: three figures, each read from the function the owning page uses: the running count = the server's status_word (D-28) over the
// same GET /strategies this page reads; unread = the alert count route the bell reads (D-29); P&L = the Positions total (lib/paperPnl).
// A failed read of one figure says so in that figure only; the browser forms no money and counts only rows (no arithmetic).
const pnl = usePaperPnl()
const rereadFailed = ref(false) // I-66 (F3): a background re-read of the list failed: the count is not current, so it shows a dash, never the old number
const runningCell = computed(() => {
  if (errorParts.value || rereadFailed.value) return { text: PAPER_NO_FIGURE, note: FIGURE_READ_FAILED_TEXT }
  if (strategies.value === null) return { text: PAPER_NO_FIGURE, note: null }
  return { text: String(strategies.value.filter(isRunning).length), note: null }
})
const unreadCell = computed(() => {
  if (!activeAlerts.loaded) return { text: PAPER_NO_FIGURE, note: null }
  if (activeAlerts.parts) return { text: PAPER_NO_FIGURE, note: FIGURE_READ_FAILED_TEXT }
  return { text: String(bellCount()), note: null } // the bell badge's own number (the server's count of unanswered actionable alerts)
})
const pnlCell = computed(() => {
  const c = pnl.totalCell.value
  if (c.kind === 'loading') return { text: PAPER_NO_FIGURE, note: null }
  return { text: c.text, suffix: c.label, note: c.note, leftOut: c.leftOut ?? null, closedNote: c.closedNote ?? null, storedAsOf: c.storedAsOf ?? null } // c.label is the charges suffix, never the figure's name
})
const figures = computed(() => [
  { id: 'running', label: HOME_RUNNING_LABEL, ...runningCell.value },
  { id: 'unread', label: HOME_UNREAD_LABEL, ...unreadCell.value },
  { id: 'pnl', label: HOME_PNL_LABEL, ...pnlCell.value },
])
async function loadHome() {
  errorParts.value = null
  try {
    const list = noteShownDate((await api.get('/strategies')).data)?.strategies
    if (!Array.isArray(list)) throw new Error('unreadable answer') // fail closed: no state is guessed
    strategies.value = list
  } catch (e) {
    errorParts.value = e?.parts ?? NEUTRAL_PARTS
  }
}
// I-66 (F3, Lane W2 D-W2-2): the running count is re-read every REREAD_MS and when the page is focused again (the Positions rhythm), so it
// never keeps a number the data has moved past; a failed re-read says so on that card only.
const REREAD_MS = 30_000
let rereadTimer = null
let seq = 0
async function reread() {
  const mine = ++seq
  try {
    const list = noteShownDate((await api.get('/strategies')).data)?.strategies
    if (!Array.isArray(list)) throw new Error('unreadable answer')
    if (mine !== seq) return
    strategies.value = list
    rereadFailed.value = false
  } catch {
    if (mine === seq) rereadFailed.value = true
  }
}
const onBack = () => { if (typeof document === 'undefined' || document.visibilityState !== 'hidden') reread() }
onMounted(() => {
  readActive().then(takeActive, dropActive); loadHome()
  rereadTimer = setInterval(reread, REREAD_MS)
  window.addEventListener('focus', onBack)
})
onBeforeUnmount(() => { clearInterval(rereadTimer); window.removeEventListener('focus', onBack); seq++ })
</script>

<template>
  <section data-testid="home" :data-state="state">
    <PageHeader parent="Home" title="Overview" />
    <IndexStrip />

    <dl v-if="state !== 'loading'" class="mt-4 flex flex-wrap gap-6 rounded-lg border border-line bg-surface px-4 py-3" data-testid="home-figures">
      <div v-for="f in figures" :key="f.id" :data-testid="`home-${f.id}`">
        <dt class="text-xs text-ink-muted">{{ f.label }}<template v-if="f.suffix && f.text !== PAPER_NO_FIGURE">{{ ' ' }}{{ f.suffix }}</template></dt>
        <dd class="text-lg font-semibold tabular-nums" :data-testid="`home-${f.id}-figure`">{{ f.text }}</dd>
        <p v-if="f.note" class="text-xs text-ink-muted" :data-testid="`home-${f.id}-note`">{{ f.note }}</p>
        <p v-if="f.closedNote" class="text-xs text-ink-muted" :data-testid="`home-${f.id}-closed`">{{ f.closedNote }}</p>
        <p v-if="f.storedAsOf" class="text-xs text-ink-muted" :data-testid="`home-${f.id}-as-of`">{{ f.storedAsOf }}</p>
        <p v-if="f.leftOut" class="text-xs text-ink-muted" :data-testid="`home-${f.id}-left-out`">{{ f.leftOut }}</p>
      </div>
    </dl>

    <ListLoadFailed v-if="state === 'error'" class="mt-4" :parts="errorParts" prefix="home-error" data-testid="home-error" @retry="loadHome" />

    <Card v-else-if="state === 'new'" class="mt-4" data-testid="home-new">
      <!-- HOME-NEW leaves this slot empty: `Welcome, [Name]` and the Pro-trial line need the signed-in user (row #433, stage 5). -->
      <div data-testid="home-welcome-slot" />
      <p class="text-lg font-semibold" data-testid="home-line">Plan your trade. Follow your strategy. Then execute.</p>
      <div class="mt-4 flex flex-wrap gap-3" data-testid="home-actions">
        <router-link to="/strategies/create-strategy" :class="PRIMARY" data-testid="action-create">Create Strategy</router-link>
        <router-link to="/market/option-chain" :class="PROMINENT" data-testid="action-chain">Explore Option Chain</router-link>
        <router-link :to="LEARN_PATH" :class="PROMINENT" data-testid="action-learn">Learn</router-link>
      </div>
      <p class="mt-2 text-sm"><router-link to="/strategy/builder" :class="SECONDARY" data-testid="action-know">I already know my strategy</router-link></p>
    </Card>

    <div v-else-if="state === 'has-strategies'" class="mt-4 grid gap-4" data-testid="home-has-strategies">
      <div class="flex flex-wrap gap-3" data-testid="home-actions">
        <router-link to="/strategies/my-strategies" :class="PRIMARY" data-testid="action-my">My Strategies</router-link>
        <router-link to="/strategies/create-strategy" :class="PROMINENT" data-testid="action-create">Create Strategy</router-link>
      </div>
      <Card title="Recent strategies" flush>
        <ul class="divide-y divide-line text-sm" data-testid="recent-strategies">
          <li
            v-for="s in recent" :key="s.id"
            class="grid min-h-9 grid-cols-[minmax(0,1.2fr)_minmax(0,2fr)_auto] items-center gap-3 px-4 py-2 hover:bg-surface-muted"
            data-testid="recent-row"
          >
            <span v-if="plainName(s.name)" class="min-w-0 truncate font-medium" data-testid="recent-name">{{ strategyListLabel({ name: s.name, id: s.id, expiries: [s.first_leg?.expiry], fallback: '' }) }}</span>
            <span v-else class="text-ink-subtle" aria-hidden="true">—</span>
            <span class="min-w-0 truncate text-ink-muted">{{ s.underlying }}, {{ strategyStatusWord(s) }}, last saved {{ istTime(s.updated_at) }}</span>
            <router-link v-if="builderLinkOf(s.id)" :to="builderLinkOf(s.id)" class="text-accent hover:underline" :data-testid="`recent-open-${s.id}`">Open in Strategy Builder</router-link>
            <span v-else aria-hidden="true"></span><!-- S-18: no usable id, no link; the grid cell stays -->
            <p v-if="s.position_kind === 'real' && recordLineOf(s)" class="col-span-full text-xs font-semibold" data-testid="recent-record-line">{{ recordLineOf(s) }}</p>
          </li>
        </ul>
      </Card>
    </div>

    <p v-if="state !== 'loading'" class="mt-6 text-xs text-ink-muted" data-testid="zerodha-line">Already trade with Zerodha? Connect when ready</p>
  </section>
</template>
