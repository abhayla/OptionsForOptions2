// Lane W2 I-66: tab A holds the builder's summary card; tab B places a paper exit on the same strategy; tab A must show the "old" tag
const { launch, shot, body, MAIN } = require('./common')
;(async () => {
  const { browser, ctx, page: A } = await launch()
  const B = await ctx.newPage()
  await A.goto(MAIN + '/strategy/builder?strategy=1'); await A.waitForTimeout(9000)
  const pick = (t) => (t.match(/[^|]*\b(old|Old|OLD|out of date|changed in another)\b[^|]*/g) || ['<no old tag>']).slice(0, 4).join(' ;; ')
  console.log('tab A before:', pick(await body(A)))
  await shot(A, 'i66-1-before')
  await B.goto(MAIN + '/positions/current-positions?tab=paper'); await B.waitForTimeout(9000)
  await B.getByRole('checkbox', { name: 'Select NIFTY 9 Nov 22950 PE' }).first().check().catch(e => console.log('B tick err'))
  await B.getByTestId('exit-selected-1').click(); await B.waitForTimeout(2500)
  await B.getByRole('button', { name: 'Confirm' }).last().click(); await B.waitForTimeout(6000)
  console.log('tab B says:', (await body(B)).match(/Exit placed[^|]*/)?.[0])
  const unk = async () => ((await body(A)).match(/[^|]*(not known yet|Updating the numbers)[^|]*/g) || ['<no unknown/updating line>']).slice(0, 2).join(' ;; ').slice(0, 220)
  for (const s of [5, 20, 60, 150]) { await A.waitForTimeout(s === 5 ? 5000 : s === 20 ? 15000 : s === 60 ? 40000 : 90000); console.log(`tab A +${s}s:`, pick(await body(A)), '||', await unk()); if (s === 20) await shot(A, 'i66-2b-tabA-20s') }
  await A.reload(); await A.waitForTimeout(9000); console.log('tab A after reload:', await unk()); await shot(A, 'i66-3-after-reload')
  await shot(A, 'i66-2-after'); await browser.close()
})()
