<template>
  <div class="space-y-8 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <!-- What to focus on + AI memo -->
    <SectionContainer title="What to Focus On" subtitle="Recommendations from your GTM targets and live pipeline state">
      <template #action>
        <div class="flex items-center gap-3">
          <span v-if="memo && generatedAt" class="text-2xs text-ctrl-dim tabnum hidden sm:inline">
            Generated {{ memoTimeLabel }}
          </span>
          <button
            @click="genMemo"
            :disabled="memoLoading"
            class="flex items-center gap-2 text-xs border border-status-info text-status-info rounded px-3 py-1.5 hover:bg-status-info-bg disabled:opacity-40 transition-all"
          >
            <Sparkles class="w-3.5 h-3.5" :class="{ 'animate-pulse': memoLoading }" />
            {{ memoLoading ? 'Generating…' : memo ? 'Regenerate strategy memo' : 'Generate strategy memo' }}
          </button>
        </div>
      </template>

      <div v-if="memo || memoError" class="mb-4 rounded border border-ctrl-border bg-ctrl-panel p-4">
        <div v-if="memoError" class="text-xs text-status-warn">{{ memoError }}</div>
        <Markdown v-else :source="memo" />
      </div>

      <div v-if="loading" class="space-y-2">
        <div v-for="i in 3" :key="i" class="h-14 bg-ctrl-raised rounded animate-pulse" />
      </div>
      <div v-else class="space-y-2">
        <div v-for="(r, i) in data.recommendations" :key="i" class="flex items-start gap-3 rounded border px-4 py-3" :class="sevClass(r.severity)">
          <component :is="sevIcon(r.severity)" class="w-4 h-4 flex-shrink-0 mt-0.5" />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-ctrl-text">{{ r.title }}</div>
            <div class="text-xs text-ctrl-muted mt-0.5">{{ r.detail }}</div>
          </div>
          <Badge variant="default" class="flex-shrink-0">{{ r.focus }}</Badge>
        </div>
      </div>
    </SectionContainer>

    <!-- KPIs vs targets -->
    <SectionContainer title="KPIs vs GTM Targets" subtitle="Click a card to drill into the underlying view">
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <button v-for="k in data.kpis" :key="k.label" @click="go(k.link)"
          class="text-left bg-ctrl-panel border rounded p-4 transition-all duration-200 hover:bg-ctrl-raised hover:shadow-float active:scale-[0.99]" :class="borderFor(k.status)">
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">{{ k.label }}</div>
          <span class="tabnum text-2xl font-semibold" :class="textFor(k.status)">{{ k.value }}{{ k.unit }}</span>
          <div class="text-2xs text-ctrl-dim mt-1 tabnum">target {{ k.target }}{{ k.unit }}</div>
        </button>
      </div>
    </SectionContainer>

    <!-- AI Ops Assistant — operator+ only (report §II.1: readonly cannot alter state,
         and the assistant burns AI budget on every call). -->
    <SectionContainer
      v-if="canUseAssistant"
      title="Ask the Assistant"
      subtitle="Natural-language questions over your live pipeline data"
    >
      <AssistantPanel />
    </SectionContainer>

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-8">
      <!-- Outreach trend -->
      <SectionContainer title="Outreach Trend" subtitle="Leads first-contacted per week (last 8 weeks)">
        <div v-if="loading" class="h-32 bg-ctrl-raised rounded animate-pulse" />
        <LineChart v-else-if="data.trend?.length" :data="data.trend" :height="120" :target="100" />
        <EmptyState v-else :icon="TrendingUp" message="No outreach in the trend window" />
      </SectionContainer>

      <!-- Goal progress -->
      <SectionContainer title="Goal Progress" subtitle="Against GTM targets">
        <div v-if="loading" class="space-y-3"><div v-for="i in 3" :key="i" class="h-8 bg-ctrl-raised rounded animate-pulse" /></div>
        <div v-else class="space-y-4">
          <div v-for="(g, key) in data.goals" :key="key">
            <div class="flex items-center justify-between mb-1 text-xs">
              <span class="text-ctrl-text">{{ g.label }}</span>
              <span class="tabnum text-ctrl-muted">{{ g.current }} / {{ g.target }}</span>
            </div>
            <div class="h-1.5 rounded-full bg-ctrl-border overflow-hidden">
              <div class="h-full rounded-full bg-status-info transition-all duration-500" :style="{ width: pctOf(g.current, g.target) + '%' }" />
            </div>
          </div>
        </div>
      </SectionContainer>
    </div>

    <GTMPlanCard />

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-8">
      <SectionContainer title="Outreach Sequence" subtitle="Leads reached at each touch (Day 1 → 21)">
        <div v-if="loading" class="h-40 bg-ctrl-raised rounded animate-pulse" />
        <BarChart v-else :data="sequenceBars" :height="160" :clickable="true" @select="go('/contacts')" />
      </SectionContainer>
      <SectionContainer title="Lead Score Distribution" subtitle="Hot = score ≥ 7 (MQL-eligible)">
        <div v-if="loading" class="h-40 bg-ctrl-raised rounded animate-pulse" />
        <BarChart v-else :data="scoreBars" :height="160" :clickable="true" @select="go('/contacts')" />
      </SectionContainer>
    </div>

    <!-- Action queue -->
    <SectionContainer title="Action Queue" subtitle="What needs attention now">
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <button @click="go('/followups')" class="text-left bg-ctrl-panel border border-status-err rounded p-4 transition-all duration-200 hover:bg-ctrl-raised hover:shadow-float active:scale-[0.99]">
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">Overdue Follow-ups</div>
          <div class="tabnum text-2xl font-semibold text-status-err">{{ data.followups?.overdue ?? 0 }}</div>
          <div class="text-2xs text-ctrl-dim mt-1">next_send_date passed</div>
        </button>
        <button @click="go('/followups')" class="text-left bg-ctrl-panel border border-ctrl-border rounded p-4 transition-all duration-200 hover:bg-ctrl-raised hover:shadow-float active:scale-[0.99]">
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">Upcoming Touches</div>
          <div class="tabnum text-2xl font-semibold text-ctrl-text">{{ data.followups?.upcoming ?? 0 }}</div>
          <div class="text-2xs text-ctrl-dim mt-1">scheduled ahead</div>
        </button>
        <button @click="go('/pipeline')" class="text-left bg-ctrl-panel border border-status-warn rounded p-4 transition-all duration-200 hover:bg-ctrl-raised hover:shadow-float active:scale-[0.99]">
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">Hot Leads Uncontacted</div>
          <div class="tabnum text-2xl font-semibold text-status-warn">{{ data.hot_uncontacted ?? 0 }}</div>
          <div class="text-2xs text-ctrl-dim mt-1">score ≥ 7, never emailed</div>
        </button>
        <button @click="go('/contacts')" class="text-left bg-ctrl-panel border border-ctrl-border rounded p-4 transition-all duration-200 hover:bg-ctrl-raised hover:shadow-float active:scale-[0.99]">
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted mb-2">Hot Contacts</div>
          <div class="tabnum text-2xl font-semibold text-status-ok">{{ data.hot_leads ?? 0 }}</div>
          <div class="text-2xs text-ctrl-dim mt-1">score ≥ 7 total</div>
        </button>
      </div>
    </SectionContainer>

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-8">
      <!-- Week + Month comparison -->
      <SectionContainer title="Trend vs Previous Period" subtitle="Week-over-week and month-over-month">
        <div v-if="loading" class="space-y-2"><div v-for="i in 4" :key="i" class="h-10 bg-ctrl-raised rounded animate-pulse" /></div>
        <div v-else class="space-y-4">
          <div>
            <div class="font-display text-2xs uppercase tracking-label text-ctrl-dim mb-1">This week vs last</div>
            <div class="divide-y divide-ctrl-divide">
              <div v-for="m in data.comparison?.metrics" :key="m.label" class="flex items-center justify-between py-2">
                <span class="text-sm text-ctrl-text">{{ m.label }}</span>
                <div class="flex items-center gap-3">
                  <span class="tabnum text-sm text-ctrl-muted">{{ m.previous }} → {{ m.current }}</span>
                  <Badge :variant="m.delta > 0 ? 'success' : m.delta < 0 ? 'error' : 'default'">{{ m.delta > 0 ? '+' : '' }}{{ m.delta }}</Badge>
                </div>
              </div>
            </div>
          </div>
          <div>
            <div class="font-display text-2xs uppercase tracking-label text-ctrl-dim mb-1">This month vs last</div>
            <div class="divide-y divide-ctrl-divide">
              <div v-for="m in data.monthly" :key="m.label" class="flex items-center justify-between py-2">
                <span class="text-sm text-ctrl-text">{{ m.label }}</span>
                <div class="flex items-center gap-3">
                  <span class="tabnum text-sm text-ctrl-muted">{{ m.previous }} → {{ m.current }}</span>
                  <Badge :variant="m.delta > 0 ? 'success' : m.delta < 0 ? 'error' : 'default'">{{ m.delta > 0 ? '+' : '' }}{{ m.delta }}</Badge>
                </div>
              </div>
            </div>
          </div>
        </div>
      </SectionContainer>

      <!-- Segment activation -->
      <SectionContainer title="Segment Activation" subtitle="Outreach coverage by research area">
        <div v-if="loading" class="space-y-2"><div v-for="i in 6" :key="i" class="h-7 bg-ctrl-raised rounded animate-pulse" /></div>
        <div v-else class="space-y-2.5">
          <div v-for="s in data.segments" :key="s.area">
            <div class="flex items-center justify-between mb-1 text-xs">
              <span class="text-ctrl-text truncate">{{ s.area }}</span>
              <span class="tabnum text-ctrl-muted">{{ s.contacted }}/{{ s.total }} <span class="text-ctrl-dim">({{ s.activation_pct }}%)</span></span>
            </div>
            <div class="h-1 rounded-full bg-ctrl-border overflow-hidden">
              <div class="h-full rounded-full transition-all duration-500" :class="s.activation_pct >= 60 ? 'bg-status-ok' : s.activation_pct >= 30 ? 'bg-status-warn' : 'bg-status-err'" :style="{ width: `${s.activation_pct}%` }" />
            </div>
          </div>
        </div>
      </SectionContainer>
    </div>

    <!-- Sequence heatmap -->
    <SectionContainer title="Sequence Reach by Research Area" subtitle="How deep each segment gets in the 5-touch sequence — spot where outreach stalls">
      <div v-if="loading" class="h-48 bg-ctrl-raised rounded animate-pulse" />
      <HeatMap v-else :steps="heatmap.steps" :rows="heatmap.areas" />
    </SectionContainer>

    <!-- Conference & geo timeline -->
    <SectionContainer title="Conference & Geo Timeline" subtitle="GTM go-to-market calendar — plan pre-event outreach 4-6 weeks ahead">
      <div class="space-y-4">
        <div>
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-dim mb-2">Conferences (highest-converting channel)</div>
          <div class="flex gap-3 flex-wrap">
            <div v-for="c in conferences" :key="c.name" class="flex-1 min-w-36 bg-ctrl-panel border border-ctrl-border rounded p-3">
              <div class="tabnum text-2xs text-status-info">{{ c.month }}</div>
              <div class="text-sm text-ctrl-text">{{ c.name }}</div>
              <div class="text-2xs text-ctrl-dim mt-0.5">{{ c.product }}</div>
            </div>
          </div>
        </div>
        <div>
          <div class="font-display text-2xs uppercase tracking-label text-ctrl-dim mb-2">Geo expansion</div>
          <div class="flex gap-3 flex-wrap">
            <div v-for="g in geoPhases" :key="g.phase" class="flex-1 min-w-44 bg-ctrl-panel border border-ctrl-border rounded p-3">
              <div class="text-sm text-ctrl-text">{{ g.phase }}</div>
              <div class="text-2xs text-ctrl-muted mt-0.5">{{ g.regions }}</div>
            </div>
          </div>
        </div>
      </div>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, AlertTriangle, Info, Sparkles, TrendingUp } from 'lucide-vue-next'
