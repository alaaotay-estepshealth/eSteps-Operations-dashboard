<template>
  <aside
    class="flex-shrink-0 flex flex-col border-r border-ctrl-border bg-ctrl-surface transition-[width] duration-200 ease-out"
    :class="collapsed ? 'w-16' : 'w-56'"
  >
    <!-- Wordmark -->
    <div
      class="px-4 pt-6 pb-5 border-b border-ctrl-border flex items-center gap-3"
      :class="collapsed ? 'justify-center' : ''"
    >
      <img
        src="/logo_inversed.png"
        alt="eSteps"
        class="h-10 w-auto flex-shrink-0 object-contain"
        draggable="false"
      />
      <div v-if="!collapsed" class="overflow-hidden">
        <div class="font-display font-bold text-base tracking-wide text-ctrl-text leading-tight truncate">eSteps</div>
        <div class="text-2xs text-ctrl-muted uppercase tracking-label mt-0.5">Operations</div>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 px-2 py-5 space-y-0.5 overflow-y-auto overflow-x-hidden">
      <template v-for="(item, idx) in visibleNav" :key="item.to">
        <div
          v-if="!collapsed && (idx === 0 || item.section !== visibleNav[idx - 1].section)"
          class="text-2xs font-display font-medium uppercase tracking-label text-ctrl-dim px-3 pt-4 pb-1 first:pt-0"
        >
          {{ item.section }}
        </div>
        <RouterLink :to="item.to" custom v-slot="{ isActive, navigate }">
          <button
            @click="navigate"
            :title="collapsed ? item.label : ''"
            class="w-full flex items-center gap-3 px-3 py-2 rounded text-left transition-all duration-150 relative"
            :class="[
              isActive ? 'bg-ctrl-panel text-ctrl-text' : 'text-ctrl-muted hover:text-ctrl-text hover:bg-ctrl-panel',
              collapsed ? 'justify-center' : '',
            ]"
          >
            <span
              class="absolute left-0 top-1 bottom-1 w-0.5 rounded-full transition-all duration-150"
              :class="isActive ? 'bg-status-info' : 'bg-transparent'"
            />
            <component :is="item.icon" class="w-4 h-4 flex-shrink-0" />
            <span v-if="!collapsed" class="text-sm truncate">{{ item.label }}</span>
            <span v-if="isActive && !collapsed" class="ml-auto w-1.5 h-1.5 rounded-full bg-status-info opacity-60" />
          </button>
        </RouterLink>
      </template>
    </nav>

    <!-- Footer -->
    <div class="px-2 py-4 border-t border-ctrl-border">
      <div v-if="!collapsed" class="px-3 py-2 mb-1">
        <div class="font-display text-2xs uppercase tracking-label text-ctrl-muted">{{ role || '—' }}</div>
        <div class="text-2xs text-ctrl-dim">{{ accessLabel }}</div>
      </div>
      <button
        @click="logout"
        :title="collapsed ? 'Logout' : ''"
        class="w-full flex items-center gap-3 px-3 py-2 rounded text-ctrl-dim hover:text-ctrl-muted hover:bg-ctrl-panel active:scale-[0.97] transition-all duration-150 text-sm"
        :class="collapsed ? 'justify-center' : ''"
      >
        <LogOut class="w-4 h-4 flex-shrink-0" />
        <span v-if="!collapsed">Logout</span>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { LayoutDashboard, TrendingUp, Workflow, Brain, FileText, LogOut, Layers, ShieldCheck, Zap, Mail, HeartHandshake, CalendarCheck, CalendarDays, Ticket, Map, Printer, Lightbulb, Users, BellRing, Sunrise, Bot, UserCog, FolderKanban, ClipboardCheck, ClipboardList } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth.js'
import { useSidebarState } from '../composables/useSidebarState.js'

const auth   = useAuthStore()
const router = useRouter()
const { collapsed } = useSidebarState()
const role   = computed(() => auth.role)
const accessLabel = computed(() => {
  switch (auth.role) {
    case 'admin':    return 'Full access'
    case 'operator': return 'Operator actions'
    case 'readonly': return 'Read only'
    default:         return 'Not signed in'
  }
})

const ALL = ['admin', 'operator', 'readonly']
const OPS = ['admin', 'operator']
const ADM = ['admin']

const nav = [
  { to: '/briefing',      label: 'Briefing',      icon: Sunrise,         section: 'Operations',  roles: ALL },
  { to: '/systems',       label: 'All Systems',   icon: Layers,          section: 'Operations',  roles: ADM },
  { to: '/overview',      label: 'Overview',      icon: LayoutDashboard, section: 'Operations',  roles: ALL },
  { to: '/insights',      label: 'Insights',      icon: Lightbulb,       section: 'Operations',  roles: ALL },
  { to: '/pipeline',      label: 'Pipeline',      icon: TrendingUp,      section: 'Pipeline',    roles: ALL },
  { to: '/contacts',      label: 'Contacts',      icon: Users,           section: 'Pipeline',    roles: ALL },
  { to: '/emails',        label: 'Email Analytics', icon: Mail,          section: 'Pipeline',    roles: ALL },
  { to: '/calendar',      label: 'Calendar',      icon: CalendarDays,    section: 'Pipeline',    roles: ALL },
  { to: '/prep',          label: 'Meeting Prep',  icon: ClipboardCheck,  section: 'Pipeline',    roles: ALL },
  { to: '/meets',         label: 'Materials',     icon: FolderKanban,    section: 'Pipeline',    roles: ALL },
  { to: '/opportunities', label: 'Deals',         icon: HeartHandshake,  section: 'Pipeline',    roles: OPS },
  { to: '/followups',     label: 'Follow-ups',    icon: BellRing,        section: 'Pipeline',    roles: OPS },
  { to: '/workflows',     label: 'Workflows',     icon: Workflow,        section: 'Automation',  roles: OPS },
  { to: '/n8n',           label: 'n8n Workflows', icon: Zap,             section: 'Automation',  roles: OPS },
  { to: '/ai',            label: 'AI Monitor',    icon: Brain,           section: 'Automation',  roles: ALL },
  { to: '/agent',         label: 'OpenClaw Agent', icon: Bot,            section: 'Automation',  roles: OPS },
  { to: '/review',        label: 'Review Queue',  icon: ShieldCheck,     section: 'Automation',  roles: OPS },
  { to: '/tickets',       label: 'Tickets',       icon: Ticket,          section: 'Strategy',    roles: OPS },
  { to: '/tasks',         label: 'Tasks',         icon: ClipboardList,   section: 'Strategy',    roles: ALL },
  { to: '/gtm',           label: 'GTM Strategy',  icon: Map,             section: 'Strategy',    roles: ADM },
  { to: '/system',        label: 'System Logs',   icon: FileText,        section: 'Strategy',    roles: ALL },
  { to: '/report',        label: 'Report',        icon: Printer,         section: 'Strategy',    roles: ALL },
  { to: '/users',         label: 'Users',         icon: UserCog,         section: 'Admin',       roles: ADM },
]

const visibleNav = computed(() => {
  const r = auth.role === 'viewer' ? 'readonly' : auth.role
  if (!r) return []
  return nav.filter(item => item.roles.includes(r))
})

function logout() {
  auth.logout()
  router.push('/login')
}
</script>
