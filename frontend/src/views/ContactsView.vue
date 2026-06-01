<template>
  <div class="space-y-6 max-w-screen-xl">

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
    <div v-if="selected" class="fixed inset-0 z-30" @click.self="close">
      <div class="absolute inset-0 bg-black/50" />
      <aside class="absolute inset-y-0 right-0 w-full max-w-md bg-ctrl-surface border-l border-ctrl-border overflow-y-auto p-6 space-y-5">
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

        <div class="grid grid-cols-2 gap-3 text-xs">
          <div><div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">Email</div><div class="text-ctrl-muted truncate">{{ selected.lead?.email || '—' }}</div></div>
          <div><div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">Research</div><div class="text-ctrl-muted truncate">{{ selected.lead?.research_interest || '—' }}</div></div>
          <div><div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">h-index</div><div class="text-ctrl-muted tabnum">{{ selected.lead?.h_index ?? '—' }}</div></div>
          <div><div class="text-ctrl-dim uppercase tracking-label text-2xs mb-0.5">Touches</div><div class="text-ctrl-muted tabnum">{{ selected.lead?.touch_number ?? 0 }}</div></div>
        </div>

        <div v-if="canAct" class="flex flex-wrap gap-1.5 pt-1">
          <button @click="drawerAct('resume')"     :disabled="acting" class="px-2.5 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-ok hover:border-status-ok disabled:opacity-30 transition-all">Reschedule</button>
          <button @click="drawerAct('pause')"       :disabled="acting" class="px-2.5 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-warn hover:border-status-warn disabled:opacity-30 transition-all">Pause</button>
          <button @click="drawerAct('set_priority', 'Priority_A')" :disabled="acting" class="px-2.5 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-ok hover:border-status-ok disabled:opacity-30 transition-all">Bump A</button>
          <button @click="drawerAct('mark_cold')"   :disabled="acting" class="px-2.5 py-1 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-err hover:border-status-err disabled:opacity-30 transition-all">Mark Cold</button>
        </div>

        <div>
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-3">Timeline</div>
          <div v-if="!selected.timeline?.length" class="text-xs text-ctrl-dim">No recorded activity.</div>
          <ol v-else class="relative border-l border-ctrl-border pl-4 space-y-4">
            <li v-for="(e, i) in selected.timeline" :key="i" class="relative">
              <span class="absolute -left-[1.32rem] top-1 w-2 h-2 rounded-full" :class="eventDot(e.type)" />
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm text-ctrl-text">{{ e.label }}</span>
                <span class="text-2xs text-ctrl-dim tabnum whitespace-nowrap">{{ fmtDateTime(e.timestamp) }}</span>
              </div>
              <p v-if="e.detail" class="text-xs text-ctrl-muted mt-1 italic">"{{ e.detail }}"</p>
            </li>
          </ol>
        </div>
      </aside>
    </div>

  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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

const stages = ['new', 'introduced', 'pitching', 'call_requested', 'cold']
const filters = ref({ search: '', hot: false, replied: '', stage: '' })

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
  try {
    await adminAPI.leadAction(selected.value.lead.lead_id, { action, value })
    await open(selected.value.lead.lead_id)
    await load()
  } catch {
    error.value = 'Action failed.'
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
