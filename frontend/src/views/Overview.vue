<template>
  <div class="space-y-8 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <!-- Campaign Progress — the single most important visual -->
    <div class="bg-ctrl-panel border border-ctrl-border rounded-md p-6">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h2 class="font-display font-semibold text-sm text-ctrl-text">Campaign Progress</h2>
          <p class="text-2xs text-ctrl-muted mt-0.5">972 researchers → 30-50 partnerships</p>
        </div>
        <span class="tabnum text-2xs text-ctrl-dim">{{ metrics.total_leads || 972 }} total leads</span>
      </div>

      <!-- Stage bars: one row per stage, width = pct of total leads -->
      <div class="space-y-2.5">
        <div
          v-for="step in funnelSteps"
          :key="step.label"
          class="flex items-center gap-4"
        >
          <div class="flex items-center gap-2 w-36 flex-shrink-0">
            <span class="w-2 h-2 rounded-full flex-shrink-0" :class="step.dotClass" />
            <span class="text-xs text-ctrl-muted truncate">{{ step.label }}</span>
          </div>
          <div class="flex-1 h-2.5 bg-ctrl-raised rounded-full overflow-hidden">
            <div
              class="h-full rounded-full transition-all duration-700"
              :class="step.bgClass"
              :style="{ width: `${step.pct}%` }"
            />
          </div>
          <div class="flex items-baseline gap-1.5 w-24 justify-end flex-shrink-0">
            <span class="tabnum text-sm font-semibold text-ctrl-text">{{ step.count }}</span>
            <span class="tabnum text-2xs text-ctrl-dim">{{ step.pct }}%</span>
          </div>
        </div>
      </div>
    </div>

    <!-- KPI strip — full row so labels don't truncate -->
    <StatRow :stats="kpiStats" :revalidating="revalidating" />

    <!-- System Health dots — its own row, breathes -->
    <div class="flex flex-wrap items-center gap-x-5 gap-y-2 bg-ctrl-panel border border-ctrl-border rounded px-4 py-3">
      <span class="text-2xs text-ctrl-dim uppercase tracking-label font-display">Systems</span>
      <div v-for="sys in systemHealth" :key="sys.slug" class="flex items-center gap-2 group relative">
        <span class="w-2 h-2 rounded-full flex-shrink-0" :class="healthDotClass(sys.status)" />
        <span class="text-xs text-ctrl-muted">{{ sys.name }}</span>
        <span class="text-2xs text-ctrl-dim tabnum">· {{ sys.last_run_ago || 'no runs' }}</span>
      </div>
      <span v-if="!systemHealth.length" class="text-2xs text-ctrl-dim">no systems registered</span>
    </div>

    <!-- Activity Feed + Pipeline Funnel side by side -->
    <div class="grid grid-cols-1 xl:grid-cols-2 gap-8">

      <!-- Activity Feed -->
      <SectionContainer title="Activity Feed" subtitle="What happened recently">
        <div v-if="loading" class="space-y-3">
          <div v-for="i in 6" :key="i" class="flex gap-3 items-start">
            <div class="w-6 h-6 bg-ctrl-raised rounded-full animate-pulse flex-shrink-0" />
            <div class="flex-1 space-y-1.5">
              <div class="h-3 bg-ctrl-raised rounded animate-pulse w-3/4" />
              <div class="h-2.5 bg-ctrl-raised rounded animate-pulse w-1/2" />
            </div>
          </div>
        </div>
        <div v-else-if="!activityFeed.length">
          <EmptyState :icon="Activity" message="No recent activity" subtext="Events appear when workflows run." />
        </div>
        <div v-else class="space-y-1">
          <div
            v-for="(event, idx) in activityFeed"
            :key="idx"
            class="flex items-start gap-3 py-2.5 border-b border-ctrl-divide last:border-0"
          >
            <div class="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5" :class="eventIconBg(event)">
              <component :is="eventIcon(event)" class="w-3 h-3" :class="eventIconColor(event)" />
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-xs font-medium text-ctrl-text truncate">{{ event.title }}</span>
                <Badge v-if="event.status" :variant="eventBadgeVariant(event.status)" class="flex-shrink-0">
                  {{ event.status }}
                </Badge>
              </div>
              <div class="flex items-center gap-2 mt-0.5">
                <span v-if="event.detail" class="text-2xs text-ctrl-muted truncate">{{ event.detail }}</span>
                <span class="text-2xs text-ctrl-dim tabnum flex-shrink-0">{{ relativeTime(event.timestamp) }}</span>
              </div>
            </div>
          </div>
        </div>
      </SectionContainer>

      <!-- Workflow Health -->
      <SectionContainer title="Workflow Health" subtitle="n8n automation status">
        <div v-if="loading" class="space-y-2">
          <div v-for="i in 4" :key="i" class="h-9 bg-ctrl-raised rounded animate-pulse" />
        </div>
        <div v-else-if="!metrics.workflows?.length">
          <EmptyState :icon="Workflow" message="No workflows registered" />
        </div>
        <div v-else class="divide-y divide-ctrl-divide">
          <div v-for="wf in metrics.workflows" :key="wf.workflow_id" class="flex items-center gap-4 py-2.5 first:pt-0 last:pb-0">
            <div class="flex-1 min-w-0">
              <div class="text-sm text-ctrl-text truncate">{{ wf.name }}</div>
              <div class="tabnum text-2xs text-ctrl-muted">{{ wf.total_runs }} runs · {{ wf.avg_duration_seconds }}s avg</div>
            </div>
            <Badge :variant="healthVariant(wf.success_rate_pct)">{{ wf.success_rate_pct }}%</Badge>
          </div>
        </div>
      </SectionContainer>
    </div>

    <!-- AI snapshot -->
    <SectionContainer title="AI Activity" subtitle="Today's LLM usage">
      <div class="grid grid-cols-3 md:grid-cols-6 gap-3">
        <div v-for="cell in aiCells" :key="cell.label" class="bg-ctrl-panel rounded border border-ctrl-border px-4 py-3">
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-1.5">{{ cell.label }}</div>
          <div class="tabnum text-lg font-semibold" :class="cell.color">{{ cell.value }}</div>
        </div>
      </div>
    </SectionContainer>

    <!-- Priority breakdown -->
    <SectionContainer title="Lead Priority" subtitle="ICP tier distribution">
      <div v-if="loading" class="flex gap-3">
        <div v-for="i in 4" :key="i" class="h-16 flex-1 bg-ctrl-raised rounded animate-pulse" />
      </div>
      <div v-else-if="!metrics.priority_breakdown?.length">
        <EmptyState :icon="Users" message="No priority data" />
      </div>
      <div v-else class="flex gap-3 flex-wrap">
        <div v-for="item in metrics.priority_breakdown" :key="item.tag" class="flex-1 min-w-28 bg-ctrl-panel border border-ctrl-border rounded p-4">
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">{{ item.tag }}</div>
          <div class="tabnum text-2xl font-semibold text-ctrl-text">{{ item.count }}</div>
        </div>
      </div>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { Activity, AlertCircle, Brain, TrendingUp, Users, Workflow, Zap } from 'lucide-vue-next'