import { adminAPI } from '../api/index.js'
import Badge from '../components/ui/Badge.vue'
import BarChart from '../components/ui/BarChart.vue'
import LineChart from '../components/ui/LineChart.vue'
import EmptyState from '../components/ui/EmptyState.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import HeatMap from '../components/ui/HeatMap.vue'
import AssistantPanel from '../components/AssistantPanel.vue'
import Markdown from '../components/ui/Markdown.vue'
import GTMPlanCard from '../components/GTMPlanCard.vue'
import { useDailyMemo } from '../composables/useDailyMemo.js'
import { useAuthStore } from '../stores/auth.js'

const router    = useRouter()
const auth      = useAuthStore()
const canUseAssistant = computed(() => auth.role === 'admin' || auth.role === 'operator')
const data      = ref({ kpis: [], recommendations: [], sequence_funnel: [], score_distribution: [], segments: [], comparison: { metrics: [] }, monthly: [], trend: [], goals: {}, followups: {} })
const heatmap   = ref({ steps: [], areas: [] })
const loading   = ref(false)
const error     = ref('')

const conferences = [
  { name: 'APTA CSM', month: 'Feb', product: 'Health' },
  { name: 'ACSM', month: 'May', product: 'Health · Mitus' },
  { name: 'RehabWeek / ICORR', month: 'Jun', product: 'Health' },
  { name: 'ISB Congress', month: 'Jul', product: 'Health · Mitus' },
  { name: 'MIT Sloan Sports', month: 'Oct', product: 'Mitus' },
  { name: 'HLTH', month: 'Oct–Nov', product: 'All' },
]
const geoPhases = [
  { phase: 'Phase 1 (→ Q2)', regions: 'US · IT · DE · UK · FR' },
  { phase: 'Phase 2 (Q3)', regions: 'UAE · KSA · AU · CA' },
  { phase: 'Phase 3 (Q4)', regions: 'JP · KR · BR' },
]
const { memo, memoError, memoLoading, generatedAt, genMemo } = useDailyMemo()
const memoTimeLabel = computed(() => {
  if (!generatedAt.value) return ''
  const d = new Date(generatedAt.value)
  if (Number.isNaN(d.getTime())) return ''
  const sameDay = d.toDateString() === new Date().toDateString()
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return sameDay ? `at ${time}` : d.toLocaleDateString()
})

