// Lane W2 I-205 (B1 branch): no broker session, stored close, market closed: what the paper book shows (tag = process.env.W2_TAG)
const { launch, shot, body, MAIN } = require('./common')
const TAG = process.env.W2_TAG || 'b1'
;(async () => {
  const { browser, page } = await launch()
  for (const [n, u] of [['home', '/home/overview'], ['live', '/strategies/live-strategies'], ['mystrat', '/strategies/my-strategies'], ['builder1', '/strategy/builder?strategy=1'], ['builder3', '/strategy/builder?strategy=3']]) {
    await page.goto(MAIN + u); await page.waitForTimeout(8000)
    const t = await body(page)
    console.log(`[${TAG}] ${n}:`, (t.match(/(Total P&L[^|]*\|[^|]*|P&L[^|]*\|[^|]*|Paper P&L[^|]*|as of[^|]*|Live \(|Closed|Last close[^|]*|not live[^|]*|left out[^|]*|Includes[^|]*)/g) || []).slice(0, 14).join(' ## ').slice(0, 900))
    await shot(page, `i205-${TAG}-${n}`)
  }
  await page.goto(MAIN + '/positions/current-positions?tab=paper'); await page.waitForTimeout(9000)
  const t = await body(page)
  console.log(`[${TAG}] positions:`, (t.match(/(Total P&L[^|]*\|[^|]*|Paper P&L[^|]*|as of[^|]*|Unbooked P&L[^|]*\|[^|]*|left out[^|]*)/g) || []).slice(0, 12).join(' ## ').slice(0, 900))
  await shot(page, `i205-${TAG}-positions`)
  const cbs = page.getByRole('checkbox', { name: /^Select / })
  console.log(`[${TAG}] leg checkboxes:`, await cbs.count())
  await cbs.first().check().catch(() => {})
  const ex = page.getByRole('button', { name: /^Exit \(\d+\)$/ }).first()
  console.log(`[${TAG}] Exit button:`, await ex.innerText().catch(() => '-'), 'enabled:', await ex.isEnabled().catch(() => 'n/a'))
  if (await ex.isEnabled().catch(() => false)) { await ex.click(); await page.waitForTimeout(3000); const d = (await page.getByRole('dialog').first().innerText().catch(() => '<none>')).replace(/\s+/g, ' '); console.log(`[${TAG}] Exit dialog:`, d.slice(0, 500)); console.log(`[${TAG}] Confirm enabled:`, await page.getByRole('button', { name: 'Confirm' }).last().isEnabled().catch(() => 'n/a')); await shot(page, `i205-${TAG}-exit-dialog`) }
  await browser.close()
})()
