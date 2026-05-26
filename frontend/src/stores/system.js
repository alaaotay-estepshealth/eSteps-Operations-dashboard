import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { systemsAPI } from '@/api'

export const useSystemStore = defineStore('system', () => {
  const systems = ref([])
  const activeSlug = ref(null)  // null = "all systems" overview
  const loading = ref(false)
  const error = ref('')

  const activeSystem = computed(() =>
    systems.value.find((s) => s.slug === activeSlug.value) ?? null
  )

  async function loadSystems() {
    if (systems.value.length > 0) return
    loading.value = true
    error.value = ''
    try {
      const res = await systemsAPI.listSystems()
      systems.value = res.data
    } catch {
      error.value = 'Failed to load systems'
    } finally {
      loading.value = false
    }
  }

  function setActive(slug) {
    activeSlug.value = slug ?? null
  }

  function syncFromUrl(route) {
    const slug = route.query.system ?? null
    if (slug !== activeSlug.value) activeSlug.value = slug
  }

  return { systems, activeSlug, activeSystem, loading, error, loadSystems, setActive, syncFromUrl }
})
