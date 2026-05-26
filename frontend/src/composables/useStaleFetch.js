import { onActivated, onBeforeUnmount, onMounted, ref } from 'vue'

const STALE_MS = 60_000

export function useStaleFetch(fetchFn) {
  const lastFetched   = ref(0)
  const revalidating  = ref(false)

  async function load() {
    revalidating.value = true
    lastFetched.value  = Date.now()
    try {
      await fetchFn()
    } finally {
      revalidating.value = false
    }
  }

  function refreshIfStale() {
    if (Date.now() - lastFetched.value > STALE_MS) load()
  }

  onMounted(() => { load(); window.addEventListener('app:refresh', load) })
  onActivated(refreshIfStale)
  onBeforeUnmount(() => window.removeEventListener('app:refresh', load))

  return { load, lastFetched, revalidating }
}
