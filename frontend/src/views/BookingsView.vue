<template>
  <div class="space-y-8 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <StatRow :stats="kpiStats" />

    <SectionContainer title="Upcoming Meetings" subtitle="Scheduled calls not yet completed">
      <Table
        :columns="bookingColumns"
        :rows="upcoming"
        :loading="loading"
        :skeleton-rows="5"
        empty-message="No upcoming meetings"
        :empty-icon="CalendarCheck"
      >
        <template #cell-scheduled_for="{ value }">
          <span class="tabnum text-ctrl-text text-xs">{{ formatDateTime(value) }}</span>
        </template>
        <template #cell-lead_name="{ value }">
          <span class="font-medium text-ctrl-text">{{ value ?? '—' }}</span>
        </template>
        <template #cell-institution="{ value }">
          <span class="text-ctrl-muted">{{ value ?? '—' }}</span>
        </template>
        <template #cell-status="{ value }">
          <Badge :variant="bookingVariant(value)">{{ value }}</Badge>
        </template>
      </Table>
    </SectionContainer>

    <SectionContainer title="Past Meetings" subtitle="Completed and no-show bookings">
      <template #action>
        <select v-model="statusFilter" @change="loadBookings()" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 focus:outline-none">
          <option value="">All status</option>
          <option value="completed">Completed</option>
          <option value="no_show">No Show</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </template>

      <Table
        :columns="bookingColumns"
        :rows="past"
        :loading="loading"
        :skeleton-rows="8"
        empty-message="No past meetings"
        :empty-icon="CalendarCheck"
      >
        <template #cell-scheduled_for="{ value }">
          <span class="tabnum text-ctrl-muted text-xs">{{ formatDateTime(value) }}</span>
        </template>
        <template #cell-lead_name="{ value }">
          <span class="font-medium text-ctrl-text">{{ value ?? '—' }}</span>
        </template>
        <template #cell-institution="{ value }">
          <span class="text-ctrl-muted">{{ value ?? '—' }}</span>
        </template>
        <template #cell-status="{ value }">
          <Badge :variant="bookingVariant(value)">{{ value }}</Badge>
        </template>
      </Table>

      <div v-if="totalBookings > pageSize" class="flex items-center justify-between pt-4 border-t border-ctrl-border mt-4">
        <span class="text-2xs text-ctrl-muted tabnum">{{ offset + 1 }}–{{ Math.min(offset + pageSize, totalBookings) }} of {{ totalBookings }}</span>
        <div class="flex gap-2">
          <button @click="offset = Math.max(0, offset - pageSize); loadBookings()" :disabled="offset === 0" class="px-3 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text disabled:opacity-30 transition-all">Prev</button>
          <button @click="offset += pageSize; loadBookings()" :disabled="offset + pageSize >= totalBookings" class="px-3 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text disabled:opacity-30 transition-all">Next</button>
        </div>
      </div>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, CalendarCheck } from 'lucide-vue-next'
import { bookingsAPI } from '../api/index.js'
import Badge from '../components/ui/Badge.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'

const stats         = ref({ upcoming: 0, completed: 0, no_show: 0, no_show_rate_pct: 0 })
const upcoming      = ref([])
const past          = ref([])
const loading       = ref(false)
const error         = ref('')
const totalBookings = ref(0)
const offset        = ref(0)
const pageSize      = 20
const statusFilter  = ref('')

const bookingColumns = [
  { key: 'scheduled_for', label: 'Scheduled' },
  { key: 'lead_name',     label: 'Lead' },
  { key: 'institution',   label: 'Institution' },
  { key: 'status',        label: 'Status' },
]

const kpiStats = computed(() => {
  const s = stats.value
  return [
    { label: 'Upcoming',     value: s.upcoming ?? 0,                       status: 'info' },
    { label: 'Completed',    value: s.completed ?? 0,                      status: 'ok' },
    { label: 'No-Shows',     value: s.no_show ?? 0,                        status: s.no_show > 0 ? 'warn' : undefined },
    { label: 'No-Show Rate', value: `${(s.no_show_rate_pct ?? 0).toFixed(1)}%`, status: s.no_show_rate_pct > 15 ? 'err' : undefined },
  ]
})

function formatDateTime(v) {
  if (!v) return '—'
  return new Date(v).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function bookingVariant(s) {
  const map = { scheduled: 'info', completed: 'success', no_show: 'error', cancelled: 'warning' }
  return map[s] ?? 'default'
}

async function loadBookings() {
  const params = { limit: pageSize, offset: offset.value }
  if (statusFilter.value) params.status = statusFilter.value
  try {
    const { data } = await bookingsAPI.list(params)
    const all = data.bookings ?? data
    const now = new Date()
    upcoming.value = all.filter((b) => new Date(b.scheduled_for) > now && b.status === 'scheduled')
    past.value = all.filter((b) => new Date(b.scheduled_for) <= now || b.status !== 'scheduled')
    totalBookings.value = data.total ?? all.length
  } catch { /* handled by load */ }
}

async function load() {
  loading.value = true
  error.value   = ''
  offset.value  = 0
  try {
    const { data } = await bookingsAPI.getStats()
    stats.value = data
    await loadBookings()
  } catch {
    error.value = 'Failed to load bookings.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
