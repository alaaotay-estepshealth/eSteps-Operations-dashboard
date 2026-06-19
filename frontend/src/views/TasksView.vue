<template>
  <div class="space-y-6 max-w-none">
    <div v-if="!isAdmin" class="bg-ctrl-panel border border-ctrl-border rounded px-4 py-2.5 text-xs text-ctrl-muted">
      Showing only tasks assigned to you.
    </div>

    <StatRow :stats="stats" />

    <SectionContainer title="Filters">
      <div class="flex flex-wrap items-center gap-2">
        <select v-model="filters.period" @change="load"
                class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5">
          <option value="">All periods</option>
          <option value="30d">30d</option>
          <option value="60d">60d</option>
          <option value="90d">90d</option>
        </select>
        <select v-model="filters.status" @change="load"
                class="bg-ctrl-panel border border-ctrl-border rounded text-xs text-ctrl-text px-2 py-1.5">
          <option value="suggested,applied">Open</option>
          <option value="suggested">Suggested only</option>
          <option value="applied">Applied only</option>
          <option value="rejected">Rejected</option>
        </select>
      </div>
    </SectionContainer>

    <SectionContainer title="Your tasks" :subtitle="`${tasks.length} item${tasks.length === 1 ? '' : 's'}`">
      <div v-if="tasks.length === 0" class="text-center py-12">
        <ClipboardList class="w-10 h-10 text-ctrl-dim mx-auto mb-2" />
        <div class="text-sm text-ctrl-muted">
          {{ isAdmin ? 'No GTM tasks yet.' : 'No tasks assigned to you yet. The latest GTM plan didn\'t route anything your way.' }}
        </div>
      </div>
      <table v-else class="w-full">
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
          <GTMTaskRow v-for="row in tasks" :key="row.id"
                      :initiative="row" :can-act="canAct"
                      @apply="onApply" @reject="onReject" />
        </tbody>
      </table>
    </SectionContainer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ClipboardList } from 'lucide-vue-next'
import { gtmTasksAPI, gtmPlanAPI } from '../api'
import { useAuthStore } from '../stores/auth.js'
import StatRow from '../components/ui/StatRow.vue'
import SectionContainer from '../components/ui/SectionContainer.vue'
import GTMTaskRow from '../components/GTMTaskRow.vue'

const auth = useAuthStore()
const isAdmin = computed(() => auth.role === 'admin')
const canAct  = computed(() => ['admin', 'operator'].includes(auth.role))

const filters = reactive({ period: '', status: 'suggested,applied' })
const tasks = ref([])

const stats = computed(() => {
  const now = Date.now()
  const overdue = tasks.value.filter(t => t.due_at && new Date(t.due_at).getTime() < now).length
  const week = tasks.value.filter(t => t.due_at && new Date(t.due_at).getTime() - now < 7 * 86400000).length
  const month = tasks.value.filter(t => t.due_at && new Date(t.due_at).getTime() - now < 30 * 86400000).length
  return [
    { label: 'Overdue',        value: overdue, status: overdue > 0 ? 'err' : undefined },
    { label: 'Due this week',  value: week,    status: week > 0 ? 'warn' : undefined },
    { label: 'Due this month', value: month },
    { label: 'Total open',     value: tasks.value.length, status: 'info' },
  ]
})

async function load() {
  const params = {}
  if (filters.period) params.period = filters.period
  if (filters.status) params.status = filters.status
  const r = await gtmTasksAPI.list(params)
  tasks.value = r.data
}

async function onApply(id) {
  const row = tasks.value.find(r => r.id === id)
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
  const row = tasks.value.find(r => r.id === id)
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
