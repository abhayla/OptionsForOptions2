const { launch, shot, body, MAIN } = require('./common')
;(async () => { const { browser, page } = await launch(); await page.goto(MAIN + '/strategy/builder?strategy=1').catch(() => {}); await page.waitForTimeout(9000)
 const t = await body(page); console.log('(c) builder with the API stopped:', (t.match(/[^|]*(could not be read|Try again|Retry)[^|]*/g) || ['-']).slice(0, 3).join(' ;; '), '| Retry/Try again buttons:', await page.getByRole('button', { name: /Retry|Try again/ }).count()); await shot(page, 'f1b-c-builder-down')
 const btn = page.getByRole('button', { name: /Retry|Try again/ }).first(); console.log('button text:', await btn.innerText().catch(() => '-')); await browser.close() })()
