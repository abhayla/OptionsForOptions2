// W-192 review fix: a click anywhere outside a menu's root element closes it (the caller's close() also returns focus to the
// menu's trigger button). One document listener per menu, removed when the component goes away.
import { onBeforeUnmount, onMounted } from 'vue'

export function useOutsideClose(isOpen, getRoot, close) {
  const onDown = (e) => {
    if (!isOpen()) return
    const root = getRoot()
    if (root && !root.contains(e.target)) close()
  }
  onMounted(() => document.addEventListener('click', onDown))
  onBeforeUnmount(() => document.removeEventListener('click', onDown))
}
