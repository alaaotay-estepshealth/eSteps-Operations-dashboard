import axios from 'axios'

const BASE = import.meta.env.VITE_API_URL || '/api'

const api = axios.create({ baseURL: BASE })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export const authAPI = {
  login: (username, password) => {
    const form = new FormData()
    form.append('username', username)
    form.append('password', password)
    return api.post('/auth/token', form)
  },
}

export const adminAPI = {
  getMetrics: () => api.get('/admin/dashboard/metrics'),
  getActivityFeed: () => api.get('/admin/dashboard/activity-feed'),
  getSystemHealth: () => api.get('/admin/dashboard/system-health'),
  getWorkflowStatus: () => api.get('/admin/workflows/status'),
  getDailyExecutions: (days = 14) => api.get(`/admin/workflows/executions/daily?days=${days}`),
  getAIDecisions: (params = {}) => api.get('/admin/ai/decisions', { params }),
  getLogs: (params = {}) => api.get('/admin/logs/operations', { params }),
  getPipelineLeads: (params = {}) => api.get('/admin/pipeline/leads', { params }),
  getResearchStats: () => api.get('/admin/pipeline/research-stats'),
  getAlerts: () => api.get('/admin/dashboard/alerts'),
  getInsights: () => api.get('/admin/insights'),
  getBriefing: () => api.get('/admin/briefing'),
  getHeatmap: () => api.get('/admin/insights/heatmap'),
  generateMemo: () => api.post('/admin/insights/memo'),
  askAssistant: (question) => api.post('/admin/insights/assistant', { question }),
  getFollowups: () => api.get('/admin/followups'),
  getContacts: (params = {}) => api.get('/admin/contacts', { params }),
  getContact: (leadId) => api.get(`/admin/contacts/${encodeURIComponent(leadId)}`),
  getPriorityQueue: (limit = 12) => api.get('/admin/contacts/priority', { params: { limit } }),
  leadAction: (leadId, body) => api.post(`/admin/leads/${encodeURIComponent(leadId)}/action`, body),
  getReviewQueue: () => api.get('/admin/human-review/queue'),
  resolveReview: (id, resolution) => api.post(`/admin/human-review/queue/${id}/resolve`, resolution),
  syncN8n: (limit = 100) => api.post(`/admin/sync-n8n?limit=${limit}`),
}

export const systemsAPI = {
  listSystems: () => api.get('/admin/systems'),
  getOverview: () => api.get('/admin/systems/overview'),
  getSystemStats: (slug, days = 7) => api.get(`/admin/systems/${slug}`, { params: { days } }),
  getSystemExecutions: (slug, params = {}) => api.get(`/admin/systems/${slug}/executions`, { params }),
  getSystemActivity: (slug) => api.get(`/admin/systems/${slug}/activity`),
}

export const n8nAPI = {
  listWorkflows: () => api.get('/proxy/n8n/workflows'),
  executeWorkflow: (id) => api.post(`/proxy/n8n/workflows/${id}/execute`),
  activateWorkflow: (id) => api.post(`/proxy/n8n/workflows/${id}/activate`),
  deactivateWorkflow: (id) => api.post(`/proxy/n8n/workflows/${id}/deactivate`),
}

export const openclawAPI = {
  status: () => api.get('/admin/openclaw/status'),
  runAgent: (body) => api.post('/admin/openclaw/agent', body),
  wake: (text) => api.post('/admin/openclaw/wake', { text }),
}

export const emailsAPI = {
  getStats: () => api.get('/admin/emails/stats'),
  getLogs: (params = {}) => api.get('/admin/emails/logs', { params }),
}

export const bookingsAPI = {
  getStats: () => api.get('/admin/bookings/stats'),
  list: (params = {}) => api.get('/admin/bookings', { params }),
}

export const opportunitiesAPI = {
  getStats: () => api.get('/admin/opportunities/stats'),
  list: (params = {}) => api.get('/admin/opportunities', { params }),
}

export const ticketsAPI = {
  getStats: () => api.get('/admin/tickets/stats'),
  list: (params = {}) => api.get('/admin/tickets', { params }),
  updateStatus: (id, data) => api.patch(`/admin/tickets/${id}/status`, data),
}

export const gtmAPI = {
  listStrategies: () => api.get('/admin/gtm/strategies'),
  getStrategy: (path) => api.get(`/admin/gtm/strategy/${encodeURIComponent(path)}`),
}

export default api
