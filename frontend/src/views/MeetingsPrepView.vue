<template>
  <div class="space-y-8 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <StatRow :stats="[
      { label: 'Next up',  value: upcoming.length, status: upcoming.length > 0 ? 'ok' : undefined, sub: 'scheduled' },
      { label: 'Recent',   value: recent.length,  sub: 'last 14 days' },
      { label: 'Open tasks',  value: totalOpenTasks, status: totalOpenTasks > 0 ? 'warn' : undefined },
      { label: 'With notes',  value: withNotes,  sub: 'drafted prep' },
    ]" />

    <SectionContainer title="Next up" subtitle="Scheduled meetings — click to open prep">
      <Table
        :columns="columns"
        :rows="upcoming"
        :loading="loading"
        :skeleton-rows="4"
        empty-message="No upcoming meetings"
        :empty-icon="CalendarClock"
      >
        <template #cell-lead_name="{ row, value }">
          <button @click="open(row.booking_id)" class="font-medium text-ctrl-text hover:text-status-info transition-colors text-left">
            {{ value ?? '—' }}
          </button>
        </template>
        <template #cell-institution="{ value }">
          <span class="text-ctrl-muted">{{ value || '—' }}</span>
        </template>
        <template #cell-scheduled_for="{ value }">
          <span class="tabnum text-2xs text-ctrl-muted">{{ formatWhen(value) }}</span>
        </template>
        <template #cell-status="{ value }">
          <Badge :variant="statusVariant(value)">{{ value }}</Badge>
        </template>
        <template #cell-prep="{ row }">
          <div class="flex items-center gap-2 text-2xs">
            <span v-if="row.has_notes" class="text-status-ok">Drafted</span>
            <span v-else class="text-ctrl-dim">No notes</span>
            <span v-if="row.open_task_count > 0" class="text-status-warn">
              · {{ row.open_task_count }} open task{{ row.open_task_count === 1 ? '' : 's' }}
            </span>
          </div>
        </template>
        <template #cell-actions="{ row }">
          <button
            @click="open(row.booking_id)"
            class="px-2 py-1 text-2xs border border-status-info/40 text-status-info rounded hover:bg-status-info-bg transition-all"
          >
            Open prep ↗
          </button>
        </template>
      </Table>
    </SectionContainer>

    <SectionContainer title="Recent" subtitle="Last 14 days — review recaps and completed tasks">
      <Table
        :columns="columns"
        :rows="recent"
        :loading="loading"
        :skeleton-rows="3"
        empty-message="No recent meetings"
        :empty-icon="History"
      >
        <template #cell-lead_name="{ row, value }">
          <button @click="open(row.booking_id)" class="font-medium text-ctrl-text hover:text-status-info transition-colors text-left">
            {{ value ?? '—' }}
          </button>
        </template>
        <template #cell-institution="{ value }">
          <span class="text-ctrl-muted">{{ value || '—' }}</span>
        </template>
        <template #cell-scheduled_for="{ value }">
          <span class="tabnum text-2xs text-ctrl-muted">{{ formatWhen(value) }}</span>
        </template>
        <template #cell-status="{ value }">
          <Badge :variant="statusVariant(value)">{{ value }}</Badge>
        </template>
        <template #cell-prep="{ row }">
          <div class="flex items-center gap-2 text-2xs">
            <span v-if="row.has_notes" class="text-status-ok">Has notes</span>
            <span v-else class="text-ctrl-dim">No recap</span>
          </div>
        </template>
        <template #cell-actions="{ row }">
          <button
            @click="open(row.booking_id)"
            class="px-2 py-1 text-2xs border border-ctrl-border text-ctrl-muted rounded hover:text-ctrl-text hover:border-ctrl-text transition-all"
          >
            Open ↗
          </button>
        </template>
      </Table>
    </SectionContainer>

    <MeetingDrawer
      :open="!!activeBookingId"
      :booking-id="activeBookingId"
      @close="activeBookingId = null"
      @changed="load"
    />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { AlertCircle, CalendarClock, History } from 'lucide-vue-next'
import { meetingsAPI } from '../api/index.js'
import { useStaleFetch } from '../composables/useStaleFetch'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'
import Badge from '../components/ui/Badge.vue'
import MeetingDrawer from '../components/MeetingDrawer.vue'

const rows = ref([])
const loading = ref(false)
const error = ref('')
const activeBookingId = ref(null)

const columns = [
  { key: 'lead_name',     label: 'Lead' },
  { key: 'institution',   label: 'Institution' },
  { key: 'scheduled_for', label: 'When' },
  { key: 'status',        label: 'Status' },
  { key: 'prep',          label: 'Prep' },
  { key: 'actions',       label: '', align: 'right' },
]

const upcoming = computed(() =>
  rows.value
    .filter(r => ['scheduled', 'confirmed', 'rescheduled'].includes(r.status))
    .filter(r => new Date(r.scheduled_for) >= startOfToday())
    .sort((a, b) => new Date(a.scheduled_for) - new Date(b.scheduled_for))
)

const recent = computed(() => {
  const cutoff = new Date(Date.now() - 14 * 24 * 3600 * 1000)
  return rows.value
    .filter(r => {
      if (!r.scheduled_for) return false
      const t = new Date(r.scheduled_for)
      return t < startOfToday() && t >= cutoff
    })
    .sort((a, b) => new Date(b.scheduled_for) - new Date(a.scheduled_for))
})

const totalOpenTasks = computed(() => upcoming.value.reduce((n, r) => n + (r.open_task_count || 0), 0))
const withNotes = computed(() => rows.value.filter(r => r.has_notes).length)

function startOfToday() {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

function open(id) {
  activeBookingId.value = id
}

function statusVariant(s) {
  if (['scheduled', 'confirmed'].includes(s)) return 'info'
  if (s === 'completed') return 'success'
  if (s === 'no_show') return 'error'
  if (s === 'canceled') return 'default'
  if (s === 'rescheduled') return 'warning'
  return 'default'
}

function formatWhen(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const day = d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' })
  const t = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return `${day}, ${t}`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await meetingsAPI.list({ limit: 100 })
    rows.value = data ?? []
  } catch {
    error.value = 'Failed to load meetings.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
