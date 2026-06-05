<template>
  <div class="space-y-6 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <StatRow :stats="[
      { label: 'In window',  value: meetings.length, sub: windowLabel },
      { label: 'Upcoming',    value: upcoming,        status: upcoming > 0 ? 'ok' : undefined },
      { label: 'Past',        value: past,            sub: 'in window' },
      { label: 'Next 7 days', value: nextWeek,        status: nextWeek > 0 ? 'info' : undefined },
    ]" />

    <SectionContainer :title="windowLabel" subtitle="15-day window of scheduled meetings — click a card to open the contact">
      <template #action>
        <div class="flex items-center gap-1.5">
          <button @click="shift(-15)" class="px-2.5 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text transition-all">‹ Back 15</button>
          <button @click="goToday"    class="px-2.5 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text transition-all">Today</button>
          <button @click="shift(15)"  class="px-2.5 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text transition-all">Forward 15 ›</button>
        </div>
      </template>

      <div class="grid grid-cols-5 gap-1.5">
        <div
          v-for="(cell, i) in cells"
          :key="i"
          class="relative min-h-[5.5rem] border border-ctrl-border rounded p-1.5 transition-colors"
          :class="[
            cell.isSunday ? 'cal-sunday text-ctrl-dim' : 'bg-ctrl-panel/40',
            cell.isToday ? 'ring-1 ring-status-info' : '',
          ]"
        >
          <div class="flex items-center justify-between mb-1">
            <div class="flex items-baseline gap-1">
              <span class="text-2xs uppercase tracking-label" :class="cell.isSunday ? 'text-ctrl-dim/60' : 'text-ctrl-dim'">{{ cell.weekday }}</span>
              <span class="text-sm tabnum font-display font-semibold" :class="cell.isToday ? 'text-status-info' : (cell.isSunday ? 'text-ctrl-dim' : 'text-ctrl-muted')">{{ cell.day }}</span>
              <span class="text-2xs text-ctrl-dim">{{ cell.month }}</span>
            </div>
            <span v-if="cell.isToday" class="text-2xs uppercase tracking-label text-status-info">Today</span>
            <span v-else-if="cell.isSunday" class="text-2xs uppercase tracking-label text-ctrl-dim">Off</span>
          </div>
          <div v-if="cell.isSunday" class="text-2xs text-ctrl-dim italic">No meetings</div>
          <div v-else class="space-y-1">
            <button
              v-for="m in cell.meetings"
              :key="m.lead_id + m.when"
              @click="openLead(m.lead_id)"
              class="block w-full text-left px-1.5 py-0.5 rounded text-2xs border transition-all hover:brightness-110"
              :class="m.status === 'past'
                ? 'bg-ctrl-raised border-ctrl-border text-ctrl-dim'
                : 'bg-status-info-bg border-status-info text-status-info'"
              :title="`${m.lead_name} · ${m.institution || '—'} · ${fmtTime(m.when)}`"
            >
              <div class="flex items-center gap-1 truncate">
                <span class="tabnum font-medium">{{ fmtTime(m.when) }}</span>
                <span class="truncate">{{ m.lead_name }}</span>
              </div>
            </button>
            <div v-if="!cell.meetings.length" class="text-2xs text-ctrl-dim">—</div>
          </div>
        </div>
      </div>
    </SectionContainer>

    <SectionContainer title="Upcoming meetings" subtitle="Next 14 days, in order">
      <Table
        :columns="upcomingColumns"
        :rows="upcomingRows"
        :loading="loading"
        :skeleton-rows="6"
        empty-message="No upcoming meetings"
        :empty-icon="CalendarCheck"
      >
        <template #cell-when="{ value }"><span class="tabnum text-ctrl-text">{{ fmtDateTime(value) }}</span></template>
        <template #cell-in_days="{ value }"><span class="tabnum text-ctrl-muted">{{ value }}d</span></template>
        <template #cell-lead_name="{ row }">
          <button @click="openLead(row.lead_id)" class="font-medium text-ctrl-text hover:text-status-info text-left">{{ row.lead_name }}</button>
        </template>
        <template #cell-institution="{ value }"><span class="text-ctrl-muted">{{ value || '—' }}</span></template>
      </Table>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { AlertCircle, CalendarCheck } from 'lucide-vue-next'
import { calendarAPI } from '../api/index.js'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'

