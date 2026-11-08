// Live test 2026-11-06 issue 29: the approaches POST took 9.5 s against the client's shared 10 s timeout, and the page
// showed "The page could not get an answer from the server." This one request carries its own 30 s timeout, and the
// page says what it is doing while the call runs.
import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import AdjustCompare from '@/components/strategy/AdjustCompare.vue'

describe('Compare approaches request (issue 29)', () => {
  it('sends POST adjustment-approaches with a 30000 ms timeout and shows the working line until it answers', async () => {
    let answer
    const client = {
      post: vi.fn(() => new Promise((resolve) => { answer = resolve })),
      get: vi.fn(async () => { throw new Error('not tracked') }),
    }
    const w = mount(AdjustCompare, { props: { strategyId: 88, client } })
    await flushPromises()
    expect(client.post).toHaveBeenCalledTimes(1)
    expect(client.post.mock.calls[0][0]).toBe('/strategies/88/adjustment-approaches')
    expect(client.post.mock.calls[0][1]).toEqual({})
    expect(client.post.mock.calls[0][2]).toEqual({ timeout: 30000 })
    expect(w.get('[data-testid="adjust-loading"]').text()).toBe('Working out the approaches...')
    answer({ data: { approaches: [] } })
    await flushPromises()
    expect(w.find('[data-testid="adjust-loading"]').exists()).toBe(false)
    w.unmount()
  })
})
