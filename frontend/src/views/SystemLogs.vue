<template>
  <div class="space-y-8 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <!-- Stats strip -->
    <StatRow :stats="logStats" />

    <!-- Toolbar -->
    <div class="flex items-center gap-3 flex-wrap">
      <select
        v-model="level"
        class="bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-2 focus:outline-none focus:border-status-info transition-colors"
      >
        <option value="">All Levels</option>
        <option value="INFO">INFO</option>
        <option value="WARNING">WARNING</option>
        <option value="ERROR">ERROR</option>
        <option value="CRITICAL">CRITICAL</option>
      </select>
      <input
        v-model="source"
        type="text"
        placeholder="Filter by source..."
        class="bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-2 w-52 focus:outline-none focus:border-status-info transition-colors placeholder-ctrl-dim"
      />
      <select
        v-model.number="hours"
        class="bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-2 focus:outline-none focus:border-status-info transition-colors"
      >
        <option :value="6">Last 6h</option>
        <option :value="24">Last 24h</option>
        <option :value="72">Last 72h</option>
        <option :value="168">Last 7d</option>
      </select>
      <button
        @click="load"
        class="px-4 py-2 bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text hover:border-ctrl-raised active:scale-[0.97] transition-all duration-150"
      >
        Apply
      </button>
      <button
        @click="clearFilters"
        class="text-ctrl-dim text-xs hover:text-ctrl-muted transition-colors"
      >
        Clear
      </button>
    </div>

    <!-- Log table -->
    <SectionContainer title="System Logs" :subtitle="tableSubtitle">
      <Table
        :columns="logColumns"
        :rows="stats.logs"
        :loading="loading"
        :skeleton-rows="12"
        empty-message="No logs in this time range"
        :empty-icon="FileText"
      >
        <template #cell-created_at="{ value }">
          <span class="tabnum text-ctrl-muted text-xs">{{ formatDate(value) }}</span>
        </template>
        <template #cell-level="{ value }">
          <Badge :variant="levelVariant(value)">{{ value }}</Badge>
        </template>
        <template #cell-source="{ value }">
          <span class="tabnum text-ctrl-muted text-xs">{{ value }}</span>
        </template>
        <template #cell-message="{ value }">
          <span class="text-xs" :class="messageColor(value)">{{ value }}</span>
        </template>
      </Table>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, FileText } from 'lucide-vue-next'
import { adminAPI } from '../api/index.js'
import Badge from '../components/ui/Badge.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'

const stats   = ref({ errors_today: 0, warnings_today: 0, info_today: 0, error_rate_pct: 0, logs: [] })
const loading = ref(false)
const error   = ref('')
const level   = ref('')
const source  = ref('')
const hours   = ref(24)

const logColumns = [
  { key: 'created_at', label: 'Time' },
  { key: 'level',      label: 'Level' },
  { key: 'source',     label: 'Source' },
  { key: 'message',    label: 'Message' },
]

const logStats = computed(() => [
  { label: 'Errors Today',   value: stats.value.errors_today,   status: stats.value.errors_today > 0 ? 'err' : undefined },
  { label: 'Warnings Today', value: stats.value.warnings_today, status: stats.value.warnings_today > 5 ? 'warn' : undefined },
  { label: 'Info Logs',      value: stats.value.info_today },
  { label: 'Error Rate',     value: `${stats.value.error_rate_pct ?? 0}%`, status: (stats.value.error_rate_pct ?? 0) > 5 ? 'err' : undefined },
])

const tableSubtitle = computed(() => {
  const parts = []
  if (level.value)  parts.push(level.value)
  if (source.value) parts.push(`source: ${source.value}`)
  parts.push(`last ${hours.value}h`)
  return parts.join(' · ')
})

function formatDate(value) { return value ? new Date(value).toLocaleString() : '—' }

function levelVariant(lvl) {
  const map = { INFO: 'info', WARNING: 'warning', ERROR: 'error', CRITICAL: 'error' }
  return map[lvl] ?? 'default'
}

function messageColor(msg) {
  if (!msg) return 'text-ctrl-text'
  const l = msg.toLowerCase()
  if (l.includes('error') || l.includes('fail') || l.includes('critical')) return 'text-status-err'
  if (l.includes('warn')  || l.includes('retry'))                           return 'text-status-warn'
  return 'text-ctrl-text'
}

function clearFilters() {
  level.value  = ''
  source.value = ''
  load()
}

async function load() {
  loading.value = true
  error.value   = ''
  try {
    const { data } = await adminAPI.getLogs({
      level:  level.value  || undefined,
      source: source.value || undefined,
      hours:  hours.value,
      limit:  100,
    })
    stats.value = data
  } catch {
    error.value = 'Failed to load logs.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
