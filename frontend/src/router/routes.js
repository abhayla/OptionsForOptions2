// Route table split out of index.js (W-055) so the responsive check can read it in Node without a browser history.
// Structure adapted from abhayla/algochanakya@bf9faf7:frontend/src/router/index.js (ADR-047): lazy routes, meta flags,
// catch-all. The route table itself is new: the seven sections (REQ-009), /settings/* and /health-status.
import { SECTIONS, ACCOUNT_ITEMS, ACCOUNT_LABEL } from './nav.js'

const Placeholder = () => import('../pages/PlaceholderPage.vue')
// Nav items that have a real page, keyed by route name (one map for every built screen: W-113, W-114, ...); every
// other nav item still shows the placeholder.
const REAL_PAGES = {
  'strategies-live-strategies': () => import('../pages/LiveStrategiesPage.vue'),
  'strategies-strategy-builder': () => import('../pages/StrategyBuilderPage.vue'), // GC-6 BUILDER-WIRE (F-49)
  'market-underlying-index-view': () => import('../pages/IndexViewPage.vue'),
  'home-overview': () => import('../pages/HomeOverviewPage.vue'), // W-115
  'market-market-context': () => import('../pages/MarketContextPage.vue'), // W-117
  'alerts-active': () => import('../pages/AlertsPage.vue'),
  'alerts-history': () => import('../pages/AlertsPage.vue'),
  'alerts-notification-settings': () => import('../pages/AlertsPage.vue'),
  'learn-strategy-education': () => import('../pages/LearnPage.vue'),
  'learn-options-concepts': () => import('../pages/LearnPage.vue'),
  'learn-platform-guidance': () => import('../pages/LearnPage.vue'),
  'market-option-chain': () => import('../pages/OptionChainPage.vue'), // W-118
  'strategies-my-strategies': () => import('../pages/MyStrategiesPage.vue'), // W-109
  'strategies-completed-strategies': () => import('../pages/MyStrategiesPage.vue'), // W-109 (completedOnly)
}

// Account pages with a real page, keyed by slug. GC-6 BILLING-SHELL (ADR-146): three text-only billing pages.
const billingShell = () => import('../pages/BillingShellPage.vue')
// W-089: Broker & Market Data is a real page too.
const SETTINGS_PAGES = {
  'subscription-billing': billingShell,
  'free-eligibility': billingShell,
  referrals: billingShell,
  'broker-market-data': () => import('../pages/BrokerSettingsPage.vue'),
}

const sectionRoutes = SECTIONS.flatMap((s) => [
  {
    path: `/${s.key}`,
    name: s.key,
    component: Placeholder,
    meta: { title: s.label, section: s.key, subItems: s.items.map(([slug, label]) => ({ to: `/${s.key}/${slug}`, label })), note: s.note || '' },
  },
  ...s.items.map(([slug, label]) => ({
    path: `/${s.key}/${slug}`,
    name: `${s.key}-${slug}`,
    component: REAL_PAGES[`${s.key}-${slug}`] ?? Placeholder,
    meta: { title: label, section: s.key, parent: s.label, ...(slug === 'completed-strategies' ? { completedOnly: true } : {}) },
  })),
])

const settingsRoutes = [
  {
    path: '/settings',
    name: 'settings',
    component: Placeholder,
    meta: {
      title: ACCOUNT_LABEL,
      section: 'settings',
      subItems: ACCOUNT_ITEMS.map(([slug, label]) => ({ to: `/settings/${slug}`, label })),
    },
  },
  ...ACCOUNT_ITEMS.map(([slug, label]) => ({
    path: `/settings/${slug}`,
    name: `settings-${slug}`,
    component: SETTINGS_PAGES[slug] ?? Placeholder,
    meta: { title: label, section: 'settings', parent: ACCOUNT_LABEL },
  })),
]

export const routes = [
  { path: '/', redirect: '/home' },
  // GC-6 row LANDING (REQ-010): public page, no app shell (meta.public); '/' stays on /home until sign-in (Stage 5).
  { path: '/welcome', name: 'landing', component: () => import('../pages/LandingPage.vue'), meta: { title: 'Welcome', public: true } },
  ...sectionRoutes,
  ...settingsRoutes,
  { path: '/strategy/builder', name: 'strategy-builder-screen', component: () => import('../pages/StrategyBuilderPage.vue'), meta: { title: 'Strategy Builder', section: 'strategies' } },
  { path: '/strategy/:id/execute', name: 'execute-strategy', component: () => import('../pages/ExecuteStrategyPage.vue'), meta: { title: 'Execute Strategy', section: 'strategies', responsiveSample: '/strategy/1/execute' } },
  { path: '/execution/returned', name: 'execution-returned', component: () => import('../pages/ExecutionReturnedPage.vue'), meta: { title: 'Back from Kite', section: 'strategies' } },
  { path: '/broker/connected', name: 'broker-connected', component: () => import('../pages/BrokerConnectedPage.vue'), meta: { title: 'Zerodha connected', section: 'settings' } },
  { path: '/broker/refused', name: 'broker-refused', component: () => import('../pages/BrokerRefusedPage.vue'), meta: { title: 'Zerodha login not completed', section: 'settings' } },
  { path: '/health-status', name: 'health-status', component: () => import('../pages/HealthPage.vue'), meta: { title: 'System health', section: 'system' } },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('../pages/NotFoundPage.vue'), meta: { title: 'Page not found' } },
]

