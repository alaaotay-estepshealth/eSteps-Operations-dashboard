<template>
  <div class="space-y-8 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <!-- KPI strip -->
    <StatRow :stats="[
      { label: 'Total Leads',      value: metrics.total_leads,         sub: 'academic researchers' },
      { label: 'Contacted',        value: funnelCount('Contacted'),    sub: 'sequence started' },
      { label: 'Replied',          value: funnelCount('Replied'),      status: funnelCount('Replied') > 0 ? 'ok' : undefined, sub: 'positive responses' },
      { label: 'Meetings Booked',  value: funnelCount('Meeting Booked'), status: funnelCount('Meeting Booked') > 0 ? 'ok' : undefined, sub: 'calendly confirmed' },
    ]" />

    <!-- Funnel + Priority -->
    <div class="grid grid-cols-1 xl:grid-cols-2 gap-8">
      <SectionContainer title="Pipeline Funnel" subtitle="Conversion by stage">
        <div v-if="loading" class="space-y-4">
          <div v-for="i in 5" :key="i" class="flex gap-4">
            <div class="h-2.5 bg-ctrl-raised rounded animate-pulse flex-1" />
            <div class="h-2.5 w-14 bg-ctrl-raised rounded animate-pulse" />
          </div>
        </div>
        <div v-else-if="!metrics.pipeline_funnel?.length">
          <EmptyState :icon="TrendingUp" message="No funnel data" />
        </div>
        <div v-else class="space-y-3.5">
          <div v-for="step in metrics.pipeline_funnel" :key="step.label">
            <div class="flex items-center justify-between mb-1.5 text-xs">
              <span class="text-ctrl-text">{{ step.label }}</span>
              <span class="tabnum text-ctrl-muted">{{ step.count }}<span class="text-ctrl-dim ml-1">({{ step.pct }}%)</span></span>
            </div>
            <div class="h-1 rounded-full bg-ctrl-border overflow-hidden">
              <div class="h-full rounded-full bg-status-info transition-all duration-500" :style="{ width: `${step.pct}%` }" />
            </div>
          </div>
        </div>
      </SectionContainer>

      <SectionContainer title="ICP Priority" subtitle="Lead distribution by tier">
        <div v-if="loading" class="space-y-2">
          <div v-for="i in 4" :key="i" class="h-9 bg-ctrl-raised rounded animate-pulse" />
        </div>
        <div v-else-if="!metrics.priority_breakdown?.length">
          <EmptyState :icon="Target" message="No priority data" />
        </div>
        <div v-else class="divide-y divide-ctrl-divide">
          <div v-for="item in metrics.priority_breakdown" :key="item.tag" class="flex items-center justify-between py-2.5 first:pt-0 last:pb-0">
            <div class="flex items-center gap-3">
              <span class="status-dot" :class="priorityDot(item.tag)" />
              <span class="text-sm text-ctrl-text">{{ item.tag }}</span>
            </div>
            <Badge :variant="priorityVariant(item.tag)">{{ item.count }}</Badge>
          </div>
        </div>
      </SectionContainer>
    </div>

    <!-- Research stats -->
    <SectionContainer title="Research Area Performance" subtitle="Reply rates by academic domain">
      <Table
        :columns="researchColumns"
        :rows="researchStats"
        :loading="loading"
        :skeleton-rows="6"
        empty-message="No research area data available"
      >
        <template #cell-reply_rate_pct="{ value }">
          <Badge :variant="replyRateVariant(value)">{{ value }}%</Badge>
        </template>
        <template #cell-total="{ value }"><span class="tabnum">{{ value }}</span></template>
        <template #cell-contacted="{ value }"><span class="tabnum">{{ value }}</span></template>
        <template #cell-replied="{ value }"><span class="tabnum">{{ value }}</span></template>
        <template #cell-meetings="{ value }"><span class="tabnum">{{ value }}</span></template>
      </Table>
    </SectionContainer>

    <!-- Leads table with filters -->
    <SectionContainer title="Leads" subtitle="Filter and browse all academic researchers">
      <template #action>
        <div class="flex items-center gap-2 flex-wrap">
          <select v-model="filters.stage" @change="loadLeads()" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 focus:outline-none">
            <option value="">All stages</option>
            <option v-for="s in stages" :key="s" :value="s">{{ s }}</option>
          </select>
          <select v-model="filters.research_interest" @change="loadLeads()" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 focus:outline-none">
            <option value="">All areas</option>
            <option v-for="r in researchAreas" :key="r" :value="r">{{ r }}</option>
          </select>
          <input v-model.number="filters.score_min" @change="loadLeads()" type="number" min="0" max="100" placeholder="Min score" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 w-28 focus:outline-none tabnum" />
          <input v-model.number="filters.score_max" @change="loadLeads()" type="number" min="0" max="100" placeholder="Max score" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 w-28 focus:outline-none tabnum" />
        </div>
      </template>

      <Table
        :columns="leadsColumns"
        :rows="leads"
        :loading="loading"
        :skeleton-rows="8"
        empty-message="No leads match filters"
        :empty-icon="Users"
      >
        <template #cell-name="{ row }">
          <span class="font-medium text-ctrl-text">{{ row.first_name }} {{ row.last_name }}</span>
        </template>
        <template #cell-institution="{ value }">
          <span class="text-ctrl-muted">{{ value }}</span>
        </template>
        <template #cell-lead_score="{ value }">
          <span class="tabnum font-semibold" :class="scoreColor(value)">{{ value }}</span>
        </template>
        <template #cell-campaign_tag="{ value }">
          <Badge :variant="priorityVariant(value)">{{ value }}</Badge>
        </template>
        <template #cell-stage="{ value }">
          <span class="text-ctrl-dim text-xs capitalize">{{ value }}</span>
        </template>
        <template #cell-actions="{ row }">
          <div class="flex items-center justify-end gap-1.5">
            <button v-if="row.next_send_date" @click="act(row, 'pause')" :disabled="actingId === row.lead_id"
              class="px-2 py-0.5 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-warn hover:border-status-warn disabled:opacity-30 transition-all">Pause</button>
            <button v-else @click="act(row, 'resume')" :disabled="actingId === row.lead_id"
              class="px-2 py-0.5 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-ok hover:border-status-ok disabled:opacity-30 transition-all">Resume</button>
            <button v-if="row.campaign_tag !== 'Priority_A'" @click="act(row, 'set_priority', 'Priority_A')" :disabled="actingId === row.lead_id"
              class="px-2 py-0.5 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-ok hover:border-status-ok disabled:opacity-30 transition-all">Bump A</button>
            <button v-if="row.stage !== 'cold'" @click="confirmAct(row, 'mark_cold')" :disabled="actingId === row.lead_id"
              class="px-2 py-0.5 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-err hover:border-status-err disabled:opacity-30 transition-all">Cold</button>
          </div>
        </template>
      </Table>

      <div v-if="totalLeads > pageSize" class="flex items-center justify-between pt-4 border-t border-ctrl-border mt-4">
        <span class="text-2xs text-ctrl-muted tabnum">{{ currentOffset + 1 }}–{{ Math.min(currentOffset + pageSize, totalLeads) }} of {{ totalLeads }}</span>
        <div class="flex gap-2">
          <button @click="prevPage" :disabled="currentOffset === 0" class="px-3 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text disabled:opacity-30 transition-all">Prev</button>
          <button @click="nextPage" :disabled="currentOffset + pageSize >= totalLeads" class="px-3 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text disabled:opacity-30 transition-all">Next</button>
        </div>
      </div>
    </SectionContainer>

  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { useToast } from '../composables/useToast.js'
