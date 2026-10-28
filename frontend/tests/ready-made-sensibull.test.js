// GC-UI step 6a (D-C03, D-C05, D-C07, D-C04, D-C02): the Ready-made tab in Sensibull's group names and order.
// The templates reply is the REAL one, captured from the running API (fixtures/strategy-templates-live.json, 41 templates).
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import ReadyMadePanel from '@/components/strategy/ReadyMadePanel.vue'
import { VIEW_GROUPS, templatesInGroup } from '@/lib/readyMade'
import LIVE from './fixtures/strategy-templates-live.json'

let templatesReply
const posts = []
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  return {
    ...actual,
    default: {
      get: (url) => {
        if (url === '/features') return Promise.resolve({ data: { order_path: 'off', held: ['platform_strikes'] } })
        if (url === '/strategy-templates') return templatesReply()
        if (url.endsWith('/expiries')) return Promise.resolve({ data: { expiries: ['2026-10-27'] } })
        return Promise.reject(new Error(url))
      },
      post: (url, body) => { posts.push([url, body]); return Promise.resolve({ data: { underlying: 'NIFTY', legs: [] } }) },
    },
  }
})

async function panel() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div/>' } }, { path: '/learn/strategy-education', component: { template: '<div/>' } }] })
  router.push('/')
  await router.isReady()
  const w = mount(ReadyMadePanel, { props: { legs: [] }, global: { plugins: [router] } })
  await flushPromises()
  return w
}
const names = (w) => w.findAll('[data-testid^="rm-template-"]').map((b) => b.get('[data-testid="rm-card-name"]').text())

beforeEach(() => {
  templatesReply = () => Promise.resolve({ data: LIVE })
  posts.length = 0
})

describe('D-C03 / D-C05 / D-C07: four groups in Sensibull order and names, from the real templates reply', () => {
  it('chips read Bullish, Bearish, Neutral, Others and Bullish starts with Buy Call', async () => {
    expect(LIVE.templates.length).toBe(41)
    const w = await panel()
    expect(w.findAll('[data-testid^="rm-group-"]').map((c) => c.text())).toEqual(['Bullish', 'Bearish', 'Neutral', 'Others'])
    expect(names(w)[0]).toBe('Buy Call')
  })

  it('each group lists the Sensibull names in Sensibull order; our extra templates come last', () => {
    const by = (key) => templatesInGroup(LIVE.templates, VIEW_GROUPS.find((g) => g.key === key)).map((t) => t.name)
    expect(by('bullish').slice(0, 11)).toEqual(['Buy Call', 'Sell Put', 'Bull Call Spread', 'Bull Put Spread', 'Call Ratio Back Spread',
      'Long Calendar with Calls', 'Bull Condor', 'Bull Butterfly', 'Range Forward', 'Long Synthetic Future', 'Buy Future'])
    expect(by('bearish').slice(0, 10)).toEqual(['Buy Put', 'Sell Call', 'Bear Call Spread', 'Bear Put Spread', 'Put Ratio Back Spread',
      'Long Calendar with Puts', 'Bear Condor', 'Bear Butterfly', 'Risk Reversal', 'Short Synthetic Future'])
    expect(by('neutral').slice(0, 8)).toEqual(['Short Straddle', 'Iron Butterfly', 'Short Strangle', 'Short Iron Condor', 'Batman',
      'Double Plateau', 'Jade Lizard', 'Reverse Jade Lizard'])
    expect(by('other').slice(0, 8)).toEqual(['Call Ratio Spread', 'Put Ratio Spread', 'Long Straddle', 'Long Iron Butterfly',
      'Long Strangle', 'Long Iron Condor', 'Strip', 'Strap'])
  })

  it('Jade Lizard is Neutral only; Covered Call and Cash-Secured Put stay listed (at the end of a group); every template appears exactly once', () => {
    const all = VIEW_GROUPS.flatMap((g) => templatesInGroup(LIVE.templates, g).map((t) => t.id))
    expect(new Set(all).size).toBe(all.length)
    expect(all.length).toBe(41)
    expect(templatesInGroup(LIVE.templates, VIEW_GROUPS[0]).map((t) => t.id)).not.toContain('jade_lizard')
    expect(all).toContain('covered_call')
    expect(all).toContain('cash_secured_put')
  })

  it('a template with an unknown view and no listed id still shows, in Others; an empty reply shows no card and a failed one an error', async () => {
    const odd = [{ id: 'odd_one', name: 'Odd One', views: ['mystery'] }]
    expect(templatesInGroup(odd, VIEW_GROUPS[3]).map((t) => t.id)).toEqual(['odd_one'])
    templatesReply = () => Promise.resolve({ data: { templates: [] } })
    expect(names(await panel())).toEqual([])
    templatesReply = () => Promise.reject({ parts: { what_happened: 'The catalogue could not be read.', impact: 'i', what_is_blocked: 'b', next_action: 'n' } })
    const failed = await panel()
    expect(failed.get('[data-testid="rm-error"]').text()).toContain('The catalogue could not be read.')
  })

  it('clicking a card still loads that template (path, template id and expiry unchanged)', async () => {
    const w = await panel()
    await w.get('[data-testid="rm-template-buy_call"]').trigger('click')
    expect(posts[0]).toEqual(['/strategies/load-template', { underlying: 'NIFTY', template_id: 'buy_call', expiry: '2026-10-27' }])
  })
})

describe('D-C04: square cards with a static payoff-shape icon', () => {
  it('every card of the real reply has one icon above its name (green above / red below a zero line), and the cards are square-ish', async () => {
    const w = await panel()
    let seen = 0
    for (const g of VIEW_GROUPS) {
      await w.get(`[data-testid="rm-group-${g.key}"]`).trigger('click')
      for (const b of w.findAll('[data-testid^="rm-template-"]')) {
        const svg = b.get('[data-testid="rm-card-icon"]')
        expect(svg.findAll('polyline').length).toBe(2)
        expect(svg.html()).toContain('text-profit')
        expect(svg.html()).toContain('text-loss')
        expect(b.classes()).toContain('aspect-[100/95]')
        expect(b.element.children[0]).toBe(svg.element) // the icon sits above the name
        seen += 1
      }
    }
    expect(seen).toBe(41)
  })

  it('a template with no listed shape shows its name and no icon, and still loads', async () => {
    templatesReply = () => Promise.resolve({ data: { templates: [{ id: 'brand_new', name: 'Brand New', views: ['bullish'] }] } })
    const w = await panel()
    const card = w.get('[data-testid="rm-template-brand_new"]')
    expect(card.find('[data-testid="rm-card-icon"]').exists()).toBe(false)
    expect(card.text()).toBe('Brand New')
    await card.trigger('click')
    expect(posts[0][1].template_id).toBe('brand_new')
  })
})

describe('D-C02: the hint line and the Learn link', () => {
  it('shows the hint under the chips with a Learn Options Strategies link to our Learn page', async () => {
    const w = await panel()
    const hint = w.get('[data-testid="rm-hint"]')
    expect(hint.text().replace(/\s+/g, ' ')).toBe('Please click on a ready-made strategy to load it Learn Options Strategies')
    expect(hint.get('a').attributes('href')).toBe('/learn/strategy-education')
    const html = w.html()
    expect(html.indexOf('rm-groups')).toBeLessThan(html.indexOf('rm-hint'))
    expect(html.indexOf('rm-hint')).toBeLessThan(html.indexOf('rm-templates'))
  })
})
