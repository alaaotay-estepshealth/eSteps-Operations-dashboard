<template>
  <div class="space-y-6 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <SectionContainer title="Contacts" subtitle="Everyone we've contacted — filter to hot leads, click a person for their timeline">
      <template #action>
        <div class="flex items-center gap-2 flex-wrap">
          <input v-model="filters.search" @keyup.enter="reload" type="text" placeholder="Search name / institution..."
            class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 w-48 focus:outline-none placeholder-ctrl-dim" />
          <button @click="toggleHot"
            class="px-3 py-1.5 text-xs rounded border transition-all flex items-center gap-1.5"
            :class="filters.hot ? 'bg-status-warn-bg border-status-warn text-status-warn' : 'bg-ctrl-panel border-ctrl-border text-ctrl-muted hover:text-ctrl-text'">
            <Flame class="w-3.5 h-3.5" /> Hot only
          </button>
          <select v-model="filters.replied" @change="reload" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 focus:outline-none">
            <option value="">All</option>
            <option value="true">Replied</option>
            <option value="false">No reply</option>
          </select>
          <select v-model="filters.stage" @change="reload" class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5 focus:outline-none">
            <option value="">All stages</option>
            <option v-for="s in stages" :key="s" :value="s">{{ s }}</option>
          </select>
        </div>
      </template>

      <Table :columns="columns" :rows="contacts" :loading="loading" :skeleton-rows="10" empty-message="No contacts match" :empty-icon="Users">
        <template #cell-name="{ row }">
          <button @click="open(row.lead_id)" class="font-medium text-ctrl-text hover:text-status-info transition-colors text-left">{{ row.name }}</button>
        </template>
        <template #cell-institution="{ value }"><span class="text-ctrl-muted">{{ value || '—' }}</span></template>
        <template #cell-lead_score="{ value }"><span class="tabnum font-semibold" :class="scoreColor(value)">{{ value }}</span></template>
        <template #cell-touches_sent="{ value }"><span class="tabnum text-ctrl-muted">{{ value }}/5</span></template>
        <template #cell-last_contacted="{ value }"><span class="tabnum text-ctrl-dim text-xs">{{ fmtDate(value) }}</span></template>
        <template #cell-replied="{ value }"><Badge :variant="value ? 'success' : 'default'">{{ value ? 'replied' : '—' }}</Badge></template>
        <template #cell-stage="{ value }"><span class="text-ctrl-dim text-xs capitalize">{{ value }}</span></template>
      </Table>

      <div v-if="total > pageSize" class="flex items-center justify-between pt-4 border-t border-ctrl-border mt-4">
        <span class="text-2xs text-ctrl-muted tabnum">{{ offset + 1 }}–{{ Math.min(offset + pageSize, total) }} of {{ total }}</span>
        <div class="flex gap-2">
          <button @click="prev" :disabled="offset === 0" class="px-3 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text disabled:opacity-30 transition-all">Prev</button>
          <button @click="next" :disabled="offset + pageSize >= total" class="px-3 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text disabled:opacity-30 transition-all">Next</button>
        </div>
      </div>
    </SectionContainer>

    <!-- Detail drawer -->
    <div v-if="selected" class="fixed inset-0 z-30" @keydown.esc="close" tabindex="-1">
      <!-- Backdrop catches outside-clicks. Aside stops propagation so clicks inside don't bubble up. -->
      <div class="absolute inset-0 bg-black/50" @click="close" />
      <aside
        @click.stop
        class="absolute inset-y-0 right-0 w-full max-w-md bg-ctrl-surface border-l border-ctrl-border overflow-y-auto p-6 space-y-5"
      >
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="font-display font-semibold text-lg text-ctrl-text">{{ selected.lead?.name }}</div>
            <div class="text-xs text-ctrl-muted">{{ selected.lead?.position }} · {{ selected.lead?.institution }}</div>
          </div>
          <button @click="close" class="text-ctrl-dim hover:text-ctrl-text text-lg leading-none">✕</button>
        </div>

        <div class="flex flex-wrap gap-2">
          <Badge :variant="scoreVariant(selected.lead?.lead_score)">score {{ selected.lead?.lead_score }}</Badge>
          <Badge variant="default">{{ selected.lead?.stage }}</Badge>
          <Badge v-if="selected.lead?.campaign_tag" :variant="selected.lead.campaign_tag === 'Priority_A' ? 'success' : 'info'">{{ selected.lead.campaign_tag }}</Badge>
        </div>

        <div>
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">Contact</div>
          <div class="grid grid-cols-2 gap-3 text-xs">
            <div class="col-span-2">
              <div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">Email</div>
              <a v-if="selected.lead?.email" :href="`mailto:${selected.lead.email}`" class="text-status-info hover:underline truncate block">{{ selected.lead.email }}</a>
              <div v-else class="text-ctrl-dim">—</div>
            </div>
            <div class="col-span-2">
              <div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">LinkedIn</div>
              <a v-if="selected.lead?.linkedin_url" :href="selected.lead.linkedin_url" target="_blank" rel="noopener" class="text-status-info hover:underline truncate block">
                {{ stripProto(selected.lead.linkedin_url) }} ↗
              </a>
              <div v-else class="text-ctrl-dim">—</div>
            </div>
            <div>
              <div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">Phone</div>
              <a v-if="selected.lead?.phone" :href="`tel:${selected.lead.phone}`" class="text-status-info hover:underline tabnum">{{ selected.lead.phone }}</a>
              <div v-else class="text-ctrl-dim">—</div>
            </div>
            <div>
              <div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">Website</div>
              <a v-if="selected.lead?.website" :href="selected.lead.website" target="_blank" rel="noopener" class="text-status-info hover:underline truncate block">{{ stripProto(selected.lead.website) }} ↗</a>
              <div v-else class="text-ctrl-dim">—</div>
            </div>
          </div>
        </div>

        <div>
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">Profile</div>
          <div class="grid grid-cols-2 gap-3 text-xs">
            <div><div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">Research</div><div class="text-ctrl-muted truncate">{{ selected.lead?.research_interest || '—' }}</div></div>
            <div><div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">Department</div><div class="text-ctrl-muted truncate">{{ selected.lead?.department || '—' }}</div></div>
            <div><div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">h-index</div><div class="text-ctrl-muted tabnum">{{ selected.lead?.h_index ?? '—' }}</div></div>
            <div><div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">Publications</div><div class="text-ctrl-muted tabnum">{{ selected.lead?.publication_count ?? '—' }}</div></div>
            <div><div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">Touches</div><div class="text-ctrl-muted tabnum">{{ selected.lead?.touch_number ?? 0 }} / 5</div></div>
            <div><div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">Next send</div><div class="text-ctrl-muted tabnum">{{ fmtDate(selected.lead?.next_send_date) }}</div></div>
          </div>
        </div>

        <div v-if="selected.lead?.notes">
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">Notes</div>
          <p class="text-xs text-ctrl-muted whitespace-pre-wrap leading-relaxed bg-ctrl-panel rounded px-3 py-2 border border-ctrl-border">{{ selected.lead.notes }}</p>
        </div>

        <div v-if="canAct" class="space-y-1.5 pt-1">
          <div class="flex flex-wrap gap-1.5">
            <button @click="openSchedule" :disabled="acting" class="px-2.5 py-1 text-2xs bg-status-info-bg text-status-info border border-status-info rounded hover:opacity-85 disabled:opacity-30 transition-all">Schedule meet</button>
            <button
              v-if="!isEngaged"
              @click="drawerAct('set_engaged')"
              :disabled="acting"
              class="px-2.5 py-1 text-2xs bg-status-ok-bg text-status-ok border border-status-ok rounded hover:opacity-85 disabled:opacity-30 transition-all"
            >Set engaged</button>
            <button
              v-else
              @click="drawerAct('unset_engaged')"
              :disabled="acting"
              class="px-2.5 py-1 text-2xs bg-status-warn-bg text-status-warn border border-status-warn rounded hover:opacity-85 disabled:opacity-30 transition-all"
              title="Revert to the previous stage"
            >Unset engaged</button>
          </div>
          <div class="flex flex-wrap gap-1.5">
            <button @click="drawerAct('resume')"     :disabled="acting" class="px-2.5 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-ok hover:border-status-ok disabled:opacity-30 transition-all">Reschedule</button>
            <button @click="drawerAct('pause')"       :disabled="acting" class="px-2.5 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-warn hover:border-status-warn disabled:opacity-30 transition-all">Pause</button>
            <button @click="drawerAct('set_priority', 'Priority_A')" :disabled="acting" class="px-2.5 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-ok hover:border-status-ok disabled:opacity-30 transition-all">Bump A</button>
            <button @click="drawerAct('mark_cold')"   :disabled="acting" class="px-2.5 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-err hover:border-status-err disabled:opacity-30 transition-all">Mark Cold</button>
          </div>
        </div>

        <div>
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-3">Timeline</div>
          <div v-if="!selected.timeline?.length" class="text-xs text-ctrl-dim">No recorded activity.</div>
          <ol v-else class="relative border-l border-ctrl-border pl-4 space-y-4">
            <li v-for="(e, i) in selected.timeline" :key="i" class="relative">
              <span class="absolute -left-[1.32rem] top-1 w-2 h-2 rounded-full" :class="eventDot(e.type)" />
              <div class="flex items-center justify-between gap-2">
                <RouterLink
                  v-if="e.type === 'meeting' && e.booking_id"
                  :to="`/meeting/${e.booking_id}`"
                  class="text-sm text-status-info hover:underline"
                >
                  {{ e.label }}
                </RouterLink>
                <span v-else class="text-sm text-ctrl-text">{{ e.label }}</span>
                <span class="text-2xs text-ctrl-dim tabnum whitespace-nowrap">{{ fmtDateTime(e.timestamp) }}</span>
              </div>
              <p v-if="e.detail" class="text-xs text-ctrl-muted mt-1 italic">"{{ e.detail }}"</p>
            </li>
          </ol>
        </div>
      </aside>
    </div>

    <!-- Schedule meeting modal -->
    <div v-if="scheduleOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-[2px]" @click.self="scheduleOpen = false">
      <div class="bg-ctrl-surface border border-ctrl-border rounded-lg shadow-2xl w-full max-w-sm mx-4 overflow-hidden">
        <form @submit.prevent="confirmSchedule">
          <div class="px-5 pt-5 flex items-start justify-between gap-3">
            <div>
              <div class="font-display font-semibold text-base text-ctrl-text leading-tight">Schedule meeting</div>
              <p class="text-xs text-ctrl-muted mt-1">{{ selected?.lead?.name }} — {{ selected?.lead?.institution }}</p>
            </div>
            <button type="button" @click="scheduleOpen = false" class="text-ctrl-dim hover:text-ctrl-text text-lg leading-none">✕</button>
          </div>
          <div class="px-5 pt-4 space-y-3">
            <div>
              <label class="block text-2xs uppercase tracking-label text-ctrl-dim mb-1">Date &amp; time</label>
              <input v-model="scheduleAt" type="datetime-local" required
                class="w-full bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-2 focus:outline-none focus:border-status-info" />
            </div>
            <p class="text-2xs text-ctrl-dim">
              This sets <span class="font-mono">meeting_scheduled_for</span>, moves the stage to
              <span class="font-mono">call_requested</span>, and pauses the drip. Audited in ops DB.
            </p>
          </div>
          <div class="flex items-center justify-end gap-2 px-5 py-4 mt-3 bg-ctrl-panel/40 border-t border-ctrl-border">
            <button type="button" @click="scheduleOpen = false" class="px-3 py-1.5 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text">Cancel</button>
            <button type="submit" :disabled="!scheduleAt || acting"
              class="px-3 py-1.5 text-xs bg-status-info-bg text-status-info border border-status-info rounded hover:opacity-85 disabled:opacity-40 transition-all">
              {{ acting ? 'Saving…' : 'Schedule' }}
            </button>
          </div>
        </form>
      </div>
    </div>

  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, Flame, Users } from 'lucide-vue-next'
