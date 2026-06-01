import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/login',         component: () => import('../views/Login.vue'),          meta: { public: true } },
  { path: '/',              redirect: '/briefing' },
  { path: '/briefing',      component: () => import('../views/BriefingView.vue') },
  { path: '/overview',      component: () => import('../views/Overview.vue') },
  { path: '/insights',      component: () => import('../views/Insights.vue') },
  { path: '/pipeline',      component: () => import('../views/Pipeline.vue') },
  { path: '/contacts',      component: () => import('../views/ContactsView.vue') },
  { path: '/followups',     component: () => import('../views/FollowupsView.vue') },
  { path: '/workflows',     component: () => import('../views/Workflows.vue') },
  { path: '/ai',            component: () => import('../views/AIMonitor.vue') },
  { path: '/review',        component: () => import('../views/HumanReview.vue') },
  { path: '/n8n',           component: () => import('../views/N8nWorkflows.vue') },
  { path: '/agent',         component: () => import('../views/OpenClawView.vue') },
  { path: '/system',        component: () => import('../views/SystemLogs.vue') },
  { path: '/systems',       component: () => import('../views/SystemsOverview.vue') },
  { path: '/systems/:slug', component: () => import('../views/SystemDetail.vue') },
  { path: '/emails',        component: () => import('../views/EmailAnalytics.vue') },
  { path: '/opportunities', component: () => import('../views/OpportunitiesDeals.vue') },
  { path: '/bookings',      component: () => import('../views/BookingsView.vue') },
  { path: '/tickets',       component: () => import('../views/TicketsView.vue') },
  { path: '/gtm',           component: () => import('../views/GTMStrategy.vue') },
  { path: '/report',        component: () => import('../views/ReportView.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (!to.meta.public && !token) return '/login'
})

export default router