import { AlertCircle, BookOpen, CalendarCheck, MessageSquare, RefreshCw, Send, Star, Target, TrendingUp, Users } from 'lucide-vue-next'
import { adminAPI } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import Badge from '../components/ui/Badge.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'

const metrics      = ref({ total_leads: 0, pipeline_funnel: [], priority_breakdown: [] })
const leads        = ref([])
const researchStats = ref([])
const loading      = ref(false)
const error        = ref('')
const totalLeads   = ref(0)
const currentOffset = ref(0)
const pageSize     = 20

const stages = ['new', 'introduced', 'pitching', 'call_requested', 'cold', 'dead']
const filters = ref({ stage: '', research_interest: '', score_min: null, score_max: null })
const researchAreas = ref([])

const researchColumns = [
  { key: 'research_interest', label: 'Area' },
  { key: 'total',             label: 'Total',     align: 'right' },
  { key: 'contacted',         label: 'Contacted', align: 'right' },
  { key: 'replied',           label: 'Replied',   align: 'right' },
  { key: 'meetings',          label: 'Meetings',  align: 'right' },
  { key: 'reply_rate_pct',    label: 'Reply %',   align: 'right' },
]

const auth     = useAuthStore()
const canAct   = computed(() => ['admin', 'operator'].includes(auth.role))
const toast    = useToast()
const actingId = ref(null)

