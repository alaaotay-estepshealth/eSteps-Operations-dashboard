<!--
  GTMPlanCard — embedded in Insights.vue after Goal Progress.
  Shows the latest claude-opus-4-7 strategy memo + 30/60/90 KPI table + risk flags.
  operator+ can Regenerate; operator+ can Apply/Reject per row.
-->
<template>
  <SectionContainer title="GTM Plan" :subtitle="subtitle">
    <template #action>
      <button v-if="canRegenerate" @click="regenerate" :disabled="regenerating"
              class="px-2.5 py-1 text-xs border border-ctrl-border rounded text-ctrl-muted hover:text-ctrl-text disabled:opacity-50 transition-all">
        <RefreshCw class="w-3 h-3 inline mr-1" :class="regenerating ? 'animate-spin' : ''" />
        {{ regenerating ? 'Generating…' : 'Regenerate' }}
      </button>
    </template>

    <div v-if="plan.status === 'none'" class="text-center py-10">
      <Sparkles class="w-8 h-8 text-ctrl-dim mx-auto mb-2" />
      <div class="text-sm text-ctrl-muted">No GTM plan yet.</div>
      <div v-if="canRegenerate" class="text-xs text-ctrl-dim mt-1">Click Regenerate to produce one from GTM-2026-OS.</div>
    </div>

    <div v-else-if="plan.status === 'rejected'" class="bg-status-err-bg border border-status-err rounded p-3">
      <div class="text-xs text-status-err font-medium">Last generation failed</div>
      <div class="text-2xs text-ctrl-dim mt-1">{{ plan.error_message || 'See server logs' }}</div>
    </div>

    <div v-else-if="plan.status === 'completed'" class="space-y-5">
      <Markdown :source="plan.output.executive_summary" />

      <div>
        <h4 class="text-2xs font-display font-medium uppercase tracking-label text-ctrl-dim mb-2">30 / 60 / 90 day targets</h4>
        <table class="w-full">
          <thead>
            <tr class="border-b border-ctrl-border">
              <th class="px-3 py-2 text-left text-2xs uppercase tracking-label text-ctrl-dim">Period</th>
              <th class="px-3 py-2 text-left text-2xs uppercase tracking-label text-ctrl-dim">Objective</th>
              <th class="px-3 py-2 text-left text-2xs uppercase tracking-label text-ctrl-dim">Target</th>
              <th class="px-3 py-2 text-left text-2xs uppercase tracking-label text-ctrl-dim">Assignee</th>
              <th class="px-3 py-2 text-left text-2xs uppercase tracking-label text-ctrl-dim">Due</th>
              <th class="px-3 py-2 text-left text-2xs uppercase tracking-label text-ctrl-dim">Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <GTMTaskRow v-for="row in initiatives" :key="row.id"
                        :initiative="row" :can-act="canRegenerate"
                        @apply="onApply" @reject="onReject" />
          </tbody>
        </table>
      </div>

      <div v-if="plan.output.risk_flags?.length">
        <h4 class="text-2xs font-display font-medium uppercase tracking-label text-ctrl-dim mb-2">Risk flags</h4>
        <ul class="space-y-1">
          <li v-for="(r, i) in plan.output.risk_flags" :key="i" class="text-xs text-ctrl-text flex items-start gap-2">
            <Badge :variant="r.severity === 'high' ? 'err' : r.severity === 'medium' ? 'warn' : 'info'">{{ r.severity }}</Badge>
            <span>{{ r.label }}<span v-if="r.source" class="text-ctrl-dim ml-1">({{ r.source }})</span></span>
          </li>
        </ul>
      </div>

      <details class="text-xs">
        <summary class="text-ctrl-muted cursor-pointer hover:text-ctrl-text">View sources ({{ plan.output.source_files?.length || 0 }})</summary>
        <ul class="mt-2 space-y-0.5">
          <li v-for="(f, i) in plan.output.source_files" :key="i" class="text-ctrl-dim tabnum">
            {{ f.path }} <span class="text-2xs">({{ f.tokens }} tok)</span>
          </li>
        </ul>
      </details>
    </div>
  </SectionContainer>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { RefreshCw, Sparkles } from 'lucide-vue-next'
import { gtmPlanAPI } from '../api'
import { useAuthStore } from '../stores/auth.js'
import SectionContainer from './ui/SectionContainer.vue'
import Markdown from './ui/Markdown.vue'
import Badge from './ui/Badge.vue'
import GTMTaskRow from './GTMTaskRow.vue'

const auth = useAuthStore()
const canRegenerate = computed(() => ['admin', 'operator'].includes(auth.role))

const plan = ref({ status: 'none', output: null })
const initiatives = ref([])
const regenerating = ref(false)

const subtitle = computed(() => {
  if (!plan.value.generated_at) return 'Not generated yet'
  const ageHours = Math.round((plan.value.age_seconds || 0) / 3600)
  if (ageHours < 1) return 'Generated just now'
  if (ageHours < 24) return `Generated ${ageHours}h ago`
  const days = Math.round(ageHours / 24)
  return `Generated ${days}d ago${days > 35 ? ' — stale, regenerate?' : ''}`
})

async function load() {
  const [pRes, iRes] = await Promise.all([
    gtmPlanAPI.getPlan(),
    gtmPlanAPI.getInitiatives(),
  ])
  plan.value = pRes.data
  initiatives.value = iRes.data
}

async function regenerate() {
  if (regenerating.value) return
  regenerating.value = true
  try {
    await gtmPlanAPI.generate()
    for (let i = 0; i < 12; i++) {
      await new Promise(r => setTimeout(r, 5000))
      const prevTs = plan.value.generated_at
      await load()
      if (plan.value.generated_at && plan.value.generated_at !== prevTs) break
    }
  } finally {
    regenerating.value = false
  }
}

async function onApply(id) {
  const row = initiatives.value.find(r => r.id === id)
  if (!row) return
  row.status = 'applied'
  try {
    const r = await gtmPlanAPI.applyInitiative(id)
    Object.assign(row, r.data)
  } catch (e) {
    row.status = 'suggested'
  }
}

async function onReject(id) {
  const row = initiatives.value.find(r => r.id === id)
  if (!row) return
  row.status = 'rejected'
  try {
    const r = await gtmPlanAPI.rejectInitiative(id)
    Object.assign(row, r.data)
  } catch (e) {
    row.status = 'suggested'
  }
}

onMounted(load)
</script>
