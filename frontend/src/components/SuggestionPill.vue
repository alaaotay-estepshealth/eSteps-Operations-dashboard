<template>
  <div class="border border-status-info/40 bg-status-info-bg/40 rounded p-2 my-1">
    <div class="flex items-center gap-2">
      <Bot :size="14" class="text-status-info shrink-0" />
      <span class="text-2xs uppercase tracking-label text-status-info">AI suggests</span>
      <span class="text-xs text-ctrl-text truncate">
        {{ payload.category }} · priority {{ payload.priority_score }}
        <template v-if="payload.assigned_to"> · assign {{ payload.assigned_to }}</template>
      </span>
      <span v-if="confidence != null" class="ml-auto text-2xs text-ctrl-muted tabnum">
        conf {{ confidence.toFixed(2) }}
      </span>
    </div>
    <div v-if="payload.rationale" class="text-2xs text-ctrl-muted italic mt-1">
      "{{ payload.rationale }}"
    </div>

    <div v-if="!editing" class="flex items-center gap-2 mt-2">
      <button
        class="px-2 py-1 text-2xs bg-status-ok-bg border border-status-ok/40 text-status-ok rounded hover:bg-status-ok/20 disabled:opacity-50"
        @click="$emit('apply')"
        :disabled="busy"
      >Apply</button>
      <button
        class="px-2 py-1 text-2xs border border-ctrl-border text-ctrl-muted rounded hover:text-ctrl-text disabled:opacity-50"
        @click="startEdit"
        :disabled="busy"
      >Edit &amp; Apply</button>
      <button
        class="px-2 py-1 text-2xs border border-status-err/40 text-status-err rounded hover:bg-status-err-bg/40 disabled:opacity-50"
        @click="$emit('reject')"
        :disabled="busy"
      >Reject</button>
    </div>

    <div v-else class="mt-2 space-y-1.5">
      <div class="grid grid-cols-3 gap-2">
        <select v-model="draft.category"
                aria-label="Category"
                class="bg-ctrl-panel border border-ctrl-border rounded px-2 py-1 text-2xs text-ctrl-text focus:outline-none">
          <option value="billing">billing</option>
          <option value="technical">technical</option>
          <option value="partnership">partnership</option>
          <option value="support">support</option>
        </select>
        <input v-model.number="draft.priority_score" type="number" min="1" max="5"
               aria-label="Priority score (1-5)"
               class="bg-ctrl-panel border border-ctrl-border rounded px-2 py-1 text-2xs text-ctrl-text focus:outline-none tabnum" />
        <select v-model="draft.assigned_to"
                aria-label="Assignee"
                class="bg-ctrl-panel border border-ctrl-border rounded px-2 py-1 text-2xs text-ctrl-text focus:outline-none">
          <option :value="null">(unassigned)</option>
          <option v-for="op in operators" :key="op" :value="op">{{ op }}</option>
        </select>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="px-2 py-1 text-2xs bg-status-ok-bg border border-status-ok/40 text-status-ok rounded hover:bg-status-ok/20 disabled:opacity-50"
          @click="commitEdit"
          :disabled="busy"
        >Apply override</button>
        <button
          class="px-2 py-1 text-2xs border border-ctrl-border text-ctrl-muted rounded hover:text-ctrl-text"
          @click="editing = false"
        >Cancel</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Bot } from 'lucide-vue-next'

const props = defineProps({
  payload:    { type: Object, required: true },
  confidence: { type: Number, default: null },
  operators:  { type: Array, default: () => [] },
  busy:       { type: Boolean, default: false },
})
const emit = defineEmits(['apply', 'reject'])

const editing = ref(false)
const draft = ref({
  category: props.payload.category,
  priority_score: props.payload.priority_score,
  assigned_to: props.payload.assigned_to ?? null,
})

function startEdit() {
  draft.value = {
    category: props.payload.category,
    priority_score: props.payload.priority_score,
    assigned_to: props.payload.assigned_to ?? null,
  }
  editing.value = true
}

function commitEdit() {
  const override = {
    ...props.payload,
    ...draft.value,
  }
  editing.value = false
  emit('apply', override)
}
</script>
