// The navigation table (REQ-009 AC-1..AC-8). The router, the header and the placeholder pages all read this one list,
// so a nav item can never exist without a route. Labels are the spec's words.
export const SECTIONS = [
  {
    key: 'home',
    label: 'Home',
    items: [
      ['overview', 'Overview'],
      ['important-alerts', 'Important alerts'],
      ['active-strategies', 'Active strategies'],
      ['account-status', 'Account status'],
    ],
  },
  {
    key: 'strategies',
    label: 'Strategies',
    items: [
      ['my-strategies', 'My Strategies'],
      ['create-strategy', 'Create Strategy'],
      ['strategy-builder', 'Strategy Builder'],
      ['live-strategies', 'Live Strategies'],
      ['adjustments', 'Adjustments'],
      ['completed-strategies', 'Completed Strategies'],
    ],
  },
  {
    key: 'positions',
    label: 'Positions',
    items: [
      ['current-positions', 'Current positions'],
      ['strategy-linked-positions', 'Strategy-linked positions'],
      ['adjustment-opportunities', 'Adjustment opportunities'],
      ['pnl-risk', 'P&L/risk'],
    ],
  },
  {
    key: 'market',
    label: 'Market',
    items: [
      ['option-chain', 'Option Chain'],
      ['underlying-index-view', 'Underlying/index view'],
      ['market-context', 'Market context'],
    ],
  },
  {
    key: 'orders',
    label: 'Orders',
    // The broker orders, import and funds view; no order-entry page exists (ADR-002, REQ-009 AC-5, ADR-160).
    note: "Your broker orders, read-only. This page never takes an order.",
    items: [
      ['pending', 'Pending'],
      ['executed', 'Executed'],
      ['failed-partial', 'Failed/partial'],
      ['execution-history', 'Execution history'],
    ],
  },
  {
    key: 'alerts',
    label: 'Alerts',
    items: [
      ['active', 'Active'],
      ['history', 'History'],
      ['notification-settings', 'Notification settings'],
    ],
  },
  {
    key: 'learn',
    label: 'Learn',
    items: [
      ['strategy-education', 'Strategy education'],
      ['options-concepts', 'Options concepts'],
      ['platform-guidance', 'Platform guidance'],
    ],
  },
]

// u504: items whose page is not built (their route is still the placeholder, ADR-193 (4)). SECTIONS keeps the spec's full
// list and the routes stay reachable by address; the menus offer only built pages, because a link to an empty page reads as
// broken. When a page is built, delete its entry here (tests/menu-no-placeholder.test.js fails if the two disagree).
export const UNBUILT_ITEMS = [
  'home/important-alerts', 'home/active-strategies', 'home/account-status', 'positions/pnl-risk',
  'orders/pending', 'orders/executed', 'orders/failed-partial', 'orders/execution-history',
  'settings/profile', 'settings/zerodha-connection', 'settings/notifications', 'settings/security', 'settings/preferences',
  'settings/strategy-preferences',
]
// ADR-193 (4) names no landing page: "/" opens the strategies list, the first page a trader needs.
export const LANDING_PATH = '/strategies/my-strategies'
const built = (key, items) => items.filter(([slug]) => !UNBUILT_ITEMS.includes(`${key}/${slug}`))
export const MENU_SECTIONS = SECTIONS.map((s) => ({ ...s, items: built(s.key, s.items) })).filter((s) => s.items.length)
// Where a section's own link goes: its first built item, or null when it has none.
export const firstBuiltPath = (key) => {
  const [slug] = built(key, SECTIONS.find((s) => s.key === key)?.items ?? ACCOUNT_ITEMS)[0] ?? []
  return slug ? `/${key}/${slug}` : null
}