import { adminAPI } from '../api/index.js'
import Badge from '../components/ui/Badge.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'

const metrics = ref({
  hours_saved_week: 0, leads_processed_week: 0, automation_rate_pct: 0,
  avg_lead_process_time_min: 0, ai_accuracy_pct: 0, human_review_queue_count: 0,
  ai_calls_today: 0, ai_cost_today_usd: 0, ai_confidence_avg: 0,
  errors_today: 0, warnings_today: 0, total_leads: 0,
  pipeline_funnel: [], priority_breakdown: [], workflows: [],
})
const activityFeed  = ref([])
const systemHealth  = ref([])
const loading       = ref(false)
const error         = ref('')
const revalidating  = ref(false)

const funnelSteps = computed(() => {
  const funnel = metrics.value.pipeline_funnel || []
  const colors = [
    { bgClass: 'bg-ctrl-muted',  dotClass: 'bg-ctrl-muted' },
    { bgClass: 'bg-status-info', dotClass: 'bg-status-info' },
    { bgClass: 'bg-status-warn', dotClass: 'bg-status-warn' },
    { bgClass: 'bg-status-ok',   dotClass: 'bg-status-ok' },
  ]
  return funnel.map((step, i) => ({
    ...step,
    bgClass: colors[i]?.bgClass || 'bg-status-info',
    dotClass: colors[i]?.dotClass || 'bg-status-info',
  }))
})

