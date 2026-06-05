<template>
  <div class="space-y-8 max-w-none">

    <div v-if="error" class="flex items-center gap-3 bg-status-err-bg border border-status-err rounded px-4 py-3 text-status-err text-xs">
      <AlertCircle class="w-4 h-4 flex-shrink-0" />
      {{ error }}
    </div>

    <StatRow :stats="[
      { label: 'Total Workflows', value: workflows.length,                          sub: 'in n8n' },
      { label: 'Active',          value: workflows.filter(w => w.active).length,   status: 'ok' },
      { label: 'Inactive',        value: workflows.filter(w => !w.active).length },
    ]" />

    <SectionContainer title="n8n Workflows" subtitle="Live workflows from n8n.estepshealth.tech">
      <template #action>
        <input
          v-model="search"
          type="text"
          placeholder="Search workflows..."
          class="bg-ctrl-panel border border-ctrl-border rounded text-sm text-ctrl-text px-3 py-1.5
                 w-52 focus:outline-none focus:border-status-info transition-colors placeholder-ctrl-dim"
        />
      </template>

      <Table
        :columns="wfColumns"
        :rows="filteredWorkflows"
        :loading="loading"
        :skeleton-rows="10"
        empty-message="No workflows found"
        :empty-icon="Workflow"
      >
        <template #cell-name="{ value }">
          <span class="font-medium text-ctrl-text">{{ value }}</span>
        </template>
        <template #cell-active="{ value }">
          <Badge :variant="value ? 'success' : 'default'">{{ value ? 'active' : 'inactive' }}</Badge>
        </template>
        <template #cell-updatedAt="{ value }">
          <span class="tabnum text-ctrl-muted text-xs">{{ formatDate(value) }}</span>
        </template>
        <template #cell-id="{ value }">
          <span class="tabnum text-ctrl-dim text-xs">{{ value }}</span>
        </template>
        <template #cell-actions="{ row }">
          <div v-if="isAdmin" class="flex items-center gap-1.5">
            <button
              @click="trigger(row.id, row.name)"
              :disabled="acting === row.id"
              class="px-2.5 py-1 text-2xs bg-status-info-bg text-status-info border border-status-info rounded
                     hover:opacity-80 active:scale-[0.97] disabled:opacity-40 transition-all tabnum"
            >Trigger</button>
            <button
              @click="toggleActive(row)"
              :disabled="acting === row.id"
              class="px-2.5 py-1 text-2xs rounded hover:opacity-80 active:scale-[0.97] disabled:opacity-40 transition-all tabnum"
              :class="row.active
                ? 'bg-status-warn-bg text-status-warn border border-status-warn'
                : 'bg-status-ok-bg text-status-ok border border-status-ok'"
            >{{ row.active ? 'Deactivate' : 'Activate' }}</button>
          </div>
        </template>
      </Table>
    </SectionContainer>

  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useStaleFetch } from '../composables/useStaleFetch'
import { AlertCircle, Workflow } from 'lucide-vue-next'
import { n8nAPI } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import Badge from '../components/ui/Badge.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import StatRow from '../components/ui/StatRow.vue'
import Table from '../components/ui/Table.vue'

const auth      = useAuthStore()
const isAdmin   = computed(() => auth.role === 'admin' || auth.role === 'operator')

const workflows = ref([])
const loading   = ref(false)
const error     = ref('')
const search    = ref('')
const acting    = ref(null)

const wfColumns = [
  { key: 'name',      label: 'Workflow' },
  { key: 'active',    label: 'Status' },
  { key: 'id',        label: 'ID' },
  { key: 'updatedAt', label: 'Updated' },
  { key: 'actions',   label: '' },
]

const filteredWorkflows = computed(() => {
  if (!search.value) return workflows.value
  const q = search.value.toLowerCase()
  return workflows.value.filter(
    (w) => w.name?.toLowerCase().includes(q) || w.id?.toString().toLowerCase().includes(q)
  )
})

function formatDate(value) {
  if (!value) return '—'
  return new Date(value).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function load() {
  loading.value = true
  error.value   = ''
  try {
    const { data } = await n8nAPI.listWorkflows()
    const raw = Array.isArray(data) ? data : (data?.data ?? [])
    workflows.value = raw.sort((a, b) => (a.name ?? '').localeCompare(b.name ?? ''))
  } catch (err) {
    // Surface the backend detail so a timeout doesn't masquerade as a missing API key.
    const detail = err?.response?.data?.detail
    if (typeof detail === 'string') {
      error.value = `Failed to load n8n workflows — ${detail}`
    } else if (err?.response?.status === 401 || err?.response?.status === 403) {
      error.value = 'Failed to load n8n workflows — auth rejected. Verify N8N_API_KEY in backend/.env.'
    } else {
      error.value = `Failed to load n8n workflows (status ${err?.response?.status ?? 'n/a'}). Check N8N_BASE_URL and that the n8n host is reachable.`
    }
  } finally {
    loading.value = false
  }
}

async function trigger(id, name) {
  if (!confirm(`Trigger workflow "${name}"?`)) return
  acting.value = id
  error.value  = ''
  try {
    await n8nAPI.executeWorkflow(id)
  } catch {
    error.value = `Failed to trigger workflow ${id}.`
  } finally {
    acting.value = null
  }
}

async function toggleActive(wf) {
  acting.value = wf.id
  error.value  = ''
  try {
    if (wf.active) {
      await n8nAPI.deactivateWorkflow(wf.id)
      wf.active = false
    } else {
      await n8nAPI.activateWorkflow(wf.id)
      wf.active = true
    }
  } catch {
    error.value = `Failed to toggle workflow ${wf.id}.`
  } finally {
    acting.value = null
  }
}

useStaleFetch(load)
</script>
