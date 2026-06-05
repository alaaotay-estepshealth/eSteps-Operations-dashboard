<template>
  <div v-if="visibleAlerts.length" class="space-y-1.5 mb-5">
    <div
      v-for="a in visibleAlerts"
      :key="a.type"
      class="flex items-center gap-2.5 rounded px-3 py-2 text-xs border transition-all"
      :class="a.severity === 'error'
        ? 'bg-status-err-bg border-status-err text-status-err'
        : 'bg-status-warn-bg border-status-warn text-status-warn'"
    >
      <component :is="a.severity === 'error' ? AlertCircle : AlertTriangle" class="w-3.5 h-3.5 flex-shrink-0" />
      <span class="flex-1 font-medium">{{ a.message }}</span>
      <RouterLink
        v-if="a.link"
        :to="a.link"
        class="text-2xs opacity-70 hover:opacity-100 whitespace-nowrap inline-flex items-center gap-1"
      >
        Resolve <span aria-hidden>→</span>
      </RouterLink>
      <button
        @click="dismiss(a)"
        class="ml-1 text-2xs opacity-50 hover:opacity-100 w-5 h-5 flex items-center justify-center rounded hover:bg-black/20 transition-opacity"
        title="Dismiss"
      >
        <X class="w-3 h-3" />
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { RouterLink } from 'vue-router'
import { AlertCircle, AlertTriangle, X } from 'lucide-vue-next'
import { adminAPI } from '../api/index.js'

const STORAGE_KEY = 'esteps:dismissed-alerts'
// Dismissals live for one day, then the banner comes back. Auth login/logout
// also clears the whole map so the next session sees every active alert.
const DISMISS_TTL_MS = 24 * 60 * 60 * 1000

const alerts = ref([])
// Map<fingerprint, dismissedAtEpochMs>
const dismissed = ref(loadDismissed())
let timer

function loadDismissed() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    // Migrate the old array format ([fp, fp, ...]) → drop it; the user opted
    // out of "forever" dismissals.
    if (Array.isArray(parsed)) return {}
    return pruneExpired(parsed)
  } catch { return {} }
}

function pruneExpired(map) {
  const now = Date.now()
  const out = {}
  for (const [fp, ts] of Object.entries(map || {})) {
    if (typeof ts === 'number' && now - ts < DISMISS_TTL_MS) out[fp] = ts
  }
  return out
}

function persistDismissed() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(dismissed.value))
}

// Fingerprint = type + severity + message → tracks "the same alert". When the
// count in the message changes (e.g. "71 → 73 review items"), the user sees the
// new banner again.
function fingerprint(a) { return `${a.type}|${a.severity}|${a.message}` }

const visibleAlerts = computed(() => alerts.value.filter(a => !(fingerprint(a) in dismissed.value)))

function dismiss(a) {
  dismissed.value = { ...dismissed.value, [fingerprint(a)]: Date.now() }
  persistDismissed()
}

async function loadAlerts() {
  if (!localStorage.getItem('token')) {
    alerts.value = []
    return
  }
  try {
    const { data } = await adminAPI.getAlerts()
    alerts.value = Array.isArray(data) ? data : []
    // Garbage-collect: drop dismissed entries that no longer match a live alert
    // OR have ticked past the TTL.
    const live = new Set(alerts.value.map(fingerprint))
    const pruned = pruneExpired(dismissed.value)
    let changed = Object.keys(pruned).length !== Object.keys(dismissed.value).length
    const next = {}
    for (const [fp, ts] of Object.entries(pruned)) {
      if (live.has(fp)) next[fp] = ts
      else changed = true
    }
    if (changed) {
      dismissed.value = next
      persistDismissed()
    }
  } catch {
    /* alerts are non-critical — fail silent */
  }
}

onMounted(() => {
  loadAlerts()
  timer = setInterval(loadAlerts, 60000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>
