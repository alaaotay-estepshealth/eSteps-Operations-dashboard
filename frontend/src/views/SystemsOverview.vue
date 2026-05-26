<template>
  <div class="space-y-8 max-w-screen-xl">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <div class="flex items-center justify-between">
      <StatRow :stats="kpiStats" class="flex-1" />
      <button
        v-if="!syncing"
        @click="syncN8n"
        class="ml-4 flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded border
               border-ctrl-border bg-ctrl-panel text-ctrl-text hover:bg-ctrl-raised transition"
        title="Pull latest executions from n8n"
      >
        <RefreshCw class="w-3.5 h-3.5" />
        Sync n8n
      </button>
      <div v-else class="ml-4 flex items-center gap-1.5 text-xs text-ctrl-dim">
        <RefreshCw class="w-3.5 h-3.5 animate-spin" />
        Syncing…
      </div>
    </div>

    <SectionContainer title="Automation Systems" subtitle="Per-system health — last 7 days">
      <div v-if="loading" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <div v-for="i in 5" :key="i" class="h-44 bg-ctrl-raised rounded animate-pulse" />
      </div>

      <EmptyState
        v-else-if="!overview?.systems?.length"
        :icon="Layers"
        message="No systems registered"
        subtext="Run python -m app.seed to seed system records."
      />

      <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <RouterLink
          v-for="sys in overview.systems"
          :key="sys.slug"
          :to="`/systems/${sys.slug}`"
          class="block bg-ctrl-panel border border-ctrl-border rounded-md p-5 no-underline shadow-panel
                 hover:bg-ctrl-raised hover:border-ctrl-border hover:shadow-float
                 active:scale-[0.99] transition-all duration-200"
        >
          <div class="flex items-start justify-between mb-4">
            <div class="min-w-0 flex-1">
              <div class="font-display font-semibold text-sm text-ctrl-text truncate">{{ sys.name }}</div>
              <div class="tabnum text-2xs text-ctrl-dim mt-0.5">{{ sys.slug }}</div>
            </div>
            <Badge :variant="sys.is_active ? 'success' : 'default'" class="ml-3 flex-shrink-0">
              {{ sys.is_active ? 'active' : 'paused' }}
            </Badge>
          </div>

          <div class="grid grid-cols-2 gap-x-4 gap-y-3 mb-4">
            <div>
              <div class="text-2xs uppercase tracking-label text-ctrl-muted mb-0.5">Executions</div>
              <div class="tabnum text-lg font-semibold text-ctrl-text">{{ sys.total_executions }}</div>
            </div>
            <div>
              <div class="text-2xs uppercase tracking-label text-ctrl-muted mb-0.5">Success Rate</div>
              <div class="tabnum text-lg font-semibold" :class="rateColor(sys.success_rate_pct)">{{ sys.success_rate_pct }}%</div>
            </div>
            <div>
              <div class="text-2xs uppercase tracking-label text-ctrl-muted mb-0.5">Avg Duration</div>
              <div class="tabnum text-sm text-ctrl-text">{{ sys.avg_duration_seconds }}s</div>
            </div>
            <div>
              <div class="text-2xs uppercase tracking-label text-ctrl-muted mb-0.5">Errors Today</div>
              <div class="tabnum text-sm" :class="sys.errors_today > 0 ? 'text-status-err' : 'text-ctrl-dim'">{{ sys.errors_today }}</div>
            </div>
          </div>

          <div v-if="sys.last_error" class="bg-status-err-bg border border-status-err rounded px-3 py-2 mb-3">
            <span class="text-2xs text-status-err truncate block">{{ sys.last_error }}</span>
          </div>

          <div class="text-2xs text-ctrl-dim border-t border-ctrl-divide pt-3">
            {{ sys.last_run_at ? `Last run ${formatRelative(sys.last_run_at)}` : 'No executions yet' }}
          </div>
        </RouterLink>
      </div>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { RouterLink } from 'vue-router'
import { AlertCircle, Layers, RefreshCw } from 'lucide-vue-next'
import { systemsAPI, adminAPI } from '@/api'
import Badge from '../components/ui/Badge.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'

const overview = ref(null)
const loading  = ref(false)
const error    = ref('')
const syncing  = ref(false)

async function syncN8n() {
  syncing.value = true
  try {
    await adminAPI.syncN8n(200)
    await load()
  } catch {
    error.value = 'Sync failed — check n8n API key.'
  } finally {
    syncing.value = false
  }
}

const kpiStats = computed(() => {
  if (!overview.value) return [
    { label: 'Active Systems',  value: '—', loading: true },
    { label: 'Executions (7d)', value: '—', loading: true },
    { label: 'Global Success',  value: '—', loading: true },
    { label: 'Errors Today',    value: '—', loading: true },
    { label: 'AI Cost Today',   value: '—', loading: true },
  ]
  const o = overview.value
  return [
    { label: 'Active Systems',  value: o.system_count,                   sub: 'registered' },
    { label: 'Executions (7d)', value: o.total_executions_7d,            sub: 'all systems' },
    { label: 'Global Success',  value: `${o.global_success_rate_pct}%`,  status: o.global_success_rate_pct >= 90 ? 'ok' : o.global_success_rate_pct >= 70 ? 'warn' : 'err' },
    { label: 'Errors Today',    value: o.errors_today,                   status: o.errors_today > 0 ? 'err' : undefined },
    { label: 'AI Cost Today',   value: `$${(o.ai_cost_today_usd ?? 0).toFixed(3)}`, sub: 'all systems' },
  ]
})

function rateColor(pct) {
  if (pct >= 90) return 'text-status-ok'
  if (pct >= 70) return 'text-status-warn'
  return 'text-status-err'
}

function formatRelative(iso) {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

async function load() {
  loading.value = true
  error.value   = ''
  try {
    const res = await systemsAPI.getOverview()
    overview.value = res.data
  } catch {
    error.value = 'Failed to load systems overview.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
