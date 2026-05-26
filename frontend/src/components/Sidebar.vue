<template>
  <aside class="w-56 flex-shrink-0 flex flex-col border-r border-ctrl-border bg-ctrl-surface">
    <!-- Wordmark -->
    <div class="px-5 pt-6 pb-5 border-b border-ctrl-border">
      <div class="font-display font-bold text-base tracking-wide text-ctrl-text">eSteps</div>
      <div class="text-2xs text-ctrl-muted uppercase tracking-label mt-0.5">Operations</div>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 px-3 py-5 space-y-0.5 overflow-y-auto">
      <template v-for="(item, idx) in nav" :key="item.to">
        <div v-if="idx === 0 || item.section !== nav[idx - 1].section" class="text-2xs font-display font-medium uppercase tracking-label text-ctrl-dim px-3 pt-4 pb-1 first:pt-0">
          {{ item.section }}
        </div>
        <RouterLink
          :to="item.to"
          custom
          v-slot="{ isActive, navigate }"
        >
          <button
            @click="navigate"
            class="w-full flex items-center gap-3 px-3 py-2 rounded text-left transition-all duration-150 relative"
            :class="isActive
              ? 'bg-ctrl-panel text-ctrl-text'
              : 'text-ctrl-muted hover:text-ctrl-text hover:bg-ctrl-panel'"
          >
            <span
              class="absolute left-0 top-1 bottom-1 w-0.5 rounded-full transition-all duration-150"
              :class="isActive ? 'bg-status-info' : 'bg-transparent'"
            />
            <component :is="item.icon" class="w-4 h-4 flex-shrink-0" />
            <span class="text-sm">{{ item.label }}</span>
            <span v-if="isActive" class="ml-auto w-1.5 h-1.5 rounded-full bg-status-info opacity-60" />
          </button>
        </RouterLink>
      </template>
    </nav>

    <!-- Footer -->
    <div class="px-3 py-4 border-t border-ctrl-border">
      <div class="px-3 py-2 mb-1">
        <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted">{{ role }}</div>
        <div class="text-2xs text-ctrl-dim">{{ role === 'admin' ? 'Full access' : 'Read only' }}</div>
      </div>
      <button
        @click="logout"
        class="w-full flex items-center gap-3 px-3 py-2 rounded text-ctrl-dim hover:text-ctrl-muted hover:bg-ctrl-panel active:scale-[0.97] transition-all duration-150 text-sm"
      >
        <LogOut class="w-4 h-4" />
        Logout
      </button>
    </div>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { LayoutDashboard, TrendingUp, Workflow, Brain, FileText, LogOut, Layers, ShieldCheck, Zap, Mail, HeartHandshake, CalendarCheck, Ticket, Map, Printer } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth.js'

const auth   = useAuthStore()
const router = useRouter()
const role   = computed(() => auth.role ?? 'viewer')

const nav = [
  { to: '/systems',       label: 'All Systems',   icon: Layers,        section: 'Operations' },
  { to: '/overview',      label: 'Overview',      icon: LayoutDashboard, section: 'Operations' },
  { to: '/pipeline',      label: 'Pipeline',      icon: TrendingUp,    section: 'Pipeline' },
  { to: '/emails',        label: 'Email Analytics', icon: Mail,        section: 'Pipeline' },
  { to: '/bookings',      label: 'Bookings',      icon: CalendarCheck, section: 'Pipeline' },
  { to: '/opportunities', label: 'Deals',         icon: HeartHandshake, section: 'Pipeline' },
  { to: '/workflows',     label: 'Workflows',     icon: Workflow,      section: 'Automation' },
  { to: '/n8n',           label: 'n8n Workflows', icon: Zap,           section: 'Automation' },
  { to: '/ai',            label: 'AI Monitor',    icon: Brain,         section: 'Automation' },
  { to: '/review',        label: 'Review Queue',  icon: ShieldCheck,   section: 'Automation' },
  { to: '/tickets',       label: 'Tickets',       icon: Ticket,        section: 'Strategy' },
  { to: '/gtm',           label: 'GTM Strategy',  icon: Map,           section: 'Strategy' },
  { to: '/system',        label: 'System Logs',   icon: FileText,      section: 'Strategy' },
  { to: '/report',        label: 'Report',        icon: Printer,       section: 'Strategy' },
]

function logout() {
  auth.logout()
  router.push('/login')
}
</script>
