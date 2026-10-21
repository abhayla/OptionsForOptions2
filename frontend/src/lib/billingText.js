// The one home of the in-app billing page texts (GC-6 row BILLING-SHELL, ADR-146). Never retype these elsewhere; the
// page and its test import from here. While ADR-055 holds every paid plan there is no action button and no trial.
import { PRICING_TEXT } from '@/lib/landingText'

// ADR-146 (1): exact. The sentence is the ADR-144 one, imported, not retyped.
export const PLAN_LINE = 'Plan: Free during early access'
export const BILLING_TEXT = PRICING_TEXT

// ADR-146 (2): exact, on Free Eligibility and Referrals.
export const NOT_AVAILABLE_TEXT = 'Not available yet. We will announce it before it starts.'

// Route slug (ACCOUNT_ITEMS) -> the lines its page shows, in order.
export const BILLING_PAGES = {
  'subscription-billing': [PLAN_LINE, BILLING_TEXT],
  'free-eligibility': [NOT_AVAILABLE_TEXT],
  referrals: [NOT_AVAILABLE_TEXT],
}
