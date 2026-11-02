// GC-ALERT1 item 5 (REQ-170 Q-AD-2): the plan sheet's alert-style control. Answers have the shape of
// GET/PUT /api/strategies/{id}/alert-style (AlertStyleOut, backend/ofo_app/routes/alert_style.py; the server side is proven
// on the ADJ-02 scenario in tests_app/test_strategy_alert_style.py). Every expected string is the answer's own text.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const calls = []
let answers = {}
vi.mock('@/services/api', async (importActual) => {
  const actual = await importActual()
  const respond = (method, url, body) => {
    calls.push({ method, url, body })
    const a = answers[`${method} ${url}`]
    if (a === undefined) return Promise.reject({ message: 'no answer', parts: null, status: 404 })
    return typeof a === 'function' ? a(body) : Promise.resolve({ data: a })
  }
  return { ...actual, default: { get: (u) => respond('GET', u), put: (u, b) => respond('PUT', u, b) } }
})
import AlertStylePicker from '@/components/strategy/AlertStylePicker.vue'

const CHOICES = [
  { value: null, label: 'Automatic (now Weekly)' }, { value: 'intraday', label: 'Intraday' },
  { value: 'weekly', label: 'Weekly' }, { value: 'monthly', label: 'Monthly' },
]
const answer = (over = {}) => ({ strategy_id: 70, label: 'Alert style', pinned: null, automatic: 'weekly', in_force: 'weekly',
  reason_text: null, choices: CHOICES, ...over })
const PATH = '/strategies/70/alert-style'

beforeEach(() => { answers = {}; calls.length = 0 })
async function open() {
  const w = mount(AlertStylePicker, { props: { strategyId: 70 } })
  await flushPromises()
  return w
}
const options = (w) => w.findAll('[data-testid=alert-style-select] option').map((o) => o.text())

describe('Alert style on the plan sheet (REQ-170 Q-AD-2)', () => {
  it('shows the server label and choices, Automatic selected when nothing is pinned', async () => {
    answers[`GET ${PATH}`] = answer()
    const w = await open()
    expect(w.get('label').text()).toContain('Alert style')
    expect(options(w)).toEqual(['Automatic (now Weekly)', 'Intraday', 'Weekly', 'Monthly'])
    expect(w.get('[data-testid=alert-style-select]').element.value).toBe('automatic')
  })

  it('picking Monthly PUTs {style: "monthly"} and shows the pin; Automatic PUTs null', async () => {
    answers[`GET ${PATH}`] = answer()
    answers[`PUT ${PATH}`] = (body) => Promise.resolve({ data: answer({ pinned: body.style, in_force: body.style ?? 'weekly' }) })
    const w = await open()
    await w.get('[data-testid=alert-style-select]').setValue('monthly')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'PUT').map((c) => c.body)).toEqual([{ style: 'monthly' }])
    expect(w.get('[data-testid=alert-style-select]').element.value).toBe('monthly')
    await w.get('[data-testid=alert-style-select]').setValue('automatic')
    await flushPromises()
    expect(calls.filter((c) => c.method === 'PUT').map((c) => c.body)).toEqual([{ style: 'monthly' }, { style: null }])
    expect(w.get('[data-testid=alert-style-select]').element.value).toBe('automatic')
  })

  it("shows the server's reason when the style cannot be told by itself", async () => {
    const reason = 'This strategy has legs on more than one expiry, so its alert style cannot be picked by itself. Pin a style.'
    answers[`GET ${PATH}`] = answer({ automatic: null, in_force: null, reason_text: reason,
      choices: [{ value: null, label: 'Automatic (not known yet)' }, ...CHOICES.slice(1)] })
    const w = await open()
    expect(w.get('[data-testid=alert-style-reason]').text()).toBe(reason)
    expect(options(w)[0]).toBe('Automatic (not known yet)')
  })

  it("a refused pin shows the server's reason verbatim and keeps the shown pin", async () => {
    answers[`GET ${PATH}`] = answer()
    answers[`PUT ${PATH}`] = () => Promise.reject({ reason: 'That is not an alert style. Pick Automatic, Intraday, Weekly or Monthly.' })
    const w = await open()
    await w.get('[data-testid=alert-style-select]').setValue('weekly')
    await flushPromises()
    expect(w.get('[data-testid=alert-style-refusal]').text()).toBe('That is not an alert style. Pick Automatic, Intraday, Weekly or Monthly.')
  })

  it('a failed read shows no style at all (never a guessed one)', async () => {
    const w = await open()
    expect(w.find('[data-testid=alert-style-select]').exists()).toBe(false)
    expect(w.get('[data-testid=alert-style-unavailable]').text()).toBe('The alert style could not be read, so none is shown.')
  })
})
