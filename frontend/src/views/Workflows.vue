<template>
  <div class="space-y-8 max-w-screen-xl">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <!-- Workflow status list -->
    <SectionContainer title="Workflow Status" subtitle="n8n execution health per workflow">
      <div v-if="loading" class="space-y-2">
        <div v-for="i in 4" :key="i" class="h-14 bg-ctrl-raised rounded animate-pulse" />
      </div>
      <div v-else-if="workflows.length === 0">
        <EmptyState :icon="Workflow" message="No workflows registered" subtext="Workflows appear when n8n sends execution events." />
      </div>
      <div v-else class="divide-y divide-ctrl-divide">
        <div
          v-for="wf in workflows"
          :key="wf.workflow_id"
          class="flex items-center gap-5 py-3.5 first:pt-0 last:pb-0"
        >
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2.5 mb-0.5">
              <Workflow class="w-3.5 h-3.5 text-ctrl-dim flex-shrink-0" />
              <span class="text-sm font-medium text-ctrl-text truncate">{{ wf.name }}</span>
            </div>
            <div class="tabnum text-2xs text-ctrl-muted ml-6">
              {{ wf.total_runs }} runs · {{ wf.avg_duration_seconds }}s avg · {{ wf.retries_today }} retries today
            </div>
          </div>
          <div class="flex items-center gap-3 flex-shrink-0">
            <Sparkline
              v-if="sparkData[wf.workflow_id]?.length"
              :data="sparkData[wf.workflow_id]"
              :color="sparkColor(wf.success_rate_pct)"
              class="hidden md:inline-block"
            />
            <span class="tabnum text-2xs text-ctrl-muted hidden md:block">
              {{ wf.failure_count }} fail<span v-if="wf.failure_count !== 1">s</span>
            </span>
            <Badge :variant="healthVariant(wf.success_rate_pct)">{{ wf.success_rate_pct }}%</Badge>
          </div>
        </div>
      </div>
    </SectionContainer>

    <!-- Execution volume chart -->
    <SectionContainer title="Daily Execution Volume" subtitle="Last 14 days — bars coloured by failure rate">
      <div v-if="loading" class="h-28 bg-ctrl-raised rounded animate-pulse" />
      <EmptyState v-else-if="!chartData.length" :icon="BarChart2" message="No daily data" />
      <div v-else>
        <div class="flex items-end gap-0.5 h-24 mb-2">
          <div
            v-for="day in chartData"
            :key="day.date"
            class="flex-1 flex flex-col justify-end group relative"
          >
            <div
              class="w-full rounded-sm transition-all duration-300 cursor-default"
              :class="day.barClass"
              :style="{ height: `${Math.max(day.heightPct, day.total > 0 ? 8 : 0)}%` }"
            >
              <span class="absolute -top-7 left-1/2 -translate-x-1/2 bg-ctrl-panel border border-ctrl-border rounded px-2 py-0.5 text-2xs tabnum text-ctrl-text whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                {{ day.total }} exec · {{ day.failures }} fail
              </span>
            </div>
          </div>
        </div>
        <div class="flex gap-0.5">
          <div v-for="day in chartData" :key="`lbl-${day.date}`" class="flex-1 text-center tabnum text-2xs text-ctrl-dim leading-none">
            {{ day.shortDate }}
          </div>
        </div>
      </div>
    </SectionContainer>

    <!-- Daily executions table -->
    <SectionContainer title="Daily Breakdown" subtitle="Execution counts per day">
      <Table
        :columns="dailyColumns"
        :rows="dailyTotals"
        :loading="loading"
        :skeleton-rows="7"
        empty-message="No daily data available"
      >
        <template #cell-date="{ value }"><span class="tabnum text-ctrl-muted">{{ value }}</span></template>
        <template #cell-executions="{ value }"><span class="tabnum">{{ value }}</span></template>
        <template #cell-successes="{ value }"><span class="tabnum text-status-ok">{{ value }}</span></template>
        <template #cell-failures="{ value }">
          <span class="tabnum" :class="value > 0 ? 'text-status-err' : 'text-ctrl-dim'">{{ value }}</span>
        </template>
      </Table>
    </SectionContainer>

    <!-- Recent failures -->
    <SectionContainer title="Recent Failures" subtitle="Last 10 execution errors">
      <div v-if="recentFailures.length === 0 && !loading">
        <EmptyState :icon="CheckCircle" message="No recent failures" subtext="All workflows running clean." />
      </div>
      <Table
        v-else
        :columns="failureColumns"
        :rows="recentFailures"
        :loading="loading"
        :skeleton-rows="4"
        empty-message="No failures recorded"
      >
        <template #cell-workflow="{ value }">
          <span class="font-medium text-ctrl-text">{{ value }}</span>
        </template>
        <template #cell-started_at="{ value }">
          <span class="tabnum text-ctrl-muted text-xs">{{ formatDate(value) }}</span>
        </template>
        <template #cell-error_message="{ value }">
          <span class="text-status-err text-xs truncate block max-w-xs">{{ value }}</span>
        </template>
      </Table>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, BarChart2, CheckCircle, Workflow } from 'lucide-vue-next'
