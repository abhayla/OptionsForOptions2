// Route table split out of index.js (W-055) so the responsive check can read it in Node without a browser history.
// Structure adapted from abhayla/algochanakya@bf9faf7:frontend/src/router/index.js (ADR-047): lazy routes, meta flags,
// catch-all. The route table itself is new: the seven sections (REQ-009), /settings/* and /health-status.
import { SECTIONS, ACCOUNT_ITEMS, ACCOUNT_LABEL } from './nav.js'

const Placeholder = () => import('../pages/PlaceholderPage.vue')

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
    component: Placeholder,
    meta: { title: label, section: s.key, parent: s.label },
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
    component: Placeholder,
    meta: { title: label, section: 'settings', parent: ACCOUNT_LABEL },
  })),
]

export const routes = [
  { path: '/', redirect: '/home' },
  ...sectionRoutes,
  ...settingsRoutes,
  { path: '/health-status', name: 'health-status', component: () => import('../pages/HealthPage.vue'), meta: { title: 'System health', section: 'system' } },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('../pages/NotFoundPage.vue'), meta: { title: 'Page not found' } },
]

