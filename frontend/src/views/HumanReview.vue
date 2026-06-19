<template>
  <div class="space-y-8 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <StatRow :stats="[
      { label: 'Pending Review', value: queue.length,  status: queue.length > 0 ? 'warn' : undefined, sub: 'SLA 4h' },
      { label: 'SLA Breaches',   value: slaBreaches,   status: slaBreaches > 0 ? 'err' : undefined },
      { label: 'Resolved',       value: resolved,       status: resolved > 0 ? 'ok' : undefined, sub: 'this session' },
    ]" />

    <SectionContainer title="Review Queue" subtitle="AI decisions requiring human verification before actioning">
      <Table
        dense
        :columns="queueColumns"
        :rows="queue"
        :loading="loading"
        :skeleton-rows="6"
        empty-message="Queue is empty — all AI decisions verified"
        :empty-icon="CheckCircle"
      >
        <template #cell-created_at="{ value }">
          <span class="tabnum text-ctrl-muted text-2xs whitespace-nowrap">{{ formatDate(value) }}</span>
        </template>
        <template #cell-request_type="{ value }">
          <span class="font-medium text-ctrl-text capitalize text-xs whitespace-nowrap">{{ value.replace(/_/g, ' ') }}</span>
        </template>
        <template #cell-input_preview="{ value }">
          <span class="text-xs text-ctrl-muted truncate block max-w-[15rem]" :title="value">{{ value ?? '—' }}</span>
        </template>
        <template #cell-confidence_score="{ value }">
          <span class="tabnum font-medium" :class="confColor(value)">
            {{ value != null ? `${(value * 100).toFixed(1)}%` : '—' }}
          </span>
        </template>
        <template #cell-age_hours="{ row }">
          <div class="flex items-center gap-2">
            <span class="tabnum text-xs" :class="row.sla_breach ? 'text-status-err' : 'text-ctrl-muted'">
              {{ row.age_hours.toFixed(1) }}h
            </span>
            <Badge v-if="row.sla_breach" variant="error">SLA</Badge>
          </div>
        </template>
        <template #cell-actions="{ row }">
          <div v-if="canReview" class="space-y-1.5">
            <div class="flex items-center gap-1 whitespace-nowrap justify-end">
              <button
                @click="resolve(row.id, 'approve')"
                :disabled="resolving === row.id"
                class="px-2 py-0.5 text-2xs bg-status-ok-bg text-status-ok border border-status-ok rounded
                       hover:opacity-80 active:scale-[0.97] disabled:opacity-40 transition-all tabnum"
              >Approve</button>
              <button
                @click="resolve(row.id, 'reject')"
                :disabled="resolving === row.id"
                class="px-2 py-0.5 text-2xs bg-status-err-bg text-status-err border border-status-err rounded
                       hover:opacity-80 active:scale-[0.97] disabled:opacity-40 transition-all tabnum"
              >Reject</button>
              <button
                @click="resolve(row.id, 'override')"
                :disabled="resolving === row.id"
                class="px-2 py-0.5 text-2xs bg-status-warn-bg text-status-warn border border-status-warn rounded
                       hover:opacity-80 active:scale-[0.97] disabled:opacity-40 transition-all tabnum"
              >Override</button>
            </div>
            <div v-if="notesOpen === row.id" class="flex gap-1.5">
              <input
                v-model="reviewerNotes"
                type="text"
                placeholder="Notes (optional)..."
                class="flex-1 bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1 focus:outline-none"
                @keyup.enter="confirmResolve(row.id)"
              />
              <button @click="confirmResolve(row.id)" class="px-2 py-1 text-2xs bg-ctrl-raised text-ctrl-text rounded hover:opacity-80">Go</button>
              <button @click="cancelResolve()" class="px-2 py-1 text-2xs text-ctrl-dim hover:text-ctrl-muted">✕</button>
            </div>
          </div>
          <span v-else class="text-2xs text-ctrl-dim">operator+ only</span>
        </template>
      </Table>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, CheckCircle } from 'lucide-vue-next'
import { adminAPI } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import Badge from '../components/ui/Badge.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'

const auth      = useAuthStore()
const canReview = computed(() => auth.isOperator)
const queue    = ref([])
const loading  = ref(false)
const error    = ref('')
const resolving = ref(null)
const resolved  = ref(0)
const notesOpen     = ref(null)
const pendingAction = ref('')
const reviewerNotes = ref('')

const queueColumns = [
  { key: 'created_at',       label: 'Time' },
  { key: 'request_type',     label: 'Type' },
  { key: 'input_preview',    label: 'Input Preview' },
  { key: 'confidence_score', label: 'Confidence', align: 'right' },
  { key: 'age_hours',        label: 'Age' },
  { key: 'actions',          label: '', align: 'right' },
]

const slaBreaches = computed(() => queue.value.filter((r) => r.sla_breach).length)

function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString(undefined, {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

function confColor(value) {
  if (value == null) return 'text-ctrl-muted'
  if (value >= 0.9) return 'text-status-ok'
  if (value >= 0.8) return 'text-status-warn'
  return 'text-status-err'
}

async function load() {
  loading.value = true
  error.value   = ''
  try {
    const { data } = await adminAPI.getReviewQueue()
    queue.value = Array.isArray(data) ? data : []
  } catch {
    error.value = 'Failed to load review queue.'
  } finally {
    loading.value = false
  }
}

async function resolve(id, action) {
  notesOpen.value = id
  pendingAction.value = action
  reviewerNotes.value = ''
}

function cancelResolve() {
  notesOpen.value = null
  pendingAction.value = ''
  reviewerNotes.value = ''
}

async function confirmResolve(id) {
  resolving.value = id
  error.value     = ''
  try {
    const payload = { action: pendingAction.value }
    if (reviewerNotes.value.trim()) payload.reviewer_notes = reviewerNotes.value.trim()
    await adminAPI.resolveReview(id, payload)
    queue.value = queue.value.filter((r) => r.id !== id)
    resolved.value++
    cancelResolve()
  } catch {
    error.value = `Failed to ${pendingAction.value} item.`
  } finally {
    resolving.value = null
  }
}

useStaleFetch(load)
</script>
