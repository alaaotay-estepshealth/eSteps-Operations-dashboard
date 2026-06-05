import { ref, watch } from 'vue'

const STORAGE_KEY = 'esteps:sidebar-collapsed'
const collapsed = ref(localStorage.getItem(STORAGE_KEY) === '1')

watch(collapsed, (v) => {
  localStorage.setItem(STORAGE_KEY, v ? '1' : '0')
})

export function useSidebarState() {
  return {
    collapsed,
    toggle: () => { collapsed.value = !collapsed.value },
    expand: () => { collapsed.value = false },
    collapse: () => { collapsed.value = true },
  }
}
