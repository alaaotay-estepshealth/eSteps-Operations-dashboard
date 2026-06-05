<template>
  <div class="space-y-8 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <StatRow :stats="kpiStats" />

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-8">
      <SectionContainer title="Deal Pipeline" subtitle="Opportunities by stage">
        <div v-if="loading" class="space-y-4">
          <div v-for="i in 5" :key="i" class="flex gap-4">
            <div class="h-2.5 bg-ctrl-raised rounded animate-pulse flex-1" />
            <div class="h-2.5 w-14 bg-ctrl-raised rounded animate-pulse" />
          </div>
        </div>
        <div v-else-if="!stats.stage_summary?.length">
          <EmptyState :icon="TrendingUp" message="No pipeline data" />
        </div>
        <div v-else class="space-y-3.5">
          <div v-for="stage in stats.stage_summary" :key="stage.stage">
            <div class="flex items-center justify-between mb-1.5 text-xs">
              <span class="text-ctrl-text capitalize">{{ stage.stage.replace(/_/g, ' ') }}</span>
              <span class="tabnum text-ctrl-muted">{{ stage.count }}<span class="text-ctrl-dim ml-1">${{ (stage.value ?? 0).toLocaleString() }}</span></span>
            </div>
            <div class="h-1 rounded-full bg-ctrl-border overflow-hidden">
              <div class="h-full rounded-full bg-status-info transition-all duration-500" :style="{ width: `${stagePct(stage)}%` }" />
            </div>
          </div>
        </div>
      </SectionContainer>

      <SectionContainer title="By Partnership Tier" subtitle="Deal value by tier">
        <div v-if="loading" class="space-y-2">
          <div v-for="i in 3" :key="i" class="h-9 bg-ctrl-raised rounded animate-pulse" />
        </div>
        <div v-else-if="!stats.tier_summary?.length">
          <EmptyState :icon="Layers" message="No tier data" />
        </div>
        <div v-else class="divide-y divide-ctrl-divide">
          <div v-for="tier in stats.tier_summary" :key="tier.tier" class="flex items-center justify-between py-2.5 first:pt-0 last:pb-0">
            <span class="text-sm text-ctrl-text capitalize">{{ tier.tier?.replace(/_/g, ' ') ?? 'Unknown' }}</span>
            <div class="flex items-center gap-3">
              <span class="tabnum text-ctrl-muted text-xs">{{ tier.count }} deals</span>
              <Badge variant="info">${{ (tier.avg_value ?? 0).toLocaleString() }} avg</Badge>
            </div>
          </div>
        </div>
      </SectionContainer>
    </div>

    <SectionContainer title="Active Opportunities" subtitle="All deals with lead context">
      <template #action>
        <select v-model="stageFilter" @change="loadOpps()" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 focus:outline-none">
          <option value="">All stages</option>
          <option v-for="s in stageOptions" :key="s" :value="s">{{ s }}</option>
        </select>
      </template>

      <Table
        :columns="oppColumns"
        :rows="opps"
        :loading="loading"
        :skeleton-rows="8"
        empty-message="No opportunities"
        :empty-icon="HeartHandshake"
      >
        <template #cell-lead_name="{ value }">
          <span class="font-medium text-ctrl-text">{{ value ?? '—' }}</span>
        </template>
        <template #cell-stage="{ value }">
          <Badge :variant="stageVariant(value)">{{ value }}</Badge>
        </template>
        <template #cell-deal_value="{ value }">
          <span class="tabnum">${{ (value ?? 0).toLocaleString() }}</span>
        </template>
        <template #cell-partnership_tier="{ value }">
          <span class="text-ctrl-muted capitalize text-xs">{{ value?.replace(/_/g, ' ') ?? '—' }}</span>
        </template>
        <template #cell-created_at="{ value }">
          <span class="tabnum text-ctrl-muted text-xs">{{ formatDate(value) }}</span>
        </template>
      </Table>

      <div v-if="totalOpps > pageSize" class="flex items-center justify-between pt-4 border-t border-ctrl-border mt-4">
        <span class="text-2xs text-ctrl-muted tabnum">{{ offset + 1 }}–{{ Math.min(offset + pageSize, totalOpps) }} of {{ totalOpps }}</span>
        <div class="flex gap-2">
          <button @click="offset = Math.max(0, offset - pageSize); loadOpps()" :disabled="offset === 0" class="px-3 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text disabled:opacity-30 transition-all">Prev</button>
          <button @click="offset += pageSize; loadOpps()" :disabled="offset + pageSize >= totalOpps" class="px-3 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text disabled:opacity-30 transition-all">Next</button>
        </div>
      </div>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, HeartHandshake, Layers, TrendingUp } from 'lucide-vue-next'
import { opportunitiesAPI } from '../api/index.js'
import Badge from '../components/ui/Badge.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'

const stats       = ref({ pipeline_value: 0, won_value: 0, active_count: 0, avg_deal_value: 0, stage_summary: [], tier_summary: [] })
const opps        = ref([])
const loading     = ref(false)
const error       = ref('')
const totalOpps   = ref(0)
const offset      = ref(0)
const pageSize    = 20
const stageFilter = ref('')
const stageOptions = ['open', 'qualified', 'proposal', 'negotiation', 'won', 'lost']

const oppColumns = [
  { key: 'lead_name',        label: 'Lead' },
  { key: 'stage',            label: 'Stage' },
  { key: 'deal_value',       label: 'Value',  align: 'right' },
  { key: 'partnership_tier', label: 'Tier' },
  { key: 'created_at',       label: 'Created' },
]

const kpiStats = computed(() => {
  const s = stats.value
  return [
    { label: 'Pipeline Value', value: `$${(s.pipeline_value ?? 0).toLocaleString()}` },
    { label: 'Won Value',      value: `$${(s.won_value ?? 0).toLocaleString()}`,      status: 'ok' },
    { label: 'Active Deals',   value: s.active_count ?? 0 },
    { label: 'Avg Deal Size',  value: `$${(s.avg_deal_value ?? 0).toLocaleString()}` },
  ]
})

function formatDate(v) { return v ? new Date(v).toLocaleDateString() : '—' }

function stageVariant(s) {
  const map = { won: 'success', lost: 'error', open: 'info', qualified: 'warning', negotiation: 'pending' }
  return map[s] ?? 'default'
}

function stagePct(stage) {
  const total = stats.value.stage_summary.reduce((s, x) => s + (x.count ?? 0), 0)
  return total ? ((stage.count / total) * 100).toFixed(1) : 0
}

async function loadOpps() {
  const params = { limit: pageSize, offset: offset.value }
  if (stageFilter.value) params.stage = stageFilter.value
  try {
    const { data } = await opportunitiesAPI.list(params)
    opps.value = data.opportunities ?? data
    totalOpps.value = data.total ?? opps.value.length
  } catch { /* handled by load */ }
}

async function load() {
  loading.value = true
  error.value   = ''
  offset.value  = 0
  try {
    const { data } = await opportunitiesAPI.getStats()
    stats.value = data
    await loadOpps()
  } catch {
    error.value = 'Failed to load opportunities.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
