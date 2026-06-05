<template>
  <div class="report-page max-w-4xl mx-auto space-y-8 print:space-y-6">

    <!-- Header -->
    <div class="flex items-center justify-between border-b border-ctrl-border pb-4 print:pb-2">
      <div>
        <h1 class="font-display font-bold text-xl text-ctrl-text">eSteps Operations Report</h1>
        <p class="text-xs text-ctrl-muted mt-1">Generated {{ now }}</p>
      </div>
      <button
        @click="printPage"
        class="px-4 py-2 text-xs font-medium rounded border border-ctrl-border bg-ctrl-panel text-ctrl-text hover:bg-ctrl-raised transition print:hidden"
      >
        Print / Save PDF
      </button>
    </div>

    <div v-if="loading" class="text-center py-20 text-ctrl-muted text-sm">Loading report data...</div>

    <template v-else>

      <!-- Campaign Summary -->
      <section>
        <h2 class="report-heading">Campaign Progress</h2>
        <div class="grid grid-cols-4 gap-4">
          <div v-for="step in metrics.pipeline_funnel" :key="step.label" class="report-card">
            <div class="report-label">{{ step.label }}</div>
            <div class="report-value">{{ step.count }}</div>
            <div class="report-sub">{{ step.pct }}%</div>
          </div>
        </div>
      </section>

      <!-- Key Metrics -->
      <section>
        <h2 class="report-heading">Key Performance Indicators</h2>
        <div class="grid grid-cols-3 gap-4">
          <div class="report-card">
            <div class="report-label">Hours Saved (Week)</div>
            <div class="report-value">{{ metrics.hours_saved_week }}h</div>
          </div>
          <div class="report-card">
            <div class="report-label">Leads Processed (Week)</div>
            <div class="report-value">{{ metrics.leads_processed_week }}</div>
          </div>
          <div class="report-card">
            <div class="report-label">Automation Rate</div>
            <div class="report-value">{{ metrics.automation_rate_pct }}%</div>
          </div>
          <div class="report-card">
            <div class="report-label">AI Accuracy</div>
            <div class="report-value">{{ metrics.ai_accuracy_pct }}%</div>
          </div>
          <div class="report-card">
            <div class="report-label">Avg Process Time</div>
            <div class="report-value">{{ metrics.avg_lead_process_time_min }}m</div>
          </div>
          <div class="report-card">
            <div class="report-label">Review Queue</div>
            <div class="report-value">{{ metrics.human_review_queue_count }}</div>
          </div>
        </div>
      </section>

      <!-- AI Summary -->
      <section>
        <h2 class="report-heading">AI Operations (Today)</h2>
        <div class="grid grid-cols-4 gap-4">
          <div class="report-card">
            <div class="report-label">Calls</div>
            <div class="report-value">{{ metrics.ai_calls_today }}</div>
          </div>
          <div class="report-card">
            <div class="report-label">Cost</div>
            <div class="report-value">${{ (metrics.ai_cost_today_usd ?? 0).toFixed(2) }}</div>
          </div>
          <div class="report-card">
            <div class="report-label">Avg Confidence</div>
            <div class="report-value">{{ metrics.ai_confidence_avg ? `${(metrics.ai_confidence_avg * 100).toFixed(1)}%` : '—' }}</div>
          </div>
          <div class="report-card">
            <div class="report-label">Budget Used</div>
            <div class="report-value">{{ metrics.ai_budget_usd ? `${((metrics.ai_cost_today_usd / metrics.ai_budget_usd) * 100).toFixed(0)}%` : '—' }}</div>
          </div>
        </div>
      </section>

      <!-- Workflow Health -->
      <section>
        <h2 class="report-heading">Workflow Health</h2>
        <table class="w-full text-xs">
          <thead>
            <tr class="border-b border-ctrl-border text-left text-ctrl-muted">
              <th class="py-2 font-medium">Workflow</th>
              <th class="py-2 font-medium text-right">Runs</th>
              <th class="py-2 font-medium text-right">Success</th>
              <th class="py-2 font-medium text-right">Avg Duration</th>
              <th class="py-2 font-medium text-right">Errors Today</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="wf in workflows" :key="wf.workflow_id" class="border-b border-ctrl-divide">
              <td class="py-2 text-ctrl-text font-medium">{{ wf.name }}</td>
              <td class="py-2 text-right tabnum">{{ wf.total_runs }}</td>
              <td class="py-2 text-right tabnum" :class="wf.success_rate_pct >= 90 ? 'text-status-ok' : 'text-status-err'">{{ wf.success_rate_pct }}%</td>
              <td class="py-2 text-right tabnum text-ctrl-muted">{{ wf.avg_duration_seconds }}s</td>
              <td class="py-2 text-right tabnum" :class="wf.failure_count > 0 ? 'text-status-err' : 'text-ctrl-dim'">{{ wf.failure_count }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- Priority Distribution -->
      <section>
        <h2 class="report-heading">Lead Priority Distribution</h2>
        <div class="grid grid-cols-4 gap-4">
          <div v-for="item in metrics.priority_breakdown" :key="item.tag" class="report-card">
            <div class="report-label">{{ item.tag }}</div>
            <div class="report-value">{{ item.count }}</div>
          </div>
        </div>
      </section>

      <!-- System Health -->
      <section v-if="systemHealth.length">
        <h2 class="report-heading">System Status</h2>
        <div class="grid grid-cols-5 gap-3">
          <div v-for="sys in systemHealth" :key="sys.slug" class="report-card text-center">
            <div class="w-3 h-3 rounded-full mx-auto mb-2" :class="dotClass(sys.status)" />
            <div class="report-label">{{ sys.name }}</div>
            <div class="text-2xs text-ctrl-dim mt-0.5">{{ sys.last_run_ago || 'idle' }}</div>
          </div>
        </div>
      </section>

    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { adminAPI } from '../api/index.js'

const metrics      = ref({})
const workflows    = ref([])
const systemHealth = ref([])
const loading      = ref(true)
const now          = new Date().toLocaleString()

function dotClass(status) {
  const map = { healthy: 'bg-status-ok', warning: 'bg-status-warn', error: 'bg-status-err', idle: 'bg-ctrl-border' }
  return map[status] || 'bg-ctrl-border'
}

function printPage() { window.print() }

async function load() {
  loading.value = true
  try {
    const [m, w, h] = await Promise.all([
      adminAPI.getMetrics(),
      adminAPI.getWorkflowStatus(),
      adminAPI.getSystemHealth().catch(() => ({ data: [] })),
    ])
    metrics.value      = m.data
    workflows.value    = w.data
    systemHealth.value = h.data || []
  } finally {
    loading.value = false
  }
}

load()
</script>

<style scoped>
.report-heading {
  @apply font-display font-semibold text-sm text-ctrl-text uppercase tracking-label mb-3 pb-1 border-b border-ctrl-divide;
}
.report-card {
  @apply bg-ctrl-panel border border-ctrl-border rounded p-4;
}
.report-label {
  @apply text-2xs uppercase tracking-label text-ctrl-muted font-display mb-1;
}
.report-value {
  @apply tabnum text-xl font-semibold text-ctrl-text;
}
.report-sub {
  @apply tabnum text-2xs text-ctrl-dim mt-0.5;
}

@media print {
  .report-page {
    color: #111 !important;
    background: white !important;
  }
  .report-card {
    border-color: #ddd !important;
    background: #fafafa !important;
  }
  .report-heading {
    color: #111 !important;
    border-color: #ccc !important;
  }
  .report-value {
    color: #111 !important;
  }
  .report-label, .report-sub {
    color: #666 !important;
  }
}
</style>
