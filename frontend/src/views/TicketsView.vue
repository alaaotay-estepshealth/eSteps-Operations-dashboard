<template>
  <div class="space-y-8 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <StatRow :stats="kpiStats" />

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-8">
      <SectionContainer title="Category Breakdown" subtitle="Tickets by AI-assigned category">
        <div v-if="loading" class="flex gap-3 flex-wrap">
          <div v-for="i in 4" :key="i" class="h-16 flex-1 min-w-28 bg-ctrl-raised rounded animate-pulse" />
        </div>
        <div v-else-if="!stats.category_breakdown?.length">
          <EmptyState :icon="Layers" message="No category data" />
        </div>
        <div v-else class="flex gap-3 flex-wrap">
          <div v-for="cat in stats.category_breakdown" :key="cat.category" class="flex-1 min-w-28 bg-ctrl-panel border border-ctrl-border rounded p-4">
            <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">{{ cat.category ?? 'Unknown' }}</div>
            <div class="tabnum text-2xl font-semibold text-ctrl-text">{{ cat.count }}</div>
          </div>
        </div>
      </SectionContainer>

      <SectionContainer title="Response Time" subtitle="Average resolution metrics">
        <div class="bg-ctrl-panel border border-ctrl-border rounded p-6 text-center">
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">Avg Response Time</div>
          <div class="tabnum text-3xl font-semibold text-ctrl-text">{{ stats.avg_response_time_hours?.toFixed(1) ?? '—' }}h</div>
          <div class="text-2xs text-ctrl-dim mt-1">target &lt; 4h SLA</div>
        </div>
      </SectionContainer>
    </div>

    <SectionContainer title="Ticket Queue" subtitle="All tickets with inline status update">
      <template #action>
        <div class="flex items-center gap-2">
          <select v-model="ticketFilters.status" @change="loadTickets()" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 focus:outline-none">
            <option value="">All status</option>
            <option value="open">Open</option>
            <option value="in_progress">In Progress</option>
            <option value="resolved">Resolved</option>
          </select>
          <select v-model="ticketFilters.category" @change="loadTickets()" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 focus:outline-none">
            <option value="">All categories</option>
            <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>
      </template>

      <Table
        :columns="ticketColumns"
        :rows="tickets"
        :loading="loading"
        :skeleton-rows="8"
        empty-message="No tickets"
        :empty-icon="Ticket"
      >
        <template #cell-created_at="{ value }">
          <span class="tabnum text-ctrl-muted text-xs">{{ formatDate(value) }}</span>
        </template>
        <template #cell-subject="{ value }">
          <span class="font-medium text-ctrl-text">{{ value ?? '—' }}</span>
        </template>
        <template #cell-category="{ value }">
          <span class="text-ctrl-muted text-xs">{{ value ?? '—' }}</span>
        </template>
        <template #cell-status="{ row }">
          <select
            v-if="isAdmin"
            :value="row.status"
            @change="updateStatus(row.id, $event.target.value)"
            class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-1.5 py-1 focus:outline-none cursor-pointer"
            :disabled="updating === row.id"
          >
            <option value="open">Open</option>
            <option value="in_progress">In Progress</option>
            <option value="resolved">Resolved</option>
          </select>
          <Badge v-else :variant="ticketVariant(row.status)">{{ row.status }}</Badge>
        </template>
        <template #cell-priority="{ value }">
          <Badge :variant="value === 'high' ? 'error' : value === 'medium' ? 'warning' : 'default'">{{ value ?? 'normal' }}</Badge>
        </template>
        <template #cell-ai_suggestion="{ row }">
          <div class="min-w-[14rem]">
            <button
              v-if="!row.suggestion && !row.human_verified"
              class="text-2xs text-status-info hover:underline disabled:opacity-50"
              :disabled="suggestingId === row.id"
              @click="getSuggestion(row)"
            >
              {{ suggestingId === row.id ? 'Asking AI…' : 'Get AI suggestion' }}
            </button>

            <SuggestionPill
              v-else-if="row.suggestion?.status === 'pending'"
              :payload="row.suggestion.payload"
              :confidence="row.suggestion.confidence"
              :operators="operators"
              :busy="applyingId === row.suggestion.id"
              @apply="(override) => applySuggestion(row, override)"
              @reject="rejectSuggestion(row)"
            />

            <span v-else-if="row.human_verified" class="text-2xs text-status-ok">
              ✓ AI triaged
              <template v-if="row.suggestion?.applied_at"> · {{ relTime(row.suggestion.applied_at) }}</template>
              <span
                v-if="row.human_override"
                class="ml-1 px-1 bg-status-warn-bg text-status-warn rounded text-3xs"
              >overridden</span>
            </span>

            <button
              v-else-if="row.suggestion?.status === 'rejected'"
              class="text-2xs text-ctrl-muted hover:text-ctrl-text"
              :disabled="suggestingId === row.id"
              @click="getSuggestion(row)"
            >
              Suggestion rejected · re-ask
            </button>

            <span v-else class="text-2xs text-ctrl-muted">—</span>
          </div>
        </template>
      </Table>

      <div v-if="totalTickets > pageSize" class="flex items-center justify-between pt-4 border-t border-ctrl-border mt-4">
        <span class="text-2xs text-ctrl-muted tabnum">{{ offset + 1 }}–{{ Math.min(offset + pageSize, totalTickets) }} of {{ totalTickets }}</span>
        <div class="flex gap-2">
          <button @click="offset = Math.max(0, offset - pageSize); loadTickets()" :disabled="offset === 0" class="px-3 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text disabled:opacity-30 transition-all">Prev</button>
          <button @click="offset += pageSize; loadTickets()" :disabled="offset + pageSize >= totalTickets" class="px-3 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text disabled:opacity-30 transition-all">Next</button>
        </div>
      </div>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, Layers, Ticket } from 'lucide-vue-next'
