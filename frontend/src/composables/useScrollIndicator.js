// Copied/adapted from abhayla/algochanakya@bf9faf7:frontend/src/composables/useScrollIndicator.js (ADR-047)
import { ref, onMounted, onUnmounted, watch } from 'vue'

/**
 * Composable for managing scroll indicators on scrollable containers.
 * Adds CSS classes 'can-scroll-left' and 'can-scroll-right' based on scroll position.
 *
 * @param {Ref<HTMLElement>} containerRef - Vue ref to the scrollable container element
 * @returns {Object} - { canScrollLeft, canScrollRight, updateScrollState }
 */
export function useScrollIndicator(containerRef) {
  const canScrollLeft = ref(false)
  const canScrollRight = ref(false)

  const updateScrollState = () => {
    if (!containerRef.value) return

    const { scrollLeft, scrollWidth, clientWidth } = containerRef.value

    canScrollLeft.value = scrollLeft > 0
    // 1px tolerance for rounding
    canScrollRight.value = scrollLeft + clientWidth < scrollWidth - 1

    containerRef.value.classList.toggle('can-scroll-left', canScrollLeft.value)
    containerRef.value.classList.toggle('can-scroll-right', canScrollRight.value)
  }

  watch(
    containerRef,
    (newVal) => {
      if (newVal) {
        newVal.addEventListener('scroll', updateScrollState)
        setTimeout(updateScrollState, 100)
      }
    },
    { immediate: true }
  )

  onMounted(() => {
    if (containerRef.value) {
      containerRef.value.addEventListener('scroll', updateScrollState)
      window.addEventListener('resize', updateScrollState)
      setTimeout(updateScrollState, 100)
    }
  })

  onUnmounted(() => {
    if (containerRef.value) {
      containerRef.value.removeEventListener('scroll', updateScrollState)
    }
    window.removeEventListener('resize', updateScrollState)
  })

  return { canScrollLeft, canScrollRight, updateScrollState }
}
