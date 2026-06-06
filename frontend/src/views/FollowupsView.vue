<template>
  <div class="space-y-8 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <StatRow :stats="[
      { label: 'Overdue',        value: data.overdue?.count ?? 0,        status: (data.overdue?.count ?? 0) > 0 ? 'err' : 'ok', sub: 'next send passed' },
      { label: 'Due Today',      value: data.due_today?.count ?? 0,      status: (data.due_today?.count ?? 0) > 0 ? 'warn' : undefined },
      { label: 'This Week',      value: data.this_week?.count ?? 0,      sub: 'scheduled ahead' },
      { label: 'Upcoming Meetings', value: data.upcoming_meetings?.count ?? 0, status: (data.upcoming_meetings?.count ?? 0) > 0 ? 'ok' : undefined },
    ]" />

    <SectionContainer
      v-for="sec in sections"
      :key="sec.key"
      :title="sec.title"
      :subtitle="`${data[sec.key]?.count ?? 0} total${(data[sec.key]?.count ?? 0) > 30 ? ' — showing first 30' : ''}`"
    >
      <Table
        :columns="columnsFor(sec)"
        :rows="sec.isTaskList ? (data[sec.key]?.tasks ?? []) : (data[sec.key]?.leads ?? [])"
        :loading="loading"
        :skeleton-rows="4"
        :empty-message="sec.empty"
        :empty-icon="sec.icon"
      >
        <template #cell-name="{ row }">
          <button
            v-if="row.booking_id"
            @click="openMeeting(row.booking_id)"
            class="font-medium text-ctrl-text hover:text-status-info transition-colors text-left"
          >{{ row.name || row.lead_name || '—' }}</button>
          <button
            v-else
            @click="openContact(row.lead_id)"
            class="font-medium text-ctrl-text hover:text-status-info transition-colors text-left"
          >{{ row.name || row.lead_name || '—' }}</button>
        </template>
        <template #cell-title="{ row }"><span class="text-ctrl-muted">{{ row.title || '—' }}</span></template>
        <template #cell-institution="{ value }"><span class="text-ctrl-muted">{{ value || '—' }}</span></template>
        <template #cell-lead_score="{ value }"><span class="tabnum font-semibold" :class="scoreColor(value)">{{ value }}</span></template>
        <template #cell-stage="{ value }"><span class="text-ctrl-dim text-xs capitalize">{{ value }}</span></template>
        <template #cell-date="{ row }">
          <span class="tabnum text-xs" :class="(sec.tone === 'err' || (sec.isTaskList && row.overdue_by_hours)) ? 'text-status-err' : 'text-ctrl-muted'">
            {{ fmtDate(row[sec.dateField]) }}
          </span>
        </template>
        <template #cell-actions="{ row }">
          <div v-if="canAct" class="flex items-center justify-end gap-1.5">
            <button @click="act(row, 'resume')" :disabled="actingId === row.lead_id"
              class="px-2 py-0.5 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-ok hover:border-status-ok disabled:opacity-30 transition-all">Reschedule</button>
            <button @click="act(row, 'mark_cold')" :disabled="actingId === row.lead_id"
              class="px-2 py-0.5 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-err hover:border-status-err disabled:opacity-30 transition-all">Drop</button>
          </div>
        </template>
      </Table>
    </SectionContainer>

    <MeetingDrawer
      :open="drawerOpen"
      :booking-id="drawerBookingId"
      @close="drawerOpen = false"
    />

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, CalendarClock, CalendarCheck, Clock, Flame } from 'lucide-vue-next'
import { adminAPI } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'
import MeetingDrawer from '../components/MeetingDrawer.vue'

const router   = useRouter()
const auth     = useAuthStore()
const canAct   = computed(() => ['admin', 'operator'].includes(auth.role))
const data     = ref({})
const loading  = ref(false)
const error    = ref('')
const actingId = ref(null)

const drawerOpen = ref(false)
const drawerBookingId = ref(null)

function openMeeting(bookingId) {
  drawerBookingId.value = bookingId
  drawerOpen.value = true
}

const sections = [
  { key: 'overdue',           title: 'Overdue Follow-ups',  dateField: 'next_send_date',      tone: 'err',  icon: AlertCircle,     empty: 'No overdue follow-ups' },
  { key: 'due_today',         title: 'Due Today',           dateField: 'next_send_date',      tone: 'warn', icon: Clock,           empty: 'Nothing due today' },
  { key: 'this_week',         title: 'This Week',           dateField: 'next_send_date',      tone: '',     icon: CalendarClock,   empty: 'Nothing scheduled this week' },
  { key: 'upcoming_meetings', title: 'Upcoming Meetings',   dateField: 'meeting_scheduled_for', tone: '',   icon: CalendarCheck,   empty: 'No upcoming meetings', noActions: true },
  { key: 'hot_needs_action',  title: 'Hot Leads Needing Action', dateField: 'next_send_date', tone: 'err',  icon: Flame,           empty: 'No hot leads waiting' },
  { key: 'open_meeting_tasks', title: 'Open Meeting Tasks',  dateField: 'due_at',              tone: 'warn', icon: Clock,           empty: 'No open meeting tasks', noActions: true, isTaskList: true },
]

function columnsFor(sec) {
  if (sec.isTaskList) {
    return [
      { key: 'name',  label: 'Lead' },
      { key: 'title', label: 'Task' },
      { key: 'date',  label: 'Due' },
    ]
  }
  const cols = [
    { key: 'name',         label: 'Name' },
    { key: 'institution',  label: 'Institution' },
    { key: 'lead_score',   label: 'Score', align: 'right' },
    { key: 'stage',        label: 'Stage' },
    { key: 'date',         label: sec.key === 'upcoming_meetings' ? 'Meeting' : 'Next Send' },
  ]
  if (canAct.value && !sec.noActions) cols.push({ key: 'actions', label: '', align: 'right' })
  return cols
}

function scoreColor(s) {
  if (s >= 9) return 'text-status-ok'
  if (s >= 7) return 'text-status-info'
  if (s >= 5) return 'text-status-warn'
  return 'text-ctrl-muted'
}
function fmtDate(v) {
  if (!v) return '—'
  return new Date(v).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}
function openContact(id) { router.push({ path: '/contacts', query: { lead: id } }) }

async function act(row, action) {
  actingId.value = row.lead_id
  error.value = ''
  try {
    await adminAPI.leadAction(row.lead_id, { action })
    await load()
  } catch {
    error.value = `Action failed for ${row.name}.`
  } finally {
    actingId.value = null
  }
}

async function load() {
  loading.value = true
  error.value   = ''
  try {
    const { data: d } = await adminAPI.getFollowups()
    data.value = d
  } catch {
    error.value = 'Failed to load follow-ups.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
