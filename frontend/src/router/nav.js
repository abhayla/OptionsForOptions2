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