const kpiStats = computed(() => {
  const m = metrics.value
  return [
    { label: 'Hours Saved',     value: m.leads_processed_week > 0 ? `${m.hours_saved_week}h` : '—',         delta: m.delta_hours_saved,      sub: 'this week' },
    { label: 'Leads Processed', value: m.leads_processed_week,           delta: m.delta_leads_processed,  sub: 'this week' },
    { label: 'Automation',      value: `${m.automation_rate_pct}%`,      delta: m.delta_automation_rate,   status: m.automation_rate_pct >= 90 ? 'ok' : 'warn' },
    { label: 'AI Accuracy',     value: (m.ai_calls_today ?? 0) > 0 ? `${m.ai_accuracy_pct}%` : '—',          delta: m.delta_ai_accuracy,      status: m.ai_accuracy_pct >= 95 ? 'ok' : 'warn' },
    { label: 'Review Queue',    value: m.human_review_queue_count,       status: m.human_review_queue_count > 0 ? 'warn' : undefined, sub: 'SLA 4h' },
  ]
})

const aiCells = computed(() => {
  const m = metrics.value
  return [
    { label: 'Calls',      value: m.ai_calls_today ?? 0,          color: 'text-ctrl-text' },
    { label: 'Cost',       value: `$${(m.ai_cost_today_usd ?? 0).toFixed(2)}`, color: (m.ai_cost_today_usd ?? 0) > 8 ? 'text-status-warn' : 'text-ctrl-text' },
    { label: 'Confidence', value: m.ai_confidence_avg ? `${(m.ai_confidence_avg * 100).toFixed(1)}%` : '—', color: m.ai_confidence_avg >= 0.9 ? 'text-status-ok' : m.ai_confidence_avg >= 0.8 ? 'text-status-warn' : 'text-status-err' },
    { label: 'Queue',      value: m.human_review_queue_count ?? 0, color: (m.human_review_queue_count ?? 0) > 0 ? 'text-status-warn' : 'text-ctrl-text' },
    { label: 'Errors',     value: m.errors_today ?? 0,             color: (m.errors_today ?? 0) > 0 ? 'text-status-err' : 'text-ctrl-text' },
    { label: 'Warnings',   value: m.warnings_today ?? 0,           color: (m.warnings_today ?? 0) > 5 ? 'text-status-warn' : 'text-ctrl-text' },
  ]
})

function healthVariant(rate) {
  if (rate >= 95) return 'success'
  if (rate >= 80) return 'warning'
  return 'error'
}

function healthDotClass(status) {
  const map = {
    healthy: 'bg-status-ok animate-pulse',
    warning: 'bg-status-warn',
    error:   'bg-status-err animate-pulse',
    idle:    'bg-ctrl-border',
  }
  return map[status] || 'bg-ctrl-border'
}

function eventIcon(event) {
  const map = { workflow: Workflow, ai: Brain, event: Zap }
  return map[event.type] || Activity
}

function eventIconBg(event) {
  const map = {
    workflow: 'bg-status-info/10',
    ai:      'bg-purple-500/10',
    event:   'bg-status-warn/10',
  }
  return map[event.type] || 'bg-ctrl-raised'
}

function eventIconColor(event) {
  const map = {
    workflow: 'text-status-info',
    ai:      'text-purple-400',
    event:   'text-status-warn',
  }
  return map[event.type] || 'text-ctrl-muted'
}

function eventBadgeVariant(status) {
  const map = { success: 'success', error: 'error', failed: 'error', warning: 'warning', completed: 'success', pending_review: 'pending' }
  return map[status] || 'default'
}

function relativeTime(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

async function load() {
  loading.value      = true
  revalidating.value = true
  error.value        = ''
  try {
    const [metricsRes, workflowsRes, feedRes, healthRes] = await Promise.all([
      adminAPI.getMetrics(),
      adminAPI.getWorkflowStatus(),
      adminAPI.getActivityFeed().catch(() => ({ data: [] })),
      adminAPI.getSystemHealth().catch(() => ({ data: [] })),
    ])
    metrics.value      = { ...metricsRes.data, workflows: workflowsRes.data }
    activityFeed.value = feedRes.data || []
    systemHealth.value = healthRes.data || []
  } catch {
    error.value = 'Failed to load dashboard.'
  } finally {
    loading.value      = false
    revalidating.value = false
  }
}

useStaleFetch(load)
</script>
