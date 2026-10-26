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
    // Strategy-linked orders only; no order-entry page exists (ADR-002, REQ-009 AC-5).
    note: 'Strategy-linked orders only. There is no order-entry form.',
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
]

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
