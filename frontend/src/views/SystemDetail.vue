<template>
  <div class="space-y-8 max-w-screen-xl">

    <div class="flex items-center gap-2">
      <RouterLink to="/systems" class="text-ctrl-dim hover:text-ctrl-muted active:scale-[0.97] text-xs transition-all duration-150">
        ← All Systems
      </RouterLink>
      <span class="text-ctrl-dim text-xs">/</span>
      <span class="text-ctrl-muted text-xs">{{ stats?.name ?? slug }}</span>
    </div>

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <StatRow :stats="kpiStats" />

    <SectionContainer title="Live Activity" subtitle="Latest workflow, AI, and system events">
      <div v-if="loading" class="space-y-2">
        <div v-for="i in 5" :key="i" class="h-8 bg-ctrl-raised rounded animate-pulse" />
      </div>
      <div v-else-if="!activity.length" class="text-xs text-ctrl-dim py-4">No recent activity for this system.</div>
      <ul v-else class="divide-y divide-ctrl-divide">
        <li v-for="(e, i) in activity" :key="i" class="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
          <span class="status-dot" :class="activityDot(e.status)" />
          <div class="flex-1 min-w-0">
            <div class="text-sm text-ctrl-text truncate">{{ e.title }}</div>
            <div v-if="e.detail" class="text-2xs text-ctrl-muted truncate">{{ e.detail }}</div>
          </div>
          <span class="text-2xs text-ctrl-dim whitespace-nowrap tabnum">{{ timeAgo(e.timestamp) }}</span>
        </li>
      </ul>
    </SectionContainer>

    <SectionContainer title="Execution History" subtitle="Recent workflow runs for this system">
      <template #action>
        <select
          v-model="statusFilter"
          class="bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-1.5 focus:outline-none focus:border-status-info transition-colors"
          @change="reloadExecutions"
        >
          <option value="">All statuses</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
          <option value="running">Running</option>
        </select>
      </template>

      <Table
        :columns="execColumns"
        :rows="executions"
        :loading="execLoading"
        :skeleton-rows="8"
        empty-message="No executions found for this system"
      >
        <template #cell-workflow_name="{ row }">
          <span class="font-medium text-ctrl-text">{{ row.workflow_name ?? row.workflow_id }}</span>
        </template>
        <template #cell-status="{ value }">
          <Badge :variant="statusVariant(value)">{{ value }}</Badge>
        </template>
        <template #cell-duration_seconds="{ value }">
          <span class="tabnum text-ctrl-muted">{{ value ? `${value}s` : '—' }}</span>
        </template>
        <template #cell-started_at="{ value }">
          <span class="tabnum text-ctrl-muted text-xs">{{ formatDate(value) }}</span>
        </template>
        <template #cell-error_message="{ value }">
          <span v-if="value" class="text-status-err text-xs truncate block max-w-xs">{{ value }}</span>
          <span v-else class="text-ctrl-dim">—</span>
        </template>
      </Table>

      <div v-if="totalExec > limit" class="flex items-center gap-3 mt-4 pt-4 border-t border-ctrl-border">
        <button
          class="px-3 py-1.5 bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text hover:border-ctrl-raised active:scale-[0.97] transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
          :disabled="offset === 0"
          @click="prev"
        >← Prev</button>
        <span class="tabnum text-2xs text-ctrl-muted">
          {{ offset + 1 }}–{{ Math.min(offset + limit, totalExec) }} of {{ totalExec }}
        </span>
        <button
          class="px-3 py-1.5 bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text hover:border-ctrl-raised active:scale-[0.97] transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
          :disabled="offset + limit >= totalExec"
          @click="next"
        >Next →</button>
      </div>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { RouterLink, useRoute } from 'vue-router'
import { AlertCircle } from 'lucide-vue-next'
import { systemsAPI } from '@/api'
import Badge from '../components/ui/Badge.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'

const route = useRoute()
const slug  = route.params.slug

const stats      = ref(null)
const loading    = ref(false)
const error      = ref('')

const activity    = ref([])
const executions  = ref([])
const totalExec   = ref(0)
const execLoading = ref(false)
const statusFilter = ref('')
const offset      = ref(0)
const limit       = 50

const execColumns = [
  { key: 'workflow_name',    label: 'Workflow' },
  { key: 'status',           label: 'Status' },
  { key: 'duration_seconds', label: 'Duration', align: 'right' },
  { key: 'started_at',       label: 'Started' },
  { key: 'error_message',    label: 'Error' },
]

const kpiStats = computed(() => {
  if (!stats.value) return Array(6).fill({ label: '', value: '—', loading: true })
  const s = stats.value
  return [
    { label: 'Executions',   value: s.total_executions,                  sub: '7 days' },
    { label: 'Success Rate', value: `${s.success_rate_pct}%`,            status: s.success_rate_pct >= 90 ? 'ok' : s.success_rate_pct >= 70 ? 'warn' : 'err' },
    { label: 'Failures',     value: s.failure_count,                     status: s.failure_count > 0 ? 'err' : undefined },
    { label: 'Avg Duration', value: `${s.avg_duration_seconds}s` },
    { label: 'AI Cost',      value: `$${(s.ai_cost_today_usd ?? 0).toFixed(3)}`, sub: 'today' },
    { label: 'Errors Today', value: s.errors_today,                      status: s.errors_today > 0 ? 'err' : undefined },
  ]
})

function statusVariant(s) {
  const map = { success: 'success', failed: 'error', running: 'info', retrying: 'warning' }
  return map[s] ?? 'default'
}

function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function activityDot(s) {
  if (['failed', 'error'].includes(s)) return 'bg-status-err'
  if (['warning', 'pending_review'].includes(s)) return 'bg-status-warn'
  if (['success', 'completed'].includes(s)) return 'bg-status-ok'
  return 'bg-ctrl-muted'
}

function timeAgo(iso) {
  if (!iso) return ''
  const m = (Date.now() - new Date(iso)) / 60000
  if (m < 1) return 'now'
  if (m < 60) return `${Math.floor(m)}m`
  if (m < 1440) return `${Math.floor(m / 60)}h`
  return `${Math.floor(m / 1440)}d`
}

async function loadActivity() {
  try {
    const res = await systemsAPI.getSystemActivity(slug)
    activity.value = res.data
  } catch {
    /* non-critical */
  }
}

function prev() { offset.value = Math.max(0, offset.value - limit); loadExecutions() }
function next() { offset.value += limit; loadExecutions() }

function reloadExecutions() {
  offset.value = 0
  loadExecutions()
}

async function loadStats() {
  loading.value = true
  error.value   = ''
  try {
    const res = await systemsAPI.getSystemStats(slug)
    stats.value = res.data
  } catch {
    error.value = 'Failed to load system stats.'
  } finally {
    loading.value = false
  }
}

async function loadExecutions() {
  execLoading.value = true
  try {
    const params = { limit, offset: offset.value }
    if (statusFilter.value) params.status = statusFilter.value
    const res = await systemsAPI.getSystemExecutions(slug, params)
    executions.value = res.data.executions
    totalExec.value  = res.data.total
  } catch {
    error.value = 'Failed to load executions.'
  } finally {
    execLoading.value = false
  }
}

async function load() {
  await Promise.all([loadStats(), loadExecutions(), loadActivity()])
}

useStaleFetch(load)
</script>
