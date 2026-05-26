<template>
  <div class="space-y-8 max-w-screen-xl">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <StatRow :stats="kpiStats" />

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-8">
      <SectionContainer title="Delivery by Step" subtitle="Sequence step performance">
        <Table
          :columns="stepColumns"
          :rows="stats.per_step"
          :loading="loading"
          :skeleton-rows="5"
          empty-message="No step data"
        >
          <template #cell-step="{ value }"><span class="tabnum font-medium">Step {{ value }}</span></template>
          <template #cell-sent="{ value }"><span class="tabnum">{{ value }}</span></template>
          <template #cell-delivered="{ value }"><span class="tabnum">{{ value }}</span></template>
          <template #cell-opened="{ value }"><span class="tabnum">{{ value }}</span></template>
          <template #cell-bounced="{ value }"><span class="tabnum">{{ value }}</span></template>
        </Table>
      </SectionContainer>

      <SectionContainer title="A/B Comparison" subtitle="Variant performance">
        <div v-if="loading" class="space-y-3">
          <div v-for="i in 3" :key="i" class="h-8 bg-ctrl-raised rounded animate-pulse" />
        </div>
        <div v-else-if="!stats.ab_comparison?.length">
          <EmptyState :icon="Split" message="No A/B data" />
        </div>
        <div v-else class="divide-y divide-ctrl-divide">
          <div v-for="v in stats.ab_comparison" :key="v.variant" class="flex items-center justify-between py-3 first:pt-0 last:pb-0">
            <div>
              <span class="font-medium text-ctrl-text">Variant {{ v.variant }}</span>
              <span class="text-2xs text-ctrl-muted ml-2">{{ v.sent }} sent</span>
            </div>
            <div class="flex items-center gap-3">
              <span class="tabnum text-xs text-ctrl-muted">{{ v.open_rate_pct?.toFixed(1) }}% open</span>
              <Badge :variant="v.open_rate_pct >= 30 ? 'success' : v.open_rate_pct >= 15 ? 'warning' : 'error'">
                {{ v.delivered }} delivered
              </Badge>
            </div>
          </div>
        </div>
      </SectionContainer>
    </div>

    <SectionContainer title="Recent Email Logs" subtitle="Individual email delivery records">
      <template #action>
        <div class="flex items-center gap-2">
          <select v-model="logFilters.status" @change="loadLogs()" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 focus:outline-none">
            <option value="">All status</option>
            <option value="sent">Sent</option>
            <option value="delivered">Delivered</option>
            <option value="opened">Opened</option>
            <option value="bounced">Bounced</option>
          </select>
          <select v-model="logFilters.ab_variant" @change="loadLogs()" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 focus:outline-none">
            <option value="">All variants</option>
            <option value="A">A</option>
            <option value="B">B</option>
          </select>
        </div>
      </template>

      <Table
        :columns="logColumns"
        :rows="logs"
        :loading="loading"
        :skeleton-rows="8"
        empty-message="No email logs"
        :empty-icon="Mail"
      >
        <template #cell-sent_at="{ value }">
          <span class="tabnum text-ctrl-muted text-xs">{{ formatDate(value) }}</span>
        </template>
        <template #cell-lead_name="{ value }">
          <span class="font-medium text-ctrl-text">{{ value ?? '—' }}</span>
        </template>
        <template #cell-status="{ value }">
          <Badge :variant="emailStatusVariant(value)">{{ value }}</Badge>
        </template>
        <template #cell-ab_variant="{ value }">
          <span class="tabnum text-ctrl-muted">{{ value ?? '—' }}</span>
        </template>
        <template #cell-sequence_step="{ value }">
          <span class="tabnum">{{ value ?? '—' }}</span>
        </template>
      </Table>

      <div v-if="totalLogs > logLimit" class="flex items-center justify-between pt-4 border-t border-ctrl-border mt-4">
        <span class="text-2xs text-ctrl-muted tabnum">{{ logOffset + 1 }}–{{ Math.min(logOffset + logLimit, totalLogs) }} of {{ totalLogs }}</span>
        <div class="flex gap-2">
          <button @click="logOffset = Math.max(0, logOffset - logLimit); loadLogs()" :disabled="logOffset === 0" class="px-3 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text disabled:opacity-30 transition-all">Prev</button>
          <button @click="logOffset += logLimit; loadLogs()" :disabled="logOffset + logLimit >= totalLogs" class="px-3 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text disabled:opacity-30 transition-all">Next</button>
        </div>
      </div>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, Mail, Split } from 'lucide-vue-next'
import { emailsAPI } from '../api/index.js'
import Badge from '../components/ui/Badge.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'

const stats   = ref({ total_sent: 0, delivery_rate_pct: 0, open_rate_pct: 0, bounce_rate_pct: 0, per_step: [], ab_comparison: [] })
const logs    = ref([])
const loading = ref(false)
const error   = ref('')
const totalLogs = ref(0)
const logOffset = ref(0)
const logLimit  = 20
const logFilters = ref({ status: '', ab_variant: '' })

const stepColumns = [
  { key: 'step',      label: 'Step',      align: 'right' },
  { key: 'sent',      label: 'Sent',      align: 'right' },
  { key: 'delivered', label: 'Delivered', align: 'right' },
  { key: 'opened',   label: 'Opened',    align: 'right' },
  { key: 'bounced',  label: 'Bounced',   align: 'right' },
]

const logColumns = [
  { key: 'sent_at',       label: 'Time' },
  { key: 'lead_name',     label: 'Lead' },
  { key: 'status',        label: 'Status' },
  { key: 'ab_variant',    label: 'Variant' },
  { key: 'sequence_step', label: 'Step', align: 'right' },
]

const kpiStats = computed(() => {
  const s = stats.value
  return [
    { label: 'Total Sent',    value: s.total_sent },
    { label: 'Delivery Rate', value: `${s.delivery_rate_pct?.toFixed(1)}%`, status: s.delivery_rate_pct >= 95 ? 'ok' : 'warn' },
    { label: 'Open Rate',     value: `${s.open_rate_pct?.toFixed(1)}%`,     status: s.open_rate_pct >= 20 ? 'ok' : s.open_rate_pct >= 10 ? 'warn' : 'err' },
    { label: 'Bounce Rate',   value: `${s.bounce_rate_pct?.toFixed(1)}%`,   status: s.bounce_rate_pct <= 3 ? 'ok' : 'err' },
  ]
})

function formatDate(v) { return v ? new Date(v).toLocaleString() : '—' }

function emailStatusVariant(s) {
  const map = { delivered: 'success', opened: 'info', sent: 'default', bounced: 'error' }
  return map[s] ?? 'default'
}

async function loadLogs() {
  const params = { limit: logLimit, offset: logOffset.value }
  if (logFilters.value.status) params.status = logFilters.value.status
  if (logFilters.value.ab_variant) params.ab_variant = logFilters.value.ab_variant
  try {
    const { data } = await emailsAPI.getLogs(params)
    logs.value = data.logs ?? data
    totalLogs.value = data.total ?? logs.value.length
  } catch { /* handled by load error */ }
}

async function load() {
  loading.value = true
  error.value   = ''
  logOffset.value = 0
  try {
    const { data } = await emailsAPI.getStats()
    stats.value = data
    await loadLogs()
  } catch {
    error.value = 'Failed to load email analytics.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