const sequenceBars = computed(() => (data.value.sequence_funnel || []).map((s, i) => ({
  label: s.step.replace('Email ', 'E'), value: s.count,
  color: i >= 3 ? 'oklch(70% 0.15 75)' : 'oklch(62% 0.12 250)',
})))
const scoreBars = computed(() => (data.value.score_distribution || []).map((s) => ({
  label: String(s.score), value: s.count,
  color: s.score >= 9 ? 'oklch(70% 0.15 150)' : s.score >= 7 ? 'oklch(62% 0.12 250)' : s.score >= 5 ? 'oklch(55% 0.02 250)' : 'oklch(58% 0.16 25)',
})))

function go(path) { if (path) router.push(path) }
function pctOf(c, t) { return t ? Math.min(100, Math.round((c / t) * 100)) : 0 }
function borderFor(s) { return { green: 'border-status-ok', amber: 'border-status-warn', red: 'border-status-err' }[s] || 'border-ctrl-border' }
function textFor(s) { return { green: 'text-status-ok', amber: 'text-status-warn', red: 'text-status-err' }[s] || 'text-ctrl-text' }
function sevClass(s) { return { high: 'bg-status-err-bg border-status-err', medium: 'bg-status-warn-bg border-status-warn', info: 'bg-ctrl-panel border-ctrl-border' }[s] || 'bg-ctrl-panel border-ctrl-border' }
function sevIcon(s) { return { high: AlertCircle, medium: AlertTriangle, info: Info }[s] || Info }

async function load() {
  loading.value = true
  error.value   = ''
  try {
    const [res, hm] = await Promise.all([adminAPI.getInsights(), adminAPI.getHeatmap()])
    data.value = res.data
    heatmap.value = hm.data
  } catch {
    error.value = 'Failed to load insights.'
  } finally {
    loading.value = false
  }
}

useStaleFetch(load)
</script>
