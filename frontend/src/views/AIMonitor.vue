<template>
  <div class="space-y-8 max-w-screen-xl">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <!-- KPI strip -->
    <StatRow :stats="aiStats" />

    <!-- Confidence distribution + type breakdown -->
    <div class="grid grid-cols-1 xl:grid-cols-2 gap-8">
      <SectionContainer title="Confidence Distribution" subtitle="Last 7 days by score band">
        <div v-if="loading" class="space-y-3">
          <div v-for="i in 5" :key="i" class="flex gap-3">
            <div class="h-3 bg-ctrl-raised rounded animate-pulse flex-1" />
            <div class="h-3 w-12 bg-ctrl-raised rounded animate-pulse" />
          </div>
        </div>
        <div v-else-if="!stats.confidence_buckets?.length">
          <EmptyState :icon="BarChart2" message="No confidence data" />
        </div>
        <div v-else class="divide-y divide-ctrl-divide">
          <div v-for="bucket in stats.confidence_buckets" :key="bucket.bucket" class="flex items-center justify-between py-2.5 first:pt-0 last:pb-0">
            <div class="flex items-center gap-3">
              <span class="status-dot" :class="confidenceDot(bucket.bucket)" />
              <span class="text-sm text-ctrl-text">{{ bucket.bucket }}</span>
            </div>
            <span class="tabnum text-ctrl-text font-medium">{{ bucket.count }}</span>
          </div>
        </div>
      </SectionContainer>

      <SectionContainer title="Request Type Breakdown" subtitle="Last 7 days by category">
        <Table
          :columns="typeColumns"
          :rows="stats.type_breakdown"
          :loading="loading"
          :skeleton-rows="4"
          empty-message="No type breakdown available"
          :empty-icon="Layers"
        >
          <template #cell-request_type="{ value }">
            <span class="font-medium text-ctrl-text capitalize">{{ value }}</span>
          </template>
          <template #cell-count="{ value }"><span class="tabnum">{{ value }}</span></template>
          <template #cell-avg_confidence="{ value }">
            <Badge :variant="confidenceVariant(value >= 0.9 ? '≥90%' : value >= 0.8 ? '80-90%' : '<80%')">
              {{ formatPct(value * 100) }}
            </Badge>
          </template>
          <template #cell-avg_cost_usd="{ value }">
            <span class="tabnum text-ctrl-muted">${{ parseFloat(value).toFixed(4) }}</span>
          </template>
        </Table>
      </SectionContainer>
    </div>

    <!-- Recent decisions -->
    <SectionContainer title="Recent AI Decisions" subtitle="Latest 25 LLM calls">
      <template #action>
        <div class="flex items-center gap-2 flex-wrap">
          <select v-model="aiFilters.request_type" @change="load()" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 focus:outline-none">
            <option value="">All types</option>
            <option value="lead_scoring">Lead Scoring</option>
            <option value="email_generation">Email Generation</option>
            <option value="reply_classification">Reply Classification</option>
            <option value="research_matching">Research Matching</option>
          </select>
          <select v-model="aiFilters.status" @change="load()" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 focus:outline-none">
            <option value="">All status</option>
            <option value="completed">Completed</option>
            <option value="pending_review">Pending Review</option>
            <option value="rejected">Rejected</option>
          </select>
          <input v-model.number="aiFilters.min_confidence" @change="load()" type="number" min="0" max="1" step="0.05" placeholder="Min conf" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 w-20 focus:outline-none tabnum" />
          <input v-model.number="aiFilters.max_confidence" @change="load()" type="number" min="0" max="1" step="0.05" placeholder="Max conf" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 w-20 focus:outline-none tabnum" />
        </div>
      </template>
      <Table
        :columns="decisionsColumns"
        :rows="stats.decisions"
        :loading="loading"
        :skeleton-rows="8"
        empty-message="No decisions recorded"
        :empty-icon="Brain"
      >
        <template #cell-created_at="{ value }">
          <span class="tabnum text-ctrl-muted text-xs">{{ formatDate(value) }}</span>
        </template>
        <template #cell-request_type="{ value }">
          <span class="font-medium capitalize">{{ value }}</span>
        </template>
        <template #cell-status="{ value }">
          <Badge :variant="statusVariant(value)">{{ value }}</Badge>
        </template>
        <template #cell-confidence_score="{ value }">
          <span class="tabnum" :class="confidenceColor(value)">{{ value ? `${(value * 100).toFixed(1)}%` : '—' }}</span>
        </template>
        <template #cell-cost_usd="{ value }">
          <span class="tabnum text-ctrl-muted">${{ value ? parseFloat(value).toFixed(4) : '0.0000' }}</span>
        </template>
      </Table>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, BarChart2, Brain, Layers } from 'lucide-vue-next'