const WINDOW_DAYS = 15
const router  = useRouter()
const meetings = ref([])
const loading  = ref(false)
const error    = ref('')
const start    = ref(startOfWeekMonday(new Date()))

function startOfDay(d) { const x = new Date(d); x.setHours(0,0,0,0); return x }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x }
function startOfWeekMonday(d) {
  // Sun=0, Mon=1 ... → shift so Monday becomes day 0.
  const x = startOfDay(d)
  const shift = (x.getDay() + 6) % 7
  return addDays(x, -shift)
}
function fmtIsoDate(d) { return d.toISOString().slice(0, 10) }
function fmtTime(v)    { return new Date(v).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) }
function fmtDateTime(v) {
  return new Date(v).toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

const windowLabel = computed(() => {
  const end = addDays(start.value, WINDOW_DAYS - 1)
  const sameMonth = start.value.getMonth() === end.getMonth() && start.value.getFullYear() === end.getFullYear()
  const fmt = (d, opts) => d.toLocaleDateString('en-GB', opts)
  if (sameMonth) {
    return `${fmt(start.value, { day: 'numeric' })}–${fmt(end, { day: 'numeric', month: 'long', year: 'numeric' })}`
  }
  return `${fmt(start.value, { day: 'numeric', month: 'short' })} → ${fmt(end, { day: 'numeric', month: 'short', year: 'numeric' })}`
})

const upcomingColumns = [
  { key: 'when',         label: 'When' },
  { key: 'in_days',      label: 'In', align: 'right' },
  { key: 'lead_name',    label: 'Name' },
  { key: 'institution',  label: 'Institution' },
]

const cells = computed(() => {
  const today = startOfDay(new Date()).getTime()
  const out = []
  for (let i = 0; i < WINDOW_DAYS; i++) {
    const day = addDays(start.value, i)
    const ymd = fmtIsoDate(day)
    const isSunday = day.getDay() === 0  // JS: Sun=0
    out.push({
      weekday: day.toLocaleDateString('en-GB', { weekday: 'short' }),
      day: day.getDate(),
      month: day.toLocaleDateString('en-GB', { month: 'short' }),
      isToday: day.getTime() === today,
      isSunday,
      meetings: isSunday ? [] : meetings.value.filter(m => m.when.slice(0, 10) === ymd),
    })
  }
  return out
})

const upcoming = computed(() => meetings.value.filter(m => m.status === 'upcoming').length)
const past     = computed(() => meetings.value.filter(m => m.status === 'past').length)
const nextWeek = computed(() => {
  const now = Date.now()
  const week = now + 7 * 24 * 60 * 60 * 1000
  return meetings.value.filter(m => {
    const t = new Date(m.when).getTime()
    return t >= now && t <= week
  }).length
})
const upcomingRows = computed(() => {
  const now = Date.now()
  return meetings.value
    .filter(m => new Date(m.when).getTime() >= now)
    .sort((a, b) => new Date(a.when) - new Date(b.when))
    .slice(0, 20)
    .map(m => ({
      ...m,
      in_days: Math.max(0, Math.round((new Date(m.when).getTime() - now) / (24 * 60 * 60 * 1000))),
    }))
})

function shift(n) { start.value = addDays(start.value, n) }
function goToday() { start.value = startOfWeekMonday(new Date()) }
function openLead(leadId) { if (leadId) router.push({ path: '/contacts', query: { lead: leadId } }) }

async function load() {
  loading.value = true
  error.value = ''
  try {
    const from = fmtIsoDate(start.value)
    const to   = fmtIsoDate(addDays(start.value, WINDOW_DAYS - 1))
    const { data } = await calendarAPI.meetings(from, to)
    meetings.value = data.meetings || []
  } catch (err) {
    error.value = err?.response?.data?.detail ?? 'Failed to load calendar.'
  } finally {
    loading.value = false
  }
}

watch(start, load, { immediate: true })
</script>

<style scoped>
/* Hashed background for Sundays so the day visually reads as "off". */
.cal-sunday {
  background-image: repeating-linear-gradient(
    -45deg,
    rgba(255, 255, 255, 0.025) 0,
    rgba(255, 255, 255, 0.025) 6px,
    transparent 6px,
    transparent 12px
  );
  background-color: rgba(0, 0, 0, 0.2);
}
</style>

