// Lane W3: D-TG-2 leg-expiry Review sentence on the build, ofo_tg #1 (leg stop above 150 on NIFTY 24300 CE = leg 1 by order)
const { chromium } = require('playwright'); const OUT = process.env.OUT || '/tmp/claude-0/sp'; const M = 'http://127.0.0.1:4173'
;(async () => { const browser = await chromium.launch(); const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 } })).newPage()
  await page.goto(M + '/strategy/builder?strategy=1'); await page.waitForTimeout(9000)
  const labels = await page.locator('select').evaluateAll(s => s.map(e => e.getAttribute('aria-label'))); console.log('selects:', labels.filter(Boolean).slice(0, 12))
  const legs = await page.locator('table tbody tr').allInnerTexts().catch(() => []); console.log('rows:', legs.slice(0, 6).map(x => x.replace(/\s+/g, ' ').slice(0, 90)))
  for (let leg = 1; leg <= 4; leg++) {
    await page.goto(M + '/strategy/builder?strategy=1'); await page.waitForTimeout(8000)
    const sel = page.getByLabel(`Change expiry of leg ${leg}`); if (!(await sel.count())) { console.log('leg', leg, 'no expiry select'); continue }
    const opts = await sel.locator('option').allInnerTexts(); await sel.selectOption({ index: 1 }).catch(() => console.log('select err')); await page.waitForTimeout(3000)
    await page.getByRole('button', { name: /Review/ }).first().click({ timeout: 8000 }).catch(() => console.log('no Review button')); await page.waitForTimeout(9000)
    const d = (await page.getByRole('dialog').first().innerText().catch(() => '<no dialog>')).replace(/\s+/g, ' ')
    console.log(`leg ${leg} options [${opts.join(' / ')}] REVIEW:`, d.slice(0, 650)); console.log('   stop sentence:', (d.match(/The stop on[^.]*\./) || ['<none>'])[0])
    await page.screenshot({ path: `${OUT}/w3b-review-leg${leg}.jpg`, type: 'jpeg', quality: 55 })
  }
  await browser.close() })()
