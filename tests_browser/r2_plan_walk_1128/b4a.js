// Lane TG item 4, Positions > Paper of strategy 1: TC-1 charges tap, TC-4/W-20/W-29(55) stop warning, W-28(5,6,8) lines, W-19, Plan button
const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, page } = await launch()
  await page.goto(MAIN + '/positions/current-positions?tab=paper&strategy=1'); await page.waitForTimeout(10000)
  let t = (await body(page)).split(' | ')
  const grep = (re, n = 6) => t.filter(l => re.test(l)).slice(0, n).map(l => l.slice(0, 230))
  console.log('PLAN BUTTONS:', await page.getByRole('button', { name: 'Plan' }).count(), '| plan-watch armed lines:', JSON.stringify(grep(/Leg stop on|Armed in the Stops/)))
  console.log('W-28(8) stop row words:', JSON.stringify(grep(/Stop when the price goes|Stop price|Stop on a leg/)))
  console.log('W-19 name nowrap:', await page.locator('text=/NIFTY 8 Dec 24300 CE/').first().evaluate(e => { const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return `h=${Math.round(r.height)} white-space=${cs.whiteSpace} sw=${e.scrollWidth} cw=${e.clientWidth}` }).catch(() => 'n/a'))
  // charges tap
  const tap = page.getByText(/Charges paid/).first(); await tap.click().catch(() => {}); await page.waitForTimeout(1500)
  t = (await body(page)).split(' | ')
  console.log('TC-1 charges tap labels:', JSON.stringify(['Before charges', 'Charges paid', 'Estimated charges to close', 'After charges'].map(x => x + ':' + t.some(l => l.includes(x)))), JSON.stringify(grep(/Estimated charges|Before charges|Charges are|rates/i, 5)))
  await shot(page, 'tc1-charges')
  // stop warning: bought leg 24000 PE protects sold 24100 PE: type a stop in a leg stop box
  const boxes = page.locator('input[placeholder], input[aria-label]'); const n = await boxes.count()
  const names = await boxes.evaluateAll(x => x.map(e => (e.getAttribute('aria-label') || e.placeholder || '') + '#' + e.type))
  console.log('inputs near Stops:', JSON.stringify(names.filter(x => /top|Above|Below|level/i.test(x)).slice(0, 12)))
  await browser.close()
})()
