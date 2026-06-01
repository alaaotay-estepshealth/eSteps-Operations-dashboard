<template>
  <div class="space-y-8 max-w-screen-xl">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <div>
      <h2 class="font-display font-semibold text-xl text-ctrl-text">{{ greeting }}</h2>
      <p class="text-xs text-ctrl-muted mt-0.5">{{ today }} · your operations briefing</p>
    </div>

    <!-- Overnight -->
    <SectionContainer title="Since Yesterday" subtitle="What changed in the last 24 hours">
      <StatRow :stats="overnightStats" />
    </SectionContainer>

    <!-- Today's priorities -->
    <SectionContainer title="Today's Priorities" subtitle="Click to act">
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <button @click="go('/followups')" class="text-left bg-ctrl-panel border border-status-err rounded p-4 transition-all duration-200 hover:bg-ctrl-raised hover:shadow-float active:scale-[0.99]">
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">Overdue Follow-ups</div>
          <div class="tabnum text-2xl font-semibold text-status-err">{{ b.priorities?.overdue ?? 0 }}</div>
        </button>
        <button @click="go('/followups')" class="text-left bg-ctrl-panel border border-status-warn rounded p-4 transition-all duration-200 hover:bg-ctrl-raised hover:shadow-float active:scale-[0.99]">
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">Due Today</div>
          <div class="tabnum text-2xl font-semibold text-status-warn">{{ b.priorities?.due_today ?? 0 }}</div>
        </button>
        <button @click="go('/pipeline')" class="text-left bg-ctrl-panel border border-ctrl-border rounded p-4 transition-all duration-200 hover:bg-ctrl-raised hover:shadow-float active:scale-[0.99]">
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">Hot Uncontacted</div>
          <div class="tabnum text-2xl font-semibold text-ctrl-text">{{ b.priorities?.hot_uncontacted ?? 0 }}</div>
        </button>
        <button @click="go('/bookings')" class="text-left bg-ctrl-panel border border-ctrl-border rounded p-4 transition-all duration-200 hover:bg-ctrl-raised hover:shadow-float active:scale-[0.99]">
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">Upcoming Meetings</div>
          <div class="tabnum text-2xl font-semibold text-status-ok">{{ b.priorities?.upcoming_meetings ?? 0 }}</div>
        </button>
      </div>
    </SectionContainer>

    <!-- Recommended to contact today -->
    <SectionContainer title="Recommended to Contact Today" subtitle="Ranked by score, uncontacted, and overdue signals">
      <Table :columns="prioColumns" :rows="priority" :loading="loading" :skeleton-rows="6" empty-message="No priority leads" :empty-icon="Flame">
        <template #cell-name="{ row }">
          <button @click="openContact(row.lead_id)" class="font-medium text-ctrl-text hover:text-status-info transition-colors text-left">{{ row.name }}</button>
        </template>
        <template #cell-institution="{ value }"><span class="text-ctrl-muted">{{ value || '—' }}</span></template>
        <template #cell-lead_score="{ value }"><span class="tabnum font-semibold" :class="scoreColor(value)">{{ value }}</span></template>
        <template #cell-reason="{ value }"><span class="text-2xs text-ctrl-muted">{{ value }}</span></template>
        <template #cell-actions="{ row }">
          <div v-if="canAct" class="flex justify-end gap-1.5">
            <button @click="bump(row)" :disabled="actingId === row.lead_id"
              class="px-2 py-0.5 text-2xs border border-ctrl-border rounded text-ctrl-muted hover:text-status-ok hover:border-status-ok disabled:opacity-30 transition-all">Bump A</button>
          </div>
        </template>
      </Table>
    </SectionContainer>

    <!-- AI memo + activity -->
    <div class="grid grid-cols-1 xl:grid-cols-2 gap-8">
      <SectionContainer title="AI Strategy Memo" subtitle="This week's read on the pipeline">
        <template #action>
          <button @click="genMemo" :disabled="memoLoading"
            class="flex items-center gap-2 text-xs border border-status-info text-status-info rounded px-3 py-1.5 hover:bg-status-info-bg disabled:opacity-40 transition-all">
            <Sparkles class="w-3.5 h-3.5" :class="{ 'animate-pulse': memoLoading }" />
            {{ memoLoading ? 'Generating…' : 'Generate' }}
          </button>
        </template>
        <div v-if="memoError" class="text-xs text-status-warn">{{ memoError }}</div>
        <pre v-else-if="memo" class="text-xs text-ctrl-text whitespace-pre-wrap font-sans leading-relaxed">{{ memo }}</pre>
        <EmptyState v-else :icon="Sparkles" message="Generate a memo for today's strategy read" />
      </SectionContainer>

      <SectionContainer title="Recent Activity" subtitle="Latest workflow, AI, and system events">
        <div v-if="loading" class="space-y-2"><div v-for="i in 5" :key="i" class="h-8 bg-ctrl-raised rounded animate-pulse" /></div>
        <ul v-else-if="activity.length" class="divide-y divide-ctrl-divide">
          <li v-for="(e, i) in activity" :key="i" class="flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
            <span class="status-dot" :class="actDot(e.status)" />
            <div class="flex-1 min-w-0">
              <div class="text-sm text-ctrl-text truncate">{{ e.title }}</div>
              <div v-if="e.detail" class="text-2xs text-ctrl-muted truncate">{{ e.detail }}</div>
            </div>
            <span class="text-2xs text-ctrl-dim whitespace-nowrap tabnum">{{ timeAgo(e.timestamp) }}</span>
          </li>
        </ul>
        <EmptyState v-else :icon="Activity" message="No recent activity" />
      </SectionContainer>
    </div>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, Activity, Sparkles, Flame } from 'lucide-vue-next'