import { adminAPI } from '../api/index.js'
import Badge from '../components/ui/Badge.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'

const stats = ref({
  calls_today: 0, cost_today_usd: 0, avg_confidence: 0,
  accuracy_pct: 0, fallback_rate_pct: 0, pending_review: 0,
  confidence_buckets: [], type_breakdown: [], decisions: [],
})
const loading = ref(false)
const error   = ref('')
const aiFilters = ref({ request_type: '', status: '', min_confidence: null, max_confidence: null })

const typeColumns = [
  { key: 'request_type',  label: 'Type' },
  { key: 'count',         label: 'Count',    align: 'right' },
  { key: 'avg_confidence', label: 'Avg Conf', align: 'right' },
  { key: 'avg_cost_usd',  label: 'Avg Cost', align: 'right' },
]

const decisionsColumns = [
  { key: 'created_at',       label: 'Time' },
  { key: 'request_type',     label: 'Type' },
  { key: 'status',           label: 'Status' },
  { key: 'confidence_score', label: 'Confidence', align: 'right' },
  { key: 'cost_usd',         label: 'Cost',       align: 'right' },
]

const budgetSubtext = computed(() => `${((stats.value.cost_today_usd / 10) * 100).toFixed(0)}% of $10 budget`)

const aiStats = computed(() => {
  const s = stats.value
  return [
    { label: 'Calls Today',    value: s.calls_today,                        sub: 'AI requests' },
    { label: 'Cost Today',     value: `$${s.cost_today_usd.toFixed(3)}`,    status: s.cost_today_usd > 8 ? 'warn' : undefined, sub: budgetSubtext.value },
    { label: 'Avg Confidence', value: formatPct(s.avg_confidence * 100),    status: s.avg_confidence >= 0.9 ? 'ok' : s.avg_confidence >= 0.8 ? 'warn' : 'err', sub: 'target >= 90%' },
    { label: 'Accuracy',       value: `${s.accuracy_pct}%`,                 status: s.accuracy_pct >= 95 ? 'ok' : 'warn', sub: 'human verified' },
    { label: 'Fallback Rate',  value: `${s.fallback_rate_pct}%`,            status: s.fallback_rate_pct > 10 ? 'err' : undefined },
    { label: 'Pending Review', value: s.pending_review,                     status: s.pending_review > 0 ? 'warn' : undefined, sub: 'SLA 4h' },
  ]
})

function formatDate(value) { return value ? new Date(value).toLocaleString() : '—' }
function formatPct(value)  { return `${parseFloat(value).toFixed(1)}%` }

function confidenceVariant(bucket) {
  if (typeof bucket !== 'string') return 'default'
  if (bucket.includes('90') || bucket.includes('≥90')) return 'success'
  if (bucket.includes('80') || bucket.includes('85'))  return 'warning'
  return 'error'
}

function confidenceDot(bucket) {
  if (bucket.includes('≥90') || bucket.includes('90')) return 'bg-status-ok'
  if (bucket.includes('80')  || bucket.includes('85')) return 'bg-status-warn'
  return 'bg-status-err'
}

function confidenceColor(value) {
  if (!value) return 'text-ctrl-muted'
  if (value >= 0.9) return 'text-status-ok'
  if (value >= 0.8) return 'text-status-warn'
  return 'text-status-err'
}

function statusVariant(status) {
  const map = { completed: 'success', pending_review: 'pending', rejected: 'error' }
  return map[status] ?? 'default'
}

async function load() {
  loading.value = true
  error.value   = ''
  try {
    const params = { limit: 25 }
    if (aiFilters.value.request_type) params.request_type = aiFilters.value.request_type
    if (aiFilters.value.status) params.status = aiFilters.value.status
    if (aiFilters.value.min_confidence != null) params.min_confidence = aiFilters.value.min_confidence
    if (aiFilters.value.max_confidence != null) params.max_confidence = aiFilters.value.max_confidence
    const { data } = await adminAPI.getAIDecisions(params)
    stats.value = data
  } catch {
    error.value = 'Failed to load AI stats.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
