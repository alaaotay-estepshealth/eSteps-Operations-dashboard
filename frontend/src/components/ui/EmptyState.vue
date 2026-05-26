<template>
  <div class="flex flex-col items-center justify-center py-14 gap-3">
    <component :is="icon" class="w-10 h-10 text-ctrl-dim opacity-40" />
    <p class="text-sm font-medium text-ctrl-muted">{{ message }}</p>
    <p v-if="subtext" class="text-xs text-ctrl-dim">{{ subtext }}</p>
    <slot />
  </div>
</template>

<script setup>
import { Inbox } from 'lucide-vue-next'

defineProps({
  icon: { type: [Object, Function], default: () => Inbox },
  message: { type: String, default: 'No data available' },
  subtext: { type: String, default: '' },
})
</script>