const leadsColumns = computed(() => {
  const cols = [
    { key: 'name',         label: 'Name' },
    { key: 'institution',  label: 'Institution' },
    { key: 'lead_score',   label: 'Score',    align: 'right' },
    { key: 'campaign_tag', label: 'Priority' },
    { key: 'stage',        label: 'Stage' },
  ]
  if (canAct.value) cols.push({ key: 'actions', label: '', align: 'right' })
  return cols
})

async function act(row, action, value = null) {
  actingId.value = row.lead_id
  error.value = ''
  try {
    await adminAPI.leadAction(row.lead_id, { action, value })
    const toastMessages = {
      resume:       'Lead resumed',
      pause:        'Lead paused',
      set_priority: 'Priority bumped to A',
      mark_cold:    'Marked cold',
    }
    toast.show(toastMessages[action] ?? 'Done')
    await loadLeads()
  } catch (err) {
    error.value = `Action failed for ${row.first_name} ${row.last_name}.`
    toast.show(err?.message || 'Action failed', 'err', 3500)
  } finally {
    actingId.value = null
  }
}

function confirmAct(row, action) {
  if (window.confirm(`Mark ${row.first_name} ${row.last_name} as cold? This stops all outreach.`)) {
    act(row, action)
  }
}

function funnelCount(label) {
  return metrics.value.pipeline_funnel.find((s) => s.label === label)?.count ?? 0
}

function priorityVariant(tag) {
  if (!tag) return 'default'
  const t = tag.toLowerCase()
  if (t.includes('priority_a') || t === 'a') return 'success'
  if (t.includes('priority_b') || t === 'b') return 'info'
  if (t.includes('priority_c') || t === 'c') return 'warning'
  return 'default'
}

function priorityDot(tag) {
  if (!tag) return 'bg-ctrl-muted'
  const t = tag.toLowerCase()
  if (t.includes('priority_a') || t === 'a') return 'bg-status-ok'
  if (t.includes('priority_b') || t === 'b') return 'bg-status-info'
  if (t.includes('priority_c') || t === 'c') return 'bg-status-warn'
  return 'bg-ctrl-border'
}

function replyRateVariant(rate) {
  if (rate >= 20) return 'success'
  if (rate >= 10) return 'warning'
  return 'error'
}

function scoreColor(score) {
  if (score >= 80) return 'text-status-ok'
  if (score >= 60) return 'text-status-info'
  if (score >= 40) return 'text-status-warn'
  return 'text-ctrl-muted'
}

async function loadLeads() {
  const params = { limit: pageSize, offset: currentOffset.value }
  if (filters.value.stage) params.stage = filters.value.stage
  if (filters.value.research_interest) params.research_interest = filters.value.research_interest
  if (filters.value.score_min != null) params.score_min = filters.value.score_min
  if (filters.value.score_max != null) params.score_max = filters.value.score_max
  try {
    const { data } = await adminAPI.getPipelineLeads(params)
    if (data.leads) {
      leads.value = data.leads
      totalLeads.value = data.total ?? data.leads.length
    } else {
      leads.value = Array.isArray(data) ? data : []
      totalLeads.value = leads.value.length
    }
  } catch { /* handled by load() error */ }
}

function prevPage() { currentOffset.value = Math.max(0, currentOffset.value - pageSize); loadLeads() }
function nextPage() { currentOffset.value += pageSize; loadLeads() }

async function load() {
  loading.value = true
  error.value   = ''
  currentOffset.value = 0
  try {
    const [metricsRes, researchRes] = await Promise.all([
      adminAPI.getMetrics(),
      adminAPI.getResearchStats(),
    ])
    metrics.value       = metricsRes.data
    researchStats.value = researchRes.data
    researchAreas.value = researchRes.data.map((r) => r.research_interest).filter(Boolean)
    await loadLeads()
  } catch {
    error.value = 'Failed to load pipeline data.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