// ADR-193 (4): what each unbuilt page will hold, in the user's words (REQ-009 AC-1..AC-8; text in the spec at REQ-009
// "Unbuilt pages"). Keyed by the route path without the leading slash. A page missing here says only that it is not built.
export const COMING_LINES = {
  'home/important-alerts': "The alerts that matter most will be collected on this page.",
  'home/active-strategies': "Your running strategies will be summarised on this page.",
  'home/account-status': "Your broker connection and subscription status will show on this page.",
  'positions/pnl-risk': "Profit and loss and risk across your positions will show on this page.",
  'orders': "Your broker orders with your broker's own status, an order import and a read-only funds and margin view will show on this page. It never takes an order.",
  'orders/pending': "Your broker orders that are still open will be listed on this page, with your broker's own status.",
  'orders/executed': "Your executed broker orders will be listed on this page.",
  'orders/failed-partial': "Your rejected and partly filled broker orders will be listed on this page, with your broker's reason.",
  'orders/execution-history': "Your past broker orders will be listed on this page, with the time we read them.",
  'settings/profile': "Your name and contact details will show on this page.",
  'settings/zerodha-connection': "Your broker connection will be managed on this page.",
  'settings/notifications': "Your notification choices will be set on this page.",
  'settings/security': "Your sign-in and security options will be set on this page.",
  'settings/preferences': "Your display preferences will be set on this page.",
  'settings/strategy-preferences': "Your default strategy choices will be set on this page.",
}

export const ACCOUNT_LABEL = 'Account & Settings'

export const ACCOUNT_ITEMS = [
  ['profile', 'Profile'],
  ['zerodha-connection', 'Zerodha connection'],
  ['subscription-billing', 'Subscription & Billing'],
  ['free-eligibility', 'Free Eligibility'],
  ['referrals', 'Referrals'],
  ['notifications', 'Notifications'],
  ['security', 'Security'],
  ['preferences', 'Preferences'],
  ['strategy-preferences', 'Strategy Preferences'],
  ['broker-market-data', 'Broker & Market Data'],
  ['app-settings', 'Settings'], // GC-SET (REQ-167): the app-wide settings page for the admin
]
export const ACCOUNT_MENU_ITEMS = built('settings', ACCOUNT_ITEMS)

// ADR-193 / UI study UI-002: how the top bar presents each section. The labels above are untouched (REQ-009); this
// only says which sections open a mega menu (Sensibull "Trade" S-002, "Analyse" S-003) and how their items group.
// Every other section opens a small single-column dropdown of its items in REQ-009 order.
export const MEGA_MENUS = {
  strategies: [
    { title: 'Build', items: ['strategy-builder', 'create-strategy'] },
    { title: 'Follow', items: ['my-strategies', 'live-strategies', 'adjustments'] },
    { title: 'Done', items: ['completed-strategies'] },
  ],
  market: [{ title: '', items: ['option-chain', 'underlying-index-view', 'market-context'] }],
}

// One-line descriptions under a mega-menu item's title (UI-002): neutral statements of what the page shows, no advice
// words (ADR-003). Keyed `<section>/<slug>`; an item without a line shows its title only.
export const ITEM_DESCRIPTIONS = {
  'strategies/strategy-builder': 'Build a strategy from legs or ready-made shapes and see every outcome',
  'strategies/create-strategy': 'Start guided or from scratch',
  'strategies/my-strategies': 'Your saved and running strategies',
  'strategies/live-strategies': 'Strategies with open positions and their health',
  'strategies/adjustments': 'Changes made to running strategies',
  'strategies/completed-strategies': 'Strategies that have been closed',
  'market/option-chain': 'Strikes, prices and open interest for one expiry',
  'market/underlying-index-view': 'The index level and how it moved',
  'market/market-context': 'Market conditions for the day in one place',
}

// UI-004: routes that use the full width with 16 px gutters (Sensibull S-107); every other page is a centred 1200 px
// column. Keyed by route name.
export const FULL_WIDTH_ROUTES = ['strategies-strategy-builder', 'strategy-builder-screen', 'market-option-chain']
