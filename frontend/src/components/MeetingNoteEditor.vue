<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between text-2xs text-ctrl-muted">
      <span v-if="aiDraftedAt">AI-drafted · {{ aiModel }} · {{ relTime(aiDraftedAt) }}</span>
      <span v-else>{{ updatedBy ? `Edited by ${updatedBy}` : 'No content yet' }}</span>
      <span :class="dirty ? 'text-status-warn' : 'text-ctrl-dim'">
        {{ dirty ? 'Saving…' : 'Saved' }}
      </span>
    </div>
    <textarea
      v-model="local"
      :placeholder="placeholder"
      class="w-full min-h-[300px] bg-ctrl-panel border border-ctrl-border rounded p-3 text-sm font-mono text-ctrl-text focus:outline-none focus:border-status-info"
      @input="onInput"
    />
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: 'Write notes in markdown…' },
  aiDraftedAt: { type: String, default: null },
  aiModel: { type: String, default: null },
  updatedBy: { type: String, default: null },
})
const emit = defineEmits(['update:modelValue', 'save'])

const local = ref(props.modelValue || '')
const dirty = ref(false)
let timer = null

watch(() => props.modelValue, (v) => {
  if (!dirty.value) local.value = v || ''
})

function onInput() {
  dirty.value = true
  emit('update:modelValue', local.value)
  if (timer) clearTimeout(timer)
  timer = setTimeout(async () => {
    try {
      await emit('save', local.value)
      dirty.value = false
    } catch {
      // Toast handled by parent
    }
  }, 4000)
}

function relTime(iso) {
  if (!iso) return ''
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}
</script>
