// REQ-004 AC-1 (issue #110): the page-scroll check alone passes when overflow:hidden clips a too-wide element. This
// check measures boxes instead: every element inside the main content must sit inside the viewport, or inside an
// element carrying SCROLLER_ATTR (an allow-list: the marker is the only way to be wide on purpose). The marked
// element itself must still fit the viewport, since it is what scrolls.
export const SCROLLER_ATTR = 'data-h-scroll'
const MAIN = '[data-testid="app-content"]'

export type Clipped = { element: string; left: number; right: number }

export async function findClippedElements(page: import('@playwright/test').Page): Promise<Clipped[]> {
  return page.evaluate(
    ({ main, attr }) => {
      const root = document.querySelector(main)
      if (!root) return [{ element: `${main} not found`, left: 0, right: 0 }]
      const vw = document.documentElement.clientWidth
      const out: { element: string; left: number; right: number }[] = []
      for (const el of [root, ...Array.from(root.querySelectorAll('*'))]) {
        if (el.parentElement && el.parentElement.closest(`[${attr}]`)) continue // inside a deliberate scroller
        if (getComputedStyle(el).display === 'none') continue
        const r = el.getBoundingClientRect()
        if (r.width === 0 && r.height === 0) continue // not rendered
        if (r.left < -0.5 || r.right > vw + 0.5) {
          const tid = el.getAttribute('data-testid')
          out.push({ element: `${el.tagName.toLowerCase()}${tid ? `[${tid}]` : ''}`, left: Math.round(r.left), right: Math.round(r.right) })
        }
      }
      return out
    },
    { main: MAIN, attr: SCROLLER_ATTR },
  )
}

export function describeClipped(route: string, width: number, bad: Clipped[]): string {
  const list = bad.slice(0, 5).map((b) => `${b.element} (${b.left}..${b.right})`).join(', ')
  return `route ${route} at ${width}px: ${bad.length} element(s) outside the viewport and not in a ${SCROLLER_ATTR} scroller: ${list}`
}
