<template>
  <div class="group flex items-center gap-2 py-1.5 border-b border-ctrl-border/40 last:border-0">
    <input
      type="checkbox"
      :checked="task.done"
      class="w-4 h-4 accent-status-ok cursor-pointer"
      @change="$emit('toggle', !task.done)"
    />
    <div class="flex-1 min-w-0">
      <input
        v-if="editing"
        v-model="draft"
        @keyup.enter="commit"
        @blur="commit"
        class="w-full bg-transparent border-b border-ctrl-border text-sm text-ctrl-text focus:outline-none focus:border-status-info"
      />
      <span
        v-else
        :class="task.done ? 'line-through text-ctrl-dim' : 'text-ctrl-text'"
        class="text-sm cursor-text"
        @click="startEdit"
      >{{ task.title }}</span>
    </div>
    <span
      v-if="task.due_at"
      :class="task.overdue_by_hours ? 'text-status-err' : 'text-ctrl-muted'"
      class="text-2xs tabnum"
    >
      {{ formatDue(task) }}
    </span>
    <button
      class="opacity-0 group-hover:opacity-100 text-ctrl-dim hover:text-status-err transition-opacity text-2xs"
      @click="$emit('delete')"
      title="Delete task"
    >×</button>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  task: { type: Object, required: true },
})
const emit = defineEmits(['toggle', 'rename', 'delete'])

const editing = ref(false)
const draft = ref(props.task.title)

function startEdit() {
  draft.value = props.task.title
  editing.value = true
}

function commit() {
  if (!editing.value) return
  editing.value = false
  const next = (draft.value || '').trim()
  if (next && next !== props.task.title) emit('rename', next)
}

function formatDue(t) {
  if (!t.due_at) return ''
  if (t.overdue_by_hours) return `${Math.round(t.overdue_by_hours)}h overdue`
  const diffH = (new Date(t.due_at).getTime() - Date.now()) / 3600000
  if (diffH < 24) return `due in ${Math.round(diffH)}h`
  return `due in ${Math.round(diffH / 24)}d`
}
</script>