import { adminAPI } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import Badge from '../components/ui/Badge.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import Table from '../components/ui/Table.vue'

const route   = useRoute()
const router  = useRouter()
const auth    = useAuthStore()
const canAct  = computed(() => ['admin', 'operator'].includes(auth.role))

const contacts = ref([])
const total    = ref(0)
const loading  = ref(false)
const error    = ref('')
const offset   = ref(0)
const pageSize = 25
const selected = ref(null)
const acting   = ref(false)

const stages = ['new', 'introduced', 'pitching', 'engaged', 'call_requested', 'cold']
const filters = ref({ search: '', hot: false, replied: '', stage: '' })

const scheduleOpen = ref(false)
const scheduleAt   = ref('')
const isEngaged = computed(() => (selected.value?.lead?.stage || '').toLowerCase() === 'engaged')

function openSchedule() {
  const existing = selected.value?.lead?.meeting_scheduled_for
  if (existing) {
    // datetime-local needs YYYY-MM-DDTHH:MM
    scheduleAt.value = new Date(existing).toISOString().slice(0, 16)
  } else {
    const d = new Date()
    d.setDate(d.getDate() + 1)
    d.setMinutes(0, 0, 0)
    scheduleAt.value = d.toISOString().slice(0, 16)
  }
  scheduleOpen.value = true
}