import { adminAPI } from '../api/index.js'
import Badge from '../components/ui/Badge.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import Sparkline from '../components/ui/Sparkline.vue'
import Table from '../components/ui/Table.vue'

const workflows = ref([])
const daily     = ref([])
const loading   = ref(false)
const error     = ref('')

const dailyColumns = [
  { key: 'date',       label: 'Date' },
  { key: 'executions', label: 'Executions', align: 'right' },
  { key: 'successes',  label: 'Successes',  align: 'right' },
  { key: 'failures',   label: 'Failures',   align: 'right' },
]

const failureColumns = [
  { key: 'workflow',      label: 'Workflow' },
  { key: 'started_at',    label: 'Time' },
  { key: 'error_message', label: 'Error' },
]

function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString()
}

function healthVariant(rate) {
  if (rate >= 95) return 'success'
  if (rate >= 80) return 'warning'
  return 'error'
}

function sparkColor(rate) {
  if (rate >= 95) return 'oklch(72% 0.14 164)'
  if (rate >= 80) return 'oklch(79% 0.15 80)'
  return 'oklch(66% 0.17 25)'
}

const sparkData = computed(() => {
  const map = {}
  daily.value.forEach((row) => {
    if (!map[row.workflow_id]) map[row.workflow_id] = {}
    map[row.workflow_id][row.date] = (map[row.workflow_id][row.date] || 0) + row.executions
  })
  const result = {}
  for (const [wfId, dateMap] of Object.entries(map)) {
    const sorted = Object.entries(dateMap).sort((a, b) => a[0].localeCompare(b[0]))
    result[wfId] = sorted.slice(-7).map(([, count]) => count)
  }
  return result
})

const dailyTotals = computed(() => {
  const map = new Map()
  daily.value.forEach((row) => {
    const cur = map.get(row.date) || { date: row.date, executions: 0, successes: 0, failures: 0 }
    cur.executions += row.executions
    cur.successes  += row.successes
    cur.failures   += row.failures
    map.set(row.date, cur)
  })
  return Array.from(map.values()).sort((a, b) => b.date.localeCompare(a.date))
})

const chartData = computed(() => {
  const asc = [...dailyTotals.value].reverse()
  const max = Math.max(...asc.map((d) => d.executions), 1)
  return asc.map((d) => {
    const failRate = d.executions > 0 ? d.failures / d.executions : 0
    return {
      date:      d.date,
      total:     d.executions,
      failures:  d.failures,
      heightPct: (d.executions / max) * 100,
      shortDate: d.date.slice(5),
      barClass:  failRate === 0
        ? 'bg-status-info'
        : failRate > 0.2
          ? 'bg-status-err'
          : 'bg-status-warn',
    }
  })
})

const recentFailures = computed(() => {
  const failures = []
  workflows.value.forEach((wf) => {
    wf.recent_failures?.forEach((f) => {
      failures.push({ id: f.id, workflow: wf.name, started_at: f.started_at, error_message: f.error_message })
    })
  })
  return failures.slice(0, 10)
})

async function load() {
  loading.value = true
  error.value   = ''
  try {
    const [statusRes, dailyRes] = await Promise.all([
      adminAPI.getWorkflowStatus(),
      adminAPI.getDailyExecutions(14),
    ])
    workflows.value = statusRes.data
    daily.value     = dailyRes.data
  } catch {
    error.value = 'Failed to load workflow status.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
