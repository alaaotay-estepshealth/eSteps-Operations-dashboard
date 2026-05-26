<template>
  <div class="space-y-8 max-w-screen-xl">

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
import { ticketsAPI } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import Badge from '../components/ui/Badge.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'

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

const ticketColumns = [
  { key: 'created_at', label: 'Created' },
  { key: 'subject',    label: 'Subject' },
  { key: 'category',   label: 'Category' },
  { key: 'status',     label: 'Status' },
  { key: 'priority',   label: 'Priority' },
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
    await loadTickets()
  } catch {
    error.value = 'Failed to load tickets.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