async function confirmSchedule() {
  if (!scheduleAt.value) return
  // Send as ISO string with Z so Postgres parses it as UTC unambiguously.
  const iso = new Date(scheduleAt.value).toISOString()
  await drawerAct('schedule_meeting', iso)
  scheduleOpen.value = false
}

const columns = [
  { key: 'name',           label: 'Name' },
  { key: 'institution',    label: 'Institution' },
  { key: 'lead_score',     label: 'Score', align: 'right' },
  { key: 'touches_sent',   label: 'Touches', align: 'right' },
  { key: 'last_contacted', label: 'Last Contact' },
  { key: 'replied',        label: 'Replied' },
  { key: 'stage',          label: 'Stage' },
]

function scoreColor(s) { return s >= 9 ? 'text-status-ok' : s >= 7 ? 'text-status-info' : s >= 5 ? 'text-status-warn' : 'text-ctrl-muted' }
function scoreVariant(s) { return s >= 9 ? 'success' : s >= 7 ? 'info' : s >= 5 ? 'warning' : 'default' }
function stripProto(url) { return (url || '').replace(/^https?:\/\//, '').replace(/\/$/, '') }
function eventDot(t) { return { reply: 'bg-status-ok', meeting: 'bg-status-info', email_sent: 'bg-ctrl-muted', outbound: 'bg-ctrl-dim' }[t] || 'bg-ctrl-muted' }
function fmtDate(v) { return v ? new Date(v).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : '—' }
function fmtDateTime(v) { return v ? new Date(v).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '' }

function toggleHot() { filters.value.hot = !filters.value.hot; reload() }
function prev() { offset.value = Math.max(0, offset.value - pageSize); load() }
function next() { offset.value += pageSize; load() }
function reload() { offset.value = 0; load() }

async function open(leadId) {
  selected.value = { lead: {}, timeline: [] }
  router.replace({ path: '/contacts', query: { lead: leadId } })
  try {
    const { data } = await adminAPI.getContact(leadId)
    selected.value = data
  } catch {
    error.value = 'Failed to load contact.'
    selected.value = null
  }
}
function close() { selected.value = null; router.replace({ path: '/contacts' }) }

async function drawerAct(action, value = null) {
  if (!selected.value?.lead?.lead_id) return
  acting.value = true
  error.value = ''
  try {
    await adminAPI.leadAction(selected.value.lead.lead_id, { action, value })
    await open(selected.value.lead.lead_id)
    await load()
  } catch (err) {
    const detail = err?.response?.data?.detail
    const msg = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map(d => d.msg).join(', ')
        : null
    error.value = msg
      ? `Action "${action}" failed: ${msg}`
      : `Action "${action}" failed (status ${err?.response?.status ?? '?'}). The backend may need a restart to load new actions.`
  } finally {
    acting.value = false
  }
}

async function load() {
  loading.value = true
  error.value   = ''
  const params = { limit: pageSize, offset: offset.value }
  if (filters.value.search) params.search = filters.value.search
  if (filters.value.hot) params.hot = true
  if (filters.value.replied) params.replied = filters.value.replied
  if (filters.value.stage) params.stage = filters.value.stage
  try {
    const { data } = await adminAPI.getContacts(params)
    contacts.value = data.contacts
    total.value = data.total
  } catch {
    error.value = 'Failed to load contacts.'
  } finally {
    loading.value = false
  }
}

onMounted(() => { if (route.query.lead) open(route.query.lead) })
useStaleFetch(load)
</script>
