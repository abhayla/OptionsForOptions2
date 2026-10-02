import { describe, it, expect } from 'vitest'
import { ESLint } from 'eslint'
import path from 'path'

const eslint = new ESLint({ cwd: path.resolve(__dirname, '..') })

async function messages(code, file) {
  const [res] = await eslint.lintText(code, { filePath: path.resolve(__dirname, '..', file) })
  return res.messages.filter((m) => m.ruleId && m.ruleId.includes('no-restricted-syntax'))
}

describe('lint rule banning literal vendor hosts (ADR-012)', () => {
  it.each(['kite.trade', 'zerodha.com', 'nseindia.com', 'api.upstox.com', 'angelone', 'dhan.co'])(
    'flags %s in a string literal',
    async (host) => {
      expect((await messages(`export const u = 'https://${host}/x'\n`, 'src/x.js')).length).toBeGreaterThan(0)
    }
  )

  it('flags a vendor host in a template literal', async () => {
    expect((await messages('export const u = `https://kite.trade/${1}`\n', 'src/x.js')).length).toBeGreaterThan(0)
  })

  it('flags a vendor host in a Vue template attribute', async () => {
    const code = '<template><a href="https://kite.trade/">x</a></template>\n'
    expect((await messages(code, 'src/x.vue')).length).toBeGreaterThan(0)
  })

  it('passes a same-origin call', async () => {
    expect(await messages("export const u = '/api/health'\n", 'src/x.js')).toEqual([])
  })
})
