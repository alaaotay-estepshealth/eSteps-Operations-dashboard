<template>
  <div v-if="alerts.length" class="space-y-1.5 mb-5">
    <RouterLink
      v-for="a in alerts"
      :key="a.type"
      :to="a.link || '/overview'"
      class="flex items-center gap-2.5 rounded px-3 py-2 text-xs border transition-all hover:brightness-125"
      :class="a.severity === 'error'
        ? 'bg-status-err-bg border-status-err text-status-err'
        : 'bg-status-warn-bg border-status-warn text-status-warn'"
    >
      <component :is="a.severity === 'error' ? AlertCircle : AlertTriangle" class="w-3.5 h-3.5 flex-shrink-0" />
      <span class="flex-1 font-medium">{{ a.message }}</span>
      <span class="text-2xs opacity-70 whitespace-nowrap">Resolve →</span>
    </RouterLink>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { RouterLink } from 'vue-router'
import { AlertCircle, AlertTriangle } from 'lucide-vue-next'
import { adminAPI } from '../api/index.js'

const alerts = ref([])
let timer

async function loadAlerts() {
  try {
    const { data } = await adminAPI.getAlerts()
    alerts.value = Array.isArray(data) ? data : []
  } catch {
    /* alerts are non-critical — fail silent */
  }
}

onMounted(() => {
  loadAlerts()
  timer = setInterval(loadAlerts, 60000)
})
onBeforeUnmount(() => clearInterval(timer))
</script>
