import { createRouter, createWebHistory } from 'vue-router'

const ALL = ['admin', 'operator', 'readonly']
const OPS = ['admin', 'operator']
const ADM = ['admin']

const routes = [
  { path: '/login',         component: () => import('../views/Login.vue'),               meta: { public: true } },
  { path: '/',              redirect: '/briefing' },
  { path: '/briefing',      component: () => import('../views/BriefingView.vue'),        meta: { roles: ALL } },
  { path: '/overview',      component: () => import('../views/Overview.vue'),            meta: { roles: ALL } },
  { path: '/insights',      component: () => import('../views/Insights.vue'),            meta: { roles: ALL } },
  { path: '/pipeline',      component: () => import('../views/Pipeline.vue'),            meta: { roles: ALL } },
  { path: '/contacts',      component: () => import('../views/ContactsView.vue'),        meta: { roles: ALL } },
  { path: '/followups',     component: () => import('../views/FollowupsView.vue'),       meta: { roles: OPS } },
  { path: '/workflows',     component: () => import('../views/Workflows.vue'),           meta: { roles: OPS } },
  { path: '/ai',            component: () => import('../views/AIMonitor.vue'),           meta: { roles: ALL } },
  { path: '/review',        component: () => import('../views/HumanReview.vue'),         meta: { roles: OPS } },
  { path: '/n8n',           component: () => import('../views/N8nWorkflows.vue'),        meta: { roles: OPS } },
  { path: '/agent',         component: () => import('../views/OpenClawView.vue'),        meta: { roles: OPS } },
  { path: '/system',        component: () => import('../views/SystemLogs.vue'),          meta: { roles: ALL } },
  { path: '/systems',       component: () => import('../views/SystemsOverview.vue'),     meta: { roles: ADM } },
  { path: '/systems/:slug', component: () => import('../views/SystemDetail.vue'),        meta: { roles: ADM } },
  { path: '/emails',        component: () => import('../views/EmailAnalytics.vue'),      meta: { roles: ALL } },
  { path: '/opportunities', component: () => import('../views/OpportunitiesDeals.vue'),  meta: { roles: OPS } },
  { path: '/bookings',      component: () => import('../views/BookingsView.vue'),        meta: { roles: ALL } },
  { path: '/calendar',      component: () => import('../views/CalendarView.vue'),        meta: { roles: ALL } },
  { path: '/meeting/:bookingId', component: () => import('../views/MeetingView.vue'),    meta: { roles: ALL } },
  { path: '/tickets',       component: () => import('../views/TicketsView.vue'),         meta: { roles: OPS } },
  { path: '/gtm',           component: () => import('../views/GTMStrategy.vue'),         meta: { roles: ADM } },
  { path: '/meets',         component: () => import('../views/MeetsView.vue'),           meta: { roles: ALL } },
  { path: '/report',        component: () => import('../views/ReportView.vue'),          meta: { roles: ALL } },
  { path: '/users',         component: () => import('../views/UsersView.vue'),           meta: { roles: ADM } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  if (to.meta.public) return true
  const token = localStorage.getItem('token')
  if (!token) return '/login'
  const raw = localStorage.getItem('role')
  const role = raw === 'viewer' ? 'readonly' : raw
  const allowed = to.meta.roles
  if (allowed && !allowed.includes(role)) return '/briefing'
  return true
})

export default router
