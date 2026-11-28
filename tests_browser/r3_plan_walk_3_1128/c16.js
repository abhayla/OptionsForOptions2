// Lane W3 item 2: W-15 builder Save-draft box, two legs on one contract (opposite sides, then same side). ofo_tg 4173, build a1d704225
const { chromium } = require('playwright'); const OUT = '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  const T = async () => (await page.locator('body').innerText()).replace(/\n+/g, ' | ')
  const rows = async () => (await page.locator('input[aria-label^="Include leg"]').evaluateAll(x => x.map(e => (e.closest('div,tr')?.innerText || '').replace(/\s+/g, ' ').slice(0, 70))))
  await page.goto(M + '/strategy/builder'); await sleep(5000); await page.getByRole('button', { name: 'Ready-made' }).click().catch(() => {}); await sleep(1000)
  await page.getByRole('button', { name: 'Bull Put Spread' }).first().click(); await sleep(6000); console.log('start rows:', await rows())
  const next = page.getByRole('button', { name: 'Next strike' }); for (let i = 0; i < 4; i++) { await next.nth(1).click(); await sleep(700) }
  const m = (await page.getByRole('dialog').first().innerText().catch(() => '')).replace(/\s+/g, ' '); console.log('modal on reaching the same contract:', m.slice(0, 300)); await page.getByRole('button', { name: 'Keep both' }).click().catch(() => console.log('no Keep both')); await sleep(1500)
  await sleep(2500); console.log('after 4 x leg 2 Next strike:', await rows()); await page.screenshot({ path: `${OUT}/c16-1-same-contract.jpg`, type: 'jpeg', quality: 55 })
  // Save draft (opposite sides)
  await page.getByRole('button', { name: /^Save$/ }).first().click(); await sleep(1500); const dlg0 = (await page.getByRole('dialog').first().innerText().catch(() => '<none>')).replace(/\s+/g, ' '); console.log('save dialog:', dlg0.slice(0, 200))
  await page.getByRole('dialog').getByRole('textbox').first().fill('W15 OPP').catch(() => {}); await page.getByRole('dialog').getByRole('button', { name: /^Save$/ }).click().catch(() => {}); await sleep(4000)
  let t = await T(); console.log('OPPOSITE sentence:', JSON.stringify((t.match(/Legs 1 and 2[^|]*\|[^|]*\|?[^|]*/) || ['<none>'])[0])); console.log('   any red box text:', JSON.stringify((t.match(/[^|]*(strategy definition|This strategy def|one leg per contract)[^|]*/g) || []).slice(0, 3))); await page.screenshot({ path: `${OUT}/c16-2-opposite.jpg`, type: 'jpeg', quality: 55 })
  console.log('modal-root buttons:', JSON.stringify(await page.locator('[data-testid=modal-root] button').allInnerTexts()), '| aria labels:', JSON.stringify(await page.locator('[data-testid=modal-root] button').evaluateAll(x => x.map(e => e.getAttribute('aria-label')))))
  await page.locator('[data-testid=modal-root] button').last().click().catch(() => {}); await sleep(1000); console.log('modal-root present after close:', await page.locator('[data-testid=modal-root]').count())
  // same side: flip leg 2 with its own Buy/Sell toggle
  const dl = page.getByRole('dialog'); if (await dl.count()) await page.keyboard.press('Escape').catch(() => {}); await sleep(800)
  const spans = page.locator('span', { hasText: /^B$/ }); for (let i = 0; i < await spans.count(); i++) { const v = await spans.nth(i).isVisible(); console.log('B span', i, 'visible', v); if (v) { await spans.nth(i).click({ force: true, timeout: 4000 }).catch((e) => console.log('click err', String(e).split('\n')[0].slice(0, 80))); await sleep(1500); console.log('   rows after click:', JSON.stringify(await rows())); break } }
  console.log('after leg 2 toggle:', await rows()); await page.screenshot({ path: `${OUT}/c16-3-toggled.jpg`, type: 'jpeg', quality: 55 })
  await page.getByRole('button', { name: /^Save$/ }).first().click({ timeout: 5000 }).catch((e) => console.log('Save click err', String(e).split('\n')[0].slice(0, 90))); await sleep(1500)
  await page.getByRole('dialog').getByRole('textbox').first().fill('W15 SAME').catch(() => {}); await page.getByRole('dialog').getByRole('button', { name: /^Save$/ }).click().catch(() => {}); await sleep(4000)
  t = await T(); console.log('SAME SIDE sentence:', JSON.stringify((t.match(/Legs 1 and 2[^|]*\|[^|]*\|?[^|]*/) || ['<none>'])[0])); console.log('   next action:', JSON.stringify((t.match(/[^|]*(Join them|one leg per contract)[^|]*/g) || []).slice(0, 3))); await page.screenshot({ path: `${OUT}/c16-4-same-side.jpg`, type: 'jpeg', quality: 55 })
  await browser.close() })()
