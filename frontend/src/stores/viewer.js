// GC-SET step 9 (REQ-169 AC-1): the ONE place the browser asks "is the person looking the admin?". Today the app has a
// single fixed owner who is the admin (as backend `routes.settings.require_admin`), so `admin` starts true; this
// becomes the admin role when sign-in lands. Admin-only controls read `isAdmin` and nothing else. It only decides what
// is SHOWN: the server refuses a non-admin on every system playbook route.
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export const useViewer = defineStore('viewer', () => {
  const admin = ref(true)
  const isAdmin = computed(() => admin.value === true)
  return { admin, isAdmin }
})
