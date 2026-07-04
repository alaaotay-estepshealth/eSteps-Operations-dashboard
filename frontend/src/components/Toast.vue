<template>
  <Transition
    enter-active-class="transition-opacity duration-200"
    leave-active-class="transition-opacity duration-200"
    enter-from-class="opacity-0"
    leave-to-class="opacity-0"
  >
    <div
      v-if="state.visible"
      role="status"
      aria-live="polite"
      class="fixed bottom-6 right-6 z-50 px-4 py-3 rounded border bg-ctrl-panel border-ctrl-border shadow-lg flex items-center gap-2 text-sm"
      :class="typeClass"
    >
      <component :is="icon" class="w-4 h-4 flex-shrink-0" />
      <span class="text-ctrl-text">{{ state.message }}</span>
    </div>
  </Transition>
</template>

<script setup>
import { computed } from 'vue'
import { CheckCircle2, AlertCircle, Info } from 'lucide-vue-next'
import { useToast } from '../composables/useToast.js'

const { state } = useToast()

const icon = computed(() => {
  switch (state.type) {
    case 'err':  return AlertCircle
    case 'info': return Info
    default:     return CheckCircle2
  }
})

const typeClass = computed(() => {
  switch (state.type) {
    case 'err':  return 'text-status-err'
    case 'info': return 'text-status-info'
    default:     return 'text-status-ok'
  }
})
</script>