import { ticketsAPI, suggestionsAPI, usersAPI } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import Badge from '../components/ui/Badge.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'
import SuggestionPill from '../components/SuggestionPill.vue'

const auth         = useAuthStore()
const isAdmin      = computed(() => auth.role === 'admin')
const stats        = ref({ open: 0, in_progress: 0, resolved: 0, avg_response_time_hours: 0, category_breakdown: [] })
const tickets      = ref([])
const loading      = ref(false)
const error        = ref('')
const updating     = ref(null)
const totalTickets = ref(0)
const offset       = ref(0)
const pageSize     = 20
const categories   = ref([])
const ticketFilters = ref({ status: '', category: '' })
const operators    = ref([])
const suggestingId = ref(null)   // ticket id currently awaiting Gemini
const applyingId   = ref(null)   // suggestion id currently being applied/rejected

const ticketColumns = [
  { key: 'created_at',    label: 'Created' },
  { key: 'subject',       label: 'Subject' },
  { key: 'category',      label: 'Category' },
  { key: 'status',        label: 'Status' },
  { key: 'priority',      label: 'Priority' },
  { key: 'ai_suggestion', label: 'AI Triage' },
]

const kpiStats = computed(() => {
  const s = stats.value
  return [
    { label: 'Open',        value: s.open ?? 0,        status: s.open > 0 ? 'warn' : undefined },
    { label: 'In Progress', value: s.in_progress ?? 0, status: 'info' },
    { label: 'Resolved',    value: s.resolved ?? 0,    status: 'ok' },
    { label: 'Avg Response', value: `${(s.avg_response_time_hours ?? 0).toFixed(1)}h`, status: (s.avg_response_time_hours ?? 0) <= 4 ? 'ok' : 'err' },
  ]
})

function formatDate(v) { return v ? new Date(v).toLocaleString() : '—' }

function ticketVariant(s) {
  const map = { open: 'warning', in_progress: 'info', resolved: 'success' }
  return map[s] ?? 'default'
}

async function updateStatus(id, newStatus) {
  updating.value = id
  error.value = ''
  try {
    await ticketsAPI.updateStatus(id, { status: newStatus })
    const ticket = tickets.value.find((t) => t.id === id)
    if (ticket) ticket.status = newStatus
  } catch {
    error.value = `Failed to update ticket ${id}.`
  } finally {
    updating.value = null
  }
}

async function loadOperators() {
  try {
    const { data } = await usersAPI.list()
    operators.value = (data?.users || data || [])
      .filter((u) => u.is_active && (u.role === 'admin' || u.role === 'operator'))
      .map((u) => u.username)
  } catch {
    operators.value = []
  }
}

async function getSuggestion(row) {
  suggestingId.value = row.id
  try {
    const { data } = await ticketsAPI.aiTriage(row.id)
    row.suggestion = data
  } catch (err) {
    const msg = err?.response?.data?.detail || 'AI triage failed'
    error.value = msg
  } finally {
    suggestingId.value = null
  }
}

async function applySuggestion(row, overridePayload = null) {
  if (!row.suggestion) return
  applyingId.value = row.suggestion.id
  try {
    const { data } = await suggestionsAPI.apply(row.suggestion.id, overridePayload)
    row.suggestion = data
    const applied = data.applied_payload || data.payload
    row.ai_category = applied.category
    row.ai_priority_score = applied.priority_score
    row.human_verified = true
    row.human_override = JSON.stringify(applied) !== JSON.stringify(data.payload)
  } catch (err) {
    const msg = err?.response?.data?.detail || 'Apply failed'
    error.value = msg
  } finally {
    applyingId.value = null
  }
}

async function rejectSuggestion(row) {
  if (!row.suggestion) return
  applyingId.value = row.suggestion.id
  try {
    const { data } = await suggestionsAPI.reject(row.suggestion.id, null)
    row.suggestion = data
  } catch (err) {
    const msg = err?.response?.data?.detail || 'Reject failed'
    error.value = msg
  } finally {
    applyingId.value = null
  }
}

function relTime(iso) {
  if (!iso) return ''
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

async function loadTickets() {
  const params = { limit: pageSize, offset: offset.value }
  if (ticketFilters.value.status) params.status = ticketFilters.value.status
  if (ticketFilters.value.category) params.category = ticketFilters.value.category
  try {
    const { data } = await ticketsAPI.list(params)
    tickets.value = data.tickets ?? data
    totalTickets.value = data.total ?? tickets.value.length
  } catch { /* handled by load */ }
}

async function load() {
  loading.value = true
  error.value   = ''
  offset.value  = 0
  try {
    const { data } = await ticketsAPI.getStats()
    stats.value = data
    categories.value = (data.category_breakdown ?? []).map((c) => c.category).filter(Boolean)
    await Promise.all([loadTickets(), loadOperators()])
  } catch {
    error.value = 'Failed to load tickets.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
