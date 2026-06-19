<!--
  GTMTaskRow — reusable row for the plan card + tasks view.
  Props:
    initiative: InitiativeRow (see backend schema)
    canAct: boolean (operator+ → show Apply/Reject)
  Emits:
    apply, reject (with initiative.id)
-->
<template>
  <tr class="border-b border-ctrl-border hover:bg-ctrl-panel/40 transition-colors">
    <td class="px-3 py-2 text-xs tabnum text-ctrl-muted">{{ initiative.period }}</td>
    <td class="px-3 py-2 text-xs text-ctrl-text">
      {{ initiative.objective_label }}
      <div v-if="initiative.rationale" class="text-2xs text-ctrl-dim mt-0.5 truncate" :title="initiative.rationale">
        {{ initiative.rationale }}
      </div>
    </td>
    <td class="px-3 py-2 text-xs tabnum text-ctrl-text">
      <span v-if="initiative.target_value != null">{{ initiative.target_value }}</span>
      <span v-else class="text-ctrl-dim">—</span>
      <span v-if="initiative.target_unit" class="ml-1 text-ctrl-muted">{{ initiative.target_unit }}</span>
    </td>
    <td class="px-3 py-2 text-xs">
      <span class="text-ctrl-text">{{ initiative.assignee_display || '—' }}</span>
      <span v-if="!initiative.assignee_user_id && initiative.assignee_label"
            class="ml-1 text-2xs text-status-warn" title="No matching user — admin can reassign">?</span>
    </td>
    <td class="px-3 py-2 text-xs tabnum text-ctrl-muted">{{ fmtDue(initiative.due_at) }}</td>
    <td class="px-3 py-2 text-xs">
      <Badge :variant="statusVariant(initiative.status)">{{ initiative.status }}</Badge>
    </td>
    <td class="px-3 py-2 text-xs">
      <div v-if="canAct && initiative.status === 'suggested'" class="flex gap-1">
        <button @click="$emit('apply', initiative.id)"
                class="px-2 py-1 bg-status-ok-bg border border-status-ok rounded text-2xs text-status-ok hover:bg-status-ok hover:text-ctrl-text transition-all">
          Apply
        </button>
        <button @click="$emit('reject', initiative.id)"
                class="px-2 py-1 bg-status-err-bg border border-status-err rounded text-2xs text-status-err hover:bg-status-err hover:text-ctrl-text transition-all">
          ×
        </button>
      </div>
    </td>
  </tr>
</template>

<script setup>
import Badge from './ui/Badge.vue'

defineProps({
  initiative: { type: Object, required: true },
  canAct:     { type: Boolean, default: false },
})

defineEmits(['apply', 'reject'])

function fmtDue(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const days = Math.round((d - Date.now()) / 86400000)
  if (days < 0) return `${-days}d overdue`
  if (days === 0) return 'today'
  return `in ${days}d`
}

function statusVariant(s) {
  return {
    suggested: 'info',
    applied:   'ok',
    rejected:  'err',
    superseded:'neutral',
  }[s] || 'neutral'
}
</script>