import { adminAPI } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import SectionContainer from '../components/ui/SectionContainer.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'

const router      = useRouter()
const auth        = useAuthStore()
const canAct      = computed(() => ['admin', 'operator'].includes(auth.role))
const b           = ref({ overnight: {}, priorities: {} })
const activity    = ref([])
const priority    = ref([])
const actingId    = ref(null)
const loading     = ref(false)
const error       = ref('')

const prioColumns = computed(() => {
  const cols = [
    { key: 'name', label: 'Name' },
    { key: 'institution', label: 'Institution' },
    { key: 'lead_score', label: 'Score', align: 'right' },
    { key: 'reason', label: 'Why' },
  ]
  if (canAct.value) cols.push({ key: 'actions', label: '', align: 'right' })
  return cols
})

function scoreColor(s) { return s >= 9 ? 'text-status-ok' : s >= 7 ? 'text-status-info' : s >= 5 ? 'text-status-warn' : 'text-ctrl-muted' }
function openContact(id) { router.push({ path: '/contacts', query: { lead: id } }) }
async function bump(row) {
  actingId.value = row.lead_id
  try {
    await adminAPI.leadAction(row.lead_id, { action: 'set_priority', value: 'Priority_A' })
    await load()
  } catch { error.value = 'Action failed.' } finally { actingId.value = null }
}
const memo        = ref('')
const memoError   = ref('')
const memoLoading = ref(false)

const greeting = computed(() => {
  const h = new Date().getHours()
  return h < 12 ? 'Good morning.' : h < 18 ? 'Good afternoon.' : 'Good evening.'
})
const today = computed(() => new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' }))

const overnightStats = computed(() => {
  const o = b.value.overnight ?? {}
  return [
    { label: 'New Replies',     value: o.new_replies ?? 0,      status: (o.new_replies ?? 0) > 0 ? 'ok' : undefined },
    { label: 'Leads Contacted', value: o.new_contacted ?? 0 },
    { label: 'Workflow Runs',   value: o.executions ?? 0 },
    { label: 'Failures',        value: o.failures ?? 0,         status: (o.failures ?? 0) > 0 ? 'err' : undefined },
    { label: 'AI Decisions',    value: o.new_ai_decisions ?? 0 },
  ]
})

function go(p) { router.push(p) }
function actDot(s) {
  if (['failed', 'error'].includes(s)) return 'bg-status-err'
  if (['warning', 'pending_review'].includes(s)) return 'bg-status-warn'
  if (['success', 'completed'].includes(s)) return 'bg-status-ok'
  return 'bg-ctrl-muted'
}
function timeAgo(iso) {
  if (!iso) return ''
  const m = (Date.now() - new Date(iso)) / 60000
  if (m < 1) return 'now'
  if (m < 60) return `${Math.floor(m)}m`
  if (m < 1440) return `${Math.floor(m / 60)}h`
  return `${Math.floor(m / 1440)}d`
}

async function genMemo() {
  memoLoading.value = true; memo.value = ''; memoError.value = ''
  try {
    const { data } = await adminAPI.generateMemo()
    memo.value = data.memo
  } catch (e) {
    memoError.value = e.response?.data?.detail || 'Could not generate memo.'
  } finally {
    memoLoading.value = false
  }
}

async function load() {
  loading.value = true; error.value = ''
  try {
    const [br, act, prio] = await Promise.all([
      adminAPI.getBriefing(), adminAPI.getActivityFeed(), adminAPI.getPriorityQueue(),
    ])
    b.value = br.data
    activity.value = act.data
    priority.value = prio.data.leads ?? []
  } catch {
    error.value = 'Failed to load briefing.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
