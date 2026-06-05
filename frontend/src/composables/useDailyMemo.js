import { ref, onMounted } from 'vue'
import { adminAPI } from '../api/index.js'

const STORAGE_KEY = 'esteps:strategy-memo'

function todayStamp() {
  return new Date().toISOString().slice(0, 10)  // YYYY-MM-DD in local time-ish
}

function readCache() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const { date, text, generated_at } = JSON.parse(raw)
    if (date !== todayStamp()) return null   // expired — different day
    if (!text) return null
    return { text, generated_at }
  } catch {
    return null
  }
}

function writeCache(text, generated_at) {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ date: todayStamp(), text, generated_at: generated_at || new Date().toISOString() }),
    )
  } catch {
    /* quota / disabled — silent */
  }
}

function clearCache() {
  try { localStorage.removeItem(STORAGE_KEY) } catch { /* noop */ }
}

/**
 * Shared cache for the daily AI strategy memo.
 * The memo persists in localStorage and is restored on mount until either:
 *   - the local-time date changes (rolls over at midnight), or
 *   - the user clicks Generate again (overwrites the cache).
 */
export function useDailyMemo() {
  const memo         = ref('')
  const memoError    = ref('')
  const memoLoading  = ref(false)
  const generatedAt  = ref('')

  onMounted(() => {
    const cached = readCache()
    if (cached) {
      memo.value        = cached.text
      generatedAt.value = cached.generated_at || ''
    }
  })

  async function genMemo() {
    memoLoading.value = true
    memoError.value   = ''
    try {
      const { data } = await adminAPI.generateMemo()
      memo.value        = data.memo
      generatedAt.value = data.generated_at || new Date().toISOString()
      writeCache(memo.value, generatedAt.value)
    } catch (e) {
      memoError.value = e.response?.data?.detail || 'Could not generate memo.'
      // keep prior cached memo on error — don't blank it
    } finally {
      memoLoading.value = false
    }
  }

  function resetMemo() {
    memo.value        = ''
    memoError.value   = ''
    generatedAt.value = ''
    clearCache()
  }

  return { memo, memoError, memoLoading, generatedAt, genMemo, resetMemo }
}
