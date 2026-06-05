<template>
  <header class="h-12 border-b border-ctrl-border bg-ctrl-surface flex items-center px-4 gap-3 sticky top-0 z-10 flex-shrink-0">
    <button
      @click="toggle"
      :title="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
      class="w-8 h-8 flex items-center justify-center rounded text-ctrl-muted hover:text-ctrl-text hover:bg-ctrl-panel active:scale-[0.95] transition-all"
    >
      <component :is="collapsed ? PanelLeftOpen : PanelLeftClose" class="w-4 h-4" />
    </button>
    <div class="flex-1 min-w-0">
      <span class="font-display font-semibold text-xs uppercase tracking-label text-ctrl-text">{{ title }}</span>
    </div>
    <div class="flex items-center gap-4 flex-shrink-0">
      <span class="tabnum text-2xs text-ctrl-muted hidden sm:block">{{ lastSync }}</span>
      <button
        class="flex items-center gap-2 text-xs text-ctrl-muted hover:text-ctrl-text border border-ctrl-border hover:border-ctrl-raised rounded px-3 py-1.5 transition-all duration-150 active:scale-[0.95]"
        @click="refresh"
      >
        <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': spinning }" />
        Refresh
      </button>
    </div>
  </header>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { PanelLeftClose, PanelLeftOpen, RefreshCw } from 'lucide-vue-next'
import { useSidebarState } from '../composables/useSidebarState.js'

const { collapsed, toggle } = useSidebarState()
const route      = useRoute()
const lastSyncAt = ref(new Date())
const spinning   = ref(false)
const now        = ref(Date.now())

let ticker
onMounted(() => { ticker = setInterval(() => { now.value = Date.now() }, 10_000) })
onBeforeUnmount(() => clearInterval(ticker))

const titles = {
  '/briefing':      'Morning Briefing',
  '/overview':      'Mission Control',
  '/insights':      'Strategy Insights',
  '/pipeline':      'Lead Pipeline',
  '/contacts':      'Contacts',
  '/followups':     'Follow-ups & Calendar',
  '/workflows':     'Workflow Executions',
  '/ai':            'AI Monitor',
  '/system':        'System Logs',
  '/systems':       'All Systems',
  '/review':        'Human Review Queue',
  '/n8n':           'n8n Workflows',
  '/agent':         'OpenClaw Agent',
  '/emails':        'Email Analytics',
  '/opportunities': 'Opportunities & Deals',
  '/bookings':      'Bookings',
  '/calendar':      'Meeting Calendar',
  '/meets':         'Meeting Prep',
  '/tickets':       'Tickets',
  '/gtm':           'GTM Strategy',
  '/report':        'Operations Report',
  '/users':         'User Management',
}

const title = computed(() => {
  if (route.path.startsWith('/systems/')) return 'System Detail'
  return titles[route.path] ?? 'Dashboard'
})

const lastSync = computed(() => {
  const diff = Math.floor((now.value - lastSyncAt.value.getTime()) / 1000)
  if (diff < 10) return 'just now'
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return lastSyncAt.value.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
})

function refresh() {
  lastSyncAt.value = new Date()
  spinning.value   = true
  setTimeout(() => (spinning.value = false), 800)
  window.dispatchEvent(new CustomEvent('app:refresh'))
}
</script>
