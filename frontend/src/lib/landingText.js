// The one home of every string on the public landing page (GC-6 row LANDING, REQ-010; ADR-144 pricing, ADR-145 footer).
// Never retype these anywhere else; the page and its test import from here. Wording is decision-support, never
// advice (ADR-003, ADR-055).

export const SAMPLE_STAMP = 'Sample · Historical'

export const PRODUCT_NAME = 'OptionsForOptions'
export const HERO_LINE = 'Plan options strategies. See every outcome.'

export const NAV_LABELS = { howItWorks: 'How it works', pricing: 'Pricing', faq: 'FAQ', logIn: 'Log in', signUp: 'Sign up' }

export const HOW_IT_WORKS = [
  { title: 'Plan the strategy', body: 'Pick an index and the legs you want to look at.' },
  { title: 'See the outcome at every level', body: 'See what each market level would mean for the strategy before you place anything.' },
  { title: 'Place it on your own Zerodha account', body: 'You review the orders and place them yourself on Kite.' },
]

// ADR-144 (1): exact.
export const PRICING_TITLE = 'Pricing'
export const PRICING_TEXT =
  'Free during early access. Paid plans will be announced before they start, and you will be told before you are charged.'

// ADR-145 (1): exact, in this order.
export const NOT_ADVICE_LINE = 'Strategies shown are for planning and education, not advice to trade.'
export const FOOTER_LINES = [
  'Zerodha Broking Ltd.: SEBI Registration no.: INZ000031633 | Passive Income Financial Solutions Private Limited | NSE AP reg. no.: AP2516003693',
  'Investments in securities market are subject to market risks, read all the related documents carefully before investing.',
  NOT_ADVICE_LINE,
]

export const FAQ = [
  { q: 'Do you ask for my Zerodha password?', a: "No. You log in on Zerodha's own page; we never see or store your password." },
  { q: 'Does the app place orders for me?', a: 'No. You review the orders and place them yourself on Kite.' },
  { q: 'Is this advice?', a: NOT_ADVICE_LINE },
]

export const SAMPLE_CHART_LABEL = 'Sample payoff of an example strategy at expiry'
// Fixed points of the sample payoff (x = market level, y = profit or loss), drawn as-is; no engine call.
export const SAMPLE_PAYOFF_POINTS = [[0, 70], [40, 70], [80, 20], [120, 20], [160, 70], [200, 70]]
